# python 3.10+, app.py, Streamlit Production Build
import streamlit as st
import pandas as pd
from googlesearch import search

st.set_page_config(page_title="Instagram OSINT Finder", layout="centered")

st.title("Instagram Comment & Mention Finder")
st.write("أدخل اسم المستخدم لاستخراج التعليقات، الإشارات، والريلز العامة عبر محركات البحث الآلية.")

username = st.text_input("Instagram Username:", "rrenguk")

if st.button("بدء البحث الشامل"):
    if username:
        with st.spinner("جاري جلب النتائج من محركات البحث..."):
            queries = [
                f'site:instagram.com "@{username}"',
                f'site:instagram.com/reel/ "{username}"',
                f'site:instagram.com/p/ "{username}"',
                f'site:instagram.com "{username}" -inurl:instagram.com/{username}'
            ]
            
            results_list = []
            for query in queries:
                try:
                    for url in search(query, num_results=10):
                        results_list.append({"Query Type": query, "URL": url})
                except Exception as e:
                    st.error(f"خطأ في الاتصال: {e}")
            
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
