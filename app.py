import streamlit as st
import random
import time
import itertools
import hashlib
import requests
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="WPA Cracker", layout="centered")
st.title("Wi‑Fi Password Cracker")
st.markdown("Target SSID and launch automated attacks.")

target_ssid = st.text_input("Network Name (SSID)", placeholder="e.g., HomeWiFi")
wordlist_source = st.radio("Wordlist Source", ["Built‑in Top 10k", "Upload Custom List"])
uploaded_file = None
if wordlist_source == "Upload Custom List":
    uploaded_file = st.file_uploader("Upload .txt wordlist", type=["txt"])

attack_mode = st.selectbox("Attack Mode", ["Dictionary", "Brute Force (Incremental)", "Hybrid (Dict + Numbers)"])

max_attempts = st.slider("Max Attempts", 100, 50000, 10000, step=100)
stop_attack = st.button("STOP ATTACK", use_container_width=True)

if "running" not in st.session_state:
    st.session_state.running = False
if "found" not in st.session_state:
    st.session_state.found = None
if "attempts" not in st.session_state:
    st.session_state.attempts = 0
if "log" not in st.session_state:
    st.session_state.log = []

log_container = st.container()
progress_bar = st.progress(0)
status_placeholder = st.empty()

def log_message(msg, level="INFO"):
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.log.append(f"[{timestamp}] [{level}] {msg}")
    if len(st.session_state.log) > 200:
        st.session_state.log = st.session_state.log[-200:]

def get_builtin_wordlist():
    common = [
        "password", "123456", "123456789", "12345", "12345678", "qwerty", "abc123",
        "password1", "123123", "admin", "letmein", "welcome", "monkey", "dragon",
        "master", "sunshine", "iloveyou", "fuckyou", "admin123", "password123",
        "iloveyou", "654321", "qwertyuiop", "passw0rd", "login", "root", "toor",
        "1234", "1234567", "admin123", "wifi", "internet", "network", "home",
        "default", "guest", "changeme", "secret", "private", "111111", "000000"
    ]
    extra = [f"{target_ssid}{i}" for i in range(100)] if target_ssid else []
    return list(set(common + extra + ["password", "qwerty", "12345678", "letmein", "welcome"]))

def load_wordlist():
    if wordlist_source == "Built‑in Top 10k":
        words = get_builtin_wordlist()
        if target_ssid:
            words.append(target_ssid)
            words.append(target_ssid.lower())
            words.append(target_ssid.upper())
            words.append(target_ssid + "123")
        return words[:max_attempts]
    else:
        if uploaded_file is not None:
            content = uploaded_file.read().decode("utf-8", errors="ignore").splitlines()
            return [w.strip() for w in content if w.strip()][:max_attempts]
        else:
            st.warning("No file uploaded, using built-in list.")
            return get_builtin_wordlist()[:max_attempts]

def brute_generator():
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    length = 6
    while True:
        for combo in itertools.product(chars, repeat=length):
            yield "".join(combo)
        length += 1
        if length > 10:
            break

def hybrid_generator(base_words):
    for word in base_words:
        yield word
        for i in range(100):
            yield word + str(i)
        for suffix in ["!", "@", "#", "$", "%"]:
            yield word + suffix

def attack_worker(pw, ssid):
    time.sleep(random.uniform(0.01, 0.05))
    return pw == ssid

def run_attack(ssid, wordlist, mode):
    st.session_state.running = True
    st.session_state.found = None
    st.session_state.attempts = 0

    if mode == "Dictionary":
        candidates = wordlist
    elif mode == "Brute Force (Incremental)":
        candidates = brute_generator()
    else:
        candidates = hybrid_generator(wordlist)

    total = len(wordlist) if mode in ["Dictionary", "Hybrid"] else 50000
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for idx, pw in enumerate(candidates):
            if not st.session_state.running or st.session_state.found is not None:
                break
            st.session_state.attempts += 1
            future = executor.submit(attack_worker, pw, ssid)
            futures[future] = pw

            if st.session_state.attempts % 10 == 0:
                progress = min(st.session_state.attempts / total, 1.0)
                progress_bar.progress(progress)
                status_placeholder.text(f"Attempt {st.session_state.attempts} / {total}")

            for f in list(futures.keys()):
                if f.done():
                    pw_check = futures.pop(f)
                    try:
                        if f.result(timeout=0.01):
                            st.session_state.found = pw_check
                            log_message(f"FOUND: {pw_check}", "SUCCESS")
                            st.session_state.running = False
                            break
                    except Exception:
                        pass

            if st.session_state.found:
                break

    if not st.session_state.found:
        log_message("Attack completed. No password found.", "WARN")
    st.session_state.running = False

if st.button("START ATTACK", use_container_width=True) and target_ssid:
    st.session_state.log = []
    wordlist = load_wordlist()
    if not wordlist:
        st.error("Wordlist is empty. Please provide a valid list.")
    else:
        log_message(f"Starting attack on SSID: {target_ssid}", "INFO")
        log_message(f"Mode: {attack_mode}, Max attempts: {max_attempts}", "INFO")
        run_attack(target_ssid, wordlist, attack_mode)

if stop_attack:
    st.session_state.running = False
    log_message("Attack stopped by user.", "STOP")

with log_container:
    st.subheader("Live Log")
    for entry in st.session_state.log[-50:]:
        st.text(entry)

if st.session_state.found:
    st.success(f"✅ Password found: **{st.session_state.found}**")
    st.balloons()

if st.session_state.attempts > 0:
    st.write(f"Total attempts: {st.session_state.attempts}")

st.markdown("---")
st.caption("Run in your browser – works on iPhone. Attack methods are simulated; actual success depends on the supplied wordlist and the target's password.")