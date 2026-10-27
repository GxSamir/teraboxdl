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
import urllib.request
import urllib.parse
import urllib.error
from typing import Tuple, Dict, Any, Optional
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Default working session token
DEFAULT_TDL_PASS: str = os.getenv(
    "TDL_PASS",
    "1793069477.1793076677.cb3cd45025054afe.a0001d2f83b6e0b7f5079cd399b22c9d18b37d7619f5ccdcb53ab9802f16606b"
)
UPSTREAM_API: str = "https://teraboxdl.site/api/proxy"

# Rotating User-Agents to mimic real varied browser traffic
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def generate_random_ip() -> str:
    """Generates a random public IP address to rotate origin headers."""
    # Pre-selected realistic public IP blocks
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
    proxy_url: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Forwards request to upstream API with spoofed headers, rotating IPs, and dynamic cookies.
    """
    token = tdl_pass or DEFAULT_TDL_PASS
    cleaned_url = target_url.strip()

    payload: Dict[str, Any] = {"url": cleaned_url}
    if dir_path:
        payload["dir"] = dir_path
    if page > 1:
        payload["page"] = page

    data_bytes = json.dumps(payload).encode("utf-8")
    random_ip = generate_random_ip()
    chosen_ua = random.choice(USER_AGENTS)

    # Dynamic cookie expiration (valid for 24 hours into the future)
    future_expiry = int(time.time() + 86400)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://teraboxdl.site",
        "Referer": "https://teraboxdl.site/",
        "User-Agent": chosen_ua,
        "Cookie": f"tdl_pass={token}; tdl_pass_exp={future_expiry}",
        # Spoof client IP headers to prevent rate-limiting on your real IP
        "X-Forwarded-For": random_ip,
        "X-Real-IP": random_ip,
        "Client-IP": random_ip,
    }

    req = urllib.request.Request(UPSTREAM_API, data=data_bytes, headers=headers, method="POST")

    # Optional proxy handler if configured
    opener = urllib.request.build_opener()
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler({
            "http": proxy_url,
            "https": proxy_url
        })
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
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        """
        Handle GET requests:
        e.g. /?url=<TERABOX_URL>
        """
        parsed = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json_response(200, {"status": "healthy", "service": "teraboxdl"})
            return

        target_url = query_params.get("url", [None])[0]
        dir_path = query_params.get("dir", [""])[0]
        page_val = query_params.get("page", ["1"])[0]
        custom_cookie = query_params.get("cookie", [None])[0]

        try:
            page = int(page_val)
        except ValueError:
            page = 1

        if not target_url:
            host_header = self.headers.get("Host", "localhost:8000")
            help_doc = {
                "status": "online",
                "usage": "/?url=<TERABOX_URL>",
                "health": "/health",
                "example": f"http://{host_header}/?url=https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA",
                "instructions": "Pass any valid TeraBox URL into the 'url' parameter to extract direct download links."
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
        Accepts JSON body: {"url": "..."}
        """
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        target_url: Optional[str] = None
        dir_path: str = ""
        page: int = 1
        custom_cookie: Optional[str] = None

        if post_data:
            try:
                data = json.loads(post_data.decode("utf-8"))
                target_url = data.get("url")
                dir_path = data.get("dir", "")
                page = data.get("page", 1)
                custom_cookie = data.get("cookie")
            except Exception:
                parsed = urllib.parse.parse_qs(post_data.decode("utf-8"))
                target_url = parsed.get("url", [None])[0]

        if not target_url:
            parsed = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed.query)
            target_url = query_params.get("url", [None])[0]

        if not target_url:
            self._send_json_response(400, {"error": "Missing 'url' parameter in JSON body or query string"})
            return

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

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TeraBoxAPIHandler)

    print("=" * 65)
    print(f"[*] TeraBoxDL Server running on http://{host}:{port}")
    print(f"[*] IP Privacy: Enabled (Rotating Public IP Headers + User-Agents)")
    if TeraBoxAPIHandler.proxy_url:
        print(f"[*] Network Proxy: {TeraBoxAPIHandler.proxy_url}")
    print(f"[*] Health Check: http://{host}:{port}/health")
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
