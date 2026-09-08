# language: python
# file: ig_comment_harvester.py
# runtime: Python 3.9+, Streamlit 1.28+
# deps: streamlit, requests, beautifulsoup4, lxml

import streamlit as st
import requests
import re
import time
import json
import hashlib
import csv
import io
from urllib.parse import quote, urlparse
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup

# ---------- Data Models ----------

@dataclass
class CommentRecord:
    username: str
    comment_text: str
    media_type: str          # "post" or "reel"
    media_shortcode: str
    media_owner: str
    timestamp: str
    source: str              # "instagram", "google", "bing", "wayback"
    url: str
    raw_data: dict = field(default_factory=dict)

# ---------- Session Manager ----------

class SessionManager:
    def __init__(self):
        self.session = requests.Session()
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        ]
        self._rotate_headers()

    def _rotate_headers(self):
        self.headers = {
            "User-Agent": self.user_agents[hash(time.time()) % len(self.user_agents)],
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "198387",
            "X-IG-WWW-Claim": "0",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.instagram.com",
            "Referer": "https://www.instagram.com/",
        }

# ---------- Instagram Public Graph API ----------

class InstagramPublicScraper:
    """Scrapes Instagram's public web API without authentication."""
    
    BASE_URL = "https://www.instagram.com"
    GRAPH_URL = "https://www.instagram.com/graphql/query/"
    
    QUERY_HASHES = {
        "user_comments": "bc3296d1ce80a24b1b6e40b1e72903f5",  # user comments query
        "media_comments": "97b41c52301f77ce508f55e66d17620e",  # media comments
        "user_search": "9b498c08113f1e09617a1703c22cab32",
    }

    def __init__(self, session: SessionManager):
        self.sm = session
        self.session = session.session

    def search_user(self, username: str) -> Optional[Dict]:
        """Search for user by username."""
        url = f"{self.BASE_URL}/web/search/topsearch/"
        params = {
            "query": username,
            "context": "blended"
        }
        try:
            resp = self.session.get(url, params=params, headers=self.sm.headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for user in data.get("users", []):
                    if user["user"]["username"].lower() == username.lower():
                        return user["user"]
            return None
        except Exception:
            return None

    def get_user_id_from_web(self, username: str) -> Optional[str]:
        """Get user ID from public web profile page."""
        try:
            # Try the __a=1 trick on profile page
            url = f"{self.BASE_URL}/{username}/?__a=1&__d=dis"
            resp = self.session.get(url, headers=self.sm.headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("graphql", {}).get("user", {}).get("id")
            
            # Fallback: parse from HTML meta tags
            url = f"{self.BASE_URL}/{username}/"
            resp = self.session.get(url, headers=self.sm.headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')
                # Look for user ID in script tags
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and 'profilePage_' in script.string:
                        match = re.search(r'"id":"(\d+)"', script.string)
                        if match:
                            return match.group(1)
                # Look in meta tags
                meta = soup.find('meta', property='al:ios:url')
                if meta and meta.get('content'):
                    match = re.search(r'user_id=(\d+)', meta['content'])
                    if match:
                        return match.group(1)
            return None
        except Exception:
            return None

    def get_user_media(self, user_id: str, max_posts: int = 50) -> List[Dict]:
        """Get user's recent media posts."""
        media_list = []
        cursor = None
        has_next = True
        
        while has_next and len(media_list) < max_posts:
            try:
                variables = {
                    "id": user_id,
                    "first": 12,
                    "after": cursor
                }
                url = f"{self.GRAPH_URL}?query_hash=69cba40317214236af40e7efa697781d&variables={quote(json.dumps(variables))}"
                resp = self.session.get(url, headers=self.sm.headers, timeout=15)
                
                if resp.status_code != 200:
                    break
                    
                data = resp.json()
                edges = data.get("data", {}).get("user", {}).get("edge_owner_to_timeline_media", {}).get("edges", [])
                
                for edge in edges:
                    node = edge["node"]
                    media_list.append({
                        "shortcode": node.get("shortcode"),
                        "id": node.get("id"),
                        "is_video": node.get("is_video", False),
                        "owner_username": node.get("owner", {}).get("username"),
                        "taken_at": node.get("taken_at_timestamp"),
                        "comment_count": node.get("edge_media_to_comment", {}).get("count", 0),
                    })
                
                page_info = data.get("data", {}).get("user", {}).get("edge_owner_to_timeline_media", {}).get("page_info", {})
                has_next = page_info.get("has_next_page", False)
                cursor = page_info.get("end_cursor")
                
                if not has_next:
                    break
                    
                time.sleep(0.5)  # Rate limit protection
                
            except Exception:
                break
                
        return media_list

    def get_media_comments(self, shortcode: str, max_comments: int = 100) -> List[Dict]:
        """Get comments on a specific media post."""
        comments = []
        cursor = None
        has_next = True
        
        while has_next and len(comments) < max_comments:
            try:
                variables = {
                    "shortcode": shortcode,
                    "first": 20,
                    "after": cursor
                }
                url = f"{self.GRAPH_URL}?query_hash=97b41c52301f77ce508f55e66d17620e&variables={quote(json.dumps(variables))}"
                resp = self.session.get(url, headers=self.sm.headers, timeout=15)
                
                if resp.status_code != 200:
                    break
                    
                data = resp.json()
                edges = data.get("data", {}).get("shortcode_media", {}).get("edge_media_to_comment", {}).get("edges", [])
                
                for edge in edges:
                    node = edge["node"]
                    comments.append({
                        "username": node.get("owner", {}).get("username"),
                        "text": node.get("text"),
                        "timestamp": node.get("created_at"),
                        "likes": node.get("edge_liked_by", {}).get("count", 0),
                    })
                
                page_info = data.get("data", {}).get("shortcode_media", {}).get("edge_media_to_comment", {}).get("page_info", {})
                has_next = page_info.get("has_next_page", False)
                cursor = page_info.get("end_cursor")
                
                if not has_next:
                    break
                    
                time.sleep(0.3)
                
            except Exception:
                break
                
        return comments

# ---------- Search Engine Scrapers ----------

class SearchEngineScraper:
    """Scrapes Google and Bing for Instagram comments by a user."""
    
    def __init__(self, session: SessionManager):
        self.sm = session
        self.session = session.session

    def google_search(self, query: str, num_results: int = 30) -> List[str]:
        """Scrape Google search results for a query."""
        results = []
        start = 0
        
        while len(results) < num_results and start < 100:
            url = f"https://www.google.com/search?q={quote(query)}&start={start}&num=20&hl=en"
            try:
                resp = self.session.get(url, headers={"User-Agent": self.sm.headers["User-Agent"]}, timeout=15)
                if resp.status_code != 200:
                    break
                    
                soup = BeautifulSoup(resp.text, 'lxml')
                
                # Extract search result URLs
                for a in soup.find_all('a'):
                    href = a.get('href', '')
                    if '/url?q=' in href:
                        clean_url = href.split('/url?q=')[1].split('&')[0]
                        if 'instagram.com' in clean_url and clean_url not in results:
                            results.append(clean_url)
                            
                # Extract cached text snippets
                for div in soup.find_all('div', class_='VwiC3b'):
                    text = div.get_text()
                    if 'instagram' in text.lower():
                        results.append(text[:200])
                        
                start += 20
                time.sleep(1)  # Respect rate limits
                
            except Exception:
                break
                
        return results[:num_results]

    def bing_search(self, query: str, num_results: int = 30) -> List[str]:
        """Scrape Bing search results for a query."""
        results = []
        start = 0
        
        while len(results) < num_results and start < 100:
            url = f"https://www.bing.com/search?q={quote(query)}&first={start}&count=20"
            try:
                resp = self.session.get(url, headers={"User-Agent": self.sm.headers["User-Agent"]}, timeout=15)
                if resp.status_code != 200:
                    break
                    
                soup = BeautifulSoup(resp.text, 'lxml')
                
                # Extract search result URLs
                for cite in soup.find_all('cite'):
                    text = cite.get_text()
                    if 'instagram.com' in text and text not in results:
                        results.append(text)
                        
                # Extract snippets
                for p in soup.find_all('p'):
                    text = p.get_text()
                    if 'instagram' in text.lower():
                        results.append(text[:200])
                        
                start += 20
                time.sleep(0.8)
                
            except Exception:
                break
                
        return results[:num_results]

    def construct_dorks(self, username: str) -> List[str]:
        """Construct search engine dorks for finding comments."""
        dorks = [
            f'"{username}" site:instagram.com comments',
            f'"{username}" site:instagram.com comment',
            f'"{username} commented" instagram',
            f'"{username}" instagram reel comment',
            f'"{username}" instagram post comment',
            f'site:instagram.com/p/ "{username}"',
            f'site:instagram.com/reel/ "{username}"',
            f'"{username}" "just commented" instagram',
            f'"{username}" "left a comment" instagram',
        ]
        return dorks

# ---------- Wayback Machine Archive ----------

class WaybackScraper:
    """Queries the Wayback Machine for archived Instagram pages."""
    
    CDX_URL = "https://web.archive.org/cdx/search/cdx"
    AVAILABILITY_URL = "https://archive.org/wayback/available"
    
    def __init__(self, session: SessionManager):
        self.sm = session
        self.session = session.session

    def get_archived_snapshots(self, username: str, limit: int = 50) -> List[Dict]:
        """Get archived snapshots of a user's Instagram profile."""
        snapshots = []
        profile_url = f"instagram.com/{username}/"
        
        params = {
            "url": profile_url,
            "output": "json",
            "limit": limit,
            "filter": "statuscode:200",
            "fl": "timestamp,original,statuscode",
            "collapse": "digest"
        }
        
        try:
            resp = self.session.get(self.CDX_URL, params=params, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                # First row is headers
                for row in data[1:]:
                    snapshots.append({
                        "timestamp": row[0],
                        "url": row[1],
                        "status_code": row[2],
                        "wayback_url": f"https://web.archive.org/web/{row[0]}/{row[1]}"
                    })
        except Exception:
            pass
            
        return snapshots

    def extract_comments_from_archive(self, wayback_url: str) -> List[Dict]:
        """Extract comments from an archived Instagram page."""
        comments = []
        try:
            resp = self.session.get(wayback_url, headers=self.sm.headers, timeout=20)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')
                
                # Look for comment JSON in script tags
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and 'edge_media_to_comment' in script.string:
                        # Try to parse JSON from script
                        try:
                            # Find JSON-like structures
                            json_matches = re.findall(r'edge_media_to_comment[^}]*}.*?"edges":\[(.*?)\]', script.string, re.DOTALL)
                            for match in json_matches:
                                # Extract comment text
                                text_matches = re.findall(r'"text":"([^"]+)"', match)
                                username_matches = re.findall(r'"username":"([^"]+)"', match)
                                for text, user in zip(text_matches, username_matches):
                                    comments.append({
                                        "username": user,
                                        "text": text,
                                        "timestamp": None,
                                    })
                        except Exception:
                            pass
                            
                # Also look for rendered comment elements
                for div in soup.find_all('div', class_=re.compile(r'comment', re.I)):
                    text = div.get_text(strip=True)
                    if text and len(text) > 2:
                        comments.append({
                            "username": "unknown",
                            "text": text[:500],
                            "timestamp": None,
                        })
                        
        except Exception:
            pass
            
        return comments

# ---------- Main Harvester ----------

class CommentHarvester:
    """Main orchestrator for harvesting all comments by a user."""
    
    def __init__(self, session: SessionManager):
        self.sm = session
        self.ig_scraper = InstagramPublicScraper(session)
        self.search_scraper = SearchEngineScraper(session)
        self.wayback_scraper = WaybackScraper(session)
        
    def harvest_user_comments(self, username: str, 
                             max_posts: int = 50,
                             max_comments_per_post: int = 100,
                             use_search_engines: bool = True,
                             use_wayback: bool = True,
                             progress_callback=None) -> List[CommentRecord]:
        """Harvest all comments by a specific user."""
        all_comments: List[CommentRecord] = []
        seen_comment_ids = set()
        
        username = username.lstrip('@').strip()
        
        # Step 1: Get user ID
        if progress_callback:
            progress_callback(0.05, "Getting user ID...")
        user_id = self.ig_scraper.get_user_id_from_web(username)
        
        if not user_id:
            # Try search
            user_data = self.ig_scraper.search_user(username)
            if user_data:
                user_id = user_data.get("id")
        
        if user_id:
            # Step 2: Get user's media
            if progress_callback:
                progress_callback(0.1, "Fetching user's media posts...")
            media_list = self.ig_scraper.get_user_media(user_id, max_posts)
            
            # Step 3: Get comments on each media post
            total_media = len(media_list)
            for idx, media in enumerate(media_list):
                if progress_callback:
                    progress = 0.1 + (0.4 * (idx / max(total_media, 1)))
                    progress_callback(progress, f"Scanning comments on post {idx+1}/{total_media}...")
                
                comments = self.ig_scraper.get_media_comments(media["shortcode"], max_comments_per_post)
                
                for comment in comments:
                    if comment["username"].lower() == username.lower():
                        comment_id = hashlib.md5(
                            f"{media['shortcode']}:{comment['text']}:{comment['timestamp']}".encode()
                        ).hexdigest()
                        
                        if comment_id not in seen_comment_ids:
                            seen_comment_ids.add(comment_id)
                            all_comments.append(CommentRecord(
                                username=username,
                                comment_text=comment["text"],
                                media_type="reel" if media["is_video"] else "post",
                                media_shortcode=media["shortcode"],
                                media_owner=media["owner_username"],
                                timestamp=str(comment.get("timestamp", "")),
                                source="instagram",
                                url=f"https://www.instagram.com/p/{media['shortcode']}/",
                                raw_data={"likes": comment.get("likes", 0)}
                            ))
        
        # Step 4: Search engine scraping
        if use_search_engines:
            if progress_callback:
                progress_callback(0.55, "Running search engine dorks...")
            
            dorks = self.search_scraper.construct_dorks(username)
            search_results = []
            
            for dork_idx, dork in enumerate(dorks):
                if progress_callback:
                    progress = 0.55 + (0.2 * (dork_idx / len(dorks)))
                    progress_callback(progress, f"Searching: {dork[:50]}...")
                
                google_results = self.search_scraper.google_search(dork, num_results=15)
                bing_results = self.search_scraper.bing_search(dork, num_results=15)
                search_results.extend(google_results)
                search_results.extend(bing_results)
                
                time.sleep(1)
            
            # Process search results
            for result in search_results:
                if 'instagram.com' in result and ('/p/' in result or '/reel/' in result):
                    shortcode_match = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', result)
                    if shortcode_match:
                        shortcode = shortcode_match.group(1)
                        comments = self.ig_scraper.get_media_comments(shortcode, max_comments_per_post)
                        
                        for comment in comments:
                            if comment["username"].lower() == username.lower():
                                comment_id = hashlib.md5(
                                    f"{shortcode}:{comment['text']}:{comment['timestamp']}".encode()
                                ).hexdigest()
                                
                                if comment_id not in seen_comment_ids:
                                    seen_comment_ids.add(comment_id)
                                    all_comments.append(CommentRecord(
                                        username=username,
                                        comment_text=comment["text"],
                                        media_type="reel" if "/reel/" in result else "post",
                                        media_shortcode=shortcode,
                                        media_owner="unknown",
                                        timestamp=str(comment.get("timestamp", "")),
                                        source="search_engine",
                                        url=result,
                                        raw_data={"search_dork": dork if 'dork' in locals() else ""}
                                    ))
        
        # Step 5: Wayback Machine
        if use_wayback:
            if progress_callback:
                progress_callback(0.8, "Querying Wayback Machine archives...")
            
            snapshots = self.wayback_scraper.get_archived_snapshots(username, limit=30)
            
            for snap_idx, snapshot in enumerate(snapshots):
                if progress_callback:
                    progress = 0.8 + (0.15 * (snap_idx / max(len(snapshots), 1)))
                    progress_callback(progress, f"Extracting from archive {snap_idx+1}/{len(snapshots)}...")
                
                archived_comments = self.wayback_scraper.extract_comments_from_archive(snapshot["wayback_url"])
                
                for comment in archived_comments:
                    if comment["username"].lower() == username.lower() or comment["username"] == "unknown":
                        comment_id = hashlib.md5(
                            f"{snapshot['timestamp']}:{comment['text']}".encode()
                        ).hexdigest()
                        
                        if comment_id not in seen_comment_ids:
                            seen_comment_ids.add(comment_id)
                            all_comments.append(CommentRecord(
                                username=username,
                                comment_text=comment["text"],
                                media_type="unknown",
                                media_shortcode="",
                                media_owner="unknown",
                                timestamp=snapshot["timestamp"],
                                source="wayback",
                                url=snapshot["wayback_url"],
                                raw_data={}
                            ))
                
                time.sleep(0.5)
        
        if progress_callback:
            progress_callback(1.0, "Harvest complete!")
            
        return all_comments

# ---------- Streamlit UI ----------

st.set_page_config(
    page_title="IG Comment Harvester",
    page_icon="🕵️",
    layout="wide"
)

st.title("🕵️ Instagram Comment Harvester")
st.markdown("Extract all comments made by a specific Instagram user across posts, reels, search engines, and web archives.")

st.markdown("---")

# Input section
col1, col2 = st.columns([3, 1])

with col1:
    target_username = st.text_input(
        "Target Instagram Username",
        placeholder="e.g. username (without @)",
        label_visibility="collapsed"
    )

with col2:
    harvest_btn = st.button("🔍 Harvest Comments", use_container_width=True, type="primary")

# Advanced settings
with st.expander("⚙️ Advanced Settings"):
    col1, col2, col3 = st.columns(3)
    with col1:
        max_posts = st.slider("Max posts to scan", 10, 200, 50)
    with col2:
        max_comments = st.slider("Max comments per post", 20, 500, 100)
    with col3:
        delay_between = st.slider("Delay between requests (seconds)", 0.1, 5.0, 0.5)
    
    col1, col2 = st.columns(2)
    with col1:
        use_search = st.checkbox("Use search engines (Google/Bing)", value=True)
    with col2:
        use_wayback = st.checkbox("Use Wayback Machine archives", value=True)

# Results container
results_container = st.container()

if harvest_btn and target_username:
    target_username = target_username.lstrip('@').strip()
    
    with results_container:
        st.markdown("---")
        st.subheader(f"📊 Harvesting comments for @{target_username}")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def update_progress(value, message):
            progress_bar.progress(value)
            status_text.text(message)
        
        sm = SessionManager()
        harvester = CommentHarvester(sm)
        
        with st.spinner("Harvesting comments..."):
            comments = harvester.harvest_user_comments(
                username=target_username,
                max_posts=max_posts,
                max_comments_per_post=max_comments,
                use_search_engines=use_search,
                use_wayback=use_wayback,
                progress_callback=update_progress
            )
        
        status_text.empty()
        
        # Display results
        if comments:
            st.success(f"✅ Found {len(comments)} comments by @{target_username}")
            
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Comments", len(comments))
            col2.metric("On Posts", sum(1 for c in comments if c.media_type == "post"))
            col3.metric("On Reels", sum(1 for c in comments if c.media_type == "reel"))
            col4.metric("From Archives", sum(1 for c in comments if c.source == "wayback"))
            
            # Dataframe
            df_data = []
            for c in comments:
                df_data.append({
                    "Comment": c.comment_text[:100] + ("..." if len(c.comment_text) > 100 else ""),
                    "Full Comment": c.comment_text,
                    "Media Type": c.media_type,
                    "Media Owner": c.media_owner,
                    "Source": c.source,
                    "URL": c.url,
                    "Timestamp": c.timestamp,
                })
            
            st.dataframe(df_data, use_container_width=True, height=400)
            
            # Download button
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=[
                "Username", "Comment", "Media Type", "Media Shortcode", 
                "Media Owner", "Source", "URL", "Timestamp"
            ])
            writer.writeheader()
            for c in comments:
                writer.writerow({
                    "Username": c.username,
                    "Comment": c.comment_text,
                    "Media Type": c.media_type,
                    "Media Shortcode": c.media_shortcode,
                    "Media Owner": c.media_owner,
                    "Source": c.source,
                    "URL": c.url,
                    "Timestamp": c.timestamp,
                })
            
            st.download_button(
                "📥 Download Comments (CSV)",
                csv_buffer.getvalue(),
                f"{target_username}_instagram_comments.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            st.warning(f"No comments found for @{target_username}. This could be because:\n"
                      "1. The account doesn't exist\n"
                      "2. The account is private\n"
                      "3. Instagram's public API is blocking requests\n"
                      "4. The user hasn't commented on accessible posts")