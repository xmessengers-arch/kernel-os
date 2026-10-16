#!/usr/bin/env python3
"""KERNEL OS v4.0 вЂ” Server Kernel (РЇРґСЂРѕ)"""

import socket
import threading
import json
import hashlib
import time
import os
import re
from datetime import datetime, timezone
from filesystem import VirtualFS
from economy import Economy

HOST = os.environ.get("KERNEL_HOST", "0.0.0.0")
PORT = int(os.environ.get("KERNEL_PORT", "4077"))
VERSION = "4.0.0"
PROTOCOL = "1.0"
EKEY_LEN = 105
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kernel_state.json")

ROLE_RANK = {"user": 0, "support": 1, "moderator": 2, "manager": 3, "root": 4}
ROLES = list(ROLE_RANK.keys())

DEFAULT_USERS = {
    "root": {"password": "root", "role": "root", "units": 999999, "plus": None, "nfts": [], "cwd": "/", "fs": {"/": {"dirs": ["app", "logs", "RPM"], "files": {}}}},
    "manager": {"password": "manager", "role": "manager", "units": 1000, "plus": None, "nfts": [], "cwd": "/", "fs": {"/": {"dirs": ["app"], "files": {}}}},
    "moderator": {"password": "moderator", "role": "moderator", "units": 0, "plus": None, "nfts": [], "cwd": "/", "fs": {"/": {"dirs": [], "files": {}}}},
    "support": {"password": "support", "role": "support", "units": 0, "plus": None, "nfts": [], "cwd": "/", "fs": {"/": {"dirs": ["logs"], "files": {}}}},
    "user": {"password": "user", "role": "user", "units": 10, "plus": None, "nfts": [], "cwd": "/", "fs": {"/": {"dirs": [], "files": {}}}},
}

RPM_AVAILABLE = ["firefox", "htop", "nano", "curl", "mc"]


def xor_crypt(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def derive_key(ekey: str) -> bytes:
    return hashlib.sha256(ekey.encode()).digest()


def now_gmt():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S GMT")


class KernelServer:
    def __init__(self):
        self.state = self.load_state()
        self.fs = VirtualFS(self.state)
        self.econ = Economy(self.state)
        self.lock = threading.Lock()

    def load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
        return {"users": dict(DEFAULT_USERS), "bans": {}, "mutes": {}, "warns": {}, "logs": []}

    def save(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def log(self, msg):
        entry = {"ts": now_gmt(), "msg": msg}
        self.state.setdefault("logs", []).append(entry)
        print(f"[LOG] {msg}")

    def send_enc(self, conn, key, text):
        payload = xor_crypt(text.encode(), key)
        conn.sendall(len(payload).to_bytes(4, "big") + payload)

    def recv_enc(self, conn, key):
        header = self._recv_exact(conn, 4)
        if not header:
            return ""
        length = int.from_bytes(header, "big")
        data = self._recv_exact(conn, length)
        if not data:
            return ""
        return xor_crypt(data, key).decode().strip()

    def _recv_exact(self, conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def handle_client(self, conn, addr):
        print(f"[CONN] {addr} connected")
        conn.settimeout(300)
        key = None
        user = None
        role = None
        try:
            prompt = "E-Key Handshake: enter 105-char E-Key (A-Za-z0-9):\n"
            plen = len(prompt.encode())
            conn.sendall(plen.to_bytes(4, "big") + prompt.encode())
            ekey_len_raw = self._recv_exact(conn, 4)
            if not ekey_len_raw:
                conn.close()
                return
            ekey_len = int.from_bytes(ekey_len_raw, "big")
            ekey_raw = self._recv_exact(conn, ekey_len)
            if not ekey_raw:
                conn.close()
                return
            ekey = ekey_raw.decode().strip()
            if len(ekey) != EKEY_LEN or not ekey.isalnum():
                err = "Invalid E-Key length or charset. Aborting.\n"
                elen = len(err.encode())
                conn.sendall(elen.to_bytes(4, "big") + err.encode())
                conn.close()
                return
            key = derive_key(ekey)
            self.send_enc(conn, key, "E-Key accepted. Secure channel established.\n")

            self.send_enc(conn, key, "Username: ")
            username = self.recv_enc(conn, key)
            self.send_enc(conn, key, "Password: ")
            password = self.recv_enc(conn, key)

            if username not in self.state["users"]:
                self.send_enc(conn, key, "Unknown user. Aborting.\n")
                conn.close()
                return
            if self.state["users"][username]["password"] != password:
                self.send_enc(conn, key, "Wrong password. Aborting.\n")
                conn.close()
                return
            if username in self.state.get("bans", {}):
                self.send_enc(conn, key, f"Account banned: {self.state['bans'][username]}\n")
                conn.close()
                return

            self.send_enc(conn, key, "2FA Code (from mobile app): ")
            code = self.recv_enc(conn, key)
            if len(code) != 6 or not code.isdigit():
                self.send_enc(conn, key, "Invalid 2FA code. Aborting.\n")
                conn.close()
                return

            user = username
            role = self.state["users"][username]["role"]
            self.log(f"{user} ({role}) connected from {addr[0]}")

            welcome = (
                "\n"
                "============================================\n"
                f"   KERNEL OS v{VERSION} вЂ” JADRA\n"
                f"   {now_gmt()}\n"
                "============================================\n"
                f"Logged in as: {user} [{role}]\n"
                "Type 'help' for commands.\n"
            )
            self.send_enc(conn, key, welcome)

            while True:
                prompt = f"terminal$ {user} > " if ROLE_RANK.get(role, 0) < ROLE_RANK["manager"] else f"terminal# {user} > "
                self.send_enc(conn, key, prompt)
                line = self.recv_enc(conn, key)
                if not line:
                    break
                if line in ("exit", "logout", "quit"):
                    self.send_enc(conn, key, "Goodbye.\n")
                    break
                parts = line.split()
                cmd = parts[0].lower()
                args = parts[1:]
                out = self.dispatch(user, role, cmd, args)
                self.send_enc(conn, key, out + "\n")
            self.log(f"{user} disconnected")
        except (socket.timeout, ConnectionResetError, BrokenPipeError, OSError):
            pass
        except Exception as e:
            print(f"[ERR] {addr}: {e}")
        finally:
            conn.close()

    def dispatch(self, user, role, cmd, args):
        rank = ROLE_RANK.get(role, 0)

        if cmd == "time":
            return now_gmt()
        if cmd == "version":
            return f"KERNEL OS {VERSION} | Protocol {PROTOCOL}"
        if cmd == "clear":
            return "\033[2J\033[H"
        if cmd == "help":
            return self.help_text(role)
        if cmd == "whoami":
            return f"{user} [{role}]"
        if cmd == "pwd":
            if rank < ROLE_RANK["manager"]:
                return "Permission denied."
            return self.fs.cwd(user)
        if cmd == "ping":
            return "pong"
        if cmd == "status":
            units, plus = self.econ.balance(user)
            plus_s = "active" if self.econ.plus_active(user) else ("expired" if plus else "none")
            return f"user={user} role={role} units={units} plus={plus_s} cwd={self.fs.cwd(user) if rank >= ROLE_RANK['manager'] else 'n/a'}"

        # FS
        fs_cmds = {"cd", "mkdir", "d", "dir", "rmdir", "ls", "touch", "cat", "echo"}
        if cmd in fs_cmds:
            if rank < ROLE_RANK["manager"]:
                if role == "support" and cmd in ("ls", "dir"):
                    cwd = self.fs.cwd(user)
                    if cwd == "/logs" or cwd.startswith("/logs/"):
                        pass
                    else:
                        return "support can only inspect /logs"
                else:
                    return "Permission denied: FS requires manager+."

        if cmd == "cd":
            if not args:
                return "Usage: cd {path}"
            ok = self.fs.cd(user, args[0])
            return f"cd -> {self.fs.cwd(user)}" if ok else "No such directory."
        if cmd == "mkdir":
            if not args:
                return "Usage: mkdir {name}"
            self.fs.mkdir(user, args[0])
            with self.lock:
                self.save()
            return f"Created: {self.fs._join(self.fs.cwd(user), args[0])}"
        if cmd in ("d", "dir", "rmdir"):
            if not args:
                return f"Usage: {cmd} {{name}}"
            ok = self.fs.rmdir(user, args[0])
            with self.lock:
                self.save()
            return "Removed." if ok else "Not found."
        if cmd == "ls":
            dirs, files = self.fs.ls(user)
            if not dirs and not files:
                return "(empty)"
            out = []
            for d in dirs:
                out.append(f"[DIR]  {d}")
            for f in files:
                out.append(f"[FILE] {f}")
            return "\n".join(out)
        if cmd == "touch":
            if not args:
                return "Usage: touch {name}"
            self.fs.write_file(user, args[0], "")
            with self.lock:
                self.save()
            return f"Touched: {args[0]}"
        if cmd == "cat":
            if not args:
                return "Usage: cat {name}"
            content = self.fs.read_file(user, args[0])
            return content if content is not None else "Not found."
        if cmd == "echo":
            if len(args) < 2 or args[1] not in (">", ">>"):
                return "Usage: echo {text} > {file}"
            text = args[0]
            fname = args[2]
            self.fs.write_file(user, fname, text)
            with self.lock:
                self.save()
            return f"Written to {fname}"

        # Moderation
        if cmd in ("ban", "unban", "mute", "warn"):
            if rank < ROLE_RANK["moderator"]:
                return "Permission denied: moderation requires moderator+."
            if not args:
                return f"Usage: {cmd} {{username}}"
            target = args[0].lstrip("@")
            if cmd == "ban":
                reason = " ".join(args[1:]) or "no reason"
                self.state.setdefault("bans", {})[target] = reason
                self.log(f"{user} banned {target}: {reason}")
                with self.lock:
                    self.save()
                return f"Banned {target}: {reason}"
            if cmd == "unban":
                self.state.get("bans", {}).pop(target, None)
                self.log(f"{user} unbanned {target}")
                with self.lock:
                    self.save()
                return f"Unbanned {target}"
            if cmd == "mute":
                duration = args[1] if len(args) > 1 else "1h"
                self.state.setdefault("mutes", {})[target] = duration
                self.log(f"{user} muted {target} for {duration}")
                with self.lock:
                    self.save()
                return f"Muted {target} for {duration}"
            if cmd == "warn":
                self.state.setdefault("warns", {})
                self.state["warns"][target] = self.state["warns"].get(target, 0) + 1
                self.log(f"{user} warned {target} (total: {self.state['warns'][target]})")
                with self.lock:
                    self.save()
                return f"Warned {target}. Total warns: {self.state['warns'][target]}"

        # Economy
        if cmd == "give":
            if rank < ROLE_RANK["manager"]:
                return "Permission denied: economy requires manager+."
            if len(args) < 2:
                return "Usage: give {user} {unit|plus|unix} [...]"
            target = args[0].lstrip("@")
            asset = args[1].lower()
            if asset == "unit":
                try:
                    amt = int(args[2])
                except (IndexError, ValueError):
                    return "Usage: give {user} unit {amount}"
                self.econ.give_units(target, amt)
                self.log(f"{user} gave {amt} units to {target}")
                with self.lock:
                    self.save()
                return f"Gave {amt} units to {target}"
            if asset == "plus":
                if len(args) < 3:
                    return "Usage: give {user} plus {N}{mess|day|year}"
                val = args[2]
                m = re.match(r"(\d+)(mess|month|day|year)", val)
                if not m:
                    return "Invalid duration format. Example: 5mess, 14day, 1year"
                num = int(m.group(1))
                unit = m.group(2)
                months = num if unit in ("mess", "month") else 0
                days = num if unit == "day" else 0
                years = num if unit == "year" else 0
                self.econ.give_plus(target, months, days, years)
                self.log(f"{user} gave Plus ({val}) to {target}")
                with self.lock:
                    self.save()
                return f"Gave Plus {val} to {target}"
            if asset == "unix":
                if rank < ROLE_RANK["root"]:
                    return "Permission denied: give unix requires root."
                if len(args) < 3:
                    return "Usage: give {user} unix {nft_id}"
                self.econ.give_nft(target, args[2])
                self.log(f"{user} gave NFT {args[2]} to {target}")
                with self.lock:
                    self.save()
                return f"Gave NFT {args[2]} to {target}"
            return f"Unknown asset: {asset}"

        # RPM
        if cmd == "rpm":
            if rank < ROLE_RANK["manager"]:
                return "Permission denied: rpm requires manager+."
            if not args:
                return "Usage: rpm install|list|remove {pkg}"
            sub = args[0].lower()
            if sub == "list":
                installed = self.state["users"][user].get("rpm_installed", [])
                return "\n".join(installed) if installed else "(no packages installed)"
            if sub == "install":
                if len(args) < 2:
                    return "Usage: rpm install {pkg}"
                pkg = args[1]
                if pkg not in RPM_AVAILABLE:
                    return f"Package '{pkg}' not found in /RPM."
                installed = self.state["users"][user].setdefault("rpm_installed", [])
                if pkg in installed:
                    return f"{pkg} already installed."
                installed.append(pkg)
                self.log(f"{user} installed {pkg}")
                with self.lock:
                    self.save()
                return f"Installed {pkg}."
            if sub == "remove":
                if len(args) < 2:
                    return "Usage: rpm remove {pkg}"
                pkg = args[1]
                installed = self.state["users"][user].get("rpm_installed", [])
                if pkg in installed:
                    installed.remove(pkg)
                    self.log(f"{user} removed {pkg}")
                    with self.lock:
                        self.save()
                    return f"Removed {pkg}."
                return f"{pkg} not installed."
            return f"Unknown rpm subcommand: {sub}"

        if cmd == "open":
            if rank < ROLE_RANK["manager"]:
                return "Permission denied."
            if not args:
                return "Usage: open {pkg}"
            installed = self.state["users"][user].get("rpm_installed", [])
            if args[0] not in installed:
                return f"{args[0]} not installed. Use: rpm install {args[0]}"
            return f"[TUI] {args[0]} launched inside kernel tunnel. (close {args[0]} to exit)"

        if cmd == "close":
            if rank < ROLE_RANK["manager"]:
                return "Permission denied."
            return f"Closed {args[0] if args else '?'}"

        # Logs
        if cmd == "logs":
            if role != "support" and rank < ROLE_RANK["manager"]:
                return "Permission denied."
            lines = self.state.get("logs", [])[-20:]
            if not lines:
                return "(no logs)"
            return "\n".join(f"[{l['ts']}] {l['msg']}" for l in lines)

        return f"Unknown command: {cmd}. Type 'help'."

    def help_text(self, role):
        rank = ROLE_RANK.get(role, 0)
        lines = [
            "=== KERNEL OS HELP ===",
            "General: time | version | clear | help | whoami | status | ping | exit",
        ]
        if rank >= ROLE_RANK["manager"]:
            lines.append("FS: cd | mkdir | d/dir | ls | touch | cat | echo | pwd")
        if role == "support":
            lines.append("Support: logs (read-only)")
        if rank >= ROLE_RANK["moderator"]:
            lines.append("Moderation: ban | unban | mute | warn")
        if rank >= ROLE_RANK["manager"]:
            lines.append("Economy: give {user} unit|plus|unix")
            lines.append("RPM: rpm install|list|remove | open {pkg} | close {pkg}")
        return "\n".join(lines)

    def run(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(10)
        print(f"KERNEL OS {VERSION} listening on {HOST}:{PORT}")
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
            t.start()


if __name__ == "__main__":
    KernelServer().run()
