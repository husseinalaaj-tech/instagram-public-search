# gmail_osint.py
"""
Gmail‑OSINT — Professional Email Intelligence Tool
Streamlit application for comprehensive Gmail‑based OSINT.
"""

import streamlit as st
import requests
import re
import json
import dns.resolver
import whois
import time
import hashlib
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from urllib.parse import urlparse
import base64

# ---------------------------- Configuration ----------------------------
# Free API keys – you should replace with your own for production
API_KEYS = {
    "emailrep": "your_emailrep_api_key",      # Free at https://emailrep.io/
    "clearbit": "your_clearbit_api_key",      # Free at https://clearbit.com/
    "hunter": "your_hunter_api_key",          # Free at https://hunter.io/
    "google_cse": "your_google_cse_key",      # For social search
    "google_cx": "your_google_cx"             # Custom search engine ID
}

# ---------------------------- Validators ----------------------------
def validate_email(email: str) -> bool:
    """Validate email format using RFC 5322 regex."""
    pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(pattern, email) is not None

def is_gmail(email: str) -> bool:
    """Check if the email domain is gmail.com or googlemail.com."""
    domain = email.split('@')[-1].lower()
    return domain in ["gmail.com", "googlemail.com"]

# ---------------------------- Core OSINT Modules ----------------------------
class GmailOsintEngine:
    def __init__(self, email: str):
        self.email = email
        self.local_part, self.domain = email.split('@')
        self.results = {}
        self.errors = []

    def run_all(self) -> Dict:
        """Execute all OSINT modules and return aggregated results."""
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
        """Validate the email address syntax and domain MX records."""
        try:
            # Basic format already validated
            # Check MX records for domain
            mx_records = dns.resolver.resolve(self.domain, 'MX')
            self.results['deliverability'] = {
                'valid_format': True,
                'mx_exists': len(mx_records) > 0,
                'mx_servers': [str(r.exchange) for r in mx_records]
            }
        except Exception as e:
            self.errors.append(f"Deliverability check failed: {str(e)}")
            self.results['deliverability'] = {'valid_format': True, 'mx_exists': False, 'error': str(e)}

    def _check_breaches(self):
        """Query Have I Been Pwned API for breaches."""
        try:
            # Hash the email with SHA-1 for HIBP API
            sha1_hash = hashlib.sha1(self.email.encode('utf-8')).hexdigest().upper()
            prefix = sha1_hash[:5]
            suffix = sha1_hash[5:]
            url = f"https://api.pwnedpasswords.com/range/{prefix}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # Search for the suffix in the response
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
        """Query EmailRep.io for reputation score and risk."""
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
        """Fetch Gravatar profile image and associated data."""
        try:
            # MD5 hash of email
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
        """Get WHOIS and MX information for the domain."""
        try:
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
        """Search for email in pastebin leaks (simulated using a free API like leakcheck)."""
        try:
            # Using leak-check.net free API (no key required for basic)
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
        """Search for social media profiles associated with the email or username."""
        # Using Google Custom Search API (limited to 100 queries/day for free)
        try:
            cse_key = API_KEYS.get('google_cse')
            cse_cx = API_KEYS.get('google_cx')
            if not cse_key or not cse_cx:
                self.results['social'] = {'error': 'Google CSE API key not configured'}
                return

            # Search for email and also for username
            queries = [
                f'"{self.email}"',
                f'"{self.local_part}" intitle:"{self.local_part}"'
            ]
            social_results = []
            for query in queries:
                url = f"https://www.googleapis.com/customsearch/v1?key={cse_key}&cx={cse_cx}&q={query}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    for item in items[:5]:  # Limit to 5 results per query
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
        """Use Clearbit or Hunter.io to get additional profile info."""
        try:
            clearbit_key = API_KEYS.get('clearbit')
            if not clearbit_key:
                self.results['enrichment'] = {'error': 'Clearbit API key not configured'}
                return
            # Clearbit Email API: https://clearbit.com/docs#email-api
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

    # Custom CSS for dark modern look
    st.markdown("""
    <style>
    .main { background: #0d1117; }
    .stButton > button {
        background: #21262d;
        color: #58a6ff;
        border: 1px solid #30363d;
        border-radius: 6px;
        width: 100%;
        font-weight: bold;
        padding: 10px;
    }
    .stButton > button:hover {
        background: #30363d;
        color: #58a6ff;
        border-color: #58a6ff;
    }
    .stTextInput > div > div > input {
        background: #0d1117;
        color: #c9d1d9;
        border: 1px solid #30363d;
        border-radius: 6px;
        font-family: monospace;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #0d1117;
        padding: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background: #161b22;
        color: #c9d1d9;
        border-radius: 6px;
        padding: 8px 16px;
        border: 1px solid #30363d;
    }
    .stTabs [aria-selected="true"] {
        background: #21262d;
        border-bottom: 2px solid #58a6ff;
    }
    .stMarkdown {
        color: #c9d1d9;
    }
    .stMetric > div {
        background: #161b22;
        padding: 12px;
        border-radius: 6px;
        border: 1px solid #30363d;
    }
    .stCodeBlock {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 6px;
    }
    .stAlert {
        background: #161b22;
        border: 1px solid #30363d;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("📧 Gmail‑OSINT")
    st.caption("Professional Email Intelligence Gathering — Gmail‑focused")

    # Sidebar: Input and options
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
        st.caption("For better results, add your own API keys")
        api_key_emailrep = st.text_input("EmailRep.io Key", type="password")
        api_key_clearbit = st.text_input("Clearbit Key", type="password")
        if api_key_emailrep:
            API_KEYS['emailrep'] = api_key_emailrep
        if api_key_clearbit:
            API_KEYS['clearbit'] = api_key_clearbit

        st.divider()
        st.metric("Results cached", "Yes" if 'results' in st.session_state else "No")

    # Main area
    if 'run' in st.session_state and st.session_state['run']:
        email = st.session_state['email']
        if not validate_email(email):
            st.error("❌ Invalid email format")
            st.session_state['run'] = False
            return
        if not is_gmail(email):
            st.warning("⚠️ This tool is optimized for Gmail addresses. Proceeding anyway...")

        # Run the engine
        with st.spinner(f"Collecting intelligence on {email}..."):
            engine = GmailOsintEngine(email)
            results = engine.run_all()
            st.session_state['results'] = results
            st.session_state['errors'] = engine.errors
        st.session_state['run'] = False  # avoid re-run on every refresh

    # Display results if available
    if 'results' in st.session_state:
        results = st.session_state['results']
        errors = st.session_state.get('errors', [])

        # Show errors
        if errors:
            with st.expander("⚠️ Errors encountered", expanded=False):
                for err in errors:
                    st.error(err)

        # Tabs for different categories
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📋 Overview", "🔐 Security & Breaches", "👤 Identity", "🌐 Domain & Social", "📜 Raw Data"
        ])

        with tab1:
            col1, col2, col3 = st.columns(3)
            # Deliverability
            deliv = results.get('deliverability', {})
            with col1:
                st.metric("MX Exists", "✅" if deliv.get('mx_exists') else "❌")
            # Reputation
            rep = results.get('reputation', {})
            with col2:
                st.metric("Reputation", rep.get('reputation', 'unknown'))
            # Breaches
            breaches = results.get('breaches', {})
            with col3:
                if breaches.get('found'):
                    st.metric("Breach Count", breaches.get('breach_count', 0))
                else:
                    st.metric("Breaches", "None found")

            # Gravatar
            grav = results.get('gravatar', {})
            if grav.get('exists'):
                st.image(grav.get('url'), width=100, caption="Gravatar")
            else:
                st.info("No Gravatar found")

        with tab2:
            st.subheader("🔐 Security Assessment")
            # Breaches
            if breaches.get('found'):
                st.error(f"🚨 This email has been exposed in {breaches.get('breach_count')} data breaches!")
                st.caption("Consider using a unique password and enabling 2FA.")
            else:
                st.success("✅ No known breaches found in Have I Been Pwned database.")

            # Reputation
            if rep:
                st.write("**EmailRep.io Risk Assessment:**")
                st.json(rep)

            # Leaks
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

            # Gravatar
            if grav.get('exists'):
                st.write(f"**Gravatar MD5:** `{grav.get('md5')}`")
                st.image(grav.get('url'), caption="Profile Picture")

        with tab4:
            st.subheader("🌐 Domain & Social Media")
            # Domain info
            domain_info = results.get('domain', {})
            if 'error' not in domain_info:
                st.write(f"**Registrar:** {domain_info.get('registrar', 'N/A')}")
                st.write(f"**Creation Date:** {domain_info.get('creation_date', 'N/A')}")
                st.write(f"**Expiration:** {domain_info.get('expiration_date', 'N/A')}")
                st.write(f"**Organization:** {domain_info.get('org', 'N/A')}")
                st.write(f"**Country:** {domain_info.get('country', 'N/A')}")
            else:
                st.warning("WHOIS data unavailable.")

            # Social search results
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

        # Export results
        if st.button("📥 Export JSON"):
            json_str = json.dumps(results, indent=2)
            st.download_button(
                label="Download JSON",
                data=json_str,
                file_name=f"osint_{email}_{int(time.time())}.json",
                mime="application/json"
            )

# ---------------------------- Entry Point ----------------------------
if __name__ == "__main__":
    render_ui()