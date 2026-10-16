import json


class VirtualFS:
    def __init__(self, state):
        self.state = state
        for u in self.state.get("users", {}):
            self.state["users"][u].setdefault("cwd", "/")
            self.state["users"][u].setdefault("fs", {"/": {"dirs": [], "files": {}}})

    def cwd(self, username):
        return self.state["users"][username].get("cwd", "/")

    def set_cwd(self, username, path):
        self.state["users"][username]["cwd"] = path

    def mkdir(self, username, name):
        fs = self.state["users"][username]["fs"]
        cwd = self.cwd(username)
        node = fs.setdefault(cwd, {"dirs": [], "files": {}})
        if name not in node["dirs"]:
            node["dirs"].append(name)
        child = self._join(cwd, name)
        fs.setdefault(child, {"dirs": [], "files": {}})
        return True

    def ls(self, username):
        fs = self.state["users"][username]["fs"]
        cwd = self.cwd(username)
        node = fs.get(cwd, {"dirs": [], "files": {}})
        return list(node.get("dirs", [])), list(node.get("files", {}).keys())

    def cd(self, username, target):
        fs = self.state["users"][username]["fs"]
        cwd = self.cwd(username)
        if target == "..":
            if cwd == "/":
                return True
            parent = cwd.rsplit("/", 1)[0] or "/"
            self.set_cwd(username, parent)
            return True
        if target == "/":
            self.set_cwd(username, "/")
            return True
        new = self._join(cwd, target)
        if new in fs:
            self.set_cwd(username, new)
            return True
        return False

    def rmdir(self, username, name):
        fs = self.state["users"][username]["fs"]
        cwd = self.cwd(username)
        node = fs.get(cwd, {"dirs": [], "files": {}})
        if name in node.get("dirs", []):
            node["dirs"].remove(name)
            child = self._join(cwd, name)
            fs.pop(child, None)
            return True
        return False

    def write_file(self, username, name, content):
        fs = self.state["users"][username]["fs"]
        cwd = self.cwd(username)
        node = fs.setdefault(cwd, {"dirs": [], "files": {}})
        node["files"][name] = content

    def read_file(self, username, name):
        fs = self.state["users"][username]["fs"]
        cwd = self.cwd(username)
        node = fs.get(cwd, {})
        return node.get("files", {}).get(name)

    def _join(self, base, name):
        if base == "/":
            return f"/{name}"
        return f"{base}/{name}"
