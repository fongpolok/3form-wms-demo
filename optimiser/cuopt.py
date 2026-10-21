"""
Client for an NVIDIA cuOpt self-hosted server (REST, JSON), as used by NVIDIA's own
cuopt_sh_client:
    POST   {url}/cuopt/request            problem -> {"reqId"} (or the answer at once)
    GET    {url}/cuopt/solution/{reqId}   {"reqId"} while busy, then {"response": {...}}
    DELETE {url}/cuopt/solution/{reqId}   tidy up on the server
    GET    {url}/cuopt/health             {"status": "RUNNING", "version": ...}
Any failure raises CuoptUnavailable with a plain message. There is no silent switch to
another engine: the caller keeps the last result and raises an alert.
"""
import logging
import time
from urllib.parse import urlsplit

import requests

from core import config

logger = logging.getLogger("aps")
HEADERS = {"CLIENT-VERSION": "custom", "Content-Type": "application/json", "Accept": "application/json"}


class CuoptUnavailable(Exception):
    pass


def check_url(url):
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise CuoptUnavailable("cuOpt address must look like http://server:5000 (set it in Settings → Integrations).")
    return url.rstrip("/")


def _headers(token):
    h = dict(HEADERS)
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def health(url, token=""):
    url = check_url(url)
    try:
        r = requests.get(f"{url}/cuopt/health", headers=_headers(token), timeout=10)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        raise CuoptUnavailable(f"cuOpt server not reachable at {url}: {exc.__class__.__name__}") from exc


def solve(url, token, problem):
    """Send one problem (routing or MILP JSON) and wait for the answer. Returns response["solver_response"]."""
    url = check_url(url)
    wait = float(config.get("optimiser.cuopt.wait_seconds", 120))
    poll = float(config.get("optimiser.cuopt.poll_seconds", 1))
    h = _headers(token)
    t0 = time.time()
    req_id = None
    try:
        r = requests.post(f"{url}/cuopt/request", json=problem, headers=h, timeout=30)
        if r.status_code >= 400:
            raise CuoptUnavailable(f"cuOpt refused the problem ({r.status_code}): {r.text[:300]}")
        body = r.json()
        req_id = body.get("reqId")
        while "response" not in body:
            if "error" in body:
                raise CuoptUnavailable(f"cuOpt error: {body['error']}")
            if time.time() - t0 > wait:
                raise CuoptUnavailable(f"cuOpt gave no answer within {wait:.0f} seconds.")
            time.sleep(poll)
            r = requests.get(f"{url}/cuopt/solution/{req_id}", headers=h, timeout=30)
            if r.status_code >= 400:
                raise CuoptUnavailable(f"cuOpt lost the request ({r.status_code}): {r.text[:300]}")
            body = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise CuoptUnavailable(f"cuOpt server not reachable at {url}: {exc.__class__.__name__}") from exc
    finally:
        if req_id:
            try:
                requests.delete(f"{url}/cuopt/solution/{req_id}", headers=h, timeout=10)
            except requests.RequestException:
                pass
    response = body["response"]
    if isinstance(response, dict) and response.get("error"):
        raise CuoptUnavailable(f"cuOpt error: {response['error']}")
    logger.info("cuOpt answered in %.1fs", time.time() - t0)
    return response.get("solver_response", response)
