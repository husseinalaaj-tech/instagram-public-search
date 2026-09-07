import streamlit as st
import requests
import json
from typing import List, Dict, Optional

# ---------------------------- Page Config ----------------------------
st.set_page_config(page_title="AI Chat Pro", page_icon="🤖", layout="wide")

# ---------------------------- Custom CSS ----------------------------
st.markdown("""
<style>
    .stTextInput > div > div > input { background-color: #1e1e1e; color: #e0e0e0; }
    .stTextArea > div > div > textarea { background-color: #1e1e1e; color: #e0e0e0; }
    .chat-message { padding: 1rem; border-radius: 0.5rem; margin-bottom: 0.5rem; display: flex; flex-direction: column; }
    .chat-message.user { background-color: #2b3138; align-self: flex-end; }
    .chat-message.assistant { background-color: #1c1c1c; align-self: flex-start; }
    .chat-message .content { white-space: pre-wrap; word-wrap: break-word; }
</style>
""", unsafe_allow_html=True)

# ---------------------------- Backend Functions ----------------------------
def call_openai(messages: List[Dict], api_key: str, model: str, temperature: float, max_tokens: int) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    raise Exception(f"OpenAI error: {resp.status_code} - {resp.text}")

def call_huggingface(messages: List[Dict], api_key: str, model: str, temperature: float, max_tokens: int) -> str:
    prompt = ""
    for msg in messages:
        if msg["role"] == "user":
            prompt += f"User: {msg['content']}\n"
        elif msg["role"] == "assistant":
            prompt += f"Assistant: {msg['content']}\n"
        else:
            prompt += f"{msg['content']}\n"
    prompt += "Assistant:"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"inputs": prompt, "parameters": {"temperature": temperature, "max_new_tokens": max_tokens, "return_full_text": False}}
    resp = requests.post(f"https://api-inference.huggingface.co/models/{model}", headers=headers, json=payload, timeout=60)
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]["generated_text"]
        return data.get("generated_text", "")
    raise Exception(f"Hugging Face error: {resp.status_code} - {resp.text}")

def call_claude(messages: List[Dict], api_key: str, model: str, temperature: float, max_tokens: int) -> str:
    """
    Claude API (Anthropic) – requires api_key and model id.
    Claude 3.5 Sonnet, Claude 3 Opus, etc.
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    # Claude uses a system prompt and a list of messages with roles "user" and "assistant".
    system = ""
    # Extract system message if present (first message with role "system")
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        else:
            chat_messages.append(msg)
    # If no system, use a default
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
    raise Exception(f"Claude error: {resp.status_code} - {resp.text}")

def call_ollama(messages: List[Dict], model: str, temperature: float, max_tokens: int, base_url: str = "http://localhost:11434") -> str:
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

# ---------------------------- Dispatcher ----------------------------
def get_response(messages: List[Dict], backend: str, config: Dict) -> str:
    if backend == "OpenAI":
        return call_openai(messages, config["api_key"], config["model"], config["temperature"], config["max_tokens"])
    elif backend == "Hugging Face":
        return call_huggingface(messages, config["api_key"], config["model"], config["temperature"], config["max_tokens"])
    elif backend == "Claude":
        return call_claude(messages, config["api_key"], config["model"], config["temperature"], config["max_tokens"])
    elif backend == "Ollama":
        return call_ollama(messages, config["model"], config["temperature"], config["max_tokens"], config.get("ollama_url", "http://localhost:11434"))
    else:
        raise ValueError(f"Unknown backend: {backend}")

# ---------------------------- Session State ----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! How can I help you today?"}]

# ---------------------------- Sidebar ----------------------------
with st.sidebar:
    st.header("⚙️ Configuration")
    backend = st.selectbox("Backend", ["OpenAI", "Hugging Face", "Claude", "Ollama"], index=3 if "Ollama" else 0)

    if backend == "OpenAI":
        api_key = st.text_input("OpenAI API Key", type="password")
        model = st.selectbox("Model", ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"], index=2)
    elif backend == "Hugging Face":
        api_key = st.text_input("Hugging Face API Key", type="password")
        model = st.text_input("Model ID", value="mistralai/Mistral-7B-Instruct-v0.1")
    elif backend == "Claude":
        api_key = st.text_input("Anthropic API Key", type="password", help="Get from console.anthropic.com")
        model = st.selectbox("Model", ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"], index=0)
    else:  # Ollama
        api_key = ""  # not used
        model = st.text_input("Model Name", value="llama2")
        ollama_url = st.text_input("Ollama URL", value="http://localhost:11434")
        st.caption("Local, unlimited tokens – run Ollama on your machine.")

    st.divider()
    st.subheader("🧠 Parameters")
    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
    max_tokens = st.slider("Max Tokens", 50, 4096, 1024, 50)
    st.caption("For Ollama, 'max_tokens' is 'num_predict' – you can set it to high values (e.g., 4096) if your hardware supports.")

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": "Chat cleared. How can I help?"}]
        st.rerun()

# ---------------------------- Chat Interface ----------------------------
st.title("🤖 AI Chat Pro")
st.caption(f"Backend: {backend} | Model: {model}")

for msg in st.session_state.messages:
    avatar = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

if prompt := st.chat_input("Type your message..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    config = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if backend in ["OpenAI", "Hugging Face", "Claude"]:
        if not api_key:
            st.error("Please enter your API key in the sidebar.")
        else:
            config["api_key"] = api_key
    if backend == "Ollama":
        config["ollama_url"] = ollama_url

    if api_key or backend == "Ollama":
        try:
            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("Thinking..."):
                    response = get_response(st.session_state.messages, backend, config)
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.session_state.messages.append({"role": "assistant", "content": f"Sorry, an error occurred: {str(e)}"})