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
# Configuration
# ============================================================

APP_TITLE = "Authorized Mining Control Center"

SSH_TIMEOUT = 10
COMMAND_TIMEOUT = 15

DEFAULT_MINER_COMMAND = "./miner"
DEFAULT_MINER_PROCESS = "miner"

# IMPORTANT:
# This application only operates on servers that the user
# explicitly adds and marks as authorized.
#
# It does NOT scan the public Internet for arbitrary servers,
# bypass authentication, or attempt access to servers without
# explicit authorization.


# ============================================================
# Page
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# Session State
# ============================================================

def init_state() -> None:
    defaults = {
        "servers": [],
        "logs": [],
        "wallet": "",
        "pool": "",
        "last_refresh": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# ============================================================
# Helpers
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def log_event(message: str, level: str = "INFO") -> None:
    st.session_state.logs.insert(
        0,
        {
            "time": utc_now(),
            "level": level,
            "message": message,
        },
    )

    st.session_state.logs = st.session_state.logs[:300]


def clean_host(value: str) -> str:
    value = value.strip()

    value = re.sub(
        r"^https?://",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = value.split("/")[0]

    return value.strip()


def valid_host(value: str) -> bool:
    if not value:
        return False

    if len(value) > 253:
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9_.:\-]+",
            value,
        )
    )


def valid_port(port: int) -> bool:
    return 1 <= int(port) <= 65535


def get_server(server_id: str) -> Optional[Dict[str, Any]]:
    for server in st.session_state.servers:
        if server["id"] == server_id:
            return server

    return None


def selected_authorized_servers() -> List[Dict[str, Any]]:
    return [
        server
        for server in st.session_state.servers
        if server.get("authorized")
        and server.get("selected")
    ]


def wallet_looks_valid(wallet: str) -> bool:
    wallet = wallet.strip()

    if len(wallet) < 10:
        return False

    if len(wallet) > 256:
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9_.:\-]+",
            wallet,
        )
    )


def pool_looks_valid(pool: str) -> bool:
    pool = pool.strip()

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9_.\-]+:\d{1,5}",
            pool,
        )
    )


# ============================================================
# SSH
# ============================================================

def load_private_key(private_key: str):
    errors = []

    key_classes = [
        paramiko.Ed25519Key,
        paramiko.RSAKey,
        paramiko.ECDSAKey,
        paramiko.DSSKey,
    ]

    for key_class in key_classes:
        try:
            from io import StringIO

            key_stream = StringIO(private_key)

            return key_class.from_private_key(key_stream)

        except Exception as exc:
            errors.append(str(exc))

    raise ValueError(
        "Unable to read SSH private key. "
        "Supported formats include RSA, ECDSA, DSS and Ed25519."
    )


def connect_ssh(
    server: Dict[str, Any],
) -> paramiko.SSHClient:

    client = paramiko.SSHClient()

    # For a production deployment, managed known_hosts is preferable.
    # This policy allows first-time connections without manual
    # known_hosts configuration.
    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    hostname = server["host"]
    port = int(server["port"])
    username = server["username"]

    private_key = server.get("private_key", "").strip()
    password = server.get("password", "").strip()

    if private_key:
        key = load_private_key(private_key)

        client.connect(
            hostname=hostname,
            port=port,
            username=username,
            pkey=key,
            timeout=SSH_TIMEOUT,
            banner_timeout=SSH_TIMEOUT,
            auth_timeout=SSH_TIMEOUT,
        )

    else:
        client.connect(
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            timeout=SSH_TIMEOUT,
            banner_timeout=SSH_TIMEOUT,
            auth_timeout=SSH_TIMEOUT,
        )

    return client


def ssh_command(
    server: Dict[str, Any],
    command: str,
    timeout: int = COMMAND_TIMEOUT,
) -> str:

    client = None

    try:
        client = connect_ssh(server)

        stdin, stdout, stderr = client.exec_command(
            command,
            timeout=timeout,
        )

        output = stdout.read().decode(
            "utf-8",
            errors="replace",
        )

        error = stderr.read().decode(
            "utf-8",
            errors="replace",
        )

        if error.strip():
            output = (
                output.rstrip()
                + "\n"
                + error.strip()
            ).strip()

        return output

    finally:
        if client:
            client.close()


# ============================================================
# Server Inspection
# ============================================================

def inspect_server(
    server: Dict[str, Any],
) -> Dict[str, Any]:

    result = {
        "online": False,
        "hostname": "",
        "os": "",
        "cpu": "",
        "ram": "",
        "uptime": "",
        "load": "",
        "error": "",
    }

    try:
        hostname = ssh_command(
            server,
            "hostname",
        )

        os_name = ssh_command(
            server,
            "uname -srm 2>/dev/null || echo unknown",
        )

        cpu = ssh_command(
            server,
            "nproc 2>/dev/null || getconf _NPROCESSORS_ONLN",
        )

        ram = ssh_command(
            server,
            "free -h 2>/dev/null | awk '/Mem:/ {print $3 \" / \" $2}'",
        )

        uptime = ssh_command(
            server,
            "uptime -p 2>/dev/null || uptime",
        )

        load = ssh_command(
            server,
            "awk '{print $1, $2, $3}' /proc/loadavg 2>/dev/null || echo N/A",
        )

        result.update(
            {
                "online": True,
                "hostname": hostname.strip(),
                "os": os_name.strip(),
                "cpu": cpu.strip(),
                "ram": ram.strip(),
                "uptime": uptime.strip(),
                "load": load.strip(),
            }
        )

    except Exception as exc:
        result["error"] = str(exc)

    server["online"] = result["online"]
    server["stats"] = result

    return result


# ============================================================
# Miner
# ============================================================

def miner_running(
    server: Dict[str, Any],
) -> bool:

    process = server.get(
        "miner_process",
        DEFAULT_MINER_PROCESS,
    ).strip()

    if not process:
        process = DEFAULT_MINER_PROCESS

    safe_process = shlex.quote(process)

    command = (
        f"pgrep -af {safe_process} "
        f"2>/dev/null || true"
    )

    try:
        output = ssh_command(
            server,
            command,
        )

        running = bool(output.strip())

        server["running"] = running

        return running

    except Exception:
        server["running"] = False
        return False


def start_mining(
    server: Dict[str, Any],
) -> Dict[str, Any]:

    if not server.get("authorized"):
        return {
            "success": False,
            "message": "Server is not marked as authorized.",
        }

    command = server.get(
        "miner_command",
        "",
    ).strip()

    if not command:
        return {
            "success": False,
            "message": "Miner command is empty.",
        }

    # The miner is assumed to already exist on the authorized server.
    # No remote software is downloaded automatically.
    remote_command = (
        "nohup "
        + command
        + " > ~/miner.log 2>&1 < /dev/null &"
    )

    try:
        ssh_command(
            server,
            remote_command,
        )

        server["running"] = True
        server["last_action"] = utc_now()

        log_event(
            f"Mining started: {server['name']}",
            "SUCCESS",
        )

        return {
            "success": True,
            "message": "Mining command started.",
        }

    except Exception as exc:
        server["running"] = False

        log_event(
            f"Start failed on {server['name']}: {exc}",
            "ERROR",
        )

        return {
            "success": False,
            "message": str(exc),
        }


def stop_mining(
    server: Dict[str, Any],
) -> Dict[str, Any]:

    process = server.get(
        "miner_process",
        DEFAULT_MINER_PROCESS,
    ).strip()

    if not process:
        process = DEFAULT_MINER_PROCESS

    safe_process = shlex.quote(process)

    command = (
        f"pkill -TERM -f {safe_process} "
        f"2>/dev/null || true"
    )

    try:
        ssh_command(
            server,
            command,
        )

        server["running"] = False
        server["last_action"] = utc_now()

        log_event(
            f"Mining stopped: {server['name']}",
            "SUCCESS",
        )

        return {
            "success": True,
            "message": "Mining stop command sent.",
        }

    except Exception as exc:
        log_event(
            f"Stop failed on {server['name']}: {exc}",
            "ERROR",
        )

        return {
            "success": False,
            "message": str(exc),
        }


# ============================================================
# Add / Remove Servers
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
        st.error(
            "Provide an SSH password or private key."
        )
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
            st.error(
                "This server already exists."
            )
            return False

    server = {
        "id": f"srv-{int(time.time() * 1000000)}",
        "name": name,
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "private_key": private_key,
        "miner_command": miner_command,
        "miner_process": (
            miner_process
            or DEFAULT_MINER_PROCESS
        ),
        "authorized": False,
        "selected": False,
        "online": False,
        "running": False,
        "hashrate": 0.0,
        "last_action": "",
        "stats": {},
    }

    st.session_state.servers.append(server)

    log_event(
        f"Server added: {name}. "
        "Authorization is required before mining.",
        "INFO",
    )

    return True


def remove_server(
    server_id: str,
) -> None:

    server = get_server(server_id)

    if not server:
        return

    if server.get("running"):
        st.error(
            "Stop mining before removing this server."
        )
        return

    st.session_state.servers = [
        s
        for s in st.session_state.servers
        if s["id"] != server_id
    ]

    log_event(
        f"Server removed: {server['name']}",
        "INFO",
    )


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:

    st.header("⛏️ Mining Settings")

    st.subheader("💰 Wallet")

    wallet = st.text_input(
        "Wallet address",
        value=st.session_state.wallet,
        type="password",
        placeholder="Enter your wallet address",
    )

    st.session_state.wallet = wallet

    if wallet and not wallet_looks_valid(wallet):
        st.warning(
            "Wallet format looks unusual. Verify it."
        )

    st.subheader("🌐 Mining Pool")

    pool = st.text_input(
        "Pool address",
        value=st.session_state.pool,
        placeholder="pool.example.com:3333",
    )

    st.session_state.pool = pool

    if pool and not pool_looks_valid(pool):
        st.warning(
            "Expected format: hostname:port"
        )

    st.divider()

    st.subheader("🔄 Monitoring")

    refresh = st.number_input(
        "Refresh interval",
        min_value=5,
        max_value=300,
        value=10,
        step=5,
    )

    st.divider()

    st.info(
        "Only servers you explicitly add and mark "
        "Authorized can be selected for mining."
    )


# ============================================================
# Header
# ============================================================

st.title("⛏️ Authorized Mining Control Center")

st.caption(
    "Manage mining workloads on explicitly authorized servers."
)


# ============================================================
# Metrics
# ============================================================

servers = st.session_state.servers

total = len(servers)

authorized = sum(
    bool(s.get("authorized"))
    for s in servers
)

selected = sum(
    bool(s.get("authorized"))
    and bool(s.get("selected"))
    for s in servers
)

online = sum(
    bool(s.get("online"))
    for s in servers
)

mining = sum(
    bool(s.get("running"))
    for s in servers
)

hashrate = sum(
    float(s.get("hashrate", 0) or 0)
    for s in servers
    if s.get("running")
)


a, b, c, d, e, f = st.columns(6)

a.metric("Servers", total)
b.metric("Authorized", authorized)
c.metric("Selected", selected)
d.metric("Online", online)
e.metric("Mining", mining)
f.metric("Hashrate", f"{hashrate:,.2f} H/s")


# ============================================================
# Add Server
# ============================================================

with st.expander(
    "➕ Add Server",
    expanded=not bool(servers),
):

    st.warning(
        "New servers are NOT authorized automatically. "
        "After adding a server, explicitly enable "
        "Authorized before selecting it."
    )

    with st.form(
        "add_server",
        clear_on_submit=True,
    ):

        c1, c2 = st.columns(2)

        with c1:

            name = st.text_input(
                "Server name",
                placeholder="Mining Server 01",
            )

            host = st.text_input(
                "Hostname / IP",
                placeholder="203.0.113.10",
            )

            port = st.number_input(
                "SSH port",
                min_value=1,
                max_value=65535,
                value=22,
            )

            username = st.text_input(
                "SSH username",
                placeholder="ubuntu",
            )

        with c2:

            password = st.text_input(
                "SSH password",
                type="password",
            )

            private_key = st.text_area(
                "SSH private key",
                height=140,
                placeholder=(
                    "-----BEGIN OPENSSH PRIVATE KEY-----"
                ),
            )

            miner_command = st.text_input(
                "Existing miner command",
                value=DEFAULT_MINER_COMMAND,
            )

            miner_process = st.text_input(
                "Miner process name",
                value=DEFAULT_MINER_PROCESS,
            )

        submit = st.form_submit_button(
            "➕ Add Server",
            use_container_width=True,
        )

        if submit:

            if add_server(
                name=name,
                host=host,
                port=int(port),
                username=username,
                password=password,
                private_key=private_key,
                miner_command=miner_command,
                miner_process=miner_process,
            ):
                st.success(
                    "Server added successfully."
                )

                st.rerun()


# ============================================================
# Global Controls
# ============================================================

st.subheader("🎛️ Controls")

c1, c2, c3, c4 = st.columns(4)

with c1:

    if st.button(
        "🔍 Test All",
        use_container_width=True,
        disabled=not servers,
    ):

        progress = st.progress(0)
        status = st.empty()

        for index, server in enumerate(
            servers,
            start=1,
        ):

            status.write(
                f"Testing {server['name']} "
                f"({index}/{total})"
            )

            inspect_server(server)

            progress.progress(
                index / total
            )

        st.session_state.last_refresh = utc_now()

        status.success(
            "Server test completed."
        )


with c2:

    selected_servers = selected_authorized_servers()

    if st.button(
        "▶️ Start Selected",
        type="primary",
        use_container_width=True,
        disabled=not selected_servers,
    ):

        if not wallet:
            st.error(
                "Enter your wallet address first."
            )

        elif not pool:
            st.error(
                "Enter your mining pool first."
            )

        elif not wallet_looks_valid(wallet):
            st.error(
                "Wallet format looks invalid."
            )

        elif not pool_looks_valid(pool):
            st.error(
                "Pool must use hostname:port format."
            )

        else:

            progress = st.progress(0)
            status = st.empty()

            for index, server in enumerate(
                selected_servers,
                start=1,
            ):

                status.write(
                    f"Starting {server['name']} "
                    f"({index}/{len(selected_servers)})"
                )

                result = start_mining(
                    server
                )

                if not result["success"]:
                    st.error(
                        f"{server['name']}: "
                        f"{result['message']}"
                    )

                progress.progress(
                    index / len(selected_servers)
                )

            status.success(
                "Start operation completed."
            )


with c3:

    running_servers = [
        s
        for s in servers
        if s.get("running")
    ]

    if st.button(
        "⏹️ Stop All",
        use_container_width=True,
        disabled=not running_servers,
    ):

        progress = st.progress(0)
        status = st.empty()

        for index, server in enumerate(
            running_servers,
            start=1,
        ):

            status.write(
                f"Stopping {server['name']} "
                f"({index}/{len(running_servers)})"
            )

            result = stop_mining(
                server
            )

            if not result["success"]:
                st.error(
                    f"{server['name']}: "
                    f"{result['message']}"
                )

            progress.progress(
                index / len(running_servers)
            )

        status.success(
            "Stop operation completed."
        )


with c4:

    if st.button(
        "🔄 Refresh",
        use_container_width=True,
        disabled=not servers,
    ):

        for server in servers:

            inspect_server(server)

            if server.get("online"):
                miner_running(server)

        st.session_state.last_refresh = utc_now()

        st.rerun()


# ============================================================
# Server List
# ============================================================

st.subheader("🖥️ Server List")

if not servers:

    st.info(
        "No servers added. Add your authorized servers above."
    )

else:

    for server in list(servers):

        with st.container(border=True):

            top1, top2, top3, top4 = st.columns(
                [3, 1, 1, 1]
            )

            with top1:

                st.markdown(
                    f"### {server['name']}"
                )

                st.caption(
                    f"{server['username']}@"
                    f"{server['host']}:"
                    f"{server['port']}"
                )

            with top2:

                if server.get("online"):
                    st.success("🟢 ONLINE")
                else:
                    st.error("🔴 OFFLINE")

            with top3:

                if server.get("running"):
                    st.success("⛏️ MINING")
                else:
                    st.info("⏹️ STOPPED")

            with top4:

                if server.get("authorized"):
                    st.success("AUTHORIZED")
                else:
                    st.warning("NOT AUTHORIZED")

            st.divider()

            c1, c2, c3, c4, c5, c6 = st.columns(
                [1.2, 1.5, 1.3, 1.3, 1.3, 1.3]
            )

            with c1:

                authorized_value = st.checkbox(
                    "Authorized",
                    value=bool(
                        server.get("authorized")
                    ),
                    key=f"authorized_{server['id']}",
                )

                server["authorized"] = (
                    authorized_value
                )

                if not authorized_value:
                    server["selected"] = False

            with c2:

                selected_value = st.checkbox(
                    "Select",
                    value=bool(
                        server.get("selected")
                    ),
                    disabled=not server.get(
                        "authorized"
                    ),
                    key=f"selected_{server['id']}",
                )

                server["selected"] = (
                    selected_value
                )

            with c3:

                if st.button(
                    "🔌 Test",
                    key=f"test_{server['id']}",
                    use_container_width=True,
                ):

                    with st.spinner(
                        "Connecting..."
                    ):

                        result = inspect_server(
                            server
                        )

                    if result["online"]:
                        st.success(
                            "Connection successful."
                        )
                    else:
                        st.error(
                            result["error"]
                        )

            with c4:

                if st.button(
                    "▶️ Start",
                    key=f"start_{server['id']}",
                    use_container_width=True,
                    disabled=(
                        not server.get(
                            "authorized"
                        )
                        or server.get(
                            "running"
                        )
                    ),
                ):

                    if not wallet or not pool:
                        st.error(
                            "Set wallet and pool first."
                        )

                    else:

                        result = start_mining(
                            server
                        )

                        if result["success"]:
                            st.success(
                                "Mining started."
                            )
                        else:
                            st.error(
                                result["message"]
                            )

            with c5:

                if st.button(
                    "⏹️ Stop",
                    key=f"stop_{server['id']}",
                    use_container_width=True,
                    disabled=not server.get(
                        "running"
                    ),
                ):

                    result = stop_mining(
                        server
                    )

                    if result["success"]:
                        st.success(
                            "Mining stopped."
                        )
                    else:
                        st.error(
                            result["message"]
                        )

            with c6:

                if st.button(
                    "✖ Remove",
                    key=f"remove_{server['id']}",
                    use_container_width=True,
                ):

                    if server.get("running"):
                        st.error(
                            "Stop mining before removing."
                        )

                    else:
                        remove_server(
                            server["id"]
                        )

                        st.rerun()

            # ------------------------------------------------
            # Server details
            # ------------------------------------------------

            stats = server.get(
                "stats",
                {},
            )

            if stats:

                d1, d2, d3, d4, d5 = st.columns(5)

                with d1:
                    st.metric(
                        "Hostname",
                        stats.get(
                            "hostname",
                            "N/A",
                        ),
                    )

                with d2:
                    st.metric(
                        "OS",
                        stats.get(
                            "os",
                            "N/A",
                        ),
                    )

                with d3:
                    st.metric(
                        "CPU",
                        stats.get(
                            "cpu",
                            "N/A",
                        ),
                    )

                with d4:
                    st.metric(
                        "RAM",
                        stats.get(
                            "ram",
                            "N/A",
                        ),
                    )

                with d5:
                    st.metric(
                        "Load",
                        stats.get(
                            "load",
                            "N/A",
                        ),
                    )

            if server.get("last_action"):
                st.caption(
                    f"Last action: "
                    f"{server['last_action']}"
                )


# ============================================================
# Logs
# ============================================================

st.subheader("📋 Activity")

if st.session_state.logs:

    logs_df = pd.DataFrame(
        st.session_state.logs
    )

    st.dataframe(
        logs_df,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "No activity recorded yet."
    )


# ============================================================
# Export
# ============================================================

st.subheader("📦 Export")

export_data = []

for server in servers:

    export_data.append(
        {
            "name": server["name"],
            "host": server["host"],
            "port": server["port"],
            "username": server["username"],
            "authorized": server["authorized"],
            "selected": server["selected"],
            "online": server["online"],
            "running": server["running"],
            "hashrate": server["hashrate"],
            "last_action": server["last_action"],
        }
    )

export_json = json.dumps(
    export_data,
    indent=2,
    ensure_ascii=False,
)

st.download_button(
    "📥 Download Server List JSON",
    data=export_json,
    file_name="authorized_servers.json",
    mime="application/json",
    use_container_width=True,
)


# ============================================================
# Footer
# ============================================================

st.divider()

st.caption(
    "Authorized-server management only. "
    "The application does not scan arbitrary Internet hosts, "
    "bypass authentication, or attempt unauthorized access."
)