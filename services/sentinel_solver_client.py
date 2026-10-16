"""Private solver transport. Never forward account headers, cookies or prompts."""
import json
import os
from urllib.request import Request, build_opener, ProxyHandler


def solver_request(path: str, payload: dict) -> dict:
    url = os.environ.get("SENTINEL_SOLVER_URL", "").rstrip("/")
    key = os.environ.get("SENTINEL_SOLVER_KEY", "")
    if not url or not key:
        raise RuntimeError("SENTINEL_SOLVER_URL and SENTINEL_SOLVER_KEY are required")
    request = Request(url + path, data=json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
    })
    # Internal calls must not pass through host HTTP(S)_PROXY.
    with build_opener(ProxyHandler({})).open(request, timeout=150) as response:
        return json.load(response)
