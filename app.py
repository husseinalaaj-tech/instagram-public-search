import io
import json
import math
import random
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Account Defense Lab",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_NAME = "Account Defense Lab"

PASSWORD_PROFILES = {
    "Weak": 0.82,
    "Medium": 0.45,
    "Strong": 0.08,
}

SCENARIOS = {
    "Credential Pressure": {
        "description": "Simulates repeated authentication pressure.",
        "base_detection": 0.35,
    },
    "Rapid Attempts": {
        "description": "Simulates a high-frequency automated pattern.",
        "base_detection": 0.55,
    },
    "Distributed Pattern": {
        "description": "Simulates attempts distributed across synthetic sources.",
        "base_detection": 0.25,
    },
    "Mixed Traffic": {
        "description": "Simulates normal and suspicious traffic together.",
        "base_detection": 0.40,
    },
}


# ============================================================
# SESSION STATE
# ============================================================

def init_state():
    defaults = {
        "running": False,
        "completed": False,
        "events": [],
        "metrics": {},
        "report": {},
        "seed": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# ============================================================
# HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def pct(value, total):
    if total <= 0:
        return 0.0
    return (value / total) * 100


# ============================================================
# SYNTHETIC TRAFFIC GENERATOR
# ============================================================

class SyntheticTrafficGenerator:

    def __init__(self, seed):
        self.rng = random.Random(seed)

    def source(self, distributed):
        if distributed:
            return (
                f"SIM-SRC-"
                f"{self.rng.randint(100, 999)}"
            )

        return "SIM-SRC-001"

    def password_profile(self, profile):
        roll = self.rng.random()

        if roll < PASSWORD_PROFILES[profile]:
            return "synthetic-match"

        return "synthetic-failure"

    def normal_or_suspicious(self, scenario):
        if scenario == "Rapid Attempts":
            return "suspicious"

        if scenario == "Distributed Pattern":
            return (
                "suspicious"
                if self.rng.random() < 0.62
                else "normal"
            )

        if scenario == "Mixed Traffic":
            return (
                "suspicious"
                if self.rng.random() < 0.50
                else "normal"
            )

        return (
            "suspicious"
            if self.rng.random() < 0.72
            else "normal"
        )


# ============================================================
# DEFENSE ENGINE
# ============================================================

class DefenseEngine:

    def __init__(
        self,
        rate_limit,
        lockout_threshold,
        lockout_duration,
        mfa_enabled,
        detection_sensitivity,
    ):
        self.rate_limit = rate_limit
        self.lockout_threshold = lockout_threshold
        self.lockout_duration = lockout_duration
        self.mfa_enabled = mfa_enabled
        self.detection_sensitivity = detection_sensitivity

        self.consecutive_failures = 0
        self.blocked = 0
        self.rate_limited = 0
        self.lockouts = 0
        self.mfa_challenges = 0
        self.detections = 0

        self.locked_until = 0.0

    def evaluate(
        self,
        timestamp,
        suspicious,
        source,
        attempts_in_window,
    ):
        result = {
            "status": "ALLOWED",
            "reason": "",
            "detection": False,
            "mfa": False,
        }

        if timestamp < self.locked_until:

            self.blocked += 1

            result["status"] = "LOCKED"
            result["reason"] = "Synthetic account lockout active."

            return result

        if attempts_in_window >= self.rate_limit:

            self.rate_limited += 1

            result["status"] = "RATE LIMITED"
            result["reason"] = "Synthetic rate limit triggered."

            return result

        detection_probability = (
            self.detection_sensitivity
            if suspicious
            else self.detection_sensitivity * 0.12
        )

        # Repeated activity increases detection likelihood.
        if attempts_in_window >= max(
            2,
            self.rate_limit // 2,
        ):
            detection_probability += 0.18

        detection_probability = clamp(
            detection_probability,
            0.0,
            0.98,
        )

        detected = random.random() < detection_probability

        if detected:

            self.detections += 1

            result["detection"] = True
            result["reason"] = "Suspicious synthetic behavior detected."

        if self.mfa_enabled and suspicious:

            if random.random() < 0.68:

                self.mfa_challenges += 1

                result["mfa"] = True
                result["status"] = "MFA CHALLENGE"
                result["reason"] = (
                    "Synthetic MFA challenge issued."
                )

                return result

        return result

    def register_failure(self, timestamp):

        self.consecutive_failures += 1

        if (
            self.consecutive_failures
            >= self.lockout_threshold
        ):

            self.locked_until = (
                timestamp
                + self.lockout_duration
            )

            self.lockouts += 1
            self.consecutive_failures = 0

            return True

        return False

    def reset_failure_counter(self):
        self.consecutive_failures = 0


# ============================================================
# SIMULATION
# ============================================================

def run_simulation(
    target,
    attempts,
    speed,
    scenario,
    password_profile,
    rate_limit,
    lockout_threshold,
    lockout_duration,
    mfa_enabled,
    detection_sensitivity,
    distributed_sources,
    live_placeholder,
    progress_bar,
    metrics_placeholder,
    console_placeholder,
):
    seed = (
        hash(
            (
                target,
                attempts,
                scenario,
                password_profile,
            )
        )
        & 0xFFFFFFFF
    )

    st.session_state.seed = seed

    generator = SyntheticTrafficGenerator(seed)

    defense = DefenseEngine(
        rate_limit=rate_limit,
        lockout_threshold=lockout_threshold,
        lockout_duration=lockout_duration,
        mfa_enabled=mfa_enabled,
        detection_sensitivity=detection_sensitivity,
    )

    events = []

    allowed = 0
    failed = 0
    blocked = 0
    successful_matches = 0
    normal_requests = 0
    suspicious_requests = 0

    start_time = time.monotonic()

    for i in range(1, attempts + 1):

        elapsed = time.monotonic() - start_time

        source = generator.source(
            distributed_sources
        )

        traffic_type = (
            generator.normal_or_suspicious(
                scenario
            )
        )

        suspicious = (
            traffic_type == "suspicious"
        )

        if suspicious:
            suspicious_requests += 1
        else:
            normal_requests += 1

        # Synthetic rolling request window.
        recent_events = [
            e
            for e in events
            if (
                elapsed
                - e["elapsed"]
                <= 5.0
            )
        ]

        attempts_in_window = len(
            recent_events
        )

        defense_result = defense.evaluate(
            timestamp=elapsed,
            suspicious=suspicious,
            source=source,
            attempts_in_window=attempts_in_window,
        )

        status = defense_result["status"]
        reason = defense_result["reason"]

        if status in (
            "LOCKED",
            "RATE LIMITED",
        ):

            blocked += 1

        elif status == "MFA CHALLENGE":

            allowed += 1

        else:

            allowed += 1

        synthetic_credential = (
            generator.password_profile(
                password_profile
            )
        )

        if (
            status not in (
                "LOCKED",
                "RATE LIMITED",
            )
        ):

            if (
                synthetic_credential
                == "synthetic-match"
                and suspicious
            ):

                successful_matches += 1
                result = "SYNTHETIC MATCH"

                defense.reset_failure_counter()

            else:

                failed += 1

                locked = defense.register_failure(
                    elapsed
                )

                if locked:
                    status = "LOCKOUT"
                    reason = (
                        "Synthetic lockout threshold reached."
                    )
                    blocked += 1

        else:

            result = "BLOCKED"

        if status == "MFA CHALLENGE":
            result = "CHALLENGE"

        elif status == "RATE LIMITED":
            result = "RATE LIMITED"

        elif status == "LOCKED":
            result = "LOCKED"

        elif status == "LOCKOUT":
            result = "LOCKOUT"

        elif (
            synthetic_credential
            == "synthetic-match"
        ):
            result = "SYNTHETIC MATCH"

        else:
            result = "FAILED"

        event = {
            "attempt": i,
            "elapsed": round(elapsed, 3),
            "source": source,
            "traffic": traffic_type,
            "credential": synthetic_credential,
            "status": status,
            "result": result,
            "reason": reason,
            "detected": defense_result[
                "detection"
            ],
            "mfa": defense_result["mfa"],
            "time": utc_now(),
        }

        events.append(event)

        # Keep the visible console compact.
        console_placeholder.code(
            "\n".join(
                [
                    (
                        f"[{e['attempt']:03d}] "
                        f"{e['traffic'].upper():10} | "
                        f"{e['source']} | "
                        f"{e['result']}"
                    )
                    for e in events[-16:]
                ]
            )
        )

        completed_pct = i / attempts

        progress_bar.progress(
            completed_pct
        )

        detection_pct = pct(
            defense.detections,
            i,
        )

        metrics_placeholder.metric(
            "Detection Rate",
            f"{detection_pct:.1f}%",
        )

        time.sleep(speed)

    duration = time.monotonic() - start_time

    detection_rate = pct(
        defense.detections,
        attempts,
    )

    block_rate = pct(
        blocked,
        attempts,
    )

    defense_effectiveness = clamp(
        (
            detection_rate * 0.35
            + block_rate * 0.35
            + (
                100
                if mfa_enabled
                else 0
            )
            * 0.15
            + (
                100
                if defense.lockouts > 0
                else 40
            )
            * 0.15
        ),
        0,
        100,
    )

    risk_score = clamp(
        100 - defense_effectiveness,
        0,
        100,
    )

    if risk_score >= 70:
        risk_level = "HIGH"
    elif risk_score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    metrics = {
        "attempts": attempts,
        "allowed": allowed,
        "failed": failed,
        "blocked": blocked,
        "synthetic_matches": successful_matches,
        "normal_requests": normal_requests,
        "suspicious_requests": suspicious_requests,
        "detections": defense.detections,
        "rate_limited": defense.rate_limited,
        "lockouts": defense.lockouts,
        "mfa_challenges": defense.mfa_challenges,
        "detection_rate": round(
            detection_rate,
            2,
        ),
        "block_rate": round(
            block_rate,
            2,
        ),
        "defense_effectiveness": round(
            defense_effectiveness,
            2,
        ),
        "risk_score": round(
            risk_score,
            2,
        ),
        "risk_level": risk_level,
        "duration_seconds": round(
            duration,
            2,
        ),
    }

    report = {
        "application": APP_NAME,
        "generated_at": utc_now(),
        "target": target,
        "scenario": scenario,
        "password_profile": password_profile,
        "configuration": {
            "attempts": attempts,
            "rate_limit": rate_limit,
            "lockout_threshold": lockout_threshold,
            "lockout_duration": lockout_duration,
            "mfa_enabled": mfa_enabled,
            "detection_sensitivity": detection_sensitivity,
            "distributed_sources": distributed_sources,
        },
        "metrics": metrics,
        "note": (
            "All credentials, targets, sources, "
            "authentication events and results are synthetic."
        ),
    }

    st.session_state.events = events
    st.session_state.metrics = metrics
    st.session_state.report = report
    st.session_state.completed = True
    st.session_state.running = False


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Lab Configuration")

    target = st.text_input(
        "Synthetic account name",
        value="demo_account",
        help=(
            "This is only a label. "
            "No account is contacted."
        ),
    )

    scenario = st.selectbox(
        "Simulation scenario",
        list(SCENARIOS.keys()),
    )

    st.caption(
        SCENARIOS[scenario]["description"]
    )

    password_profile = st.selectbox(
        "Synthetic credential profile",
        list(PASSWORD_PROFILES.keys()),
    )

    attempts = st.slider(
        "Synthetic attempts",
        10,
        500,
        100,
        10,
    )

    speed = st.slider(
        "Animation delay",
        0.0,
        0.15,
        0.02,
        0.01,
    )

    st.divider()

    st.subheader("Defense Controls")

    rate_limit = st.slider(
        "Rate limit / 5 sec",
        2,
        30,
        8,
    )

    lockout_threshold = st.slider(
        "Lockout threshold",
        3,
        20,
        7,
    )

    lockout_duration = st.slider(
        "Lockout duration",
        1,
        30,
        8,
    )

    detection_sensitivity = st.slider(
        "Detection sensitivity",
        0.10,
        0.95,
        0.65,
        0.05,
    )

    mfa_enabled = st.toggle(
        "Synthetic MFA",
        value=True,
    )

    distributed_sources = st.toggle(
        "Distributed synthetic sources",
        value=False,
    )


# ============================================================
# HEADER
# ============================================================

st.title("🛡️ Account Defense Lab")

st.caption(
    "Offline cybersecurity simulation environment"
)

st.warning(
    "Simulation only. No login request, network request, "
    "password test, or real account access is performed."
)

st.divider()


# ============================================================
# TOP CONTROLS
# ============================================================

col_a, col_b, col_c = st.columns(3)

with col_a:
    start = st.button(
        "▶️ Start Simulation",
        type="primary",
        use_container_width=True,
    )

with col_b:
    reset = st.button(
        "🔄 Reset",
        use_container_width=True,
    )

with col_c:
    st.metric(
        "Network Requests",
        "0",
    )


if reset:

    st.session_state.events = []
    st.session_state.metrics = {}
    st.session_state.report = {}
    st.session_state.completed = False
    st.session_state.running = False

    st.rerun()


# ============================================================
# START SIMULATION
# ============================================================

if start:

    if not target.strip():
        st.error(
            "Enter a synthetic account name."
        )
        st.stop()

    st.session_state.running = True
    st.session_state.completed = False
    st.session_state.events = []

    st.subheader(
        "🔴 Live Simulation"
    )

    progress = st.progress(0)

    status_col, metric_col = st.columns(2)

    with status_col:
        status_box = st.empty()

    with metric_col:
        live_detection = st.empty()

    console = st.empty()

    status_box.info(
        "Starting offline simulation..."
    )

    run_simulation(
        target=target.strip(),
        attempts=attempts,
        speed=speed,
        scenario=scenario,
        password_profile=password_profile,
        rate_limit=rate_limit,
        lockout_threshold=lockout_threshold,
        lockout_duration=lockout_duration,
        mfa_enabled=mfa_enabled,
        detection_sensitivity=detection_sensitivity,
        distributed_sources=distributed_sources,
        live_placeholder=None,
        progress_bar=progress,
        metrics_placeholder=live_detection,
        console_placeholder=console,
    )

    status_box.success(
        "Simulation completed."
    )

    st.rerun()


# ============================================================
# DASHBOARD
# ============================================================

metrics = st.session_state.metrics

if metrics:

    st.divider()

    st.header("📊 Security Dashboard")

    a, b, c, d, e = st.columns(5)

    a.metric(
        "Attempts",
        metrics["attempts"],
    )

    b.metric(
        "Blocked",
        metrics["blocked"],
    )

    c.metric(
        "Detected",
        metrics["detections"],
    )

    d.metric(
        "MFA Challenges",
        metrics["mfa_challenges"],
    )

    e.metric(
        "Risk",
        metrics["risk_level"],
    )

    st.divider()

    # ========================================================
    # SCORE
    # ========================================================

    score = metrics[
        "defense_effectiveness"
    ]

    st.subheader(
        "🛡️ Defense Effectiveness"
    )

    st.progress(
        score / 100
    )

    st.write(
        f"**{score:.1f} / 100**"
    )

    if metrics["risk_level"] == "LOW":

        st.success(
            "The simulated defense configuration "
            "performed well."
        )

    elif metrics["risk_level"] == "MEDIUM":

        st.warning(
            "The simulated defense configuration "
            "has room for improvement."
        )

    else:

        st.error(
            "The simulated configuration showed "
            "significant defensive weaknesses."
        )

    # ========================================================
    # CHARTS
    # ========================================================

    events_df = pd.DataFrame(
        st.session_state.events
    )

    if not events_df.empty:

        st.subheader(
            "📈 Simulation Metrics"
        )

        chart_df = pd.DataFrame(
            {
                "Attempt": events_df[
                    "attempt"
                ],
                "Detected": events_df[
                    "detected"
                ].astype(int),
                "Blocked": events_df[
                    "status"
                ].isin(
                    [
                        "LOCKED",
                        "LOCKOUT",
                        "RATE LIMITED",
                    ]
                ).astype(int),
                "MFA": events_df[
                    "mfa"
                ].astype(int),
            }
        )

        st.line_chart(
            chart_df.set_index(
                "Attempt"
            )
        )

        # ====================================================
        # RESULT DISTRIBUTION
        # ====================================================

        distribution = (
            events_df[
                "result"
            ]
            .value_counts()
            .rename_axis("Result")
            .reset_index(
                name="Count"
            )
        )

        st.bar_chart(
            distribution.set_index(
                "Result"
            )
        )

    # ========================================================
    # METRICS TABLE
    # ========================================================

    st.subheader(
        "📋 Detailed Metrics"
    )

    metrics_table = pd.DataFrame(
        [
            {
                "Metric": "Total attempts",
                "Value": metrics["attempts"],
            },
            {
                "Metric": "Normal requests",
                "Value": metrics["normal_requests"],
            },
            {
                "Metric": "Suspicious requests",
                "Value": metrics["suspicious_requests"],
            },
            {
                "Metric": "Allowed",
                "Value": metrics["allowed"],
            },
            {
                "Metric": "Failed",
                "Value": metrics["failed"],
            },
            {
                "Metric": "Blocked",
                "Value": metrics["blocked"],
            },
            {
                "Metric": "Synthetic matches",
                "Value": metrics[
                    "synthetic_matches"
                ],
            },
            {
                "Metric": "Detections",
                "Value": metrics["detections"],
            },
            {
                "Metric": "Rate limited",
                "Value": metrics[
                    "rate_limited"
                ],
            },
            {
                "Metric": "Lockouts",
                "Value": metrics["lockouts"],
            },
            {
                "Metric": "MFA challenges",
                "Value": metrics[
                    "mfa_challenges"
                ],
            },
            {
                "Metric": "Detection rate",
                "Value": (
                    f"{metrics['detection_rate']:.2f}%"
                ),
            },
            {
                "Metric": "Block rate",
                "Value": (
                    f"{metrics['block_rate']:.2f}%"
                ),
            },
            {
                "Metric": "Risk score",
                "Value": metrics["risk_score"],
            },
            {
                "Metric": "Duration",
                "Value": (
                    f"{metrics['duration_seconds']:.2f}s"
                ),
            },
        ]
    )

    st.dataframe(
        metrics_table,
        use_container_width=True,
        hide_index=True,
    )

    # ========================================================
    # EVENT LOG
    # ========================================================

    st.subheader(
        "🧾 Event Log"
    )

    st.dataframe(
        events_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "elapsed": st.column_config.NumberColumn(
                "Elapsed",
                format="%.3f",
            ),
            "detected": st.column_config.CheckboxColumn(
                "Detected"
            ),
            "mfa": st.column_config.CheckboxColumn(
                "MFA"
            ),
        },
    )

    # ========================================================
    # RECOMMENDATIONS
    # ========================================================

    st.subheader(
        "💡 Security Recommendations"
    )

    recommendations = []

    if metrics["detection_rate"] < 50:
        recommendations.append(
            "Increase behavioral detection sensitivity."
        )

    if metrics["block_rate"] < 30:
        recommendations.append(
            "Consider stricter rate limiting."
        )

    if not mfa_enabled:
        recommendations.append(
            "Enable MFA for stronger account protection."
        )

    if metrics["lockouts"] == 0:
        recommendations.append(
            "Consider adding an account protection threshold."
        )

    if metrics["detection_rate"] >= 70:
        recommendations.append(
            "Detection performance is strong in this simulation."
        )

    if metrics["rate_limited"] > 0:
        recommendations.append(
            "Rate limiting successfully reduced synthetic traffic pressure."
        )

    if metrics["mfa_challenges"] > 0:
        recommendations.append(
            "MFA successfully added an additional simulated defense layer."
        )

    for recommendation in recommendations:
        st.write(
            f"• {recommendation}"
        )

    # ========================================================
    # EXPORT
    # ========================================================

    st.subheader(
        "📦 Export"
    )

    report_json = json.dumps(
        st.session_state.report,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    events_csv = events_df.to_csv(
        index=False
    ).encode("utf-8")

    excel_buffer = io.BytesIO()

    with pd.ExcelWriter(
        excel_buffer,
        engine="openpyxl",
    ) as writer:

        events_df.to_excel(
            writer,
            sheet_name="Events",
            index=False,
        )

        metrics_table.to_excel(
            writer,
            sheet_name="Metrics",
            index=False,
        )

    excel_buffer.seek(0)

    x1, x2, x3 = st.columns(3)

    with x1:

        st.download_button(
            "⬇️ Events CSV",
            data=events_csv,
            file_name="security_simulation_events.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with x2:

        st.download_button(
            "⬇️ Excel Report",
            data=excel_buffer.getvalue(),
            file_name="security_simulation_report.xlsx",
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    with x3:

        st.download_button(
            "⬇️ JSON Report",
            data=report_json,
            file_name="security_simulation_report.json",
            mime="application/json",
            use_container_width=True,
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Account Defense Lab • Offline synthetic security simulator • "
    "Network Requests: 0"
)