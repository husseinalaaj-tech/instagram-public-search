import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="AI Assistant",
    page_icon="🤖",
    layout="centered",
)

st.title("🤖 AI Assistant")
st.caption("Powered by OpenAI + Streamlit")

# -----------------------------
# Configuration
# -----------------------------

DEFAULT_MODEL = "gpt-5.6-luna"

if "messages" not in st.session_state:
    st.session_state.messages = []

# -----------------------------
# Sidebar
# -----------------------------

with st.sidebar:
    st.header("⚙️ Settings")

    model = st.text_input(
        "Model",
        value=DEFAULT_MODEL,
        help="Enter the OpenAI model you want to use.",
    )

    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# -----------------------------
# API Client
# -----------------------------

try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    st.error(
        "OPENAI_API_KEY is missing.\n\n"
        "Add it to Streamlit Secrets before using the application."
    )
    st.stop()

client = OpenAI(api_key=api_key)

# -----------------------------
# Display conversation
# -----------------------------

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# -----------------------------
# Chat input
# -----------------------------

prompt = st.chat_input("Ask anything...")

if prompt:
    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        try:
            stream = client.responses.create(
                model=model,
                input=st.session_state.messages,
                stream=True,
            )

            for event in stream:
                if event.type == "response.output_text.delta":
                    full_response += event.delta
                    response_placeholder.markdown(full_response + "▌")

            response_placeholder.markdown(full_response)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": full_response,
                }
            )

        except Exception as e:
            error_message = f"⚠️ AI request failed:\n\n`{str(e)}`"
            response_placeholder.error(error_message)

            if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
                st.session_state.messages.pop()