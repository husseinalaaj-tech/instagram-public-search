import streamlit as st

st.set_page_config(
    page_title="Instagram Public Search",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 Instagram Public Search")
st.write("أدخل Instagram Username للبدء.")

username = st.text_input(
    "Instagram Username",
    placeholder="مثال: rrenguk"
)

if st.button("🚀 Start Search"):

    if username.strip():
        st.success(f"Username المدخل: @{username.strip()}")
    else:
        st.warning("يرجى إدخال Username أولاً.")
        Create Streamlit app