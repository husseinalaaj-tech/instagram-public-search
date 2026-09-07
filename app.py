import streamlit as st
import requests
import json
import time
from typing import List, Dict, Optional

# ---------------------------- Page Config ----------------------------
st.set_page_config(
    page_title="AI Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------- Custom CSS ----------------------------
st.markdown("""
<style>
    .stTextInput > div > div > input {
        background-color: #1e1e1e;
        color: #e0e0e0;
    }
    .stTextArea > div > div > textarea {
        background-color: #1e1e1e;
        color: #e0e0e0;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
        display: flex;
        flex-direction: column;
    }
    .chat-message.user {
        background-color: #2b3138;
        align-self: flex-end;
    }
    .chat-message.assistant {
        background-color: #1c1c1c;
        align-self: flex-start;
    }
    .chat-message .content {
        white-space: pre-wrap;
        word-wrap: break-word;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------- Backend Functions ----------------------------
def call_openai(messages: List[Dict], api_key: str, model: str, temperature: float, max_tokens: int) -> str:
    """Call OpenAI Chat Completion API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")

def call_huggingface(messages: List[Dict], api_key: str, model: str, temperature: float, max_tokens: int) -> str:
    """Call Hugging Face Inference API (text-generation)."""
    # Convert messages to a single prompt with chat template
    prompt = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            prompt += f"User: {content}\n"
        elif role == "assistant":
            prompt += f"Assistant: {content}\n"
        else:
            prompt += f"{content}\n"
    prompt += "Assistant:"

    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "temperature": temperature,
            "max_new_tokens": max_tokens,
            "return_full_text": False
        }
    }
    response = requests.post(
        f"https://api-inference.huggingface.co/models/{model}",
        headers=headers,
        json=payload,
        timeout=60
    )
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]["generated_text"]
        else:
            return data.get("generated_text", "")
    else:
        raise Exception(f"Hugging Face API error: {response.status_code} - {response.text}")

def call_ollama(messages: List[Dict], model: str, temperature: float, max_tokens: int, base_url: str = "http://localhost:11434") -> str:
    """Call local Ollama API."""
    # Ollama expects a prompt, not messages; we build a prompt
    prompt = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            prompt += f"User: {content}\n"
        elif role == "assistant":
            prompt += f"Assistant: {content}\n"
        else:
            prompt += f"{content}\n"
    prompt += "Assistant:"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }
    response = requests.post(
        f"{base_url}/api/generate",
        json=payload,
        timeout=120
    )
    if response.status_code == 200:
        return response.json()["response"]
    else:
        raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

# ---------------------------- Backend Dispatcher ----------------------------
def get_response(messages: List[Dict], backend: str, config: Dict) -> str:
    """Route to the selected backend."""
    if backend == "OpenAI":
        return call_openai(
            messages,
            config["api_key"],
            config["model"],
            config["temperature"],
            config["max_tokens"]
        )
    elif backend == "Hugging Face":
        return call_huggingface(
            messages,
            config["api_key"],
            config["model"],
            config["temperature"],
            config["max_tokens"]
        )
    elif backend == "Ollama":
        return call_ollama(
            messages,
            config["model"],
            config["temperature"],
            config["max_tokens"],
            config.get("ollama_url", "http://localhost:11434")
        )
    else:
        raise ValueError(f"Unsupported backend: {backend}")

# ---------------------------- Session State Initialization ----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! How can I help you today?"}]

# ---------------------------- Sidebar Configuration ----------------------------
with st.sidebar:
    st.header("⚙️ Configuration")
    backend = st.selectbox(
        "Backend",
        ["OpenAI", "Hugging Face", "Ollama"],
        index=0
    )

    # Backend-specific settings
    if backend == "OpenAI":
        api_key = st.text_input("OpenAI API Key", type="password", help="Get from platform.openai.com")
        model = st.selectbox("Model", ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"], index=2)
    elif backend == "Hugging Face":
        api_key = st.text_input("Hugging Face API Key", type="password", help="Get from huggingface.co/settings/tokens")
        model = st.text_input("Model ID", value="mistralai/Mistral-7B-Instruct-v0.1")
    else:  # Ollama
        api_key = ""  # not needed
        model = st.text_input("Model Name", value="llama2")
        ollama_url = st.text_input("Ollama URL", value="http://localhost:11434")

    st.divider()
    st.subheader("🧠 Parameters")
    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
    max_tokens = st.slider("Max Tokens", 50, 4096, 1024, 50)

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": "Chat cleared. How can I help?"}]
        st.rerun()

# ---------------------------- Main Chat Interface ----------------------------
st.title("🤖 AI Chat")
st.caption(f"Backend: {backend} | Model: {model if backend != 'Ollama' else model}")

# Display chat history
for msg in st.session_state.messages:
    role = msg["role"]
    avatar = "🧑" if role == "user" else "🤖"
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Type your message..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # Prepare config
    config = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if backend == "OpenAI" or backend == "Hugging Face":
        if not api_key:
            st.error("Please enter your API key in the sidebar.")
        else:
            config["api_key"] = api_key
    if backend == "Ollama":
        config["ollama_url"] = ollama_url

    # Get assistant response
    try:
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Thinking..."):
                response = get_response(st.session_state.messages, backend, config)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.session_state.messages.append({"role": "assistant", "content": f"Sorry, an error occurred: {str(e)}"})