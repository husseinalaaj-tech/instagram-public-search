import streamlit as st
import requests
import json
import re

# ---------------------------- Page Config ----------------------------
st.set_page_config(page_title="AI Chat Ultra", page_icon="🤖", layout="wide")

# ---------------------------- Backend Functions ----------------------------
def call_ollama(messages, model, temperature, max_tokens, base_url="http://localhost:11434"):
    """Call local Ollama server."""
    # Validate URL – must start with http:// or https:// and contain 'localhost' or '127.0.0.1' or be a valid IP
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Ollama URL must start with http:// or https://")
    # If URL points to a public domain (like claude.ai), reject it
    forbidden_domains = ["claude.ai", "anthropic.com", "openai.com", "huggingface.co"]
    for domain in forbidden_domains:
        if domain in base_url.lower():
            raise ValueError(f"Ollama URL cannot point to {domain}. Use a local address like http://localhost:11434")

    # Check if server is reachable
    try:
        resp = requests.get(base_url, timeout=2)
        # If we get HTML, it's probably a web page, not Ollama
        if "text/html" in resp.headers.get("Content-Type", ""):
            raise ValueError("The URL returned HTML – make sure it's an Ollama server, not a web page.")
    except requests.exceptions.ConnectionError:
        raise ConnectionError(f"Cannot connect to Ollama at {base_url}. Start it with `ollama serve`.")

    # Build prompt
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
        # Check if response is JSON
        try:
            data = resp.json()
            return data["response"]
        except json.JSONDecodeError:
            raise Exception("Ollama returned invalid JSON – is the URL correct?")
    else:
        raise Exception(f"Ollama error: {resp.status_code} - {resp.text[:200]}")

def call_claude(messages, api_key, model, temperature, max_tokens):
    """Call Claude via Anthropic API."""
    if not api_key:
        raise ValueError("Anthropic API key is required.")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    system = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        else:
            chat_messages.append(msg)
    if not system:
        system = "You are a helpful assistant."

    payload = {
        "model": model,
        "system": system,
        "messages": chat_messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
    if resp.status_code == 200:
        return resp.json()["content"][0]["text"]
    else:
        raise Exception(f"Claude error: {resp.status_code} - {resp.text[:200]}")

# ---------------------------- Dispatcher ----------------------------
def get_response(messages, backend, config):
    if backend == "Ollama":
        return call_ollama(messages, config["model"], config["temperature"], config["max_tokens"], config.get("ollama_url", "http://localhost:11434"))
    elif backend == "Claude":
        return call_claude(messages, config["api_key"], config["model"], config["temperature"], config["max_tokens"])
    else:
        raise ValueError(f"Unknown backend: {backend}")

# ---------------------------- Session State ----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! Choose a backend and start chatting."}]

# ---------------------------- Sidebar ----------------------------
with st.sidebar:
    st.header("⚙️ Configuration")
    backend = st.selectbox("Backend", ["Ollama", "Claude"], index=0)

    if backend == "Ollama":
        model = st.text_input("Model Name", value="llama2")
        ollama_url = st.text_input("Ollama URL", value="http://localhost:11434")
        st.caption("Make sure Ollama is running: `ollama serve`")
        # Test connection button
        if st.button("🔌 Test Ollama Connection"):
            try:
                resp = requests.get(ollama_url, timeout=2)
                if "text/html" in resp.headers.get("Content-Type", ""):
                    st.error("❌ The URL returned HTML – not an Ollama server. Check the URL.")
                else:
                    st.success(f"✅ Connected to Ollama at {ollama_url}")
            except Exception as e:
                st.error(f"❌ Cannot connect: {e}")
    else:  # Claude
        api_key = st.text_input("Anthropic API Key", type="password", help="Get from console.anthropic.com")
        model = st.selectbox("Model", ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"], index=0)
        st.caption("Claude API has rate limits; your key must have credits.")

    st.divider()
    st.subheader("🧠 Parameters")
    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
    max_tokens = st.slider("Max Tokens", 50, 4096, 1024, 50)

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": "Chat cleared. How can I help?"}]
        st.rerun()

# ---------------------------- Main Chat ----------------------------
st.title("🤖 AI Chat Ultra")
st.caption(f"Backend: {backend} | Model: {model if backend == 'Ollama' else model}")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Type your message..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build config
    config = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if backend == "Ollama":
        config["ollama_url"] = ollama_url
    else:  # Claude
        config["api_key"] = api_key

    try:
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = get_response(st.session_state.messages, backend, config)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
    except ValueError as e:
        st.error(f"❌ Configuration error: {e}")
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
    except ConnectionError as e:
        st.error(f"🔌 Connection error: {e}")
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})