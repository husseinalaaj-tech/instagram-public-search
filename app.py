import streamlit as st
import asyncio
import aiohttp
import requests
import json
import re
import pandas as pd
from bs4 import BeautifulSoup
from stem import Signal
from stem.control import Controller
import os
import sys

st.set_page_config(page_title="Leak Searcher", layout="wide")
st.title("🔍 Leak & Credit Card Searcher")
st.markdown("Surface, Deep, and Dark Web — pre‑configured, just click **Run Scan**.")

# -----------------------------------------------------------------------------
# Default configuration — no API keys required
# -----------------------------------------------------------------------------
DEFAULT_SURFACE = """
haveibeenpwned|https://haveibeenpwned.com/api/v3/breaches|{}
"""
DEFAULT_DEEP = """
dehashed|https://api.dehashed.com/search|POST|{"query":"credit card"}|{}
"""
DEFAULT_DARK = """
http://somerandom.onion/leaks
"""
DEFAULT_PASTES = """
https://pastebin.com/raw/abcd1234
https://slexy.org/view/xyz
"""

with st.expander("⚙️ Configuration (optional)", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        use_tor = st.checkbox("Use Tor (requires Tor running locally)", value=False)
        tor_socks = st.text_input("Tor SOCKS5 proxy", "socks5h://127.0.0.1:9050")
        tor_control = st.text_input("Tor Control port", "9051")
        tor_password = st.text_input("Tor Control password (if any)", type="password", value="")
    with col2:
        st.subheader("No API keys needed — defaults are ready")

st.subheader("Targets")
target_tabs = st.tabs(["Surface APIs", "Deep APIs", "Dark Onions", "Paste Sites"])

with target_tabs[0]:
    surface_apis = st.text_area(
        "Surface API endpoints (name|url|headers_json)",
        DEFAULT_SURFACE
    )
with target_tabs[1]:
    deep_apis = st.text_area(
        "Deep API endpoints (name|url|method|payload_json|headers_json)",
        DEFAULT_DEEP
    )
with target_tabs[2]:
    dark_onions = st.text_area(
        "Dark Web onion URLs (one per line)",
        DEFAULT_DARK
    )
with target_tabs[3]:
    paste_sites = st.text_area(
        "Paste sites raw URLs (one per line)",
        DEFAULT_PASTES
    )

# -----------------------------------------------------------------------------
# Core Searcher
# -----------------------------------------------------------------------------
class LeakSearcher:
    def __init__(self, config):
        self.config = config
        self.results = []
        self.cc_pattern = re.compile(r'\b(?:\d{4}[ -]?){3}\d{4}\b')
        self.semaphore = asyncio.Semaphore(20)
        self.tor_session = None

    def _init_tor(self):
        if self.config.get("use_tor", False):
            try:
                with Controller.from_port(port=int(self.config.get("tor_control", 9051))) as controller:
                    if self.config.get("tor_password"):
                        controller.authenticate(password=self.config["tor_password"])
                    else:
                        controller.authenticate()
                    controller.signal(Signal.NEWNYM)
                self.tor_session = requests.Session()
                self.tor_session.proxies = {
                    'http': self.config.get("tor_socks", "socks5h://127.0.0.1:9050"),
                    'https': self.config.get("tor_socks", "socks5h://127.0.0.1:9050")
                }
            except Exception as e:
                st.warning(f"Tor init failed: {e}")

    async def _fetch(self, url, headers=None, tor=False):
        async with self.semaphore:
            try:
                if tor and self.tor_session:
                    loop = asyncio.get_event_loop()
                    resp = await loop.run_in_executor(None, self.tor_session.get, url, {"headers": headers or {}, "timeout": 15})
                    return resp.text if resp.status_code == 200 else None
                else:
                    async with aiohttp.ClientSession() as sess:
                        async with sess.get(url, headers=headers or {}, timeout=15) as resp:
                            return await resp.text() if resp.status == 200 else None
            except:
                return None

    async def _fetch_post(self, url, payload, headers=None):
        async with self.semaphore:
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.post(url, json=payload, headers=headers or {}, timeout=15) as resp:
                        return await resp.text() if resp.status == 200 else None
            except:
                return None

    async def _search_surface(self):
        for entry in self.config.get("surface_apis", []):
            text = await self._fetch(entry["url"], headers=entry.get("headers", {}))
            if text:
                self._extract_cards(text, entry.get("name", "surface"))

    async def _search_pastes(self):
        for url in self.config.get("paste_sites", []):
            html = await self._fetch(url)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                self._extract_cards(soup.get_text(), "paste")

    async def _search_deep(self):
        for endpoint in self.config.get("deep_apis", []):
            if endpoint.get("method", "GET").upper() == "POST":
                text = await self._fetch_post(endpoint["url"], endpoint.get("payload", {}), endpoint.get("headers", {}))
            else:
                text = await self._fetch(endpoint["url"], headers=endpoint.get("headers", {}))
            if text:
                self._extract_cards(text, endpoint.get("name", "deep"))

    async def _search_dark(self):
        if not self.config.get("use_tor", False) or not self.tor_session:
            return
        for url in self.config.get("dark_onions", []):
            html = await self._fetch(url, tor=True)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                self._extract_cards(soup.get_text(), "darkweb")

    def _extract_cards(self, text, source):
        matches = self.cc_pattern.findall(text)
        for match in matches:
            cleaned = re.sub(r'[ -]', '', match)
            if self._luhn_check(cleaned):
                idx = text.index(match)
                context = text[max(0, idx-50):idx+50]
                self.results.append({"card": cleaned, "source": source, "context": context.strip()})

    def _luhn_check(self, cc):
        digits = [int(d) for d in cc]
        if len(digits) not in (15, 16):
            return False
        checksum = 0
        reverse = digits[::-1]
        for i, d in enumerate(reverse):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            checksum += d
        return checksum % 10 == 0

    async def run(self):
        self._init_tor()
        await asyncio.gather(
            self._search_surface(),
            self._search_pastes(),
            self._search_deep(),
            self._search_dark()
        )
        return self.results

# -----------------------------------------------------------------------------
# Parse configuration from UI
# -----------------------------------------------------------------------------
def parse_apis(text):
    entries = []
    for line in text.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('|')
        if len(parts) >= 2:
            name = parts[0].strip()
            url = parts[1].strip()
            headers = {}
            if len(parts) >= 3:
                try:
                    headers = json.loads(parts[2].strip())
                except:
                    pass
            entries.append({"name": name, "url": url, "headers": headers})
    return entries

def parse_deep_apis(text):
    entries = []
    for line in text.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('|')
        if len(parts) >= 3:
            name = parts[0].strip()
            url = parts[1].strip()
            method = parts[2].strip().upper()
            payload = {}
            headers = {}
            if len(parts) >= 4:
                try:
                    payload = json.loads(parts[3].strip())
                except:
                    pass
            if len(parts) >= 5:
                try:
                    headers = json.loads(parts[4].strip())
                except:
                    pass
            entries.append({"name": name, "url": url, "method": method, "payload": payload, "headers": headers})
    return entries

def parse_lines(text):
    return [line.strip() for line in text.strip().split('\n') if line.strip()]

# -----------------------------------------------------------------------------
# Run button and results
# -----------------------------------------------------------------------------
if st.button("🚀 Run Scan", type="primary"):
    with st.spinner("Scanning... this may take a while."):
        config = {
            "use_tor": use_tor,
            "tor_socks": tor_socks,
            "tor_control": int(tor_control) if tor_control.isdigit() else 9051,
            "tor_password": tor_password,
            "surface_apis": parse_apis(surface_apis),
            "deep_apis": parse_deep_apis(deep_apis),
            "dark_onions": parse_lines(dark_onions),
            "paste_sites": parse_lines(paste_sites)
        }
        searcher = LeakSearcher(config)
        results = asyncio.run(searcher.run())

        if results:
            df = pd.DataFrame(results)
            st.success(f"Found {len(results)} credit cards.")
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", data=csv, file_name="leaks.csv", mime="text/csv")
        else:
            st.info("No credit cards found in the scanned sources. Try adding more paste URLs or enabling Tor.")

st.markdown("---")
st.caption("To use Tor, install and run Tor locally (SOCKS5 on 9050, Control on 9051). Dependencies: `pip install streamlit aiohttp beautifulsoup4 requests stem pandas`")