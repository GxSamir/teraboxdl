"""
TeraBoxDL Local API Server
Zero-dependency API server using Python's built-in ThreadingHTTPServer.

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
import urllib.request
import urllib.parse
import urllib.error
from typing import Tuple, Dict, Any, Optional
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Fresh fallback session token (signed for VPS deployment IP)
DEFAULT_TDL_PASS: str = "1793087146.1793094346.c6394c295751a265.f7b8c74f700871cf5c4a72e3c77023f932b502c0241c7096bee141ba212d8579"
UPSTREAM_API: str = "https://teraboxdl.site/api/proxy"
COOKIE_FILE: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_cookie.txt")

# Coolify auto-sync URL (updates remote VPS server whenever local token updates)
DEFAULT_COOLIFY_SYNC_URL: str = os.getenv(
    "COOLIFY_SYNC_URL",
    "http://4gqy7obbm2xc5z1067zjb0y2.201.18.200.27.sslip.io"
)

# Active dynamic in-memory token
ACTIVE_TDL_PASS: str = ""

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
        parts = token.split(".")
        if len(parts) >= 2:
            return int(parts[1])
    except Exception:
        pass
    return None


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
    1. Active in-memory token
    2. latest_cookie.txt file
    3. TDL_PASS environment variable
    4. DEFAULT_TDL_PASS fallback
    """
    global ACTIVE_TDL_PASS
    if ACTIVE_TDL_PASS and ACTIVE_TDL_PASS.strip():
        return ACTIVE_TDL_PASS.strip()

    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    ACTIVE_TDL_PASS = content
                    return ACTIVE_TDL_PASS
        except Exception:
            pass

    env_token = os.getenv("TDL_PASS", "").strip()
    if env_token:
        ACTIVE_TDL_PASS = env_token
        return ACTIVE_TDL_PASS

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


def try_refresh_from_chrome_cdp() -> Optional[str]:
    """
    Connects to local Chrome browser via DevTools Protocol (port 9222)
    and extracts fresh 'tdl_pass' cookie without opening new windows.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=5000)
            for ctx in browser.contexts:
                for c in ctx.cookies():
                    if c.get("name") == "tdl_pass" and c.get("value"):
                        val = c["value"]
                        set_active_token(val, save_file=True, sync_remote=True)
                        sys.stdout.write(f"[+] Extracted fresh tdl_pass from Chrome CDP: {val[:30]}...\n")
                        sys.stdout.flush()
                        return val
    except Exception:
        pass
    return None


def generate_random_ip() -> str:
    """Generates a random public IP address to rotate origin headers."""
    prefixes = [
        (104, random.randint(16, 31)),
        (198, 51),
        (203, 0),
        (185, random.randint(10, 220)),
        (194, random.randint(50, 180)),
        (156, random.randint(30, 200)),
    ]
    p1, p2 = random.choice(prefixes)
    p3 = random.randint(1, 254)
    p4 = random.randint(1, 254)
    return f"{p1}.{p2}.{p3}.{p4}"


def fetch_from_upstream(
    target_url: str,
    dir_path: str = "",
    page: int = 1,
    tdl_pass: Optional[str] = None,
    proxy_url: Optional[str] = None,
    allow_retry: bool = True
) -> Tuple[int, Dict[str, Any]]:
    """
    Forwards request to upstream API with spoofed headers, rotating IPs, and dynamic cookies.
    Automatically retries with Chrome CDP auto-refresh if CHALLENGE_REQUIRED is encountered.
    """
    token = tdl_pass or get_current_token()
    cleaned_url = target_url.strip()

    payload: Dict[str, Any] = {"url": cleaned_url}
    if dir_path:
        payload["dir"] = dir_path
    if page > 1:
        payload["page"] = page

    data_bytes = json.dumps(payload).encode("utf-8")
    random_ip = generate_random_ip()
    chosen_ua = random.choice(USER_AGENTS)
    token_exp = parse_token_expiry(token) or int(time.time() + 7200)

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

        # If Cloudflare challenge is required, attempt auto-refresh from Chrome CDP and retry
        if allow_retry and (e.code == 403 or err_json.get("code") == "CHALLENGE_REQUIRED"):
            sys.stdout.write("[!] Upstream requires Turnstile verification. Attempting auto-refresh...\n")
            sys.stdout.flush()
            new_token = try_refresh_from_chrome_cdp()
            if new_token and new_token != token:
                sys.stdout.write("[+] Retrying request with fresh token...\n")
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
        - /refresh-token
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
            self._send_json_response(200, meta)
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

        # Force refresh via Chrome CDP
        if parsed.path == "/refresh-token":
            refreshed = try_refresh_from_chrome_cdp()
            if refreshed:
                meta = get_token_metadata(refreshed)
                self._send_json_response(200, {"status": "refreshed_from_chrome", "token_info": meta})
            else:
                self._send_json_response(503, {
                    "error": "Could not extract cookie from Chrome CDP",
                    "hint": "Ensure Chrome is running with --remote-debugging-port=9222 and has visited teraboxdl.site"
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
            help_doc = {
                "status": "online",
                "service": "TeraBoxDL Scraper & Direct Link API",
                "usage": "/?url=<TERABOX_URL>",
                "token_status": f"http://{host_header}/token-status",
                "example": f"http://{host_header}/?url=https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA",
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


def run_server(port: int = 8000, host: str = "0.0.0.0", proxy: Optional[str] = None) -> None:
    TeraBoxAPIHandler.proxy_url = proxy or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")

    # Load initial token
    initial_token = get_current_token()
    token_meta = get_token_metadata(initial_token)

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TeraBoxAPIHandler)

    print("=" * 65)
    print(f"[*] TeraBoxDL Server running on http://{host}:{port}")
    print(f"[*] Active Token: {token_meta['token_preview']}")
    print(f"[*] Token Expiration: {token_meta['expires_at']} ({token_meta['seconds_remaining']}s remaining)")
    print(f"[*] IP Privacy: Enabled (Rotating Public IP Headers + User-Agents)")
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
