# ai_chat_ultra.py
import streamlit as st
import requests
import json
import sys
import traceback

# ---------------------------- Page Config ----------------------------
st.set_page_config(page_title="AI Chat Ultra", page_icon="🤖", layout="wide")

# ---------------------------- Global Error Handler ----------------------------
try:
    # ---------------------------- Backend Functions ----------------------------
    def call_ollama(messages, model, temperature, max_tokens, base_url="http://localhost:11434"):
        # Check if Ollama is running
        try:
            requests.get(base_url, timeout=2)
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to Ollama at {base_url}. Start it with `ollama serve`.")

        prompt = ""
        for msg in messages:
            if msg["role"] == "user":
                prompt += f"User: {msg['content']}\n"
            elif msg["role"] == "assistant":
                prompt += f"Assistant: {msg['content']}\n"
            else:
                prompt += f"{msg['content']}\n"
        prompt += "Assistant:"

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens}
        }
        resp = requests.post(f"{base_url}/api/generate", json=payload, timeout=120)
        if resp.status_code == 200:
            return resp.json()["response"]
        raise Exception(f"Ollama error: {resp.status_code} - {resp.text}")

    # ---------------------------- Session State ----------------------------
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat. (Ollama mode)"}]

    # ---------------------------- Sidebar ----------------------------
    with st.sidebar:
        st.header("⚙️ Configuration")
        backend = "Ollama"  # Fixed to Ollama for simplicity
        model = st.text_input("Model Name", value="llama2")
        ollama_url = st.text_input("Ollama URL", value="http://localhost:11434")
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
        max_tokens = st.slider("Max Tokens", 50, 4096, 1024, 50)
        if st.button("🔌 Test Connection"):
            try:
                requests.get(ollama_url, timeout=2)
                st.success(f"✅ Connected to Ollama at {ollama_url}")
            except Exception as e:
                st.error(f"❌ Cannot connect: {e}")

        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = [{"role": "assistant", "content": "Chat cleared. How can I help?"}]
            st.rerun()

    # ---------------------------- Main Chat ----------------------------
    st.title("🤖 AI Chat (Ollama)")
    st.caption(f"Model: {model} | Temperature: {temperature} | Max Tokens: {max_tokens}")

    # Display messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    if prompt := st.chat_input("Type your message..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get response
        try:
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = call_ollama(
                        st.session_state.messages,
                        model,
                        temperature,
                        max_tokens,
                        ollama_url
                    )
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.session_state.messages.append({"role": "assistant", "content": f"Error: {str(e)}"})

except Exception as e:
    # If anything else crashes, display it here
    st.error("💥 Critical error – please check the logs below:")
    st.code(traceback.format_exc())
    st.stop()