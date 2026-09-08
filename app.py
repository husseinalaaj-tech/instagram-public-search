# python 3.10+, app.py, Streamlit Production Build with Robust Scraper
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib.parse
import time

st.set_page_config(page_title="Instagram OSINT Finder", layout="centered")

st.title("Instagram Comment & Mention Finder")
st.write("أدخل اسم المستخدم لاستخراج التعليقات، الإشارات، والريلز العامة عبر محركات البحث الآلية.")

username = st.text_input("Instagram Username:", "rrenguk")

def search_duckduckgo(query):
    urls = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        encoded_query = urllib.parse.quote(query)
        resp = requests.get(f"https://html.duckduckgo.com/html/?q={encoded_query}", headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', class_='result__url'):
                href = a.get('href')
                if href:
                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if 'uddg' in qs:
                        urls.append(qs['uddg'][0])
    except Exception:
        pass
    return list(set(urls))

if st.button("بدء البحث الشامل"):
    if username:
        with st.spinner("جاري جلب النتائج عبر محركات البحث الآمنة..."):
            queries = [
                f'site:instagram.com "@{username}"',
                f'site:instagram.com/reel/ "{username}"',
                f'site:instagram.com/p/ "{username}"',
                f'site:instagram.com "{username}" -inurl:instagram.com/{username}'
            ]
            
            results_list = []
            for query in queries:
                found_urls = search_duckduckgo(query)
                for url in found_urls:
                    results_list.append({"Query Type": query, "URL": url})
                time.sleep(1)
            
            if results_list:
                df = pd.DataFrame(results_list).drop_duplicates(subset=["URL"])
                st.success(f"[+] تم العثور على {len(df)} نتيجة فريدة بنجاح!")
                st.dataframe(df, use_container_width=True)
                
                csv_data = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="تحميل النتائج (CSV)",
                    data=csv_data,
                    file_name=f"{username}_osint_results.csv",
                    mime="text/csv"
                )
            else:
                st.warning("[-] لم يتم العثور على نتائج مطابقة لهذا اليوزر حالياً.")
    else:
        st.error("الرجاء إدخال اسم مستخدم صحيح أولاً.")
