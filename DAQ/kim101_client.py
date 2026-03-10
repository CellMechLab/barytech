# kim101_client.py
# Tiny client for your Windows KIM101 bridge.


import json, time, traceback
from typing import Optional, Tuple, Union

try:
    import requests
except Exception:
    requests = None
import urllib.request

Json = dict
Resp = Tuple[bool, Union[Json, str]]

class KimClient:
    def __init__(self, endpoint: str = "", timeout: float = 4.0, verbose: bool = False, **kw):
        if not endpoint and "base_url" in kw:
            endpoint = kw["base_url"]
        self.base = (endpoint or "").rstrip("/")
        self.timeout = float(timeout)
        self.verbose = bool(verbose)
        self._session = requests.Session() if requests else None

    def configured(self) -> bool:
        return bool(self.base)

    def _ok(self, data: Json) -> Resp:
        return True, data

    def _err(self, e: Exception) -> Resp:
        msg = f"{type(e).__name__}: {e}"
        if self.verbose:
            msg += "\n" + traceback.format_exc()
        return False, msg

    # ------------ transport ------------
    def _get(self, path: str) -> Resp:
        url = f"{self.base}{path}"
        try:
            if self._session:
                r = self._session.get(url, timeout=self.timeout)
                r.raise_for_status()
                return self._ok(r.json())
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "ignore")
                return self._ok(json.loads(raw))
        except Exception as e:
            return self._err(e)

    def _post(self, path: str, data: Optional[Json] = None) -> Resp:
        url = f"{self.base}{path}"
        try:
            if self._session:
                if data is None:
                    r = self._session.post(url, timeout=self.timeout)
                else:
                    r = self._session.post(
                        url,
                        data=json.dumps(data),
                        headers={"Content-Type": "application/json"},
                        timeout=self.timeout,
                    )
                r.raise_for_status()
                return self._ok(r.json() if r.content else {})
            if data is None:
                req = urllib.request.Request(url, method="POST")
            else:
                body = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "ignore")
                return self._ok(json.loads(raw) if raw else {})
        except Exception as e:
            return self._err(e)

    # ------------ API ------------
    def info(self) -> Resp:
        return self._get("/info")

    def enable(self) -> Resp:
        return self._post("/enable")

    def zero(self, ch: int) -> Resp:
        return self._post(f"/zero?ch={int(ch)}")

    def position(self, ch: int) -> Resp:
        ok, data = self._get(f"/position?ch={int(ch)}")
        if not ok:
            return False, data
        try:
            return True, {"pos": int(data.get("pos", 0))}
        except Exception:
            return False, f"Bad payload: {data}"

    def move_steps(self, ch: int, steps: int, rate: int = None, accel: int = None) -> Resp:
        payload = {"ch": int(ch), "steps": int(steps)}
        if rate  is not None: payload["rate"]  = int(rate)
        if accel is not None: payload["accel"] = int(accel)
        if self.verbose:
            print(f"[KimClient] POST /move_to {payload}")
        return self._post("/move_to", payload)

    def move_xy_steps(self, x_steps: int, y_steps: int, rate: int = None, accel: int = None) -> Resp:
        ok1, r1 = self.move_steps(1, int(x_steps), rate, accel)
        if not ok1:
            return False, r1
        ok2, r2 = self.move_steps(2, int(y_steps), rate, accel)
        if not ok2:
            return False, r2
        return True, {"ok": True}

    def wait_until_reached(self, x_target: int, y_target: int, tol: int = 1, timeout: float = 8.0, poll: float = 0.05) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            okx, px = self.position(1)
            oky, py = self.position(2)
            if okx and oky:
                if abs(int(px.get("pos",0)) - x_target) <= tol and abs(int(py.get("pos",0)) - y_target) <= tol:
                    return True
            time.sleep(poll)
        return False
