import html
import io
import json
import re
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_TITLE = "Account Security Assessment"
APP_VERSION = "2.0"

DEFAULT_DELAY = 0.30
MIN_DELAY = 0.10
MAX_DELAY = 1.00

MAX_USERNAME_LENGTH = 30
MAX_ATTEMPTS = 500

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SECURITY / VALIDATION
# ============================================================

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9._]+$"
)


def sanitize_username(value: str) -> str:
    """
    Normalize and validate a username.

    This function does not contact Instagram or any
    external service.
    """
    value = str(value or "").strip()

    if value.startswith("@"):
        value = value[1:]

    value = value.strip()

    if len(value) > MAX_USERNAME_LENGTH:
        raise ValueError(
            f"Username must be {MAX_USERNAME_LENGTH} characters or fewer."
        )

    if not value:
        raise ValueError("Please enter a username.")

    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError(
            "Username may contain only letters, numbers, dots and underscores."
        )

    return value


def safe_text(value: str) -> str:
    """Escape text before displaying it as HTML."""
    return html.escape(str(value))


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


# ============================================================
# SESSION STATE
# ============================================================

def initialize_state():
    defaults = {
        "assessment_complete": False,
        "assessment_running": False,
        "username": "",
        "events": [],
        "findings": [],
        "score": None,
        "report": {},
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()


# ============================================================
# ASSESSMENT ENGINE
# ============================================================

def calculate_score(
    mfa_enabled: bool,
    rate_limit_enabled: bool,
    lockout_enabled: bool,
    monitoring_enabled: bool,
    recovery_enabled: bool,
    suspicious_activity_detection: bool,
) -> int:
    """
    Calculate a defensive security score.

    This is an assessment model, not a real account test.
    """

    score = 0

    if mfa_enabled:
        score += 25

    if rate_limit_enabled:
        score += 20

    if lockout_enabled:
        score += 15

    if monitoring_enabled:
        score += 15

    if recovery_enabled:
        score += 10

    if suspicious_activity_detection:
        score += 15

    return score


def get_risk_level(score: int) -> str:
    if score >= 85:
        return "LOW"
    if score >= 65:
        return "MODERATE"
    if score >= 40:
        return "HIGH"
    return "CRITICAL"


def generate_findings(
    mfa_enabled,
    rate_limit_enabled,
    lockout_enabled,
    monitoring_enabled,
    recovery_enabled,
    suspicious_activity_detection,
):
    findings = []

    if not mfa_enabled:
        findings.append(
            {
                "severity": "CRITICAL",
                "area": "MFA",
                "finding": "Multi-factor authentication is disabled.",
                "recommendation": (
                    "Enable MFA wherever the account supports it."
                ),
            }
        )

    if not rate_limit_enabled:
        findings.append(
            {
                "severity": "HIGH",
                "area": "Rate Limiting",
                "finding": "Rate limiting is not configured.",
                "recommendation": (
                    "Use progressive rate limiting for authentication attempts."
                ),
            }
        )

    if not lockout_enabled:
        findings.append(
            {
                "severity": "HIGH",
                "area": "Account Protection",
                "finding": "Account lockout protection is disabled.",
                "recommendation": (
                    "Introduce a temporary protection mechanism "
                    "after repeated failed authentication attempts."
                ),
            }
        )

    if not monitoring_enabled:
        findings.append(
            {
                "severity": "MEDIUM",
                "area": "Monitoring",
                "finding": "Security event monitoring is disabled.",
                "recommendation": (
                    "Monitor authentication failures and unusual activity."
                ),
            }
        )

    if not recovery_enabled:
        findings.append(
            {
                "severity": "MEDIUM",
                "area": "Recovery",
                "finding": "Recovery configuration is incomplete.",
                "recommendation": (
                    "Verify that recovery email/phone and backup methods "
                    "are current."
                ),
            }
        )

    if not suspicious_activity_detection:
        findings.append(
            {
                "severity": "MEDIUM",
                "area": "Detection",
                "finding": "Suspicious activity detection is disabled.",
                "recommendation": (
                    "Enable alerts and behavioral detection where available."
                ),
            }
        )

    if not findings:
        findings.append(
            {
                "severity": "INFO",
                "area": "Overall",
                "finding": "No major configuration weaknesses were identified.",
                "recommendation": (
                    "Continue monitoring the account and keep recovery "
                    "information up to date."
                ),
            }
        )

    return findings


# ============================================================
# SIMULATION EVENTS
# ============================================================

def build_assessment_events(
    username,
    mfa_enabled,
    rate_limit_enabled,
    lockout_enabled,
    monitoring_enabled,
    recovery_enabled,
    suspicious_activity_detection,
):
    """
    Build a small set of useful local assessment events.

    No requests are made.
    """

    events = []

    def add_event(stage, status, detail):
        events.append(
            {
                "time": utc_now(),
                "stage": stage,
                "status": status,
                "detail": detail,
            }
        )

    add_event(
        "Input Validation",
        "PASS",
        f"Username '{username}' accepted as a local identifier.",
    )

    add_event(
        "Network Access",
        "PASS",
        "External network access disabled for this assessment.",
    )

    add_event(
        "Authentication Testing",
        "SKIPPED",
        "No real login or password testing is performed.",
    )

    add_event(
        "MFA",
        "PASS" if mfa_enabled else "WARN",
        (
            "MFA protection is enabled."
            if mfa_enabled
            else "MFA protection is disabled."
        ),
    )

    add_event(
        "Rate Limiting",
        "PASS" if rate_limit_enabled else "WARN",
        (
            "Rate limiting is configured."
            if rate_limit_enabled
            else "Rate limiting is not configured."
        ),
    )

    add_event(
        "Lockout Protection",
        "PASS" if lockout_enabled else "WARN",
        (
            "Lockout protection is configured."
            if lockout_enabled
            else "Lockout protection is not configured."
        ),
    )

    add_event(
        "Security Monitoring",
        "PASS" if monitoring_enabled else "WARN",
        (
            "Monitoring is enabled."
            if monitoring_enabled
            else "Security monitoring is disabled."
        ),
    )

    add_event(
        "Recovery",
        "PASS" if recovery_enabled else "WARN",
        (
            "Recovery configuration is marked as available."
            if recovery_enabled
            else "Recovery configuration requires attention."
        ),
    )

    add_event(
        "Suspicious Activity Detection",
        "PASS"
        if suspicious_activity_detection
        else "WARN",
        (
            "Detection is enabled."
            if suspicious_activity_detection
            else "Suspicious activity detection is disabled."
        ),
    )

    add_event(
        "Assessment",
        "PASS",
        "Local security assessment completed.",
    )

    return events


# ============================================================
# REPORT
# ============================================================

def create_report(
    username,
    score,
    risk_level,
    findings,
    configuration,
):
    return {
        "application": APP_TITLE,
        "version": APP_VERSION,
        "generated_at": utc_now(),
        "username": username,
        "assessment_type": "Offline Security Assessment",
        "network_requests": 0,
        "score": score,
        "risk_level": risk_level,
        "configuration": configuration,
        "findings": findings,
        "limitations": [
            "No Instagram login was performed.",
            "No password was tested.",
            "No private information was accessed.",
            "No external service was contacted.",
            "Results represent a defensive configuration assessment."
        ],
    }


# ============================================================
# EXPORT HELPERS
# ============================================================

def create_excel_report(
    events,
    findings,
    report,
):
    events_df = pd.DataFrame(events)
    findings_df = pd.DataFrame(findings)

    metrics_df = pd.DataFrame(
        [
            {
                "Metric": "Username",
                "Value": report["username"],
            },
            {
                "Metric": "Score",
                "Value": report["score"],
            },
            {
                "Metric": "Risk Level",
                "Value": report["risk_level"],
            },
            {
                "Metric": "Network Requests",
                "Value": report["network_requests"],
            },
        ]
    )

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        metrics_df.to_excel(
            writer,
            sheet_name="Summary",
            index=False,
        )

        findings_df.to_excel(
            writer,
            sheet_name="Findings",
            index=False,
        )

        events_df.to_excel(
            writer,
            sheet_name="Events",
            index=False,
        )

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>
    .main-title {
        font-size: 38px;
        font-weight: 800;
        margin-bottom: 4px;
    }

    .subtitle {
        color: #777;
        margin-bottom: 20px;
    }

    .account-box {
        padding: 18px;
        border-radius: 12px;
        border: 1px solid rgba(128,128,128,.25);
        margin-bottom: 15px;
    }

    .score-box {
        padding: 20px;
        border-radius: 12px;
        border: 1px solid rgba(128,128,128,.25);
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="main-title">🛡️ Account Security Assessment</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    "Local defensive assessment — no external requests"
    "</div>",
    unsafe_allow_html=True,
)

st.info(
    "This tool evaluates security settings locally. "
    "It does not log into Instagram, test passwords, "
    "access private data, or bypass security controls."
)


# ============================================================
# USERNAME INPUT
# ============================================================

st.subheader("👤 Account")

username_input = st.text_input(
    "Instagram Username",
    value=st.session_state.username,
    placeholder="@your_username",
    max_chars=MAX_USERNAME_LENGTH + 1,
    help="Enter the username you want to use as the assessment label.",
)

st.caption(
    "Example: @example_user"
)


# ============================================================
# SIDEBAR SETTINGS
# ============================================================

with st.sidebar:

    st.header("⚙️ Assessment Settings")

    st.subheader("Protection")

    mfa_enabled = st.checkbox(
        "Multi-factor authentication",
        value=True,
    )

    rate_limit_enabled = st.checkbox(
        "Rate limiting",
        value=True,
    )

    lockout_enabled = st.checkbox(
        "Lockout protection",
        value=True,
    )

    monitoring_enabled = st.checkbox(
        "Security monitoring",
        value=True,
    )

    recovery_enabled = st.checkbox(
        "Recovery methods configured",
        value=True,
    )

    suspicious_activity_detection = st.checkbox(
        "Suspicious activity detection",
        value=True,
    )

    st.divider()

    st.subheader("Display Speed")

    delay = st.slider(
        "Assessment animation",
        min_value=MIN_DELAY,
        max_value=MAX_DELAY,
        value=DEFAULT_DELAY,
        step=0.05,
    )

    st.divider()

    st.caption(
        f"{APP_TITLE} v{APP_VERSION}"
    )


# ============================================================
# START / RESET
# ============================================================

col_start, col_reset = st.columns(2)

with col_start:

    start = st.button(
        "▶️ START ASSESSMENT",
        type="primary",
        use_container_width=True,
    )

with col_reset:

    reset = st.button(
        "🔄 RESET",
        use_container_width=True,
    )


if reset:

    for key in [
        "assessment_complete",
        "assessment_running",
        "username",
        "events",
        "findings",
        "score",
        "report",
    ]:
        if key == "assessment_complete":
            st.session_state[key] = False
        elif key == "assessment_running":
            st.session_state[key] = False
        elif key == "username":
            st.session_state[key] = ""
        elif key in ("events", "findings"):
            st.session_state[key] = []
        else:
            st.session_state[key] = None

    st.rerun()


# ============================================================
# RUN
# ============================================================

if start:

    try:
        username = sanitize_username(
            username_input
        )

    except ValueError as exc:

        st.error(str(exc))
        st.stop()

    st.session_state.username = username
    st.session_state.assessment_running = True
    st.session_state.assessment_complete = False

    st.session_state.events = []
    st.session_state.findings = []

    st.divider()

    st.subheader(
        f"🔍 Assessing @{safe_text(username)}"
    )

    status = st.empty()
    progress = st.progress(0)

    event_display = st.empty()

    stages = [
        "Validating username",
        "Checking assessment scope",
        "Verifying network isolation",
        "Evaluating MFA",
        "Evaluating rate limiting",
        "Evaluating lockout protection",
        "Evaluating monitoring",
        "Evaluating recovery",
        "Evaluating suspicious activity detection",
        "Calculating security score",
        "Generating report",
    ]

    total_stages = len(stages)

    for index, stage in enumerate(
        stages,
        start=1,
    ):

        status.info(
            f"Stage {index}/{total_stages}: {stage}"
        )

        time.sleep(delay)

        progress.progress(
            index / total_stages
        )

        current_event = {
            "time": utc_now(),
            "stage": stage,
            "status": "RUNNING",
            "detail": "Local assessment step.",
        }

        st.session_state.events.append(
            current_event
        )

        display_df = pd.DataFrame(
            st.session_state.events[-8:]
        )

        event_display.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )

    # Generate actual assessment results.
    score = calculate_score(
        mfa_enabled=mfa_enabled,
        rate_limit_enabled=rate_limit_enabled,
        lockout_enabled=lockout_enabled,
        monitoring_enabled=monitoring_enabled,
        recovery_enabled=recovery_enabled,
        suspicious_activity_detection=(
            suspicious_activity_detection
        ),
    )

    risk_level = get_risk_level(score)

    findings = generate_findings(
        mfa_enabled=mfa_enabled,
        rate_limit_enabled=rate_limit_enabled,
        lockout_enabled=lockout_enabled,
        monitoring_enabled=monitoring_enabled,
        recovery_enabled=recovery_enabled,
        suspicious_activity_detection=(
            suspicious_activity_detection
        ),
    )

    configuration = {
        "mfa_enabled": mfa_enabled,
        "rate_limit_enabled": rate_limit_enabled,
        "lockout_enabled": lockout_enabled,
        "monitoring_enabled": monitoring_enabled,
        "recovery_enabled": recovery_enabled,
        "suspicious_activity_detection": (
            suspicious_activity_detection
        ),
    }

    report = create_report(
        username=username,
        score=score,
        risk_level=risk_level,
        findings=findings,
        configuration=configuration,
    )

    # Replace staged events with meaningful final events.
    st.session_state.events = build_assessment_events(
        username=username,
        mfa_enabled=mfa_enabled,
        rate_limit_enabled=rate_limit_enabled,
        lockout_enabled=lockout_enabled,
        monitoring_enabled=monitoring_enabled,
        recovery_enabled=recovery_enabled,
        suspicious_activity_detection=(
            suspicious_activity_detection
        ),
    )

    st.session_state.findings = findings
    st.session_state.score = score
    st.session_state.report = report
    st.session_state.assessment_running = False
    st.session_state.assessment_complete = True

    status.success(
        "Assessment completed."
    )

    time.sleep(0.4)

    st.rerun()


# ============================================================
# RESULTS
# ============================================================

if st.session_state.assessment_complete:

    username = st.session_state.username
    score = st.session_state.score
    report = st.session_state.report
    findings = st.session_state.findings
    events = st.session_state.events

    st.divider()

    st.subheader(
        f"📊 Results for @{safe_text(username)}"
    )

    # --------------------------------------------------------
    # MAIN METRICS
    # --------------------------------------------------------

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Security Score",
        f"{score}/100",
    )

    c2.metric(
        "Risk Level",
        report["risk_level"],
    )

    c3.metric(
        "Findings",
        len(
            [
                x
                for x in findings
                if x["severity"] != "INFO"
            ]
        ),
    )

    c4.metric(
        "Network Requests",
        "0",
    )

    st.divider()

    # --------------------------------------------------------
    # SCORE BAR
    # --------------------------------------------------------

    st.subheader(
        "Security Score"
    )

    st.progress(
        score / 100
    )

    if score >= 85:

        st.success(
            "Strong defensive configuration."
        )

    elif score >= 65:

        st.warning(
            "Moderate configuration. "
            "Some improvements are recommended."
        )

    elif score >= 40:

        st.warning(
            "High risk configuration. "
            "Several protections should be improved."
        )

    else:

        st.error(
            "Critical configuration weaknesses detected."
        )

    # --------------------------------------------------------
    # FINDINGS
    # --------------------------------------------------------

    st.subheader(
        "🔎 Findings"
    )

    findings_df = pd.DataFrame(
        findings
    )

    st.dataframe(
        findings_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "severity": "Severity",
            "area": "Area",
            "finding": "Finding",
            "recommendation": "Recommendation",
        },
    )

    # --------------------------------------------------------
    # PROTECTION MATRIX
    # --------------------------------------------------------

    st.subheader(
        "🔐 Protection Matrix"
    )

    protection_rows = [
        {
            "Protection": "MFA",
            "Status": (
                "Enabled"
                if mfa_enabled
                else "Disabled"
            ),
        },
        {
            "Protection": "Rate Limiting",
            "Status": (
                "Enabled"
                if rate_limit_enabled
                else "Disabled"
            ),
        },
        {
            "Protection": "Lockout",
            "Status": (
                "Enabled"
                if lockout_enabled
                else "Disabled"
            ),
        },
        {
            "Protection": "Monitoring",
            "Status": (
                "Enabled"
                if monitoring_enabled
                else "Disabled"
            ),
        },
        {
            "Protection": "Recovery",
            "Status": (
                "Configured"
                if recovery_enabled
                else "Needs Attention"
            ),
        },
        {
            "Protection": "Suspicious Activity Detection",
            "Status": (
                "Enabled"
                if suspicious_activity_detection
                else "Disabled"
            ),
        },
    ]

    protection_df = pd.DataFrame(
        protection_rows
    )

    st.dataframe(
        protection_df,
        use_container_width=True,
        hide_index=True,
    )

    # --------------------------------------------------------
    # EVENT LOG
    # --------------------------------------------------------

    with st.expander(
        "🧾 Assessment Event Log"
    ):

        events_df = pd.DataFrame(
            events
        )

        st.dataframe(
            events_df,
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # LIMITATIONS
    # --------------------------------------------------------

    with st.expander(
        "ℹ️ Assessment limitations"
    ):

        for limitation in report[
            "limitations"
        ]:
            st.write(
                f"• {limitation}"
            )

    # --------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------

    st.subheader(
        "📦 Export"
    )

    events_df = pd.DataFrame(
        events
    )

    findings_df = pd.DataFrame(
        findings
    )

    excel_data = create_excel_report(
        events=events,
        findings=findings,
        report=report,
    )

    json_data = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    csv_data = findings_df.to_csv(
        index=False
    ).encode("utf-8")

    e1, e2, e3 = st.columns(3)

    with e1:

        st.download_button(
            "⬇️ Findings CSV",
            data=csv_data,
            file_name=(
                f"{username}_security_findings.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    with e2:

        st.download_button(
            "⬇️ Excel Report",
            data=excel_data,
            file_name=(
                f"{username}_security_assessment.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    with e3:

        st.download_button(
            "⬇️ JSON Report",
            data=json_data,
            file_name=(
                f"{username}_security_assessment.json"
            ),
            mime="application/json",
            use_container_width=True,
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    f"{APP_TITLE} v{APP_VERSION} • "
    "Offline assessment • Network requests: 0"
)