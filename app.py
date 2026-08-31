import json
import re
import shlex
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import paramiko
import streamlit as st


# ============================================================
# Application Configuration
# ============================================================

APP_TITLE = "Authorized Mining Control Center"

DEFAULT_SSH_PORT = 22
DEFAULT_REFRESH_SECONDS = 10
SSH_TIMEOUT_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 15

# The miner must already exist on the authorized server.
# Example:
#   ./xmrig -o pool.example.com:3333 -u WALLET -p SERVER
DEFAULT_MINER_COMMAND = "./miner"

# Never automatically discover arbitrary Internet hosts.
# Servers must be explicitly added and authorized by the user.


# ============================================================
# Page Configuration
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# Styling
# ============================================================

st.markdown(
    """
    <style>
        .main {
            padding-top: 1rem;
        }

        .metric-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 12px;
            padding: 16px;
            min-height: 110px;
        }

        .status-online {
            font-weight: 700;
        }

        .status-offline {
            font-weight: 700;
        }

        .small-muted {
            opacity: 0.7;
            font-size: 0.85rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Session State
# ============================================================

def initialize_state() -> None:
    if "servers" not in st.session_state:
        st.session_state.servers = []

    if "logs" not in st.session_state:
        st.session_state.logs = []

    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = None

    if "global_running" not in st.session_state:
        st.session_state.global_running = False


initialize_state()


# ============================================================
# Utility Functions
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def add_log(message: str, level: str = "INFO") -> None:
    entry = {
        "time": now_utc(),
        "level": level,
        "message": message,
    }

    st.session_state.logs.insert(0, entry)

    # Prevent unlimited growth.
    st.session_state.logs = st.session_state.logs[:300]


def clean_host(host: str) -> str:
    host = host.strip()

    host = re.sub(r"^https?://", "", host, flags=re.IGNORECASE)
    host = host.split("/")[0]

    return host.strip()


def valid_host(host: str) -> bool:
    if not host:
        return False

    if len(host) > 253:
        return False

    # Accept IPv4, IPv6-like values, and hostnames.
    if re.match(r"^[A-Za-z0-9_.:\-]+$", host):
        return True

    return False


def valid_port(port: int) -> bool:
    return 1 <= int(port) <= 65535


def generate_server_id() -> str:
    return f"server-{int(time.time() * 1000)}"


def find_server(server_id: str) -> Optional[Dict[str, Any]]:
    for server in st.session_state.servers:
        if server["id"] == server_id:
            return server

    return None


def get_selected_servers() -> List[Dict[str, Any]]:
    return [
        server
        for server in st.session_state.servers
        if server.get("authorized", False)
        and server.get("selected", False)
    ]


# ============================================================
# SSH
# ============================================================

def create_ssh_client(
    hostname: str,
    port: int,
    username: str,
    password: Optional[str] = None,
    private_key: Optional[str] = None,
) -> paramiko.SSHClient:

    client = paramiko.SSHClient()

    # Known-host checking is preferred in production.
    # AutoAddPolicy is used here only to make first-time deployment
    # practical. Users should replace this with managed host keys
    # for high-security environments.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    if private_key:
        private_key = private_key.strip()

        key_file = paramiko.StringIO(private_key)

        key = None
        key_errors = []

        for key_class in (
            paramiko.Ed25519Key,
            paramiko.RSAKey,
            paramiko.ECDSAKey,
            paramiko.DSSKey,
        ):
            try:
                key_file.seek(0)
                key = key_class.from_private_key(key_file)
                break
            except Exception as exc:
                key_errors.append(str(exc))

        if key is None:
            raise ValueError("Unable to parse the SSH private key.")

        client.connect(
            hostname=hostname,
            port=port,
            username=username,
            pkey=key,
            timeout=SSH_TIMEOUT_SECONDS,
            banner_timeout=SSH_TIMEOUT_SECONDS,
            auth_timeout=SSH_TIMEOUT_SECONDS,
        )

    else:
        client.connect(
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            timeout=SSH_TIMEOUT_SECONDS,
            banner_timeout=SSH_TIMEOUT_SECONDS,
            auth_timeout=SSH_TIMEOUT_SECONDS,
        )

    return client


def execute_ssh(
    server: Dict[str, Any],
    command: str,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> str:

    client = None

    try:
        client = create_ssh_client(
            hostname=server["host"],
            port=int(server["port"]),
            username=server["username"],
            password=server.get("password"),
            private_key=server.get("private_key"),
        )

        stdin, stdout, stderr = client.exec_command(
            command,
            timeout=timeout,
        )

        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")

        if error.strip():
            output = f"{output}\n{error}".strip()

        return output

    finally:
        if client is not None:
            client.close()


# ============================================================
# Server Commands
# ============================================================

def get_server_stats(server: Dict[str, Any]) -> Dict[str, Any]:
    commands = {
        "hostname": "hostname",
        "uptime": "uptime -p 2>/dev/null || uptime",
        "cpu": "nproc 2>/dev/null || getconf _NPROCESSORS_ONLN",
        "ram": "free -m 2>/dev/null | awk '/Mem:/ {print $3 \"/\" $2 \" MB\"}'",
        "load": "awk '{print $1,$2,$3}' /proc/loadavg 2>/dev/null || echo N/A",
    }

    result = {
        "online": False,
        "hostname": "",
        "uptime": "",
        "cpu": "",
        "ram": "",
        "load": "",
        "error": "",
    }

    try:
        hostname = execute_ssh(server, commands["hostname"])
        uptime = execute_ssh(server, commands["uptime"])
        cpu = execute_ssh(server, commands["cpu"])
        ram = execute_ssh(server, commands["ram"])
        load = execute_ssh(server, commands["load"])

        result.update(
            {
                "online": True,
                "hostname": hostname.strip(),
                "uptime": uptime.strip(),
                "cpu": cpu.strip(),
                "ram": ram.strip(),
                "load": load.strip(),
            }
        )

    except Exception as exc:
        result["error"] = str(exc)

    return result


def get_miner_status(server: Dict[str, Any]) -> Dict[str, Any]:
    miner_name = server.get("miner_process", "").strip()

    if not miner_name:
        miner_name = "miner"

    safe_name = shlex.quote(miner_name)

    command = (
        f"pgrep -af {safe_name} 2>/dev/null || true"
    )

    try:
        output = execute_ssh(server, command)

        running = bool(output.strip())

        return {
            "running": running,
            "output": output.strip(),
            "error": "",
        }

    except Exception as exc:
        return {
            "running": False,
            "output": "",
            "error": str(exc),
        }


def start_miner(server: Dict[str, Any]) -> Dict[str, Any]:
    if not server.get("authorized", False):
        return {
            "success": False,
            "message": "Server is not authorized.",
        }

    command = server.get("miner_command", "").strip()

    if not command:
        return {
            "success": False,
            "message": "Miner command is empty.",
        }

    # Run an already-installed miner in the background.
    #
    # The command itself is supplied by the user for their authorized
    # server. We do not download software or scan external servers.
    remote_command = (
        "nohup "
        + command
        + " > ~/miner.log 2>&1 < /dev/null &"
    )

    try:
        execute_ssh(server, remote_command, timeout=COMMAND_TIMEOUT_SECONDS)

        server["running"] = True
        server["last_action"] = now_utc()

        add_log(
            f"Mining started on {server['name']}.",
            "SUCCESS",
        )

        return {
            "success": True,
            "message": "Mining start command sent.",
        }

    except Exception as exc:
        server["running"] = False

        add_log(
            f"Failed to start mining on {server['name']}: {exc}",
            "ERROR",
        )

        return {
            "success": False,
            "message": str(exc),
        }


def stop_miner(server: Dict[str, Any]) -> Dict[str, Any]:
    miner_process = server.get("miner_process", "").strip()

    if not miner_process:
        miner_process = "miner"

    safe_process = shlex.quote(miner_process)

    command = (
        f"pkill -TERM -f {safe_process} 2>/dev/null || true"
    )

    try:
        execute_ssh(server, command)

        server["running"] = False
        server["last_action"] = now_utc()

        add_log(
            f"Mining stopped on {server['name']}.",
            "SUCCESS",
        )

        return {
            "success": True,
            "message": "Mining stop command sent.",
        }

    except Exception as exc:
        add_log(
            f"Failed to stop mining on {server['name']}: {exc}",
            "ERROR",
        )

        return {
            "success": False,
            "message": str(exc),
        }


# ============================================================
# Wallet / Pool Validation
# ============================================================

def looks_like_wallet(value: str) -> bool:
    value = value.strip()

    if not value:
        return False

    if len(value) < 10:
        return False

    if len(value) > 256:
        return False

    return bool(re.match(r"^[A-Za-z0-9_\-\.]+$", value))


def looks_like_pool(value: str) -> bool:
    value = value.strip()

    if not value:
        return False

    if len(value) > 253:
        return False

    return bool(
        re.match(
            r"^[A-Za-z0-9_.\-]+:\d{1,5}$",
            value,
        )
    )


# ============================================================
# Server Management
# ============================================================

def add_server(
    name: str,
    host: str,
    port: int,
    username: str,
    password: str,
    private_key: str,
    miner_command: str,
    miner_process: str,
) -> bool:

    name = name.strip()
    host = clean_host(host)
    username = username.strip()
    password = password.strip()
    private_key = private_key.strip()
    miner_command = miner_command.strip()
    miner_process = miner_process.strip()

    if not name:
        st.error("Server name is required.")
        return False

    if not valid_host(host):
        st.error("Invalid hostname or IP address.")
        return False

    if not valid_port(port):
        st.error("Invalid SSH port.")
        return False

    if not username:
        st.error("SSH username is required.")
        return False

    if not password and not private_key:
        st.error("Provide either an SSH password or private key.")
        return False

    if not miner_command:
        st.error("Miner command is required.")
        return False

    for existing in st.session_state.servers:
        if (
            existing["host"].lower() == host.lower()
            and int(existing["port"]) == int(port)
            and existing["username"] == username
        ):
            st.error("This server already exists.")
            return False

    server = {
        "id": generate_server_id(),
        "name": name,
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "private_key": private_key,
        "miner_command": miner_command,
        "miner_process": miner_process or "miner",
        "authorized": False,
        "selected": False,
        "online": False,
        "running": False,
        "hashrate": 0.0,
        "last_action": "",
        "stats": {},
    }

    st.session_state.servers.append(server)

    add_log(
        f"Added server '{name}'. Authorization is required before mining.",
        "INFO",
    )

    return True


def remove_server(server_id: str) -> None:
    server = find_server(server_id)

    if not server:
        return

    if server.get("running"):
        st.warning(
            f"Stop mining on {server['name']} before removing it."
        )
        return

    st.session_state.servers = [
        s
        for s in st.session_state.servers
        if s["id"] != server_id
    ]

    add_log(
        f"Removed server '{server['name']}'.",
        "INFO",
    )


def test_server(server: Dict[str, Any]) -> Dict[str, Any]:
    stats = get_server_stats(server)

    server["online"] = stats["online"]
    server["stats"] = stats

    if stats["online"]:
        add_log(
            f"{server['name']} is online.",
            "SUCCESS",
        )
    else:
        add_log(
            f"{server['name']} is offline: {stats.get('error', 'Unknown error')}",
            "ERROR",
        )

    return stats


# ============================================================
# Refresh
# ============================================================

def refresh_all_servers() -> None:
    for server in st.session_state.servers:
        stats = get_server_stats(server)

        server["online"] = stats["online"]
        server["stats"] = stats

        if stats["online"]:
            miner = get_miner_status(server)

            if not miner["error"]:
                server["running"] = miner["running"]


# ============================================================
# Export
# ============================================================

def export_servers_json() -> str:
    safe_servers = []

    for server in st.session_state.servers:
        copy = dict(server)

        # Never export credentials.
        copy.pop("password", None)
        copy.pop("private_key", None)

        safe_servers.append(copy)

    return json.dumps(
        safe_servers,
        indent=2,
        ensure_ascii=False,
    )


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.header("⚙️ Control Center")

    st.subheader("Wallet")

    wallet = st.text_input(
        "Wallet address",
        type="password",
        help="Used by your miner command/configuration.",
    )

    pool = st.text_input(
        "Mining pool",
        placeholder="pool.example.com:3333",
    )

    if wallet and not looks_like_wallet(wallet):
        st.warning("Wallet format looks unusual. Verify it before starting.")

    if pool and not looks_like_pool(pool):
        st.warning("Pool should normally look like host:port.")

    st.divider()

    refresh_seconds = st.number_input(
        "Refresh interval (seconds)",
        min_value=5,
        max_value=300,
        value=DEFAULT_REFRESH_SECONDS,
        step=5,
    )

    st.divider()

    st.subheader("Safety")

    st.info(
        "Only servers manually added to this application and explicitly "
        "marked Authorized can be selected for mining."
    )

    st.divider()

    if st.button(
        "🔄 Refresh All Servers",
        use_container_width=True,
    ):
        with st.spinner("Refreshing server status..."):
            refresh_all_servers()

        st.session_state.last_refresh = now_utc()
        st.rerun()

    if st.download_button(
        "📥 Export Server List",
        data=export_servers_json(),
        file_name="authorized_servers.json",
        mime="application/json",
        use_container_width=True,
    ):
        pass


# ============================================================
# Header
# ============================================================

st.title("⛏️ Authorized Mining Control Center")

st.caption(
    "Manage mining workloads on servers you explicitly control or are authorized to use."
)


# ============================================================
# Add Server
# ============================================================

with st.expander("➕ Add Authorized Server", expanded=not st.session_state.servers):
    st.warning(
        "Adding a server does not authorize it automatically. "
        "You must explicitly mark it Authorized before mining."
    )

    with st.form("add_server_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            server_name = st.text_input(
                "Server name",
                placeholder="My Mining Server 01",
            )

            server_host = st.text_input(
                "Hostname / IP",
                placeholder="192.168.1.10",
            )

            server_port = st.number_input(
                "SSH port",
                min_value=1,
                max_value=65535,
                value=DEFAULT_SSH_PORT,
            )

            ssh_username = st.text_input(
                "SSH username",
                placeholder="ubuntu",
            )

        with col2:
            ssh_password = st.text_input(
                "SSH password",
                type="password",
            )

            ssh_private_key = st.text_area(
                "SSH private key",
                type="password",
                height=120,
                placeholder="-----BEGIN OPENSSH PRIVATE KEY-----",
            )

            miner_command = st.text_input(
                "Miner command",
                value=DEFAULT_MINER_COMMAND,
                help=(
                    "Command for a miner already installed on the server."
                ),
            )

            miner_process = st.text_input(
                "Miner process name",
                value="miner",
            )

        submitted = st.form_submit_button(
            "➕ Add Server",
            use_container_width=True,
        )

        if submitted:
            success = add_server(
                name=server_name,
                host=server_host,
                port=int(server_port),
                username=ssh_username,
                password=ssh_password,
                private_key=ssh_private_key,
                miner_command=miner_command,
                miner_process=miner_process,
            )

            if success:
                st.success(
                    "Server added. Authorize it below before selecting it."
                )
                st.rerun()


# ============================================================
# Statistics
# ============================================================

servers = st.session_state.servers

total_servers = len(servers)
authorized_servers = sum(
    1 for s in servers if s.get("authorized")
)
selected_servers = sum(
    1
    for s in servers
    if s.get("authorized") and s.get("selected")
)
online_servers = sum(
    1 for s in servers if s.get("online")
)
running_servers = sum(
    1 for s in servers if s.get("running")
)

total_hashrate = sum(
    float(s.get("hashrate", 0) or 0)
    for s in servers
    if s.get("running")
)


m1, m2, m3, m4, m5, m6 = st.columns(6)

m1.metric("Total Servers", total_servers)
m2.metric("Authorized", authorized_servers)
m3.metric("Selected", selected_servers)
m4.metric("Online", online_servers)
m5.metric("Mining", running_servers)
m6.metric("Hashrate", f"{total_hashrate:,.2f} H/s")


# ============================================================
# Global Controls
# ============================================================

st.subheader("🎛️ Mining Controls")

control1, control2, control3 = st.columns(3)

with control1:
    start_all = st.button(
        "▶️ Start Selected",
        type="primary",
        use_container_width=True,
        disabled=selected_servers == 0,
    )

with control2:
    stop_all = st.button(
        "⏹️ Stop All",
        use_container_width=True,
        disabled=running_servers == 0,
    )

with control3:
    check_selected = st.button(
        "🔍 Test Selected",
        use_container_width=True,
        disabled=selected_servers == 0,
    )


# ============================================================
# Start Selected
# ============================================================

if start_all:
    if not wallet:
        st.error("Enter your wallet address before starting mining.")

    elif not pool:
        st.error("Enter your mining pool before starting mining.")

    elif not looks_like_wallet(wallet):
        st.error("Wallet address format looks invalid.")

    elif not looks_like_pool(pool):
        st.error("Mining pool must look like host:port.")

    else:
        selected = get_selected_servers()

        progress = st.progress(0)
        status = st.empty()

        for index, server in enumerate(selected, start=1):
            status.write(
                f"Starting mining on {server['name']} "
                f"({index}/{len(selected)})..."
            )

            result = start_miner(server)

            if not result["success"]:
                st.error(
                    f"{server['name']}: {result['message']}"
                )

            progress.progress(
                index / len(selected)
            )

        status.success("Start operation completed.")
        st.session_state.global_running = True


# ============================================================
# Stop All
# ============================================================

if stop_all:
    running = [
        s
        for s in st.session_state.servers
        if s.get("running")
    ]

    progress = st.progress(0)
    status = st.empty()

    for index, server in enumerate(running, start=1):
        status.write(
            f"Stopping {server['name']} "
            f"({index}/{len(running)})..."
        )

        result = stop_miner(server)

        if not result["success"]:
            st.error(
                f"{server['name']}: {result['message']}"
            )

        progress.progress(
            index / len(running)
        )

    st.session_state.global_running = False

    status.success("Stop operation completed.")


# ============================================================
# Test Selected
# ============================================================

if check_selected:
    selected = get_selected_servers()

    progress = st.progress(0)
    status = st.empty()

    for index, server in enumerate(selected, start=1):
        status.write(
            f"Testing {server['name']} "
            f"({index}/{len(selected)})..."
        )

        test_server(server)

        progress.progress(
            index / len(selected)
        )

    status.success("Server checks completed.")


# ============================================================
# Server Table / Controls
# ============================================================

st.subheader("🖥️ Servers")

if not servers:
    st.info(
        "No servers have been added yet. Add an authorized server above."
    )
else:
    for server in list(st.session_state.servers):

        with st.container(border=True):

            top1, top2, top3, top4, top5 = st.columns(
                [2.2, 1.2, 1.2, 1.5, 1.2]
            )

            with top1:
                st.markdown(
                    f"### {server['name']}"
                )

                st.caption(
                    f"{server['username']}@"
                    f"{server['host']}:{server['port']}"
                )

            with top2:
                if server.get("online"):
                    st.success("ONLINE")
                else:
                    st.error("OFFLINE")

            with top3:
                if server.get("running"):
                    st.success("MINING")
                else:
                    st.info("STOPPED")

            with top4:
                st.metric(
                    "Hashrate",
                    f"{float(server.get('hashrate', 0) or 0):,.2f} H/s",
                )

            with top5:
                authorized = st.checkbox(
                    "Authorized",
                    value=bool(server.get("authorized")),
                    key=f"auth_{server['id']}",
                )

                server["authorized"] = authorized

            st.divider()

            c1, c2, c3, c4, c5, c6 = st.columns(6)

            with c1:
                selected = st.checkbox(
                    "Select",
                    value=bool(server.get("selected")),
                    key=f"select_{server['id']}",
                    disabled=not server.get("authorized"),
                )

                server["selected"] = selected

            with c2:
                if st.button(
                    "🔌 Test",
                    key=f"test_{server['id']}",
                    use_container_width=True,
                ):
                    with st.spinner("Testing..."):
                        stats = test_server(server)

                    if stats["online"]:
                        st.success("Connection OK")
                    else:
                        st.error(
                            stats.get(
                                "error",
                                "Connection failed",
                            )
                        )

            with c3:
                if st.button(
                    "▶️ Start",
                    key=f"start_{server['id']}",
                    use_container_width=True,
                    disabled=(
                        not server.get("authorized")
                        or server.get("running")
                    ),
                ):
                    if not wallet or not pool:
                        st.error(
                            "Set wallet and pool in the sidebar first."
                        )
                    else:
                        result = start_miner(server)

                        if result["success"]:
                            st.success("Start command sent.")
                        else:
                            st.error(result["message"])

            with c4:
                if st.button(
                    "⏹️ Stop",
                    key=f"stop_{server['id']}",
                    use_container_width=True,
                    disabled=not server.get("running"),
                ):
                    result = stop_miner(server)

                    if result["success"]:
                        st.success("Stop command sent.")
                    else:
                        st.error(result["message"])

            with c5:
                if st.button(
                    "🔄 Refresh",
                    key=f"refresh_{server['id']}",
                    use_container_width=True,
                ):
                    with st.spinner("Refreshing..."):
                        test_server(server)

                    st.rerun()

            with c6:
                if st.button(
                    "🗑️ Remove",
                    key=f"remove_{server['id']}",
                    use_container_width=True,
                ):
                    remove_server(server["id"])
                    st.rerun()

            stats = server.get("stats", {})

            if stats:
                s1, s2, s3, s4 = st.columns(4)

                with s1:
                    st.metric(
                        "Hostname",
                        stats.get("hostname", "N/A"),
                    )

                with s2:
                    st.metric(
                        "CPU",
                        stats.get("cpu", "N/A"),
                    )

                with s3:
                    st.metric(
                        "RAM",
                        stats.get("ram", "N/A"),
                    )

                with s4:
                    st.metric(
                        "Load",
                        stats.get("load", "N/A"),
                    )

            if server.get("last_action"):
                st.caption(
                    f"Last action: {server['last_action']}"
                )


# ============================================================
# Logs
# ============================================================

st.subheader("📋 Activity Log")

if not st.session_state.logs:
    st.info("No activity yet.")
else:
    log_df = pd.DataFrame(
        st.session_state.logs,
        columns=["time", "level", "message"],
    )

    st.dataframe(
        log_df,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# Footer
# ============================================================

st.divider()

st.caption(
    "This control panel only operates on servers explicitly added and "
    "authorized by the operator. It does not scan the public Internet "
    "for arbitrary servers or attempt to bypass authentication, "
    "firewalls, rate limits, or other access controls."
)