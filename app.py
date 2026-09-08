import streamlit as st
import time
import random
import threading
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import os

# ===== إعداد الصفحة =====
st.set_page_config(page_title="Instagram Mass Reporter", layout="wide")
st.title("📢 Instagram Mass Reporter")
st.markdown("أرسل بلاغات مكثفة لحساب إنستغرام حتى يتم تعليقه.")

# ===== تهيئة Session State =====
if "running" not in st.session_state:
    st.session_state.running = False
if "reports_sent" not in st.session_state:
    st.session_state.reports_sent = 0
if "reports_success" not in st.session_state:
    st.session_state.reports_success = 0
if "reports_fail" not in st.session_state:
    st.session_state.reports_fail = 0
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "total_reports_planned" not in st.session_state:
    st.session_state.total_reports_planned = 0
if "current_account_index" not in st.session_state:
    st.session_state.current_account_index = 0
if "current_report_index" not in st.session_state:
    st.session_state.current_report_index = 0
if "accounts_list" not in st.session_state:
    st.session_state.accounts_list = []
if "proxies_list" not in st.session_state:
    st.session_state.proxies_list = []
if "target_username" not in st.session_state:
    st.session_state.target_username = ""
if "report_type" not in st.session_state:
    st.session_state.report_type = "spam"
if "reports_per_account" not in st.session_state:
    st.session_state.reports_per_account = 10
if "delay_min" not in st.session_state:
    st.session_state.delay_min = 5
if "delay_max" not in st.session_state:
    st.session_state.delay_max = 15
if "use_proxies" not in st.session_state:
    st.session_state.use_proxies = False
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "driver" not in st.session_state:
    st.session_state.driver = None

# ===== دوال الإبلاغ =====
def get_driver(proxy=None):
    options = Options()
    options.add_argument("--headless")  # علق هذا السطر إذا أردت رؤية المتصفح
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    if proxy and st.session_state.use_proxies:
        options.add_argument(f'--proxy-server={proxy}')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def login(driver, username, password):
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(random.uniform(2, 4))
    try:
        username_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        username_field.send_keys(username)
        password_field = driver.find_element(By.NAME, "password")
        password_field.send_keys(password)
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        time.sleep(random.uniform(3, 6))
        try:
            not_now = driver.find_element(By.XPATH, "//button[contains(text(), 'Not Now')]")
            not_now.click()
            time.sleep(1)
        except:
            pass
        return True
    except Exception:
        return False

def report_user(driver, target, report_type):
    driver.get(f"https://www.instagram.com/{target}/")
    time.sleep(random.uniform(2, 4))
    try:
        dots = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@role, 'button') and @aria-label='More options']"))
        )
        dots.click()
        time.sleep(1)
        report_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Report')]"))
        )
        report_btn.click()
        time.sleep(1)
        # اختيار نوع البلاغ
        type_map = {
            "spam": "Spam",
            "impersonation": "Impersonation",
            "inappropriate": "Inappropriate",
            "bullying": "Bullying"
        }
        type_text = type_map.get(report_type, "Spam")
        type_btn = driver.find_element(By.XPATH, f"//span[contains(text(), '{type_text}')]")
        type_btn.click()
        time.sleep(1)
        submit = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Submit')]"))
        )
        submit.click()
        time.sleep(2)
        try:
            close = driver.find_element(By.XPATH, "//button[contains(text(), 'Done')]")
            close.click()
        except:
            pass
        return True
    except Exception:
        return False

def do_next_report():
    """تنفيذ بلاغ واحد من قائمة الانتظار، وتحديث الحالة"""
    if st.session_state.stop_requested:
        st.session_state.running = False
        st.session_state.stop_requested = False
        return

    accounts = st.session_state.accounts_list
    if st.session_state.current_account_index >= len(accounts):
        st.session_state.running = False
        return

    acc = accounts[st.session_state.current_account_index]
    proxy = None
    if st.session_state.use_proxies and st.session_state.proxies_list:
        proxy = st.session_state.proxies_list[st.session_state.current_account_index % len(st.session_state.proxies_list)]

    # إنشاء متصفح جديد لكل حساب (يمكن تحسينه بإعادة استخدام، لكنه أسهل)
    driver = get_driver(proxy)
    try:
        if login(driver, acc["username"], acc["password"]):
            success = report_user(driver, st.session_state.target_username, st.session_state.report_type)
            st.session_state.reports_sent += 1
            if success:
                st.session_state.reports_success += 1
            else:
                st.session_state.reports_fail += 1
        else:
            st.session_state.reports_fail += 1
    except Exception as e:
        st.session_state.reports_fail += 1
    finally:
        driver.quit()

    # التقدم للحساب التالي أو البلاغ التالي
    st.session_state.current_report_index += 1
    if st.session_state.current_report_index >= st.session_state.reports_per_account:
        st.session_state.current_account_index += 1
        st.session_state.current_report_index = 0

    # التحقق من انتهاء المهمة
    if st.session_state.current_account_index >= len(accounts):
        st.session_state.running = False

    # تأخير عشوائي
    delay = random.uniform(st.session_state.delay_min, st.session_state.delay_max)
    time.sleep(delay)

    # إعادة تشغيل التطبيق لتحديث الواجهة
    st.rerun()

# ===== واجهة المستخدم =====
with st.sidebar:
    st.header("⚙️ الإعدادات")
    target = st.text_input("👤 اسم الضحية (Target)", value=st.session_state.target_username)
    st.session_state.target_username = target

    report_type = st.selectbox("📋 نوع البلاغ", ["spam", "impersonation", "inappropriate", "bullying"], index=0)
    st.session_state.report_type = report_type

    reports_per = st.number_input("🔢 عدد البلاغات لكل حساب", min_value=1, max_value=100, value=st.session_state.reports_per_account, step=1)
    st.session_state.reports_per_account = reports_per

    col1, col2 = st.columns(2)
    with col1:
        delay_min = st.number_input("⏱️ أقل تأخير (ث)", min_value=1, max_value=60, value=st.session_state.delay_min, step=1)
        st.session_state.delay_min = delay_min
    with col2:
        delay_max = st.number_input("⏱️ أقصى تأخير (ث)", min_value=2, max_value=120, value=st.session_state.delay_max, step=1)
        st.session_state.delay_max = delay_max

    use_proxy = st.checkbox("🌐 استخدام بروكسيات", value=st.session_state.use_proxies)
    st.session_state.use_proxies = use_proxy

    accounts_text = st.text_area("👥 حسابات (username:password كل سطر)", height=150)
    proxies_text = st.text_area("🌍 بروكسيات (http://ip:port كل سطر)", height=100)

    # تحديث القوائم
    if accounts_text:
        new_accounts = []
        for line in accounts_text.strip().splitlines():
            if ":" in line:
                parts = line.split(":", 1)
                new_accounts.append({"username": parts[0].strip(), "password": parts[1].strip()})
        st.session_state.accounts_list = new_accounts
    else:
        st.session_state.accounts_list = []

    if proxies_text:
        new_proxies = [p.strip() for p in proxies_text.strip().splitlines() if p.strip()]
        st.session_state.proxies_list = new_proxies
    else:
        st.session_state.proxies_list = []

    # أزرار التحكم
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🚀 بدء الإبلاغ", type="primary", disabled=st.session_state.running):
            # تحقق من وجود حسابات وهدف
            if not st.session_state.accounts_list:
                st.error("⚠️ يجب إدخال حسابات على الأقل.")
            elif not st.session_state.target_username:
                st.error("⚠️ يجب إدخال اسم الضحية.")
            else:
                # إعادة تعيين العدادات
                st.session_state.running = True
                st.session_state.stop_requested = False
                st.session_state.reports_sent = 0
                st.session_state.reports_success = 0
                st.session_state.reports_fail = 0
                st.session_state.current_account_index = 0
                st.session_state.current_report_index = 0
                st.session_state.start_time = time.time()
                st.session_state.total_reports_planned = len(st.session_state.accounts_list) * st.session_state.reports_per_account
                st.rerun()
    with col_btn2:
        if st.button("⏹️ إيقاف", disabled=not st.session_state.running):
            st.session_state.stop_requested = True
            st.session_state.running = False
            st.rerun()

# ===== عرض الإحصائيات =====
if st.session_state.running:
    placeholder = st.empty()
    with placeholder.container():
        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
        total_planned = st.session_state.total_reports_planned
        sent = st.session_state.reports_sent
        success = st.session_state.reports_success
        fail = st.session_state.reports_fail

        # حساب السرعة
        elapsed = time.time() - st.session_state.start_time if st.session_state.start_time else 0.001
        speed = sent / elapsed if elapsed > 0 else 0

        col_stats1.metric("📤 أُرسل", sent, f"{speed:.2f} بلاغ/ث")
        col_stats2.metric("✅ نجح", success)
        col_stats3.metric("❌ فشل", fail)
        col_stats4.metric("📊 متبقٍ", max(0, total_planned - sent))

        progress = sent / total_planned if total_planned > 0 else 0
        st.progress(progress, text=f"التقدم: {int(progress*100)}%")

    # تنفيذ البلاغ التالي (يتم استدعاؤه بعد كل تحديث)
    do_next_report()

else:
    # عرض الحالة النهائية إذا انتهى
    if st.session_state.reports_sent > 0:
        st.success("✅ انتهت الحملة.")
        col1, col2, col3 = st.columns(3)
        col1.metric("إجمالي", st.session_state.reports_sent)
        col2.metric("نجح", st.session_state.reports_success)
        col3.metric("فشل", st.session_state.reports_fail)
        elapsed = time.time() - st.session_state.start_time if st.session_state.start_time else 0
        st.info(f"الوقت المستغرق: {elapsed:.2f} ثانية")

# ===== قسم فحص الثغرات =====
with st.expander("🔍 فحص ثغرات نظام البلاغات"):
    if st.button("تشغيل الفحص"):
        st.info("جارٍ فحص الثغرات... (محاكاة)")
        # يمكن إضافة اختبارات فعلية هنا (مثل تجربة أنواع بلاغات مختلفة)
        time.sleep(2)
        st.write("✅ تم الفحص. النتائج:")
        st.json({
            "نوع البلاغ الأكثر فعالية": "impersonation",
            "إمكانية الإبلاغ بدون تأكيد البريد": "نعم",
            "عدد البلاغات المطلوبة للتبند": "غير محدد (يعتمد على عوامل أخرى)"
        })

st.caption("ملاحظة: يتطلب تثبيت Chrome و Chromedriver (يتم تنزيله تلقائياً). استخدم حسابات وبروكسيات حقيقية لزيادة الفعالية.")