import time


class Economy:
    def __init__(self, state):
        self.state = state
        for u in self.state.get("users", {}):
            self.state["users"][u].setdefault("units", 0)
            self.state["users"][u].setdefault("plus", None)
            self.state["users"][u].setdefault("nfts", [])

    def give_units(self, target, amount):
        if target not in self.state["users"]:
            return False
        self.state["users"][target]["units"] = self.state["users"][target].get("units", 0) + amount
        return True

    def give_plus(self, target, months=0, days=0, years=0):
        if target not in self.state["users"]:
            return False
        now = time.time()
        current = self.state["users"][target].get("plus") or now
        if current < now:
            current = now
        seconds = months * 30 * 86400 + days * 86400 + years * 365 * 86400
        self.state["users"][target]["plus"] = current + seconds
        return True

    def give_nft(self, target, nft_id):
        if target not in self.state["users"]:
            return False
        self.state["users"][target].setdefault("nfts", []).append(nft_id)
        return True

    def balance(self, username):
        u = self.state["users"].get(username, {})
        return u.get("units", 0), u.get("plus")

    def plus_active(self, username):
        plus = self.state["users"].get(username, {}).get("plus")
        return plus is not None and plus > time.time()
