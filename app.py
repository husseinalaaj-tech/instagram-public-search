from __future__ import annotations

import hashlib
import hmac
import secrets
import string
import time
from dataclasses import dataclass
from typing import Dict, List

import requests
import streamlit as st
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn


# ============================================================
# CONFIG
# ============================================================

HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"

# Intentionally fictional laboratory accounts.
LAB_ACCOUNTS = {
    "researcher": "V7!qR2#nL9@xP4$k",
    "admin_lab": "Z8@Lm4!Qp7#Wx2$R",
    "security_lab": "Q4#vN8!sT2@kL7$xP",
}


# ============================================================
# LOCAL LAB SERVER
# ============================================================

server = FastAPI(
    title="Local Authentication Lab",
)


class LoginRequest(BaseModel):
    username: str
    password: str


@dataclass
class AccountState:
    password_hash: str
    attempts: int = 0
    started_at: float | None = None
    solved: bool = False


def hash_password(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


account_state: Dict[str, AccountState] = {
    username: AccountState(
        password_hash=hash_password(password)
    )
    for username, password in LAB_ACCOUNTS.items()
}


@server.get("/health")
def health():
    return {
        "status": "ok",
        "environment": "LOCAL_ONLY",
    }


@server.post("/lab/authenticate")
def authenticate(request: LoginRequest):

    account = account_state.get(
        request.username
    )

    if account is None:
        return {
            "success": False,
            "reason": "unknown_account",
        }

    if account.started_at is None:
        account.started_at = time.perf_counter()

    account.attempts += 1

    supplied_hash = hash_password(
        request.password
    )

    valid = hmac.compare_digest(
        supplied_hash,
        account.password_hash,
    )

    if valid:

        account.solved = True

        elapsed = (
            time.perf_counter()
            - account.started_at
        )

        return {
            "success": True,
            "reason": "password_matched",
            "attempts": account.attempts,
            "elapsed": elapsed,
        }

    return {
        "success": False,
        "reason": "invalid_password",
        "attempts": account.attempts,
    }


@server.post("/lab/reset")
def reset():

    for username, password in LAB_ACCOUNTS.items():

        account_state[username] = AccountState(
            password_hash=hash_password(password)
        )

    return {
        "success": True,
    }


# ============================================================
# LOCAL SERVER CONTROL
# ============================================================

@st.cache_resource
def start_local_server():

    config = uvicorn.Config(
        server,
        host=HOST,
        port=PORT,
        log_level="warning",
    )

    instance = uvicorn.Server(config)

    import threading

    thread = threading.Thread(
        target=instance.run,
        daemon=True,
    )

    thread.start()

    time.sleep(0.5)

    return thread


# ============================================================
# CANDIDATE GENERATION
# ============================================================

COMMON_PASSWORDS = [
    "password",
    "123456",
    "12345678",
    "qwerty",
    "admin",
    "welcome",
    "letmein",
    "password123",
    "admin123",
    "researcher",
    "security",
]


def generate_candidates(
    mode: str,
    custom_text: str,
) -> List[str]:

    if mode == "Common passwords":

        return COMMON_PASSWORDS.copy()

    if mode == "Custom list":

        return [
            item.strip()
            for item in custom_text.splitlines()
            if item.strip()
        ]

    # Small LOCAL educational search space.
    if mode == "Small exhaustive":

        alphabet = "abc123"

        candidates = []

        for length in range(1, 5):

            def build(prefix: str, remaining: int):

                if remaining == 0:

                    candidates.append(prefix)

                    return

                for char in alphabet:

                    build(
                        prefix + char,
                        remaining - 1,
                    )

            build("", length)

        return candidates

    return []


# ============================================================
# HTTP CLIENT
# ============================================================

def local_request(
    username: str,
    password: str,
):

    # Hard safety boundary.
    url = (
        f"http://{HOST}:{PORT}"
        "/lab/authenticate"
    )

    response = requests.post(
        url,
        json={
            "username": username,
            "password": password,
        },
        timeout=2,
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# STREAMLIT UI
# ============================================================

st.set_page_config(
    page_title="Local Brute-Force Lab",
    page_icon="🧪",
    layout="wide",
)


st.title(
    "🧪 Local Brute-Force Research Lab"
)

st.caption(
    "Real HTTP requests against fictional accounts "
    "running on localhost."
)

st.warning(
    "LOCAL LAB ONLY — this application contains "
    "no external target configuration."
)


# Start local service.
start_local_server()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("Laboratory Target")

    username = st.selectbox(
        "Choose fictional account",
        list(LAB_ACCOUNTS.keys()),
    )

    st.code(
        f"{HOST}:{PORT}"
    )

    st.divider()

    st.write(
        "Authentication endpoint:"
    )

    st.code(
        "/lab/authenticate"
    )

    if st.button(
        "Reset Laboratory",
        use_container_width=True,
    ):

        try:

            response = requests.post(
                f"{BASE_URL}/lab/reset",
                timeout=2,
            )

            response.raise_for_status()

            st.session_state.results = []

            st.success(
                "Laboratory reset."
            )

        except Exception as exc:

            st.error(str(exc))


# ============================================================
# ACCOUNT INFORMATION
# ============================================================

st.subheader(
    "Selected Laboratory Account"
)

col1, col2, col3 = st.columns(3)

with col1:

    st.metric(
        "Account",
        username,
    )

with col2:

    st.metric(
        "Target",
        "127.0.0.1",
    )

with col3:

    st.metric(
        "Network",
        "LOCAL",
    )


with st.expander(
    "Show laboratory password"
):

    st.code(
        LAB_ACCOUNTS[username]
    )

    st.caption(
        "This credential belongs only to the "
        "fictional local laboratory account."
    )


# ============================================================
# TEST STRATEGY
# ============================================================

st.subheader(
    "Candidate Strategy"
)

mode = st.selectbox(
    "Mode",
    [
        "Common passwords",
        "Custom list",
        "Small exhaustive",
    ],
)


custom_text = ""

if mode == "Custom list":

    custom_text = st.text_area(
        "Candidates",
        value=(
            "password\n"
            "123456\n"
            "admin\n"
            "LabPassword\n"
        ),
        height=180,
    )


candidates = generate_candidates(
    mode,
    custom_text,
)


st.write(
    f"Candidates prepared: **{len(candidates)}**"
)


# ============================================================
# RUN
# ============================================================

if "results" not in st.session_state:

    st.session_state.results = []


run = st.button(
    "▶ RUN LOCAL TEST",
    type="primary",
    use_container_width=True,
)


if run:

    try:

        health = requests.get(
            f"{BASE_URL}/health",
            timeout=2,
        )

        health.raise_for_status()

    except Exception:

        st.error(
            "Local authentication service "
            "is unavailable."
        )

        st.stop()


    if not candidates:

        st.error(
            "No candidates were supplied."
        )

        st.stop()


    results = []

    progress = st.progress(0)

    status = st.empty()

    started = time.perf_counter()

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        attempt_started = (
            time.perf_counter()
        )

        response = local_request(
            username,
            candidate,
        )

        attempt_time = (
            time.perf_counter()
            - attempt_started
        )

        row = {
            "attempt": index,
            "candidate": candidate,
            "success": response.get(
                "success",
                False,
            ),
            "reason": response.get(
                "reason",
                "unknown",
            ),
            "request_time_ms":
                round(
                    attempt_time * 1000,
                    3,
                ),
        }

        results.append(row)

        status.write(
            f"Attempt {index}/{len(candidates)} — "
            f"{row['reason']}"
        )

        progress.progress(
            index / len(candidates)
        )

        if row["success"]:

            break


    total_time = (
        time.perf_counter()
        - started
    )

    st.session_state.results = results

    st.success(
        "Local HTTP authentication test completed."
    )

    st.metric(
        "Total runtime",
        f"{total_time:.4f} seconds",
    )


# ============================================================
# RESULTS
# ============================================================

if st.session_state.results:

    st.divider()

    st.subheader(
        "Results"
    )

    results = (
        st.session_state.results
    )

    successful = [
        row
        for row in results
        if row["success"]
    ]

    attempts = len(results)

    c1, c2, c3 = st.columns(3)

    with c1:

        st.metric(
            "HTTP Requests",
            attempts,
        )

    with c2:

        st.metric(
            "Password Found",
            "YES"
            if successful
            else "NO",
        )

    with c3:

        st.metric(
            "Average Request",
            f"{sum(
                r['request_time_ms']
                for r in results
            ) / attempts:.3f} ms",
        )


    if successful:

        match = successful[0]

        st.success(
            "Laboratory password matched."
        )

        st.write(
            f"Matched candidate: "
            f"`{match['candidate']}`"
        )

        st.write(
            f"Attempts required: "
            f"`{match['attempt']}`"
        )

    else:

        st.info(
            "The supplied candidate set did not "
            "contain the laboratory password."
        )


    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )


    st.subheader(
        "Export"
    )

    dataframe = (
        __import__("pandas")
        .DataFrame(results)
    )

    csv_data = dataframe.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Download CSV",
        csv_data,
        "local_bruteforce_results.csv",
        "text/csv",
        use_container_width=True,
    )


# ============================================================
# ARCHITECTURE
# ============================================================

with st.expander(
    "Architecture"
):

    st.code(
        """
Streamlit UI
     |
     | HTTP POST
     v
127.0.0.1:8765
     |
     v
FastAPI Authentication Endpoint
     |
     v
Fictional Account Store
     |
     v
SHA-256 + constant-time comparison
     |
     v
Authentication Result
     |
     v
Streamlit Results / CSV
        """,
        language="text",
    )


st.divider()

st.caption(
    "Local Brute-Force Research Lab • "
    "No external targets are supported."
)