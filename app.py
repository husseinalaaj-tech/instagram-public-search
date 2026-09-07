import streamlit as st
import requests
import json
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import random
import pandas as pd
from io import StringIO
import base64
import os
import sys
import tempfile
import shutil
from urllib.parse import urlparse, parse_qs

# محاولة استيراد مكتبات البحث (اختيارية)
try:
    from googlesearch import search as google_search
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

st.set_page_config(
    page_title="Instagram Comment Extractor",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تنسيق CSS مخصص
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stButton>button { background-color: #ff4b4b; color: white; border-radius: 8px; font-weight: bold; }
    .stTextInput>div>div>input { background-color: #1e1e1e; color: #00ff00; }
    .stTextArea>div>div>textarea { background-color: #1e1e1e; color: #00ff00; font-family: monospace; }
    .success-box { padding: 10px; border-radius: 5px; background-color: #1a472a; border-left: 4px solid #00ff00; }
    .error-box { padding: 10px; border-radius: 5px; background-color: #472a1a; border-left: 4px solid #ff4b4b; }
    .warning-box { padding: 10px; border-radius: 5px; background-color: #4a4a1a; border-left: 4px solid #ffff00; }
    .info-box { padding: 10px; border-radius: 5px; background-color: #1a1a47; border-left: 4px solid #4b4bff; }
    pre { background-color: #1e1e1e; padding: 10px; border-radius: 5px; overflow-x: auto; }
    .metric-card { background-color: #1e1e1e; padding: 15px; border-radius: 10px; text-align: center; }
    .comment-card { background-color: #1a1a2e; padding: 12px; border-radius: 8px; margin: 8px 0; border-left: 3px solid #ff4b4b; }
    .post-link { color: #4b8bff; text-decoration: none; }
    .timestamp { color: #888; font-size: 0.8em; }
</style>
""", unsafe_allow_html=True)

# عنوان التطبيق
st.title("💬 Instagram Comment Extractor")
st.markdown("*Search and extract all comments made by a specific Instagram user across posts and reels*")

# تهيئة حالة الجلسة
if 'search_history' not in st.session_state:
    st.session_state.search_history = []
if 'current_results' not in st.session_state:
    st.session_state.current_results = []
if 'search_running' not in st.session_state:
    st.session_state.search_running = False

# ===== الفئات الأساسية =====

class InstagramCommentExtractor:
    """الماسح الأساسي لاستخراج التعليقات"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        })
        self.csrf_token = None
        self._init_session()
    
    def _init_session(self):
        """تهيئة الجلسة وجلب توكن CSRF"""
        try:
            resp = self.session.get("https://www.instagram.com/", timeout=10)
            self.csrf_token = self.session.cookies.get("csrftoken")
            self.session.headers.update({"X-CSRFToken": self.csrf_token} if self.csrf_token else {})
        except:
            pass
    
    def search_posts(self, username, max_results=50, engine="duckduckgo"):
        """البحث عن منشورات قد تحتوي على تعليقات من المستخدم"""
        posts = []
        if engine == "duckduckgo":
            posts = self._search_duckduckgo(username, max_results)
        elif engine == "google" and GOOGLE_AVAILABLE:
            posts = self._search_google(username, max_results)
        else:
            posts = self._search_duckduckgo(username, max_results)  # fallback
        return posts
    
    def _search_duckduckgo(self, username, max_results):
        """البحث عبر DuckDuckGo (HTML)"""
        query = f'"{username}" site:instagram.com "comment" OR "replied"'
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query}
        posts = []
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                # استخراج الروابط التي تحتوي على instagram.com/p/ أو instagram.com/reel/
                links = re.findall(r'href="(https?://(?:www\.)?instagram\.com/(?:p|reel)/[^/"]+)"', resp.text)
                # إزالة التكرارات
                unique_links = list(dict.fromkeys(links))
                # أخذ أول max_results
                for link in unique_links[:max_results]:
                    shortcode = self._extract_shortcode(link)
                    if shortcode:
                        posts.append({"shortcode": shortcode, "url": link, "type": "post" if "/p/" in link else "reel"})
        except Exception as e:
            st.warning(f"DuckDuckGo search error: {e}")
        return posts
    
    def _search_google(self, username, max_results):
        """البحث عبر Google باستخدام مكتبة googlesearch"""
        posts = []
        if not GOOGLE_AVAILABLE:
            return posts
        query = f'"{username}" site:instagram.com'
        try:
            for url in google_search(query, num_results=max_results, lang="en"):
                if "instagram.com/p/" in url or "instagram.com/reel/" in url:
                    shortcode = self._extract_shortcode(url)
                    if shortcode:
                        posts.append({"shortcode": shortcode, "url": url, "type": "post" if "/p/" in url else "reel"})
        except Exception as e:
            st.warning(f"Google search error: {e}")
        return posts
    
    def _extract_shortcode(self, url):
        """استخراج الكود المختصر من رابط المنشور"""
        match = re.search(r'instagram\.com/(?:p|reel)/([^/?#]+)', url)
        return match.group(1) if match else None
    
    def get_post_comments(self, shortcode, max_comments=100):
        """جلب تعليقات منشور معين"""
        url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=1"
        comments = []
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # استخراج التعليقات من بيانات JSON
                graphql = data.get("graphql", {})
                shortcode_media = graphql.get("shortcode_media", {})
                edge_media_to_comment = shortcode_media.get("edge_media_to_comment", {})
                edges = edge_media_to_comment.get("edges", [])
                for edge in edges:
                    node = edge.get("node", {})
                    comment_text = node.get("text", "")
                    commenter = node.get("owner", {}).get("username", "")
                    timestamp = node.get("created_at", 0)
                    comments.append({
                        "text": comment_text,
                        "commenter": commenter,
                        "timestamp": timestamp,
                        "shortcode": shortcode
                    })
                # قد نحتاج إلى التصفح للصفحات التالية إذا كان هناك أكثر من max_comments
                # (يمكن تحسينها لاحقاً)
                return comments[:max_comments]
        except Exception as e:
            pass
        return comments
    
    def extract_comments_for_user(self, username, max_posts=50, search_engine="duckduckgo", max_comments_per_post=50):
        """الوظيفة الرئيسية: استخراج جميع التعليقات من المستخدم"""
        results = []
        # البحث عن المنشورات
        posts = self.search_posts(username, max_posts, search_engine)
        if not posts:
            return results, 0
        
        total_posts = len(posts)
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # معالجة المنشورات بالتوازي
        def process_post(post):
            shortcode = post["shortcode"]
            url = post["url"]
            comments = self.get_post_comments(shortcode, max_comments_per_post)
            user_comments = []
            for c in comments:
                if c["commenter"].lower() == username.lower():
                    user_comments.append({
                        "comment": c["text"],
                        "post_url": url,
                        "shortcode": shortcode,
                        "timestamp": datetime.fromtimestamp(c["timestamp"]).isoformat() if c["timestamp"] else "Unknown",
                        "commenter": c["commenter"]
                    })
            return user_comments
        
        processed = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(process_post, post): post for post in posts}
            for future in as_completed(futures):
                processed += 1
                progress = processed / total_posts
                progress_bar.progress(progress)
                status_text.text(f"Processing posts: {processed}/{total_posts}")
                user_comments = future.result()
                results.extend(user_comments)
        
        progress_bar.empty()
        status_text.empty()
        return results, total_posts

# ===== واجهة المستخدم =====

with st.sidebar:
    st.header("⚙️ Search Configuration")
    
    target_username = st.text_input("Instagram Username", placeholder="e.g., john_doe", value="")
    
    st.subheader("Search Options")
    search_engine = st.selectbox(
        "Search Engine",
        ["DuckDuckGo (recommended)", "Google (if available)"],
        index=0
    )
    engine_key = "duckduckgo" if "DuckDuckGo" in search_engine else "google"
    
    max_posts = st.slider("Max posts to search", min_value=5, max_value=100, value=30, step=5)
    max_comments_per_post = st.slider("Max comments per post", min_value=10, max_value=200, value=50, step=10)
    
    st.divider()
    st.caption("💡 The tool searches for posts where the username might appear in comments, then extracts the actual comments.")
    st.caption("🔍 Uses search engines to find relevant posts. Results may vary.")
    
    if not GOOGLE_AVAILABLE and engine_key == "google":
        st.warning("Google search library not installed. Fallback to DuckDuckGo.")
    
    start_button = st.button("🚀 Start Extraction", type="primary", use_container_width=True)

# الأقسام الرئيسية
tab1, tab2, tab3 = st.tabs(["📊 Results", "📜 History", "ℹ️ Help"])

with tab1:
    if start_button and target_username:
        if st.session_state.search_running:
            st.warning("Search already in progress.")
        else:
            st.session_state.search_running = True
            st.session_state.current_results = []
            
            try:
                extractor = InstagramCommentExtractor()
                with st.spinner(f"Searching and extracting comments for @{target_username}..."):
                    results, total_posts = extractor.extract_comments_for_user(
                        username=target_username,
                        max_posts=max_posts,
                        search_engine=engine_key,
                        max_comments_per_post=max_comments_per_post
                    )
                
                st.session_state.current_results = results
                st.session_state.search_running = False
                
                if results:
                    st.success(f"✅ Found {len(results)} comments from @{target_username} across {total_posts} posts.")
                    
                    # عرض الإحصائيات
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total Comments Found", len(results))
                    col2.metric("Posts Scanned", total_posts)
                    col3.metric("Unique Posts", len(set(r['shortcode'] for r in results)))
                    
                    # عرض النتائج في جدول
                    df = pd.DataFrame(results)
                    st.dataframe(df[['comment', 'post_url', 'timestamp']], use_container_width=True)
                    
                    # عرض كل تعليق بشكل بطاقة
                    st.subheader("Comments List")
                    for idx, row in df.iterrows():
                        st.markdown(f"""
                        <div class="comment-card">
                            <div><strong>💬</strong> {row['comment']}</div>
                            <div><a href="{row['post_url']}" target="_blank" class="post-link">🔗 View Post</a> <span class="timestamp">{row['timestamp']}</span></div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # زر تصدير CSV
                    csv = df.to_csv(index=False).encode('utf-8')
                    b64 = base64.b64encode(csv).decode()
                    href = f'<a href="data:file/csv;base64,{b64}" download="comments_{target_username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv">📥 Download CSV</a>'
                    st.markdown(href, unsafe_allow_html=True)
                    
                    # حفظ في التاريخ
                    st.session_state.search_history.append({
                        "username": target_username,
                        "timestamp": datetime.now().isoformat(),
                        "total_comments": len(results),
                        "posts_scanned": total_posts,
                        "results": results
                    })
                else:
                    st.warning(f"❌ No comments found for @{target_username}. Try adjusting search parameters or username.")
            
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                st.session_state.search_running = False
    
    # عرض النتائج الحالية إذا كانت موجودة
    if not start_button and st.session_state.current_results:
        results = st.session_state.current_results
        st.success(f"Showing last results: {len(results)} comments found.")
        df = pd.DataFrame(results)
        st.dataframe(df[['comment', 'post_url', 'timestamp']], use_container_width=True)
        # إلخ...

with tab2:
    st.subheader("Search History")
    if st.session_state.search_history:
        for idx, record in enumerate(reversed(st.session_state.search_history)):
            with st.expander(f"Search #{len(st.session_state.search_history)-idx} - @{record['username']} - {record['timestamp']}"):
                st.write(f"Total comments: {record['total_comments']}")
                st.write(f"Posts scanned: {record['posts_scanned']}")
                if record['results']:
                    sample = record['results'][:3]
                    for r in sample:
                        st.write(f"- {r['comment']} ({r['post_url']})")
                    if len(record['results']) > 3:
                        st.write(f"... and {len(record['results'])-3} more")
                else:
                    st.write("No comments found.")
    else:
        st.info("No search history yet.")

with tab3:
    st.subheader("How it works")
    st.markdown("""
    1. **Search for posts**: The tool uses a search engine (DuckDuckGo or Google) to find Instagram posts that might contain comments from the target user.
    2. **Extract comments**: For each found post, it fetches the comments (up to the limit) using Instagram's public API.
    3. **Filter**: It filters comments to keep only those made by the specified username.
    4. **Present results**: Results are displayed in a table and as comment cards, with links to the original posts.
    
    **Important Notes**:
    - The search engine may not find all posts where the user commented; results depend on search engine indexing.
    - Instagram may rate-limit requests; use responsibly.
    - Some posts may be private or not accessible; those will be skipped.
    - The tool does not require login, but some endpoints may need a CSRF token (automatically handled).
    """)
    
    st.subheader("Installation Requirements")
    st.code("""
    pip install streamlit requests pandas googlesearch-python
    """, language="bash")
    st.caption("If Google search is not installed, the tool will fallback to DuckDuckGo.")

# تذييل
st.divider()
st.caption("💬 Instagram Comment Extractor | For educational and authorized use only")