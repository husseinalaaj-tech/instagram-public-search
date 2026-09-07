import streamlit as st
import itertools

st.set_page_config(page_title="Targeted Intelligence Wordlist Generator", layout="centered")

st.title("🎯 OSINT Targeted Wordlist Generator")
st.write("Streamlit execution interface for high-precision intelligence permutation.")

# Sidebar / Input Configuration
st.sidebar.header("Target Configuration Seeds")
f_input = st.sidebar.text_input("First Names (comma separated)", value="adian, adyan")
l_input = st.sidebar.text_input("Last Names (comma separated)", value="alboherb, alborebh")
d_input = st.sidebar.text_input("Dates / Years (comma separated)", value="24, 02, 2006, 06, 2402, 24022006, 240206, feb24, 24feb")
sep_input = st.sidebar.text_input("Separators (comma separated, use space for empty)", value=" ,.,_,-")

if st.button("Generate Wordlist Matrix"):
    first_names = [x.strip() for x in f_input.split(",")]
    last_names = [x.strip() for x in l_input.split(",")]
    dates = [x.strip() for x in d_input.split(",")]
    separators = [s if s != " " else "" for s in sep_input.split(",")]

    wordlist = set()
    
    # Base combinations
    for f in first_names:
        for l in last_names:
            for sep in separators:
                wordlist.add(f"{f}{sep}{l}")
                wordlist.add(f"{l}{sep}{f}")
                if l: wordlist.add(f"{f}{sep}{l[0]}")
                if f: wordlist.add(f"{f[0]}{sep}{l}")
                
    base_bases = list(wordlist) + first_names + last_names + ["adian.alborebh", "adian_alborebh"]
    
    # Add birthdate permutations
    for base in base_bases:
        for d in dates:
            for sep in separators:
                wordlist.add(f"{base}{sep}{d}")
                wordlist.add(f"{d}{sep}{base}")

    # Capitalization variations
    final_passwords = set()
    for pwd in wordlist:
        if not pwd: continue
        final_passwords.add(pwd.lower())
        final_passwords.add(pwd.capitalize())
        final_passwords.add(pwd.upper())
        for sep in ['.', '_', '-']:
            if sep in pwd:
                parts = pwd.split(sep)
                final_passwords.add(sep.join([p.capitalize() for p in parts]))

    sorted_list = sorted(list(final_passwords))
    
    st.success(f"[+] Compiled successfully! Total unique permutations: {len(sorted_list)}")
    
    # Live preview container
    st.text_area("Wordlist Preview (First 100 entries)", "\n".join(sorted_list[:100]), height=200)
    
    # Direct file download payload
    wordlist_text = "\n".join(sorted_list)
    st.download_button(
        label="📥 Download Complete Wordlist (.txt)",
        data=wordlist_text,
        file_name="adian_target_wordlist.txt",
        mime="text/plain"
    )
