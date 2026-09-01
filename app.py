from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict

from fastapi import FastAPI
from pydantic import BaseModel


HOST = "127.0.0.1"
PORT = 8080

FAKE_USERNAME = "lab_user"
FAKE_PASSWORD = "LabPassword-2026"

LOCKOUT_THRESHOLD = 5
LOCKOUT_SECONDS = 30

RATE_LIMIT_MAX = 3
RATE_LIMIT_WINDOW = 5

DETECTION_THRESHOLD = 3


def password_hash(password: str) -> str:
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


@dataclass
class AccountState:
    username: str
    password_hash: str

    failed_attempts: int = 0
    locked_until: float = 0.0
    attempts: list[float] = field(
        default_factory=list
    )


accounts: Dict[str, AccountState] = {
    FAKE_USERNAME: AccountState(
        username=FAKE_USERNAME,
        password_hash=password_hash(
            FAKE_PASSWORD
        ),
    )
}

state_lock = Lock()

app = FastAPI(
    title="Local Brute-Force Security Lab",
    version="1.0.0",
)


class LoginRequest(BaseModel):
    username: str
    password: str


def now() -> float:
    return time.time()


def is_locked(account: AccountState) -> bool:
    return now() < account.locked_until


def cleanup_attempts(account: AccountState) -> None:
    cutoff = now() - RATE_LIMIT_WINDOW

    account.attempts = [
        timestamp
        for timestamp in account.attempts
        if timestamp >= cutoff
    ]


def rate_limited(account: AccountState) -> bool:
    cleanup_attempts(account)

    return len(account.attempts) >= RATE_LIMIT_MAX


def detection_triggered(account: AccountState) -> bool:
    return (
        account.failed_attempts
        >= DETECTION_THRESHOLD
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": "local",
        "host": HOST,
    }


@app.get("/lab/account")
def account_info():
    return {
        "username": FAKE_USERNAME,
        "environment": "LOCAL_TEST_ACCOUNT",
    }


@app.post("/lab/authenticate")
def authenticate(request: LoginRequest):

    with state_lock:

        account = accounts.get(
            request.username
        )

        if account is None:
            return {
                "success": False,
                "reason": "unknown_account",
            }

        if is_locked(account):

            remaining = max(
                0,
                int(
                    account.locked_until
                    - now()
                ),
            )

            return {
                "success": False,
                "reason": "locked",
                "remaining_seconds": remaining,
                "detected": True,
            }

        if rate_limited(account):

            return {
                "success": False,
                "reason": "rate_limited",
                "detected": True,
            }

        account.attempts.append(now())

        supplied_hash = password_hash(
            request.password
        )

        valid = hmac.compare_digest(
            supplied_hash,
            account.password_hash,
        )

        if valid:

            account.failed_attempts = 0

            return {
                "success": True,
                "reason": "authenticated",
                "detected": False,
            }

        account.failed_attempts += 1

        locked = (
            account.failed_attempts
            >= LOCKOUT_THRESHOLD
        )

        if locked:
            account.locked_until = (
                now() + LOCKOUT_SECONDS
            )

        return {
            "success": False,
            "reason": (
                "locked"
                if locked
                else "invalid_password"
            ),
            "failed_attempts":
                account.failed_attempts,
            "locked": locked,
            "detected":
                detection_triggered(account),
        }


@app.post("/lab/reset")
def reset_account():

    with state_lock:

        accounts[
            FAKE_USERNAME
        ] = AccountState(
            username=FAKE_USERNAME,
            password_hash=password_hash(
                FAKE_PASSWORD
            ),
        )

    return {
        "success": True,
        "message": "Local lab account reset.",
    }