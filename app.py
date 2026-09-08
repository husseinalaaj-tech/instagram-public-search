# language: python
# file: ig_session_fix.py
# runtime: Python 3.9+, requests, streamlit

import requests
import re
import time
import json
from bs4 import BeautifulSoup

class FixedIGSession:
    """
    Instagram session that maintains cookies and proper headers.
    Visits homepage first to get csrftoken and other cookies,
    then uses mobile API endpoints that are less likely to be blocked.
    """
    
    BASE_URL = "https://www.instagram.com"
    API_URL = "https://i.instagram.com/api/v1"
    GRAPHQL_URL = "https://www.instagram.com/graphql/query"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "X-IG-App-ID": "936619743392459",
            "X-IG-App-Locale": "en_US",
            "X-IG-Device-ID": "android-0a1b2c3d4e5f6a7b",
            "X-IG-Timezone-Offset": "0",
            "X-IG-WWW-Claim": "hmac.AR1pYbF1yF1mJ2xD2Kq0q4qV4YQ4C6QzY4Z6U8H3o4A",
            "X-Instagram-AJAX": "1",
            "X-Requested-With": "XMLHttpRequest",
        })
        self._initialize_cookies()
    
    def _initialize_cookies(self):
        """Visit homepage to get essential cookies."""
        try:
            # Get main page to set cookies
            resp = self.session.get(
                self.BASE_URL + "/",
                headers={"User-Agent": self.session.headers["User-Agent"]},
                timeout=15
            )
            # Extract csrftoken from cookies if present
            if "csrftoken" in self.session.cookies:
                self.session.headers["X-CSRFToken"] = self.session.cookies["csrftoken"]
            else:
                # Try to extract from HTML
                match = re.search(r'"csrf_token":"([^"]+)"', resp.text)
                if match:
                    self.session.headers["X-CSRFToken"] = match.group(1)
                    self.session.cookies.set("csrftoken", match.group(1))
            
            # Get mobile API cookies
            self.session.get(
                self.API_URL + "/users/web_profile_info/?username=instagram",
                headers={"User-Agent": self.session.headers["User-Agent"]},
                timeout=15
            )
        except Exception:
            pass
    
    def get_headers(self, extra=None):
        headers = self.session.headers.copy()
        if extra:
            headers.update(extra)
        return headers
    
    def get_user_profile(self, username):
        """Use i.instagram.com API which is more resistant to blocks."""
        url = f"{self.API_URL}/users/web_profile_info/"
        params = {"username": username}
        try:
            resp = self.session.get(url, params=params, headers=self.get_headers(), timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                user = data.get("data", {}).get("user", {})
                return {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "full_name": user.get("full_name"),
                    "profile_pic_url": user.get("profile_pic_url"),
                    "is_private": user.get("is_private"),
                    "followers": user.get("edge_followed_by", {}).get("count"),
                    "following": user.get("edge_follow", {}).get("count"),
                    "posts_count": user.get("edge_owner_to_timeline_media", {}).get("count"),
                    "biography": user.get("biography"),
                }
            elif resp.status_code == 429:
                return {"error": "rate_limited"}
            elif resp.status_code == 404:
                return {"error": "not_found"}
            else:
                return {"error": f"status_{resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_user_media(self, user_id, count=12, cursor=None):
        """Use GraphQL with cookies."""
        variables = {"id": user_id, "first": count, "after": cursor}
        url = f"{self.GRAPHQL_URL}?query_hash=69cba40317214236af40e7efa697781d&variables={json.dumps(variables)}"
        headers = self.get_headers()
        headers["X-CSRFToken"] = self.session.cookies.get("csrftoken", "")
        try:
            resp = self.session.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                edges = data.get("data", {}).get("user", {}).get("edge_owner_to_timeline_media", {}).get("edges", [])
                page_info = data.get("data", {}).get("user", {}).get("edge_owner_to_timeline_media", {}).get("page_info", {})
                media = []
                for edge in edges:
                    node = edge["node"]
                    media.append({
                        "id": node.get("id"),
                        "shortcode": node.get("shortcode"),
                        "is_video": node.get("is_video"),
                        "owner": node.get("owner", {}).get("username"),
                    })
                return {"media": media, "page_info": page_info}
            return {"error": f"status_{resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_media_comments(self, shortcode, count=20, cursor=None):
        """Get comments for a media shortcode."""
        variables = {"shortcode": shortcode, "first": count, "after": cursor}
        url = f"{self.GRAPHQL_URL}?query_hash=97b41c52301f77ce508f55e66d17620e&variables={json.dumps(variables)}"
        headers = self.get_headers()
        headers["X-CSRFToken"] = self.session.cookies.get("csrftoken", "")
        try:
            resp = self.session.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                edges = data.get("data", {}).get("shortcode_media", {}).get("edge_media_to_comment", {}).get("edges", [])
                page_info = data.get("data", {}).get("shortcode_media", {}).get("edge_media_to_comment", {}).get("page_info", {})
                comments = []
                for edge in edges:
                    node = edge["node"]
                    comments.append({
                        "username": node.get("owner", {}).get("username"),
                        "text": node.get("text"),
                        "timestamp": node.get("created_at"),
                    })
                return {"comments": comments, "page_info": page_info}
            return {"error": f"status_{resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}

# Example usage function for Streamlit integration
def harvest_comments_fixed(username, max_posts=50, max_comments=100, progress_cb=None):
    """Fixed harvester using the robust session."""
    ig = FixedIGSession()
    results = []
    
    # Get profile
    if progress_cb:
        progress_cb(0.05, "Fetching profile...")
    profile = ig.get_user_profile(username)
    if "error" in profile:
        if progress_cb:
            progress_cb(0, f"Profile error: {profile['error']}")
        return results
    
    user_id = profile.get("id")
    if not user_id:
        return results
    
    # Get media
    if progress_cb:
        progress_cb(0.1, "Fetching user media...")
    media_list = []
    cursor = None
    while len(media_list) < max_posts:
        resp = ig.get_user_media(user_id, count=min(12, max_posts - len(media_list)), cursor=cursor)
        if "error" in resp:
            break
        media_list.extend(resp["media"])
        page_info = resp.get("page_info", {})
        if not page_info.get("has_next_page"):
            break
        cursor = page_info.get("end_cursor")
        time.sleep(0.5)
    
    # Get comments on each media
    total = len(media_list)
    for i, media in enumerate(media_list):
        if progress_cb:
            progress_cb(0.1 + 0.5 * (i / total), f"Scanning comments {i+1}/{total}...")
        cursor = None
        while True:
            resp = ig.get_media_comments(media["shortcode"], count=20, cursor=cursor)
            if "error" in resp:
                break
            for c in resp["comments"]:
                if c["username"].lower() == username.lower():
                    results.append({
                        "comment": c["text"],
                        "media_type": "reel" if media["is_video"] else "post",
                        "shortcode": media["shortcode"],
                        "owner": media["owner"],
                        "timestamp": c["timestamp"],
                    })
            page_info = resp.get("page_info", {})
            if not page_info.get("has_next_page") or len(results) >= max_comments:
                break
            cursor = page_info.get("end_cursor")
            time.sleep(0.3)
    
    if progress_cb:
        progress_cb(1.0, "Done")
    return results