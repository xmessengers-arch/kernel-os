#!/usr/bin/env python3
"""KERNEL OS Client вЂ” Р›РѕРІРёС‚РµР»СЊ
E-Key вЂ” РјР°СЃС‚РµСЂ-РєР»СЋС‡. РўРѕР»СЊРєРѕ СЃ РЅРёРј РјРѕР¶РЅРѕ РІРѕР№С‚Рё."""

import sys
import os
import json
import time
import base64
import urllib.request
import urllib.error

REPO = "xmessengers-arch/kernel-os"
API = "https://api.github.com"
BRANCH = "main"
SESSION_PATH = "kernel/session"
EKEY_LEN = 105

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "kernel-os")
CONFIG_FILE = os.path.join(CONFIG_DIR, "session.json")


def get_token():
    # РўРѕРєРµРЅ Р±РµСЂС‘С‚СЃСЏ РёР· РїРµСЂРµРјРµРЅРЅРѕР№ РѕРєСЂСѓР¶РµРЅРёСЏ РёР»Рё С„Р°Р№Р»Р° РєРѕРЅС„РёРіСѓСЂР°С†РёРё
    token = os.environ.get("KERNEL_TOKEN", "")
    if not token:
        token_file = os.path.join(CONFIG_DIR, "token")
        try:
            with open(token_file) as f:
                token = f.read().strip()
        except Exception:
            pass
    return token


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)


class GitHubKernel:
    def __init__(self, token):
        self.token = token
        self.session_id = None
        self.role = "user"

    def _api(self, method, path, body=None):
        url = f"{API}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "KERNEL-OS-Client",
        }
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": e.code}

    def get_file(self, path):
        r = self._api("GET", f"/repos/{REPO}/contents/{path}?ref={BRANCH}")
        if "content" in r:
            return base64.b64decode(r["content"]).decode()
        return None

    def put_file(self, path, content, message):
        r = self._api("GET", f"/repos/{REPO}/contents/{path}?ref={BRANCH}")
        sha = r.get("sha")
        body = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": BRANCH,
        }
        if sha:
            body["sha"] = sha
        return self._api("PUT", f"/repos/{REPO}/contents/{path}", body)

    def get_commit_ts(self):
        r = self._api("GET", f"/repos/{REPO}/commits?path={SESSION_PATH}/resp&sha={BRANCH}&per_page=1")
        if isinstance(r, list) and r:
            return r[0]["commit"]["committer"]["date"]
        return None

    def get_master_ekey(self):
        raw = self.get_file("kernel/ekey")
        return base64.b64decode(raw.strip()).decode() if raw else None

    def setup(self, username):
        roles = {"root": "root", "manager": "manager", "moderator": "moderator", "support": "support"}
        self.session_id = username
        self.role = roles.get(username, "user")
        self.put_file(f"{SESSION_PATH}/id", username, f"kernel: login {username}")
        self.put_file(f"{SESSION_PATH}/role", self.role, f"kernel: role {self.role}")
        self.put_file(f"{SESSION_PATH}/cmd", "", "kernel: reset")
        time.sleep(1)

    def send_command(self, cmd):
        ts_before = self.get_commit_ts()
        self.put_file(f"{SESSION_PATH}/cmd", cmd, f"kernel: {cmd}")
        for _ in range(30):
            time.sleep(2)
            ts_after = self.get_commit_ts()
            if ts_after and ts_after != ts_before:
                resp = self.get_file(f"{SESSION_PATH}/resp")
                return resp if resp is not None else "(РЅРµС‚ РѕС‚РІРµС‚Р°)"
        return "(С‚Р°Р№РјР°СѓС‚ вЂ” СЏРґСЂРѕ РЅРµ РѕС‚РІРµС‚РёР»Рѕ)"


def main():
    print("=" * 46)
    print("   KERNEL OS Client вЂ” Р›РѕРІРёС‚РµР»СЊ")
    print("=" * 46)
    print()
    print("  connecting", end="", flush=True)
    for _ in range(6):
        time.sleep(0.4)
        print(".", end="", flush=True)
    print()

    token = get_token()
    if not token:
        print("  РќРµС‚ РґРѕСЃС‚СѓРїР° Рє РЇРґСЂСѓ OS.")
        print("  РћР±СЂР°С‚РёСЃСЊ Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ РґР»СЏ РїРѕР»СѓС‡РµРЅРёСЏ РґРѕСЃС‚СѓРїР°.")
        input("\nPress Enter to exit...")
        return

    kernel = GitHubKernel(token)
    master_ekey = kernel.get_master_ekey()

    if not master_ekey:
        print("  РќРµС‚ СЃРІСЏР·Рё СЃ РЇРґСЂРѕРј OS.")
        input("\nPress Enter to exit...")
        return

    print("  connected.\n")

    config = load_config()
    saved_ekey = config.get("ekey")
    username = config.get("user")
    role = config.get("role")

    if saved_ekey and username and saved_ekey == master_ekey:
        kernel.session_id = username
        kernel.role = role or "user"
        print(f"  РЎ РІРѕР·РІСЂР°С‰РµРЅРёРµРј, {username} [{kernel.role}]")
        print()
    else:
        print("  РўСЂРµР±СѓРµС‚СЃСЏ E-Key РґР»СЏ РґРѕСЃС‚СѓРїР° Рє РЇРґСЂСѓ OS.")
        print()
        ekey = input("  E-Key: ").strip()

        if ekey != master_ekey:
            print("\n  РќРµРІРµСЂРЅС‹Р№ E-Key. Р”РѕСЃС‚СѓРї Р·Р°РїСЂРµС‰С‘РЅ.")
            input("Press Enter to exit...")
            return

        print("\n  E-Key РїСЂРёРЅСЏС‚.")
        print()

        username = input("  Username: ").strip()
        if not username:
            print("  РћС‚РјРµРЅР°.")
            input("Press Enter to exit...")
            return

        roles = {"root": "root", "manager": "manager", "moderator": "moderator", "support": "support"}
        kernel.session_id = username
        kernel.role = roles.get(username, "user")

        kernel.setup(username)
        save_config({"ekey": ekey, "user": username, "role": kernel.role})

        print(f"\n  РђРІС‚РѕСЂРёР·РѕРІР°РЅ: {username} [{kernel.role}]")
        print("  РЎРµСЃСЃРёСЏ СЃРѕС…СЂР°РЅРµРЅР°. РЎР»РµРґСѓСЋС‰РёР№ Р·Р°РїСѓСЃРє вЂ” Р±РµР· E-Key.\n")

    while True:
        try:
            cmd = input(f"terminal$ {username} > ").strip()
            if not cmd:
                continue
            resp = kernel.send_command(cmd)
            if resp.strip() == "Goodbye.":
                print(resp)
                break
            if resp == "__CLEAR__":
                os.system("cls" if os.name == "nt" else "clear")
            else:
                print(resp)
        except (EOFError, KeyboardInterrupt):
            print("\n  Disconnecting...")
            break

    print("\n  Session closed.")


if __name__ == "__main__":
    main()
