# gmail_osint_fixed.py
import streamlit as st
import requests
import re
import json
import hashlib
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional, List, Tuple

# Optional DNS
try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

# ---------------------------- Configuration ----------------------------
MAX_WORKERS = 8
CACHE_TTL = 3600
RETRY_COUNT = 3
RETRY_BACKOFF = 1

# ---------------------------- Helpers ----------------------------
def validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

def is_gmail(email: str) -> bool:
    return email.split('@')[-1].lower() in ["gmail.com", "googlemail.com"]

def safe_request_json(url: str, headers: Dict = None, timeout: int = 10) -> Tuple[Optional[Dict], Optional[str]]:
    """GET request returning JSON; returns (data, error)."""
    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json(), None
            elif resp.status_code == 429:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
                continue
            else:
                return None, f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as e:
            if attempt == RETRY_COUNT - 1:
                return None, str(e)
            time.sleep(RETRY_BACKOFF * (2 ** attempt))
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON: {str(e)}"
    return None, "Max retries exceeded"

# ---------------------------- OSINT Modules ----------------------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def check_deliverability(email: str) -> Dict:
    domain = email.split('@')[-1]
    result = {"valid_format": validate_email(email), "mx_exists": False, "servers": []}
    try:
        if DNS_AVAILABLE:
            mx = dns.resolver.resolve(domain, 'MX')
            result["mx_exists"] = len(mx) > 0
            result["servers"] = [str(r.exchange) for r in mx]
            result["method"] = "dnspython"
        else:
            socket.gethostbyname(domain)
            result["mx_exists"] = True
            result["servers"] = ["(resolved via A record)"]
            result["method"] = "socket_fallback"
    except Exception as e:
        result["error"] = str(e)
    return result

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def check_hibp(email: str) -> Dict:
    """HIBP returns plain text; handle accordingly."""
    sha1 = hashlib.sha1(email.encode()).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    url = f"https://api.pwnedpasswords.com/range/{prefix}"
    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if line.startswith(suffix):
                        count = int(line.split(':')[1])
                        return {"found": True, "count": count}
                return {"found": False, "count": 0}
            elif resp.status_code == 429:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
                continue
            else:
                return {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            if attempt == RETRY_COUNT - 1:
                return {"error": str(e)}
            time.sleep(RETRY_BACKOFF * (2 ** attempt))
    return {"error": "Max retries exceeded"}

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def check_emailrep(email: str, api_key: str = "") -> Dict:
    if not api_key:
        return {"error": "No API key provided"}
    url = f"https://emailrep.io/{email}"
    headers = {"Key": api_key}
    data, err = safe_request_json(url, headers=headers)
    if err:
        return {"error": err}
    return {
        "reputation": data.get("reputation", "unknown"),
        "suspicious": data.get("suspicious", False),
        "risk_score": data.get("details", {}).get("risk_score", 0),
        "raw": data
    }

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def check_gravatar(email: str) -> Dict:
    md5 = hashlib.md5(email.lower().encode()).hexdigest()
    url = f"https://www.gravatar.com/avatar/{md5}?d=404&s=200"
    try:
        resp = requests.head(url, timeout=5)
        if resp.status_code == 200:
            return {"exists": True, "url": url, "md5": md5}
    except:
        pass
    return {"exists": False}

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def check_domain_whois(domain: str) -> Dict:
    try:
        import whois
        w = whois.whois(domain)
        return {
            "registrar": w.registrar,
            "creation": str(w.creation_date),
            "expiration": str(w.expiration_date),
            "name_servers": w.name_servers,
            "org": w.org,
            "country": w.country
        }
    except ImportError:
        return {"error": "python-whois module not installed"}
    except Exception as e:
        return {"error": f"WHOIS lookup failed: {str(e)}"}

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def check_leaks(email: str) -> Dict:
    url = f"https://leak-check.net/api/public?check={email}"
    data, err = safe_request_json(url)
    if err:
        return {"error": err}
    if data is None:
        return {"error": "Empty response from leak API"}
    return {
        "found": data.get("found", False),
        "sources": data.get("sources", [])
    }

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def social_search(email: str, local_part: str, cse_key: str, cse_cx: str) -> List[Dict]:
    if not cse_key or not cse_cx:
        return []
    results = []
    queries = [f'"{email}"', f'"{local_part}"']
    for q in queries:
        url = f"https://www.googleapis.com/customsearch/v1?key={cse_key}&cx={cse_cx}&q={q}"
        data, err = safe_request_json(url)
        if data and "items" in data:
            for item in data["items"][:3]:
                results.append({
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet")
                })
    return results

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def clearbit_enrich(email: str, api_key: str) -> Dict:
    if not api_key:
        return {"error": "No Clearbit key"}
    url = f"https://person.clearbit.com/v2/combined/find?email={email}"
    headers = {"Authorization": f"Bearer {api_key}"}
    data, err = safe_request_json(url, headers=headers)
    if err:
        return {"error": err}
    return {
        "person": data.get("person"),
        "company": data.get("company")
    }

# ---------------------------- Parallel Engine ----------------------------
def run_osint(email: str, api_keys: Dict) -> Dict:
    results = {}
    progress_bar = st.progress(0, text="Starting...")
    status_text = st.empty()

    tasks = [
        ("deliverability", check_deliverability, email),
        ("hibp", check_hibp, email),
        ("gravatar", check_gravatar, email),
        ("domain", check_domain_whois, email.split('@')[-1]),
        ("leaks", check_leaks, email),
    ]
    if api_keys.get("emailrep"):
        tasks.append(("emailrep", check_emailrep, email, api_keys["emailrep"]))
    if api_keys.get("clearbit"):
        tasks.append(("clearbit", clearbit_enrich, email, api_keys["clearbit"]))
    if api_keys.get("google_cse") and api_keys.get("google_cx"):
        tasks.append(("social", social_search, email, email.split('@')[0], api_keys["google_cse"], api_keys["google_cx"]))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_name = {}
        for task in tasks:
            if len(task) == 3:
                future = executor.submit(task[1], task[2])
            elif len(task) == 4:
                future = executor.submit(task[1], task[2], task[3])
            else:
                future = executor.submit(task[1], task[2], task[3], task[4])
            future_to_name[future] = task[0]

        completed = 0
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {"error": str(e)}
            completed += 1
            progress_bar.progress(completed / len(tasks), f"{completed}/{len(tasks)}")
            status_text.text(f"🔄 {name} done")

    progress_bar.empty()
    status_text.empty()
    return results

# ---------------------------- Streamlit UI ----------------------------
def render_ui():
    st.set_page_config(page_title="Gmail‑OSINT Ultimate", page_icon="🔍", layout="wide")
    st.markdown("""
    <style>
    .main { background: #0d1117; }
    .stButton > button { background: #21262d; color: #58a6ff; border: 1px solid #30363d; border-radius: 6px; width: 100%; font-weight: bold; }
    .stButton > button:hover { background: #30363d; border-color: #58a6ff; }
    .stTextInput > div > div > input { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: #0d1117; padding: 8px; }
    .stTabs [data-baseweb="tab"] { background: #161b22; color: #c9d1d9; border-radius: 6px; padding: 8px 16px; border: 1px solid #30363d; }
    .stTabs [aria-selected="true"] { background: #21262d; border-bottom: 2px solid #58a6ff; }
    .stMetric > div { background: #161b22; padding: 12px; border-radius: 6px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

    st.title("🔍 Gmail‑OSINT Ultimate")
    st.caption("Real‑time email intelligence with parallel processing")

    with st.sidebar:
        st.header("⚙️ API Keys")
        emailrep_key = st.text_input("EmailRep.io Key", type="password")
        clearbit_key = st.text_input("Clearbit Key", type="password")
        google_cse_key = st.text_input("Google CSE Key", type="password")
        google_cx = st.text_input("Google CSE ID", type="password")

        st.divider()
        target_email = st.text_input("Gmail address", placeholder="example@gmail.com")
        if st.button("🔎 Run OSINT", use_container_width=True):
            if not target_email:
                st.warning("Enter an email.")
            elif not validate_email(target_email):
                st.error("Invalid email format.")
            else:
                st.session_state["email"] = target_email
                st.session_state["api_keys"] = {
                    "emailrep": emailrep_key,
                    "clearbit": clearbit_key,
                    "google_cse": google_cse_key,
                    "google_cx": google_cx
                }
                st.session_state["run"] = True
                st.rerun()

    if "run" in st.session_state and st.session_state["run"]:
        email = st.session_state["email"]
        api_keys = st.session_state["api_keys"]
        with st.spinner(f"Gathering intel on {email}..."):
            results = run_osint(email, api_keys)
        st.session_state["results"] = results
        st.session_state["run"] = False
        st.rerun()

    if "results" in st.session_state:
        results = st.session_state["results"]
        email = st.session_state.get("email", "unknown")

        errors = {k: v for k, v in results.items() if isinstance(v, dict) and "error" in v}
        if errors:
            with st.expander("⚠️ Some modules returned errors", expanded=False):
                for mod, err in errors.items():
                    st.error(f"{mod}: {err['error']}")

        tabs = st.tabs(["📊 Dashboard", "🔐 Security", "👤 Identity", "🌐 Web & Domain", "📜 JSON"])
        with tabs[0]:
            col1, col2, col3 = st.columns(3)
            deliv = results.get("deliverability", {})
            col1.metric("MX Valid", "✅" if deliv.get("mx_exists") else "❌")
            hibp = results.get("hibp", {})
            if hibp.get("found"):
                col2.metric("Breaches", hibp.get("count", 0), delta="⚠️ breached")
            else:
                col2.metric("Breaches", "None")
            grav = results.get("gravatar", {})
            col3.metric("Gravatar", "✅" if grav.get("exists") else "❌")
            if grav.get("exists"):
                st.image(grav["url"], width=120, caption="Gravatar")

            rep = results.get("emailrep", {})
            if rep and "reputation" in rep:
                st.metric("EmailRep Reputation", rep["reputation"])
                st.metric("Risk Score", rep.get("risk_score", 0))

        with tabs[1]:
            st.subheader("🔐 Security Findings")
            if hibp.get("found"):
                st.error(f"🚨 Found in {hibp['count']} data breaches.")
            else:
                st.success("✅ No breaches in HIBP.")

            leaks = results.get("leaks", {})
            if leaks.get("found"):
                st.warning(f"📢 Found in paste leaks: {', '.join(leaks.get('sources', []))}")
            else:
                st.success("No paste leaks detected.")

            if rep and "suspicious" in rep:
                if rep["suspicious"]:
                    st.warning("⚠️ Email flagged as suspicious by EmailRep.")
                else:
                    st.info("EmailRep considers this email safe.")

        with tabs[2]:
            st.subheader("👤 Identity Enrichment")
            clearbit = results.get("clearbit", {})
            if clearbit and "person" in clearbit and clearbit["person"]:
                p = clearbit["person"]
                st.write(f"**Name:** {p.get('name', {}).get('fullName', 'N/A')}")
                st.write(f"**Location:** {p.get('location', 'N/A')}")
                st.write(f"**Bio:** {p.get('bio', 'N/A')}")
                st.write(f"**Site:** {p.get('site', 'N/A')}")
                if clearbit.get("company"):
                    st.write(f"**Company:** {clearbit['company'].get('name', 'N/A')}")
            else:
                st.info("No enrichment data.")

            if grav.get("exists"):
                st.write(f"**Gravatar MD5:** `{grav['md5']}`")

        with tabs[3]:
            st.subheader("🌐 Domain & Social")
            domain = results.get("domain", {})
            if domain and "error" not in domain:
                st.write(f"**Registrar:** {domain.get('registrar', 'N/A')}")
                st.write(f"**Created:** {domain.get('creation', 'N/A')}")
                st.write(f"**Expires:** {domain.get('expiration', 'N/A')}")
                st.write(f"**Organization:** {domain.get('org', 'N/A')}")
                st.write(f"**Country:** {domain.get('country', 'N/A')}")
            else:
                st.warning("WHOIS info not available.")

            social = results.get("social", [])
            if social:
                st.write("**Social / Web mentions:**")
                for item in social[:10]:
                    st.markdown(f"- [{item['title']}]({item['link']})")
            else:
                st.info("No social results.")

        with tabs[4]:
            st.subheader("📜 Raw JSON")
            st.json(results)

        if st.button("📥 Export JSON"):
            st.download_button(
                label="Download",
                data=json.dumps(results, indent=2),
                file_name=f"osint_{email}_{int(time.time())}.json",
                mime="application/json"
            )

if __name__ == "__main__":
    render_ui()