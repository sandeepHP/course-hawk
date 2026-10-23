import time

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}
_session = requests.Session()
_session.headers.update(HEADERS)
_last_request = 0.0
MIN_GAP_SEC = 1.5  # be gentle with every site


def get(url: str, **kwargs) -> requests.Response:
    global _last_request
    wait = MIN_GAP_SEC - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()
    resp = _session.get(url, timeout=kwargs.pop("timeout", 20), **kwargs)
    resp.raise_for_status()
    return resp
