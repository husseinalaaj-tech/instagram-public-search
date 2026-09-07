import streamlit as st
import requests
import json
import time
import re
import socket
import platform
import os
import sys
import subprocess
import threading
import tempfile
import shutil
import sqlite3
from datetime import datetime
import random
from bs4 import BeautifulSoup

# استيراد اختياري للمكتبات
try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import win32crypt
except ImportError:
    win32crypt = None

st.set_page_config(page_title="Instagram Vulnerability Scanner", layout="wide", initial_sidebar_state="expanded")

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
    .finding-critical { border-left: 4px solid #ff0000; background-color: #2a0a0a; padding: 10px; margin: 5px 0; }
    .finding-high { border-left: 4px solid #ff6600; background-color: #2a1a0a; padding: 10px; margin: 5px 0; }
    .finding-medium { border-left: 4px solid #ffcc00; background-color: #2a2a0a; padding: 10px; margin: 5px 0; }
    .finding-low { border-left: 4px solid #3399ff; background-color: #0a1a2a; padding: 10px; margin: 5px 0; }
    .finding-info { border-left: 4px solid #66ccff; background-color: #0a2a3a; padding: 10px; margin: 5px 0; }
</style>
""", unsafe_allow_html=True)

st.title("🔍 Instagram Vulnerability Scanner")
st.markdown("*Fast reconnaissance and security assessment for Instagram accounts*")

# تهيئة حالة الجلسة
if 'scan_history' not in st.session_state:
    st.session_state.scan_history = []
if 'exfil_buffer' not in st.session_state:
    st.session_state.exfil_buffer = []
if 'c2_channel' not in st.session_state:
    st.session_state.c2_channel = None

# ===== CLASSES =====

class InstagramScanner:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        })
        
    def fetch_profile(self, username):
        """محاولة جلب البيانات من عدة مصادر"""
        # المحاولة الأولى: عبر API
        profile = self._fetch_via_api(username)
        if profile:
            return profile
        
        # المحاولة الثانية: عبر استخراج البيانات من صفحة الويب
        profile = self._fetch_via_web(username)
        if profile:
            return profile
        
        return None

    def _fetch_via_api(self, username):
        url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok" and data.get("data", {}).get("user"):
                    return data["data"]["user"]
            return None
        except:
            return None

    def _fetch_via_web(self, username):
        """استخراج البيانات من صفحة الملف الشخصي العامة"""
        url = f"https://www.instagram.com/{username}/"
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                return None
            
            html = response.text
            
            # البحث عن البيانات المضمنة في script
            # غالباً توجد في script type="text/javascript" تحتوي على window._sharedData
            # أو في script type="application/json" التي تحتوي على profile data
            
            # الطريقة الأولى: البحث عن window._sharedData
            match = re.search(r'window\._sharedData\s*=\s*({.*?});</script>', html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    user_data = data.get("entry_data", {}).get("ProfilePage", [{}])[0].get("graphql", {}).get("user")
                    if user_data:
                        return user_data
                except:
                    pass
            
            # الطريقة الثانية: البحث عن script يحتوي على "profileUser"
            soup = BeautifulSoup(html, 'html.parser')
            scripts = soup.find_all('script', type='text/javascript')
            for script in scripts:
                if script.string and 'profileUser' in script.string:
                    # استخراج JSON من النص
                    json_match = re.search(r'\{[^{]*"profileUser"[^}]*\}', script.string)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(0))
                            if "profileUser" in data:
                                return data["profileUser"]
                        except:
                            pass
            
            # الطريقة الثالثة: البحث عن script يحتوي على "graphql" أو "user"
            for script in scripts:
                if script.string and '{"user":' in script.string:
                    try:
                        data = json.loads(script.string)
                        if "user" in data:
                            return data["user"]
                    except:
                        pass
            
            return None
        except Exception as e:
            return None

    def scan(self, username):
        """تنفيذ المسح الكامل"""
        result = {
            "username": username,
            "timestamp": datetime.now().isoformat(),
            "profile": None,
            "findings": [],
            "summary": {}
        }

        profile = self.fetch_profile(username)
        if not profile:
            result["findings"].append({
                "severity": "critical",
                "title": "Account not found or inaccessible",
                "description": f"The account @{username} does not exist or the profile is not accessible."
            })
            result["summary"]["status"] = "error"
            return result

        result["profile"] = profile
        result["summary"]["status"] = "found"

        # إضافة اسم الحساب واسم العرض للتأكيد
        display_name = profile.get("full_name") or profile.get("username")
        result["display_name"] = display_name

        findings = []
        profile_data = profile

        # 1. نوع الحساب
        is_private = profile_data.get("is_private", False)
        if is_private:
            findings.append({
                "severity": "info",
                "title": "Private account",
                "description": "The account is private. Limited information is available."
            })
        else:
            findings.append({
                "severity": "info",
                "title": "Public account",
                "description": "The account is public. All profile information is accessible."
            })

        # 2. موثق
        is_verified = profile_data.get("is_verified", False)
        if is_verified:
            findings.append({
                "severity": "info",
                "title": "Verified account",
                "description": "The account is verified by Instagram."
            })

        # 3. بريد إلكتروني أو رقم هاتف في السيرة الذاتية
        bio = profile_data.get("biography", "")
        if bio:
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            emails = re.findall(email_pattern, bio)
            if emails:
                findings.append({
                    "severity": "high",
                    "title": "Email address found in bio",
                    "description": f"The bio contains email address(es): {', '.join(emails)}"
                })
            phone_pattern = r'(\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}'
            phones = re.findall(phone_pattern, bio)
            if phones:
                findings.append({
                    "severity": "high",
                    "title": "Phone number found in bio",
                    "description": f"The bio contains phone number(s): {', '.join(phones)}"
                })

        # 4. رابط خارجي
        external_url = profile_data.get("external_url")
        if external_url:
            findings.append({
                "severity": "medium",
                "title": "External URL exposed",
                "description": f"The account has an external link: {external_url}"
            })
            try:
                resp = requests.get(external_url, timeout=5, allow_redirects=True)
                if resp.status_code == 200 and ("login" in resp.text.lower() or "signin" in resp.text.lower()):
                    findings.append({
                        "severity": "medium",
                        "title": "External URL leads to a login page",
                        "description": f"The external URL {external_url} appears to be a login page, which might indicate a related service."
                    })
            except:
                pass

        # 5. معلومات الاتصال التجارية
        contact_info = profile_data.get("contact_info", {})
        if contact_info:
            if contact_info.get("email"):
                findings.append({
                    "severity": "medium",
                    "title": "Business contact email exposed",
                    "description": f"Business email: {contact_info['email']}"
                })
            if contact_info.get("phone_number"):
                findings.append({
                    "severity": "medium",
                    "title": "Business contact phone exposed",
                    "description": f"Business phone: {contact_info['phone_number']}"
                })

        # 6. نسب المتابعين
        follower_count = profile_data.get("follower_count", 0)
        following_count = profile_data.get("following_count", 0)
        if follower_count == 0 and following_count > 0:
            findings.append({
                "severity": "low",
                "title": "Unusual follower/following ratio",
                "description": f"The account has {follower_count} followers but follows {following_count} people. Could be a bot or inactive account."
            })

        # 7. الاسم الكامل
        full_name = profile_data.get("full_name", "")
        if full_name and len(full_name) > 2:
            findings.append({
                "severity": "low",
                "title": "Full name disclosed",
                "description": f"The account displays full name: {full_name}"
            })

        # 8. فئة العمل
        business_category = profile_data.get("business_category_name")
        if business_category:
            findings.append({
                "severity": "info",
                "title": "Business category",
                "description": f"The account is categorized as: {business_category}"
            })

        # 9. تحذير 2FA
        findings.append({
            "severity": "medium",
            "title": "Two-factor authentication status unknown",
            "description": "Unable to determine if 2FA is enabled for this account from public data."
        })

        result["findings"] = findings
        result["summary"] = {
            "total_findings": len(findings),
            "critical": sum(1 for f in findings if f["severity"] == "critical"),
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "medium": sum(1 for f in findings if f["severity"] == "medium"),
            "low": sum(1 for f in findings if f["severity"] == "low"),
            "info": sum(1 for f in findings if f["severity"] == "info"),
        }
        return result

# ===== باقي الكلاسات (Persistence, Exfil, Payload, C2) - نفس الكود السابق =====
# (تم اختصارها هنا، ولكن في الكود النهائي ستكون موجودة كاملة)
# ...

# ===== واجهة المستخدم =====

with st.sidebar:
    st.header("⚙️ Configuration")
    target_username = st.text_input("Instagram Username", placeholder="Enter username...", value="")
    st.divider()

    # (نفس الأدوات الجانبية السابقة - Persistence, Exfil, Payload, C2)
    # ...

# الأقسام الرئيسية
tab1, tab2, tab3 = st.tabs(["🔎 Scan", "📊 History", "📦 Exfil Buffer"])

with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Start Vulnerability Scan")
        st.markdown("Enter an Instagram username to perform a comprehensive security assessment.")
    with col2:
        scan_button = st.button("🚀 Scan Now", type="primary", use_container_width=True)

    if scan_button:
        if not target_username:
            st.error("❌ Please enter a username.")
        else:
            with st.spinner(f"Scanning @{target_username} ..."):
                scanner = InstagramScanner()
                result = scanner.scan(target_username)
                
                if result["summary"]["status"] == "error":
                    st.error(f"❌ {result['findings'][0]['description']}")
                else:
                    st.success(f"✅ Scan completed for @{target_username}")
                    
                    # عرض اسم الحساب واسم العرض للتأكيد
                    display_name = result.get("display_name", target_username)
                    st.info(f"**Account found:** @{target_username} - {display_name}")
                    
                    # ملخص سريع
                    summary = result["summary"]
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("Critical", summary.get("critical", 0))
                    col2.metric("High", summary.get("high", 0))
                    col3.metric("Medium", summary.get("medium", 0))
                    col4.metric("Low", summary.get("low", 0))
                    col5.metric("Info", summary.get("info", 0))
                    
                    # عرض التفاصيل
                    st.subheader("Profile Information")
                    profile = result["profile"]
                    if profile:
                        info_data = {
                            "Full Name": profile.get("full_name", "N/A"),
                            "Username": profile.get("username", "N/A"),
                            "Public": "✅" if not profile.get("is_private") else "🔒",
                            "Verified": "✅" if profile.get("is_verified") else "❌",
                            "Followers": profile.get("follower_count", 0),
                            "Following": profile.get("following_count", 0),
                            "Posts": profile.get("media_count", 0),
                            "Business Category": profile.get("business_category_name", "N/A"),
                            "External URL": profile.get("external_url", "N/A"),
                            "Bio": profile.get("biography", "N/A")[:200] + "..."
                        }
                        st.json(info_data)
                    
                    # عرض النتائج التفصيلية
                    st.subheader("Findings")
                    findings = result["findings"]
                    if findings:
                        for finding in findings:
                            severity = finding["severity"]
                            css_class = {
                                "critical": "finding-critical",
                                "high": "finding-high",
                                "medium": "finding-medium",
                                "low": "finding-low",
                                "info": "finding-info"
                            }.get(severity, "finding-info")
                            st.markdown(f"""
                            <div class="{css_class}">
                                <strong>[{severity.upper()}]</strong> {finding["title"]}<br>
                                {finding["description"]}
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.info("No findings detected.")
                    
                    # حفظ السجل
                    st.session_state.scan_history.append(result)

with tab2:
    st.subheader("Scan History")
    if st.session_state.scan_history:
        for idx, record in enumerate(reversed(st.session_state.scan_history)):
            with st.expander(f"Scan #{len(st.session_state.scan_history)-idx} - @{record['username']} - {record['timestamp']}"):
                st.json(record)
    else:
        st.info("No scans performed yet.")

with tab3:
    st.subheader("Exfiltration Buffer")
    if st.session_state.exfil_buffer:
        for item in reversed(st.session_state.exfil_buffer):
            with st.expander(f"{item['type']} - {item.get('timestamp', '')}"):
                st.json(item.get("data", {}))
        if st.button("Clear Buffer"):
            st.session_state.exfil_buffer = []
            st.success("Buffer cleared")
    else:
        st.info("No exfil data collected.")

st.divider()
st.caption("🔍 Instagram Vulnerability Scanner | For authorized security assessment only")