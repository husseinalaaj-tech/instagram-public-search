# file: insta_harvester_app.py
# runtime: Python 3.9+, install: pip install streamlit requests beautifulsoup4 lxml

import streamlit as st
import requests
import re
import time
import json
import hashlib
import csv
import io
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

# ---------------- Session with cookies ----------------
class IGSession:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-IG-App-ID": "936619743392459",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.instagram.com/",
        })
        self._warmup()

    def _warmup(self):
        try:
            r = self.s.get("https://www.instagram.com/", timeout=10)
            token = self.s.cookies.get("csrftoken")
            if not token:
                m = re.search(r'csrf_token":"([^"]+)"', r.text)
                if m:
                    token = m.group(1)
                    self.s.cookies.set("csrftoken", token)
            if token:
                self.s.headers["X-CSRFToken"] = token
        except:
            pass

    def get(self, url, **kwargs):
        kwargs.setdefault("timeout", 15)
        return self.s.get(url, **kwargs)

# ---------------- Profile fetch ----------------
def fetch_profile(username: str, session: IGSession) -> Optional[Dict]:
    api = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    try:
        r = session.get(api)
        if r.status_code == 200:
            data = r.json()
            u = data.get("data", {}).get("user", {})
            if u:
                return {
                    "id": u.get("id"),
                    "username": u.get("username"),
                    "full_name": u.get("full_name"),
                    "pic": u.get("profile_pic_url"),
                    "private": u.get("is_private"),
                    "followers": u.get("edge_followed_by", {}).get("count"),
                    "following": u.get("edge_follow", {}).get("count"),
                    "posts": u.get("edge_owner_to_timeline_media", {}).get("count"),
                    "bio": u.get("biography"),
                }
    except:
        pass
    return None

# ---------------- Media & comments ----------------
def fetch_media(session: IGSession, user_id: str, max_posts: int) -> List[Dict]:
    media = []
    cursor = None
    while len(media) < max_posts:
        variables = {"id": user_id, "first": 12, "after": cursor}
        url = f"https://www.instagram.com/graphql/query/?query_hash=69cba40317214236af40e7efa697781d&variables={json.dumps(variables)}"
        try:
            r = session.get(url)
            if r.status_code != 200:
                break
            data = r.json()
            edges = data["data"]["user"]["edge_owner_to_timeline_media"]["edges"]
            for e in edges:
                n = e["node"]
                media.append({
                    "shortcode": n["shortcode"],
                    "is_video": n["is_video"],
                    "owner": n["owner"]["username"],
                })
            page_info = data["data"]["user"]["edge_owner_to_timeline_media"]["page_info"]
            if not page_info["has_next_page"]:
                break
            cursor = page_info["end_cursor"]
            time.sleep(0.4)
        except:
            break
    return media

def fetch_comments(session: IGSession, shortcode: str, max_comments: int) -> List[Dict]:
    comments = []
    cursor = None
    while len(comments) < max_comments:
        variables = {"shortcode": shortcode, "first": 20, "after": cursor}
        url = f"https://www.instagram.com/graphql/query/?query_hash=97b41c52301f77ce508f55e66d17620e&variables={json.dumps(variables)}"
        try:
            r = session.get(url)
            if r.status_code != 200:
                break
            data = r.json()
            edges = data["data"]["shortcode_media"]["edge_media_to_comment"]["edges"]
            for e in edges:
                n = e["node"]
                comments.append({
                    "username": n["owner"]["username"],
                    "text": n["text"],
                    "timestamp": n["created_at"],
                })
            page_info = data["data"]["shortcode_media"]["edge_media_to_comment"]["page_info"]
            if not page_info["has_next_page"]:
                break
            cursor = page_info["end_cursor"]
            time.sleep(0.3)
        except:
            break
    return comments

# ---------------- Search engine dorks ----------------
def search_dorks(username: str) -> List[str]:
    return [
        f'"{username}" site:instagram.com comments',
        f'"{username} commented" instagram',
        f'"{username}" instagram reel comment',
        f'"{username}" instagram post comment',
        f'site:instagram.com/p/ "{username}"',
        f'site:instagram.com/reel/ "{username}"',
    ]

def google_search(session: IGSession, query: str, num=10) -> List[str]:
    results = []
    try:
        url = f"https://www.google.com/search?q={query}&num={num}"
        r = session.get(url)
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a'):
            href = a.get('href', '')
            if '/url?q=' in href and 'instagram.com' in href:
                clean = href.split('/url?q=')[1].split('&')[0]
                if clean not in results:
                    results.append(clean)
    except:
        pass
    return results

def bing_search(session: IGSession, query: str, num=10) -> List[str]:
    results = []
    try:
        url = f"https://www.bing.com/search?q={query}&count={num}"
        r = session.get(url)
        soup = BeautifulSoup(r.text, 'lxml')
        for cite in soup.find_all('cite'):
            text = cite.get_text()
            if 'instagram.com' in text and text not in results:
                results.append(text)
    except:
        pass
    return results

# ---------------- Wayback ----------------
def wayback_search(username: str) -> List[str]:
    snapshots = []
    try:
        cdx = f"https://web.archive.org/cdx/search/cdx?url=instagram.com/{username}/&output=json&limit=20&filter=statuscode:200&collapse=digest"
        r = requests.get(cdx, timeout=15)
        if r.status_code == 200:
            data = r.json()
            for row in data[1:]:
                snapshots.append(f"https://web.archive.org/web/{row[0]}/{row[1]}")
    except:
        pass
    return snapshots

def extract_archive_comments(url: str) -> List[Dict]:
    comments = []
    try:
        r = requests.get(url, timeout=20)
        soup = BeautifulSoup(r.text, 'lxml')
        # try script JSON
        scripts = soup.find_all('script')
        for s in scripts:
            if s.string and 'edge_media_to_comment' in s.string:
                texts = re.findall(r'"text":"([^"]+)"', s.string)
                users = re.findall(r'"username":"([^"]+)"', s.string)
                for t, u in zip(texts, users):
                    comments.append({"username": u, "text": t})
        # fallback to visible comment divs
        for div in soup.find_all('div', class_=re.compile('comment', re.I)):
            t = div.get_text(strip=True)
            if t and len(t) > 2:
                comments.append({"username": "unknown", "text": t[:500]})
    except:
        pass
    return comments

# ---------------- Main harvester ----------------
def harvest_all(username: str, max_posts=30, max_comments=50,
                use_search=True, use_wayback=True, progress=None) -> List[Dict]:
    session = IGSession()
    results = []
    seen = set()

    # profile
    if progress: progress(0.02, "Fetching profile...")
    profile = fetch_profile(username, session)
    if profile and progress:
        progress(0.05, f"Profile: @{profile['username']}")

    # if public, scan own media comments
    if profile and not profile["private"] and profile["id"]:
        if progress: progress(0.08, "Scanning user's own media...")
        media = fetch_media(session, profile["id"], max_posts)
        total = len(media)
        for i, m in enumerate(media):
            if progress:
                progress(0.08 + 0.4*(i/total if total else 1), f"Post {i+1}/{total}")
            comments = fetch_comments(session, m["shortcode"], max_comments)
            for c in comments:
                if c["username"].lower() == username.lower():
                    key = f"{m['shortcode']}:{c['text']}"
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "comment": c["text"],
                            "type": "reel" if m["is_video"] else "post",
                            "owner": m["owner"],
                            "shortcode": m["shortcode"],
                            "source": "instagram",
                            "url": f"https://www.instagram.com/p/{m['shortcode']}/",
                        })

    # search engines
    if use_search:
        if progress: progress(0.5, "Searching engines...")
        dorks = search_dorks(username)
        for d in dorks:
            g = google_search(session, d, 5)
            b = bing_search(session, d, 5)
            for url in g + b:
                if '/p/' in url or '/reel/' in url:
                    m = re.search(r'/(p|reel)/([A-Za-z0-9_-]+)', url)
                    if m:
                        shortcode = m.group(2)
                        comments = fetch_comments(session, shortcode, max_comments)
                        for c in comments:
                            if c["username"].lower() == username.lower():
                                key = f"{shortcode}:{c['text']}"
                                if key not in seen:
                                    seen.add(key)
                                    results.append({
                                        "comment": c["text"],
                                        "type": "reel" if m.group(1) == "reel" else "post",
                                        "owner": "unknown",
                                        "shortcode": shortcode,
                                        "source": "search",
                                        "url": url,
                                    })
                time.sleep(0.2)

    # wayback
    if use_wayback:
        if progress: progress(0.75, "Checking archives...")
        snapshots = wayback_search(username)
        for snap in snapshots:
            comments = extract_archive_comments(snap)
            for c in comments:
                if c["username"].lower() == username.lower() or c["username"] == "unknown":
                    key = f"{snap}:{c['text']}"
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "comment": c["text"],
                            "type": "archive",
                            "owner": "unknown",
                            "shortcode": "",
                            "source": "wayback",
                            "url": snap,
                        })
            time.sleep(0.2)

    if progress: progress(1.0, "Done")
    return results

# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="IG Comment Harvester", layout="wide")
st.title("🕵️ Instagram Comment Harvester")
st.markdown("Extract all comments by a user across posts, reels, search engines and archives.")

# Input
col1, col2 = st.columns([3,1])
with col1:
    username = st.text_input("Instagram username", placeholder="username without @")
with col2:
    harvest = st.button("🔍 Harvest", use_container_width=True, type="primary")

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    max_posts = st.slider("Max posts (public)", 10, 100, 30)
    max_comments = st.slider("Max comments per post", 20, 200, 50)
    use_search = st.checkbox("Use search engines", True)
    use_wayback = st.checkbox("Use Wayback Machine", True)

# Profile preview (when username entered)
if username and username.strip():
    with st.spinner("Loading profile..."):
        s = IGSession()
        prof = fetch_profile(username.strip(), s)
        if prof:
            st.session_state['profile'] = prof
        else:
            st.session_state.pop('profile', None)

if 'profile' in st.session_state and st.session_state['profile']:
    p = st.session_state['profile']
    col1, col2 = st.columns([1,3])
    with col1:
        if p['pic']:
            st.image(p['pic'], width=150)
    with col2:
        st.subheader(f"@{p['username']} ({p['full_name']})")
        st.write(f"**Status:** {'🔒 Private' if p['private'] else '🌐 Public'}")
        st.write(f"**ID:** {p['id']}")
        st.write(f"**Followers:** {p['followers']} | **Following:** {p['following']} | **Posts:** {p['posts']}")
        if p['bio']:
            st.write(f"**Bio:** {p['bio']}")

# Harvesting logic
if harvest and username and username.strip():
    target = username.strip().lstrip('@')
    progress_bar = st.progress(0)
    status = st.empty()
    def update(v, msg):
        progress_bar.progress(v)
        status.text(msg)

    with st.spinner("Harvesting..."):
        comments = harvest_all(target, max_posts, max_comments,
                               use_search, use_wayback, update)

    progress_bar.empty()
    status.empty()

    if comments:
        st.success(f"Found {len(comments)} comments")
        # metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", len(comments))
        c2.metric("On posts/reels", sum(1 for x in comments if x['type'] in ('post','reel')))
        c3.metric("Archives/search", sum(1 for x in comments if x['source'] in ('search','wayback')))

        df = [{
            "Comment": c['comment'][:100] + ("..." if len(c['comment'])>100 else ""),
            "Full Comment": c['comment'],
            "Media Type": c['type'],
            "Owner": c['owner'],
            "Source": c['source'],
            "URL": c['url'],
        } for c in comments]
        st.dataframe(df, use_container_width=True, height=400)

        # download CSV
        csv_buf = io.StringIO()
        writer = csv.DictWriter(csv_buf, fieldnames=["Comment","Media Type","Owner","Source","URL"])
        writer.writeheader()
        for c in comments:
            writer.writerow({"Comment":c['comment'],"Media Type":c['type'],
                             "Owner":c['owner'],"Source":c['source'],"URL":c['url']})
        st.download_button("📥 Download CSV", csv_buf.getvalue(),
                           f"{target}_comments.csv", "text/csv", use_container_width=True)
    else:
        st.warning("No comments found. Try increasing search depth or verifying username.")