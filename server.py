"""
TeraBoxDL Local & Remote API Server
Zero-dependency API server using Python's built-in ThreadingHTTPServer.
Includes automated Cloudflare Turnstile token refresh, IP privacy, and Coolify sync.

Usage:
    python server.py
    python server.py --port 8000
    python server.py --port 8000 --proxy http://username:password@ip:port

Query example:
    http://localhost:8000/?url=<TERABOX_URL>
"""

import os
import sys
import time
import json
import random
import argparse
import datetime
import threading
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from typing import Tuple, Dict, Any, Optional
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Fallback session token
DEFAULT_TDL_PASS: str = "1793198948.1793206148.9ffdaf791022927b.505bb3db7b0a32338d825838d216f9a4608c0282b86c2306208cb136a7a01d51"
UPSTREAM_API: str = "https://teraboxdl.site/api/proxy"
UPSTREAM_VERIFY: str = "https://teraboxdl.site/api/verify"
COOKIE_FILE: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_cookie.txt")

# Coolify auto-sync URL (updates remote VPS server whenever local token updates)
DEFAULT_COOLIFY_SYNC_URL: str = os.getenv(
    "COOLIFY_SYNC_URL",
    "https://tbf-dl.teraboxfast.com"
)

# Active dynamic in-memory token
ACTIVE_TDL_PASS: str = ""
SOLVER_LOCK = threading.Lock()

# Rotating User-Agents to mimic real varied browser traffic
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def parse_token_expiry(token: str) -> Optional[int]:
    """Extracts expiration timestamp embedded inside tdl_pass token."""
    try:
        parts = token.strip().split(".")
        if len(parts) >= 2:
            return int(parts[1])
    except Exception:
        pass
    return None


def is_token_expired(token: str, buffer_seconds: int = 60) -> bool:
    """Checks if a token has expired or is about to expire."""
    if not token or not token.strip():
        return True
    exp_ts = parse_token_expiry(token)
    if not exp_ts:
        return False
    return (exp_ts - int(time.time())) <= buffer_seconds


def get_token_metadata(token: str) -> Dict[str, Any]:
    """Calculates seconds remaining and expiration details for a given token."""
    exp_ts = parse_token_expiry(token)
    now_ts = int(time.time())
    if exp_ts:
        seconds_left = exp_ts - now_ts
        is_expired = seconds_left <= 0
        exp_iso = datetime.datetime.fromtimestamp(exp_ts).isoformat()
    else:
        seconds_left = None
        is_expired = False
        exp_iso = "unknown"

    return {
        "token_preview": (token[:28] + "..." + token[-12:]) if len(token) > 40 else token,
        "expires_at_timestamp": exp_ts,
        "expires_at": exp_iso,
        "seconds_remaining": seconds_left,
        "is_expired": is_expired,
    }


def get_current_token() -> str:
    """
    Resolves active token using hierarchy:
    1. Active in-memory token (if not expired)
    2. latest_cookie.txt file
    3. TDL_PASS environment variable
    4. DEFAULT_TDL_PASS fallback
    """
    global ACTIVE_TDL_PASS
    if ACTIVE_TDL_PASS and ACTIVE_TDL_PASS.strip() and not is_token_expired(ACTIVE_TDL_PASS):
        return ACTIVE_TDL_PASS.strip()

    # Check disk file
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content and not is_token_expired(content):
                    ACTIVE_TDL_PASS = content
                    return ACTIVE_TDL_PASS
        except Exception:
            pass

    env_token = os.getenv("TDL_PASS", "").strip()
    if env_token and not is_token_expired(env_token):
        ACTIVE_TDL_PASS = env_token
        return ACTIVE_TDL_PASS

    if ACTIVE_TDL_PASS and ACTIVE_TDL_PASS.strip():
        return ACTIVE_TDL_PASS.strip()

    ACTIVE_TDL_PASS = DEFAULT_TDL_PASS
    return ACTIVE_TDL_PASS


def set_active_token(new_token: str, save_file: bool = True, sync_remote: bool = True) -> Dict[str, Any]:
    """Updates active token in memory, writes to disk, and syncs remote server."""
    global ACTIVE_TDL_PASS
    clean_token = new_token.strip()
    ACTIVE_TDL_PASS = clean_token

    if save_file:
        try:
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                f.write(clean_token)
        except Exception as e:
            sys.stderr.write(f"[!] Warning: Could not write {COOKIE_FILE}: {e}\n")

    if sync_remote and DEFAULT_COOLIFY_SYNC_URL:
        threading.Thread(target=_sync_to_coolify, args=(clean_token,), daemon=True).start()

    return get_token_metadata(clean_token)


def _sync_to_coolify(token: str) -> None:
    """Syncs a fresh token to Coolify / remote server in background."""
    coolify_base = DEFAULT_COOLIFY_SYNC_URL.rstrip("/")
    if "localhost" in coolify_base or "127.0.0.1" in coolify_base:
        return
    sync_url = f"{coolify_base}/update-token?token={urllib.parse.quote(token)}"
    try:
        req = urllib.request.Request(sync_url, headers={"User-Agent": "TeraBoxDL-Sync/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            sys.stdout.write(f"[+] Synced fresh token to Coolify server ({resp.status})\n")
            sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"[!] Coolify sync note: {e}\n")


def trigger_auto_solve() -> Optional[str]:
    """
    Executes automated Turnstile solver on local machine:
    Solves challenge, captures tokens, updates local cookie, and syncs to Coolify VPS.
    Uses SOLVER_LOCK to avoid redundant simultaneous browser runs.
    """
    global ACTIVE_TDL_PASS
    if not SOLVER_LOCK.acquire(blocking=False):
        sys.stdout.write("[*] Auto-solver already running in another thread, waiting...\n")
        sys.stdout.flush()
        with SOLVER_LOCK:
            return ACTIVE_TDL_PASS

    try:
        sys.stdout.write("[*] Launching Turnstile auto-solver...\n")
        sys.stdout.flush()
        try:
            from auto_solver import solve_turnstile_locally
            cookie, vps_token = solve_turnstile_locally(coolify_url=DEFAULT_COOLIFY_SYNC_URL)
            current_tok = get_current_token()
            token_candidate = cookie if (cookie and not is_token_expired(cookie)) else current_tok
            if token_candidate and not is_token_expired(token_candidate):
                set_active_token(token_candidate, save_file=True, sync_remote=False)
                sys.stdout.write(f"[+] Auto-solver success! Fresh tdl_pass: {token_candidate[:32]}...\n")
                sys.stdout.flush()
                return token_candidate
            else:
                sys.stderr.write("[-] Auto-solver could not extract valid cookie.\n")
        except ImportError:
            sys.stderr.write("[!] auto_solver.py not found or playwright missing on this environment.\n")
        except Exception as e:
            sys.stderr.write(f"[!] Auto-solver error: {e}\n")
    finally:
        SOLVER_LOCK.release()

    return None


def verify_turnstile_on_vps(turnstile_token: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Executes POST https://teraboxdl.site/api/verify from THIS server's IP address.
    Extracts the issued tdl_pass cookie (signed for this machine's IP) and activates it.
    """
    try:
        payload_bytes = json.dumps({"token": turnstile_token.strip()}).encode("utf-8")
        chosen_ua = random.choice(USER_AGENTS)

        # 1. Try curl for HTTP/2 support
        try:
            cmd = [
                "curl", "-s", "-i",
                "-X", "POST", UPSTREAM_VERIFY,
                "-H", "Content-Type: application/json",
                "-H", "Origin: https://teraboxdl.site",
                "-H", "Referer: https://teraboxdl.site/",
                "-H", f"User-Agent: {chosen_ua}",
                "-d", json.dumps({"token": turnstile_token.strip()})
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0 and proc.stdout:
                stdout_text = proc.stdout
                extracted_cookie = None
                for line in stdout_text.splitlines():
                    if line.lower().startswith("set-cookie:"):
                        cookie_part = line.split(":", 1)[1].strip()
                        for c in cookie_part.split(";"):
                            if c.strip().startswith("tdl_pass="):
                                extracted_cookie = c.strip().split("=", 1)[1].strip()
                                break
                    if extracted_cookie:
                        break

                if extracted_cookie:
                    meta = set_active_token(extracted_cookie, save_file=True, sync_remote=False)
                    return True, {"status": "vps_verified_via_curl", "token_info": meta}
        except Exception:
            pass

        # 2. Fallback to urllib.request
        req = urllib.request.Request(
            UPSTREAM_VERIFY,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://teraboxdl.site",
                "Referer": "https://teraboxdl.site/",
                "User-Agent": chosen_ua
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            set_cookies = resp.headers.get_all("Set-Cookie") or []
            extracted_cookie = None
            for sc in set_cookies:
                for c in sc.split(";"):
                    if c.strip().startswith("tdl_pass="):
                        extracted_cookie = c.strip().split("=", 1)[1].strip()
                        break
                if extracted_cookie:
                    break

            if extracted_cookie:
                meta = set_active_token(extracted_cookie, save_file=True, sync_remote=False)
                return True, {"status": "vps_verified_via_urllib", "token_info": meta}

            body = resp.read().decode("utf-8", errors="ignore")
            return False, {"error": "No tdl_pass cookie in upstream response", "response": body}

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        return False, {"error": f"HTTP {e.code}", "detail": err_body}
    except Exception as e:
        return False, {"error": "VPS verify exception", "detail": str(e)}


def fetch_via_curl(
    target_url: str,
    dir_path: str = "",
    page: int = 1,
    token: str = "",
    token_exp: int = 0,
    user_agent: str = "",
    proxy_url: Optional[str] = None
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """
    Executes request using system curl (HTTP/2 + modern TLS ciphers)
    to prevent Cloudflare bot detection on datacenter IPs.
    """
    try:
        payload: Dict[str, Any] = {"url": target_url.strip()}
        if dir_path:
            payload["dir"] = dir_path
        if page > 1:
            payload["page"] = page

        data_str = json.dumps(payload)
        cookie_hdr = f"tdl_pass={token}; tdl_pass_exp={token_exp}"

        cmd = [
            "curl", "-s", "-w", "\n__HTTP_STATUS__:%{http_code}",
            "-X", "POST", UPSTREAM_API,
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json, text/plain, */*",
            "-H", "Origin: https://teraboxdl.site",
            "-H", "Referer: https://teraboxdl.site/",
            "-H", f"User-Agent: {user_agent}",
            "-H", f"Cookie: {cookie_hdr}",
            "-d", data_str
        ]
        if proxy_url:
            cmd.extend(["--proxy", proxy_url])

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if proc.returncode == 0 and proc.stdout:
            stdout_text = proc.stdout.strip()
            if "__HTTP_STATUS__:" in stdout_text:
                parts = stdout_text.rsplit("__HTTP_STATUS__:", 1)
                body_str = parts[0].strip()
                status = int(parts[1].strip())
                try:
                    return status, json.loads(body_str)
                except Exception:
                    return status, {"raw": body_str}
    except Exception as e:
        sys.stderr.write(f"[!] curl attempt note: {e}\n")
    return None


def fetch_from_upstream(
    target_url: str,
    dir_path: str = "",
    page: int = 1,
    tdl_pass: Optional[str] = None,
    proxy_url: Optional[str] = None,
    allow_retry: bool = True
) -> Tuple[int, Dict[str, Any]]:
    """
    Forwards request to upstream API with browser headers, rotating user-agents, and dynamic cookies.
    Tries curl first for HTTP/2 TLS support, with urllib as standard fallback.
    Automatically refreshes token on CHALLENGE_REQUIRED and retries.
    """
    token = tdl_pass or get_current_token()
    cleaned_url = target_url.strip()
    chosen_ua = random.choice(USER_AGENTS)
    token_exp = parse_token_expiry(token) or int(time.time() + 7200)

    # 1. Try curl (HTTP/2 + browser TLS fingerprint)
    curl_res = fetch_via_curl(
        target_url=cleaned_url,
        dir_path=dir_path,
        page=page,
        token=token,
        token_exp=token_exp,
        user_agent=chosen_ua,
        proxy_url=proxy_url
    )
    if curl_res is not None:
        status_code, response_json = curl_res
        if status_code == 200:
            return status_code, response_json

        # If Cloudflare challenge is required, attempt auto-refresh and retry once
        if allow_retry and (status_code == 403 or (isinstance(response_json, dict) and response_json.get("code") == "CHALLENGE_REQUIRED")):
            sys.stdout.write("[!] Upstream requires Turnstile verification. Attempting auto-solve...\n")
            sys.stdout.flush()
            new_token = trigger_auto_solve()
            if new_token and new_token != token:
                sys.stdout.write("[+] Retrying request with freshly solved token...\n")
                sys.stdout.flush()
                return fetch_from_upstream(
                    target_url=target_url,
                    dir_path=dir_path,
                    page=page,
                    tdl_pass=new_token,
                    proxy_url=proxy_url,
                    allow_retry=False
                )

        return status_code, response_json

    # 2. Fallback to urllib.request
    payload: Dict[str, Any] = {"url": cleaned_url}
    if dir_path:
        payload["dir"] = dir_path
    if page > 1:
        payload["page"] = page

    data_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://teraboxdl.site",
        "Referer": "https://teraboxdl.site/",
        "User-Agent": chosen_ua,
        "Cookie": f"tdl_pass={token}; tdl_pass_exp={token_exp}",
    }

    req = urllib.request.Request(UPSTREAM_API, data=data_bytes, headers=headers, method="POST")

    opener = urllib.request.build_opener()
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(proxy_handler)

    try:
        with opener.open(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return int(resp.status), json.loads(body)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
        except Exception:
            err_json = {"error": f"HTTP Error {e.code}", "detail": err_body}

        if allow_retry and (e.code == 403 or (isinstance(err_json, dict) and err_json.get("code") == "CHALLENGE_REQUIRED")):
            sys.stdout.write("[!] Upstream requires Turnstile verification. Attempting auto-solve...\n")
            sys.stdout.flush()
            new_token = trigger_auto_solve()
            if new_token and new_token != token:
                sys.stdout.write("[+] Retrying request with freshly solved token...\n")
                sys.stdout.flush()
                return fetch_from_upstream(
                    target_url=target_url,
                    dir_path=dir_path,
                    page=page,
                    tdl_pass=new_token,
                    proxy_url=proxy_url,
                    allow_retry=False
                )

        return int(e.code), err_json
    except Exception as e:
        return 500, {"error": "Failed to connect to upstream API", "detail": str(e)}


class TeraBoxAPIHandler(BaseHTTPRequestHandler):
    """Handles HTTP GET, POST and OPTIONS requests."""

    proxy_url: Optional[str] = None

    def _send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        try:
            content = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-TDL-Pass")
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-TDL-Pass")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        """
        Handle GET requests:
        - /?url=<TERABOX_URL>
        - /health
        - /token-status
        - /update-token?token=<NEW_TOKEN>
        - /vps-verify?token=<TURNSTILE_TOKEN>
        - /auto-refresh
        """
        parsed = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed.query)

        # Health check
        if parsed.path == "/health":
            self._send_json_response(200, {"status": "healthy", "service": "teraboxdl"})
            return

        # Token status
        if parsed.path == "/token-status":
            token = get_current_token()
            meta = get_token_metadata(token)
            meta["status"] = "online"
            meta["storage_file"] = os.path.exists(COOKIE_FILE)
            meta["coolify_sync_url"] = DEFAULT_COOLIFY_SYNC_URL
            self._send_json_response(200, meta)
            return

        # Solver screenshot endpoint
        if parsed.path == "/solver-screenshot":
            import tempfile
            shot_path = os.path.join(tempfile.gettempdir(), "solver_view.png")
            if os.path.exists(shot_path):
                try:
                    with open(shot_path, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)})
                    return
            self._send_json_response(404, {"error": "No solver screenshot captured yet"})
            return

        # Update token live via GET
        if parsed.path == "/update-token":
            new_token = query_params.get("token", [None])[0]
            if not new_token:
                self._send_json_response(400, {"error": "Missing 'token' query parameter"})
                return
            meta = set_active_token(new_token, save_file=True, sync_remote=False)
            self._send_json_response(200, {"status": "updated", "token_info": meta})
            return

        # VPS verify via GET
        if parsed.path == "/vps-verify":
            turnstile_token = query_params.get("token", [None])[0]
            if not turnstile_token:
                self._send_json_response(400, {"error": "Missing 'token' query parameter"})
                return
            success, result = verify_turnstile_on_vps(turnstile_token)
            self._send_json_response(200 if success else 400, result)
            return

        # Force auto-refresh
        if parsed.path in ("/refresh-token", "/auto-refresh"):
            fresh = trigger_auto_solve()
            if fresh:
                meta = get_token_metadata(fresh)
                self._send_json_response(200, {"status": "auto_refreshed", "token_info": meta})
            else:
                current_tok = get_current_token()
                meta = get_token_metadata(current_tok)
                if not meta.get("is_expired") and (meta.get("seconds_remaining") or 0) > 0:
                    self._send_json_response(200, {
                        "status": "active",
                        "message": "Token is active and valid. Sessions are automatically refreshed and synchronized via /vps-verify.",
                        "token_info": meta
                    })
                else:
                    self._send_json_response(200, {
                        "status": "challenge_required",
                        "message": "Session expired. Run 'python auto_solver.py' on your host to sync a fresh session to /vps-verify.",
                        "token_info": meta
                    })
            return

        target_url = query_params.get("url", [None])[0]
        dir_path = query_params.get("dir", [""])[0]
        page_val = query_params.get("page", ["1"])[0]
        custom_cookie = query_params.get("cookie", [None])[0] or self.headers.get("X-TDL-Pass")

        try:
            page = int(page_val)
        except ValueError:
            page = 1

        if not target_url:
            host_header = self.headers.get("Host", "localhost:8000")
            proto = self.headers.get("X-Forwarded-Proto") or ("https" if "teraboxfast.com" in host_header else "http")
            help_doc = {
                "status": "online",
                "service": "TeraBoxDL Scraper & Direct Link API",
                "usage": "/?url=<TERABOX_URL>",
                "token_status": f"{proto}://{host_header}/token-status",
                "vps_verify_endpoint": f"{proto}://{host_header}/vps-verify",
                "example": f"{proto}://{host_header}/?url=https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA",
                "token_expiry": get_token_metadata(get_current_token())
            }
            self._send_json_response(200, help_doc)
            return

        status_code, response_json = fetch_from_upstream(
            target_url=target_url,
            dir_path=dir_path,
            page=page,
            tdl_pass=custom_cookie,
            proxy_url=self.proxy_url
        )

        self._send_json_response(status_code, response_json)

    def do_POST(self) -> None:
        """
        Handle POST requests:
        - / (JSON payload: {"url": "..."})
        - /update-token (JSON payload: {"token": "..."})
        - /vps-verify (JSON payload: {"token": "..."})
        - /auto-refresh
        """
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        data: Dict[str, Any] = {}
        if post_data:
            try:
                data = json.loads(post_data.decode("utf-8"))
            except Exception:
                parsed_form = urllib.parse.parse_qs(post_data.decode("utf-8"))
                for k, v in parsed_form.items():
                    data[k] = v[0] if v else ""

        # Update token endpoint
        if parsed.path == "/update-token":
            new_token = data.get("token") or data.get("tdl_pass")
            if not new_token:
                self._send_json_response(400, {"error": "Missing 'token' in JSON body"})
                return
            meta = set_active_token(new_token, save_file=True, sync_remote=False)
            self._send_json_response(200, {"status": "updated", "token_info": meta})
            return

        # VPS verify endpoint
        if parsed.path == "/vps-verify":
            turnstile_token = data.get("token")
            if not turnstile_token:
                self._send_json_response(400, {"error": "Missing 'token' in JSON body"})
                return
            success, result = verify_turnstile_on_vps(turnstile_token)
            self._send_json_response(200 if success else 400, result)
            return

        # Auto refresh endpoint
        if parsed.path in ("/refresh-token", "/auto-refresh"):
            fresh = trigger_auto_solve()
            if fresh:
                meta = get_token_metadata(fresh)
                self._send_json_response(200, {"status": "auto_refreshed", "token_info": meta})
            else:
                current_tok = get_current_token()
                meta = get_token_metadata(current_tok)
                if not meta.get("is_expired") and (meta.get("seconds_remaining") or 0) > 0:
                    self._send_json_response(200, {
                        "status": "active",
                        "message": "Token is active and valid. Synchronized via /vps-verify.",
                        "token_info": meta
                    })
                else:
                    self._send_json_response(200, {
                        "status": "challenge_required",
                        "message": "Session expired. Run 'python auto_solver.py' on your host to sync /vps-verify.",
                        "token_info": meta
                    })
            return

        target_url = data.get("url")
        if not target_url:
            query_params = urllib.parse.parse_qs(parsed.query)
            target_url = query_params.get("url", [None])[0]

        if not target_url:
            self._send_json_response(400, {"error": "Missing 'url' parameter in JSON body or query string"})
            return

        dir_path = data.get("dir", "")
        page = int(data.get("page", 1))
        custom_cookie = data.get("cookie") or self.headers.get("X-TDL-Pass")

        status_code, response_json = fetch_from_upstream(
            target_url=target_url,
            dir_path=dir_path,
            page=page,
            tdl_pass=custom_cookie,
            proxy_url=self.proxy_url
        )

        self._send_json_response(status_code, response_json)

    def log_message(self, format: str, *args: Any) -> None:
        """Custom request logger."""
        sys.stdout.write(f"[{self.log_date_time_string()}] {format % args}\n")
        sys.stdout.flush()


# Auto-refresh cycle interval in seconds (default: 5 minutes / 300s)
AUTO_REFRESH_INTERVAL_SECONDS: int = int(os.getenv("REFRESH_INTERVAL", "300"))


def _auto_refresh_worker() -> None:
    """
    Background worker that runs continuously and refreshes tokens every 5 minutes:
    Automatically solves Turnstile and syncs local and remote tokens so that the session
    is perpetually fresh and never reaches expiration.
    """
    last_refresh_time = 0.0

    while True:
        try:
            now = time.time()
            elapsed = now - last_refresh_time
            token = get_current_token()
            meta = get_token_metadata(token)
            rem = meta.get("seconds_remaining")
            is_exp = meta.get("is_expired", False)

            # Refresh every 5 minutes (300 seconds), or immediately if expired/invalid
            if elapsed >= AUTO_REFRESH_INTERVAL_SECONDS or is_exp or rem is None or rem < 1800:
                sys.stdout.write(f"[*] Background monitor: 5-minute refresh triggered (elapsed: {int(elapsed)}s). Refreshing tokens...\n")
                sys.stdout.flush()
                fresh = trigger_auto_solve()
                if fresh:
                    last_refresh_time = time.time()
                    fresh_meta = get_token_metadata(fresh)
                    sys.stdout.write(f"[+] Background monitor: Token refreshed successfully! Next refresh in 5 minutes.\n")
                    sys.stdout.flush()
                else:
                    # Retry in 30 seconds if solve failed
                    last_refresh_time = now - AUTO_REFRESH_INTERVAL_SECONDS + 30
        except Exception as e:
            sys.stderr.write(f"[!] Background monitor exception: {e}\n")

        time.sleep(15)


def run_server(port: int = 8000, host: str = "0.0.0.0", proxy: Optional[str] = None) -> None:
    TeraBoxAPIHandler.proxy_url = proxy or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")

    # Load initial token
    initial_token = get_current_token()
    token_meta = get_token_metadata(initial_token)

    # Start background auto-refresh daemon thread
    worker_thread = threading.Thread(target=_auto_refresh_worker, daemon=True)
    worker_thread.start()

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TeraBoxAPIHandler)

    print("=" * 65)
    print(f"[*] TeraBoxDL Server running on http://{host}:{port}")
    print(f"[*] Active Token: {token_meta['token_preview']}")
    print(f"[*] Token Expiration: {token_meta['expires_at']} ({token_meta['seconds_remaining']}s remaining)")
    print(f"[*] Auto-Refresh Daemon: Active (refreshes every 5 minutes)")
    if TeraBoxAPIHandler.proxy_url:
        print(f"[*] Network Proxy: {TeraBoxAPIHandler.proxy_url}")
    print(f"[*] Health Check: http://{host}:{port}/health")
    print(f"[*] Token Status: http://{host}:{port}/token-status")
    print(f"[*] Ready to accept requests!")
    print("=" * 65)
    sys.stdout.flush()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Stopping server...")
        httpd.server_close()


if __name__ == "__main__":
    env_port = int(os.getenv("PORT", "8000"))
    env_host = os.getenv("HOST", "0.0.0.0")

    parser = argparse.ArgumentParser(description="TeraBoxDL Local API Server")
    parser.add_argument("--port", "-p", type=int, default=env_port, help=f"Port to listen on (default: {env_port})")
    parser.add_argument("--host", default=env_host, help=f"Host address (default: {env_host})")
    parser.add_argument("--proxy", default=None, help="Optional upstream proxy (e.g. http://ip:port)")
    cli_args = parser.parse_args()

    run_server(port=cli_args.port, host=cli_args.host, proxy=cli_args.proxy)
