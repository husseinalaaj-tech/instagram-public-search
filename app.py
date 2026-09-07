import streamlit as st
import requests
import re
import json
import time
import hashlib
import socket
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from urllib.parse import urlparse
import base64

# Try to import dnspython; fallback gracefully
try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

# ---------------------------- Configuration ----------------------------
API_KEYS = {
    "emailrep": "",
    "clearbit": "",
    "hunter": "",
    "google_cse": "",
    "google_cx": ""
}

# ---------------------------- Validators ----------------------------
def validate_email(email: str) -> bool:
    pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(pattern, email) is not None

def is_gmail(email: str) -> bool:
    domain = email.split('@')[-1].lower()
    return domain in ["gmail.com", "googlemail.com"]

# ---------------------------- Core OSINT Engine ----------------------------
class GmailOsintEngine:
    def __init__(self, email: str):
        self.email = email
        self.local_part, self.domain = email.split('@')
        self.results = {}
        self.errors = []

    def run_all(self) -> Dict:
        with st.spinner("Collecting intelligence..."):
            self._check_deliverability()
            self._check_breaches()
            self._get_reputation()
            self._get_gravatar()
            self._get_domain_info()
            self._check_leaks()
            self._social_search()
            self._email_enrichment()
        return self.results

    def _check_deliverability(self):
        """Check MX records; fallback to A record if dnspython missing."""
        result = {'valid_format': True, 'mx_exists': False, 'mx_servers': []}
        try:
            if DNS_AVAILABLE:
                mx_records = dns.resolver.resolve(self.domain, 'MX')
                result['mx_exists'] = len(mx_records) > 0
                result['mx_servers'] = [str(r.exchange) for r in mx_records]
                result['method'] = 'dnspython'
            else:
                # Fallback: check if domain resolves (A record)
                try:
                    socket.gethostbyname(self.domain)
                    result['mx_exists'] = True
                    result['mx_servers'] = ['(resolved via A record)']
                    result['method'] = 'socket_fallback'
                    self.errors.append("dnspython not installed – MX check limited to A record resolution.")
                except socket.gaierror:
                    result['mx_exists'] = False
                    result['mx_servers'] = []
                    result['method'] = 'socket_fallback'
        except Exception as e:
            self.errors.append(f"Deliverability check failed: {str(e)}")
            result['error'] = str(e)
        self.results['deliverability'] = result

    def _check_breaches(self):
        try:
            sha1_hash = hashlib.sha1(self.email.encode('utf-8')).hexdigest().upper()
            prefix = sha1_hash[:5]
            suffix = sha1_hash[5:]
            url = f"https://api.pwnedpasswords.com/range/{prefix}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                lines = response.text.splitlines()
                for line in lines:
                    if line.startswith(suffix):
                        count = int(line.split(':')[1])
                        self.results['breaches'] = {
                            'found': True,
                            'breach_count': count,
                            'hash_prefix': prefix
                        }
                        break
                else:
                    self.results['breaches'] = {'found': False, 'breach_count': 0}
            else:
                self.results['breaches'] = {'error': f"API error {response.status_code}"}
        except Exception as e:
            self.errors.append(f"HIBP check failed: {str(e)}")
            self.results['breaches'] = {'error': str(e)}

    def _get_reputation(self):
        try:
            url = f"https://emailrep.io/{self.email}"
            headers = {'Key': API_KEYS.get('emailrep', '')}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.results['reputation'] = {
                    'reputation': data.get('reputation', 'unknown'),
                    'suspicious': data.get('suspicious', False),
                    'risk_score': data.get('details', {}).get('risk_score', 0),
                    'details': data
                }
            else:
                self.results['reputation'] = {'error': f"API error {response.status_code}"}
        except Exception as e:
            self.errors.append(f"EmailRep.io check failed: {str(e)}")
            self.results['reputation'] = {'error': str(e)}

    def _get_gravatar(self):
        try:
            hash_md5 = hashlib.md5(self.email.lower().encode('utf-8')).hexdigest()
            gravatar_url = f"https://www.gravatar.com/avatar/{hash_md5}?d=404&s=200"
            response = requests.get(gravatar_url, timeout=5)
            if response.status_code == 200:
                self.results['gravatar'] = {
                    'exists': True,
                    'url': gravatar_url,
                    'md5': hash_md5
                }
            else:
                self.results['gravatar'] = {'exists': False}
        except Exception as e:
            self.errors.append(f"Gravatar check failed: {str(e)}")
            self.results['gravatar'] = {'error': str(e)}

    def _get_domain_info(self):
        try:
            import whois
            domain_info = whois.whois(self.domain)
            self.results['domain'] = {
                'registrar': domain_info.registrar,
                'creation_date': str(domain_info.creation_date),
                'expiration_date': str(domain_info.expiration_date),
                'name_servers': domain_info.name_servers,
                'org': domain_info.org,
                'country': domain_info.country
            }
        except Exception as e:
            self.errors.append(f"WHOIS lookup failed: {str(e)}")
            self.results['domain'] = {'error': str(e)}

    def _check_leaks(self):
        try:
            url = f"https://leak-check.net/api/public?check={self.email}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.results['leaks'] = {
                    'found': data.get('found', False),
                    'sources': data.get('sources', []),
                    'details': data
                }
            else:
                self.results['leaks'] = {'error': f"API error {response.status_code}"}
        except Exception as e:
            self.errors.append(f"Leak check failed: {str(e)}")
            self.results['leaks'] = {'error': str(e)}

    def _social_search(self):
        try:
            cse_key = API_KEYS.get('google_cse')
            cse_cx = API_KEYS.get('google_cx')
            if not cse_key or not cse_cx:
                self.results['social'] = {'error': 'Google CSE API key not configured'}
                return
            queries = [f'"{self.email}"', f'"{self.local_part}" intitle:"{self.local_part}"']
            social_results = []
            for query in queries:
                url = f"https://www.googleapis.com/customsearch/v1?key={cse_key}&cx={cse_cx}&q={query}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    for item in items[:5]:
                        social_results.append({
                            'title': item.get('title'),
                            'link': item.get('link'),
                            'snippet': item.get('snippet')
                        })
            self.results['social'] = social_results
        except Exception as e:
            self.errors.append(f"Social search failed: {str(e)}")
            self.results['social'] = {'error': str(e)}

    def _email_enrichment(self):
        try:
            clearbit_key = API_KEYS.get('clearbit')
            if not clearbit_key:
                self.results['enrichment'] = {'error': 'Clearbit API key not configured'}
                return
            url = f"https://person.clearbit.com/v2/combined/find?email={self.email}"
            headers = {'Authorization': f'Bearer {clearbit_key}'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.results['enrichment'] = {
                    'person': data.get('person'),
                    'company': data.get('company')
                }
            else:
                self.results['enrichment'] = {'error': f"API error {response.status_code}"}
        except Exception as e:
            self.errors.append(f"Clearbit enrichment failed: {str(e)}")
            self.results['enrichment'] = {'error': str(e)}

# ---------------------------- Streamlit UI ----------------------------
def render_ui():
    st.set_page_config(
        page_title="Gmail‑OSINT — Email Intelligence",
        page_icon="📧",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.markdown("""
    <style>
    .main { background: #0d1117; }
    .stButton > button {
        background: #21262d; color: #58a6ff; border: 1px solid #30363d; border-radius: 6px; width: 100%; font-weight: bold; padding: 10px;
    }
    .stButton > button:hover { background: #30363d; color: #58a6ff; border-color: #58a6ff; }
    .stTextInput > div > div > input { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; font-family: monospace; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #0d1117; padding: 8px; }
    .stTabs [data-baseweb="tab"] { background: #161b22; color: #c9d1d9; border-radius: 6px; padding: 8px 16px; border: 1px solid #30363d; }
    .stTabs [aria-selected="true"] { background: #21262d; border-bottom: 2px solid #58a6ff; }
    .stMarkdown { color: #c9d1d9; }
    .stMetric > div { background: #161b22; padding: 12px; border-radius: 6px; border: 1px solid #30363d; }
    .stCodeBlock { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; }
    </style>
    """, unsafe_allow_html=True)

    st.title("📧 Gmail‑OSINT")
    st.caption("Professional Email Intelligence Gathering — Gmail‑focused")

    # Warn if dnspython is missing
    if not DNS_AVAILABLE:
        st.warning("⚠️ `dnspython` not installed – MX checks will be limited. Install it for full functionality: `pip install dnspython`")

    with st.sidebar:
        st.header("🔍 Target Email")
        target_email = st.text_input("Enter Gmail address", placeholder="example@gmail.com")
        if st.button("🔎 Start OSINT", use_container_width=True):
            if target_email:
                st.session_state['email'] = target_email
                st.session_state['run'] = True
            else:
                st.warning("Please enter an email address.")

        st.divider()
        st.subheader("⚙️ API Keys (optional)")
        api_key_emailrep = st.text_input("EmailRep.io Key", type="password")
        api_key_clearbit = st.text_input("Clearbit Key", type="password")
        if api_key_emailrep:
            API_KEYS['emailrep'] = api_key_emailrep
        if api_key_clearbit:
            API_KEYS['clearbit'] = api_key_clearbit

        st.divider()
        st.metric("Results cached", "Yes" if 'results' in st.session_state else "No")

    if 'run' in st.session_state and st.session_state['run']:
        email = st.session_state['email']
        if not validate_email(email):
            st.error("❌ Invalid email format")
            st.session_state['run'] = False
        else:
            if not is_gmail(email):
                st.warning("⚠️ This tool is optimized for Gmail addresses. Proceeding anyway...")
            with st.spinner(f"Collecting intelligence on {email}..."):
                engine = GmailOsintEngine(email)
                results = engine.run_all()
                st.session_state['results'] = results
                st.session_state['errors'] = engine.errors
            st.session_state['run'] = False

    if 'results' in st.session_state:
        results = st.session_state['results']
        errors = st.session_state.get('errors', [])

        if errors:
            with st.expander("⚠️ Errors encountered", expanded=False):
                for err in errors:
                    st.error(err)

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📋 Overview", "🔐 Security & Breaches", "👤 Identity", "🌐 Domain & Social", "📜 Raw Data"
        ])

        with tab1:
            col1, col2, col3 = st.columns(3)
            deliv = results.get('deliverability', {})
            with col1:
                st.metric("MX Exists", "✅" if deliv.get('mx_exists') else "❌")
            rep = results.get('reputation', {})
            with col2:
                st.metric("Reputation", rep.get('reputation', 'unknown'))
            breaches = results.get('breaches', {})
            with col3:
                if breaches.get('found'):
                    st.metric("Breach Count", breaches.get('breach_count', 0))
                else:
                    st.metric("Breaches", "None found")

            grav = results.get('gravatar', {})
            if grav.get('exists'):
                st.image(grav.get('url'), width=100, caption="Gravatar")
            else:
                st.info("No Gravatar found")

        with tab2:
            st.subheader("🔐 Security Assessment")
            if breaches.get('found'):
                st.error(f"🚨 This email has been exposed in {breaches.get('breach_count')} data breaches!")
                st.caption("Consider using a unique password and enabling 2FA.")
            else:
                st.success("✅ No known breaches found in Have I Been Pwned database.")
            if rep:
                st.write("**EmailRep.io Risk Assessment:**")
                st.json(rep)
            leaks = results.get('leaks', {})
            if leaks.get('found'):
                st.warning("📢 Email found in paste leaks. Sources: " + ", ".join(leaks.get('sources', [])))
            else:
                st.success("No paste leaks detected.")

        with tab3:
            st.subheader("👤 Identity & Enrichment")
            enrichment = results.get('enrichment', {})
            if enrichment and 'person' in enrichment:
                person = enrichment['person']
                st.write(f"**Name:** {person.get('name', {}).get('fullName', 'N/A')}")
                st.write(f"**Location:** {person.get('location', 'N/A')}")
                st.write(f"**Bio:** {person.get('bio', 'N/A')}")
                st.write(f"**Company:** {enrichment.get('company', {}).get('name', 'N/A')}")
                if person.get('site'):
                    st.write(f"**Website:** {person['site']}")
            else:
                st.info("No enrichment data available (API key may be missing or email not found).")
            if grav.get('exists'):
                st.write(f"**Gravatar MD5:** `{grav.get('md5')}`")
                st.image(grav.get('url'), caption="Profile Picture")

        with tab4:
            st.subheader("🌐 Domain & Social Media")
            domain_info = results.get('domain', {})
            if 'error' not in domain_info:
                st.write(f"**Registrar:** {domain_info.get('registrar', 'N/A')}")
                st.write(f"**Creation Date:** {domain_info.get('creation_date', 'N/A')}")
                st.write(f"**Expiration:** {domain_info.get('expiration_date', 'N/A')}")
                st.write(f"**Organization:** {domain_info.get('org', 'N/A')}")
                st.write(f"**Country:** {domain_info.get('country', 'N/A')}")
            else:
                st.warning("WHOIS data unavailable.")

            social = results.get('social', [])
            if social and not isinstance(social, dict):
                st.write("**Social Media / Web Presence:**")
                for item in social[:10]:
                    st.markdown(f"- [{item.get('title')}]({item.get('link')})")
            else:
                st.info("No social media results found (Google CSE not configured or no results).")

        with tab5:
            st.subheader("📜 Raw JSON Data")
            st.json(results)

        if st.button("📥 Export JSON"):
            json_str = json.dumps(results, indent=2)
            st.download_button(
                label="Download JSON",
                data=json_str,
                file_name=f"osint_{email}_{int(time.time())}.json",
                mime="application/json"
            )

if __name__ == "__main__":
    render_ui()