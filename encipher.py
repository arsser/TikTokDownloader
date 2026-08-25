# Douyin web a_bogus via real Chrome BDMS (www.douyin.com pageId=6241).
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

__all__ = ["ABogus"]

_SIGNER = (
    Path(__file__).resolve().parent.parent
    / "DouyinLiveMonitor-Remastered"
    / "node_scraper"
    / "sign_aweme.mjs"
)
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


def _infer_path(query: str) -> str:
    q = query.lower()
    if "collects_id=" in q:
        return "/aweme/v1/web/collects/video/list/"
    if "listcollection" in q:
        return "/aweme/v1/web/aweme/listcollection/"
    if "mix/listcollection" in q:
        return "/aweme/v1/web/mix/listcollection/"
    return "/aweme/v1/web/collects/list/"


def _sign_via_server(qs: str, method: str, ua: str, path: str) -> str:
    url = os.environ.get("A_BOGUS_SIGN_URL", "http://127.0.0.1:5557/sign")
    payload = json.dumps(
        {"query": qs, "method": method, "ua": ua, "path": path}
    ).encode("utf-8")
    req = Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as resp:
            sig = resp.read().decode("utf-8", errors="replace").strip()
        return sig if sig and " " not in sig and len(sig) >= 80 else ""
    except (URLError, TimeoutError, OSError):
        return ""


class ABogus:
    path = "/aweme/v1/web/collects/list/"

    def __init__(self, user_agent: str = _DEFAULT_UA, platform: str | None = None):
        self.user_agent = user_agent or _DEFAULT_UA
        self.path = "/aweme/v1/web/collects/list/"

    def get_value(
        self,
        query: dict | str | None = None,
        data: dict | str | None = None,
        method: str | None = None,
        user_agent: str = "",
        **kwargs,
    ) -> str:
        if isinstance(data, str) and data.upper() in {"GET", "POST"} and method is None:
            method = data
            data = None
        method = (method or "GET").upper()
        ua = user_agent or self.user_agent or _DEFAULT_UA
        if isinstance(query, dict):
            qs = urlencode(query, quote_via=quote)
        else:
            qs = str(query or "")
        if not qs:
            raise ValueError("empty query for a_bogus")
        path = getattr(self, "path", None) or _infer_path(qs)
        if sig := _sign_via_server(qs, method, ua, path):
            return sig
        if not _SIGNER.is_file():
            raise FileNotFoundError(str(_SIGNER))
        proc = subprocess.run(
            [
                "node",
                str(_SIGNER),
                "--query",
                qs,
                "--method",
                method,
                "--ua",
                ua,
                "--path",
                path,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )
        sig = (proc.stdout or "").strip()
        if proc.returncode != 0 or not sig:
            err = (proc.stderr or proc.stdout or "sign failed").strip()
            raise RuntimeError(err[:500])
        return sig
