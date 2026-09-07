# app.py
# Python 3.11+ / Streamlit 1.40+
# Dependencies: streamlit, pandas
#
# Purpose:
#   Local defensive dashboard for inspecting a user-provided network inventory.
# Inputs:
#   CSV with: ip, mac, hostname, vendor, signal_dbm
# Outputs:
#   Filterable inventory + basic security observations.
#
# Run:
#   pip install streamlit pandas
#   streamlit run app.py

import io
import pandas as pd
import streamlit as st

REQUIRED_COLUMNS = {
    "ip",
    "mac",
    "hostname",
    "vendor",
    "signal_dbm",
}

st.set_page_config(
    page_title="Wi-Fi Security Lab",
    page_icon="📡",
    layout="wide",
)

st.title("📡 Wi-Fi Security Lab")
st.caption("Defensive inventory dashboard for networks you own or administer.")

uploaded = st.file_uploader(
    "Upload your authorized network inventory CSV",
    type=["csv"],
)

if uploaded is None:
    st.info(
        "CSV columns: ip, mac, hostname, vendor, signal_dbm"
    )
    st.stop()

try:
    raw = pd.read_csv(io.BytesIO(uploaded.getvalue()))
except Exception as exc:
    st.error(f"Invalid CSV: {exc}")
    st.stop()

missing = REQUIRED_COLUMNS - set(raw.columns)
if missing:
    st.error(
        "Missing required columns: "
        + ", ".join(sorted(missing))
    )
    st.stop()

df = raw.copy()
df["signal_dbm"] = pd.to_numeric(
    df["signal_dbm"],
    errors="coerce",
)

search = st.text_input(
    "Search",
    placeholder="IP, MAC, hostname, or vendor...",
)

if search:
    searchable = (
        df.astype(str)
        .apply(lambda col: col.str.contains(search, case=False, na=False))
        .any(axis=1)
    )
    df = df[searchable]

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Devices", len(df))

with col2:
    st.metric(
        "Unique vendors",
        df["vendor"].replace("", pd.NA).nunique(),
    )

with col3:
    weak_signal = (df["signal_dbm"] < -75).sum()
    st.metric("Weak signal", int(weak_signal))

st.subheader("Authorized Device Inventory")

st.dataframe(
    df.sort_values(
        by=["signal_dbm", "ip"],
        ascending=[False, True],
    ),
    use_container_width=True,
    hide_index=True,
)

st.subheader("Defensive Checks")

checks = pd.DataFrame(
    {
        "Check": [
            "Missing hostname",
            "Missing vendor",
            "Weak signal (< -75 dBm)",
            "Duplicate MAC",
            "Duplicate IP",
        ],
        "Count": [
            int(df["hostname"].isna().sum()),
            int(df["vendor"].isna().sum()),
            int((df["signal_dbm"] < -75).sum()),
            int(df["mac"].duplicated(keep=False).sum()),
            int(df["ip"].duplicated(keep=False).sum()),
        ],
    }
)

st.dataframe(
    checks,
    use_container_width=True,
    hide_index=True,
)

csv_bytes = df.to_csv(index=False).encode("utf-8")

st.download_button(
    "Export filtered inventory",
    data=csv_bytes,
    file_name="authorized_wifi_inventory.csv",
    mime="text/csv",
)