"""
TeraBoxDL Automated Turnstile Solver
Automatically solves Cloudflare Turnstile on teraboxdl.site using Chrome CDP or an offscreen Chrome instance.
Captures fresh local tdl_pass cookies and fresh Turnstile tokens for remote Coolify VPS verification.
"""

import os
import sys
import time
import socket
import subprocess
import urllib.request
import urllib.parse
import json
from typing import Optional, Dict, Any, Tuple

DEFAULT_TERABOX_TEST_URL = "https://1024terabox.com/s/1t2m3ENR75NinLa_v6FM2pg"
DEFAULT_VPS_URL = "https://tbf-dl.teraboxfast.com"


def is_port_open(port: int = 9222, host: str = "127.0.0.1") -> bool:
    """Checks if a TCP port is currently open."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.8)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def find_chrome_executable() -> Optional[str]:
    """Finds Google Chrome executable path on Windows or Linux."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def send_token_to_vps(vps_url: str, turnstile_token: str) -> bool:
    """Sends fresh Turnstile token to Coolify VPS /vps-verify endpoint."""
    try:
        clean_url = vps_url.rstrip("/") + "/vps-verify"
        payload = json.dumps({"token": turnstile_token}).encode("utf-8")
        req = urllib.request.Request(
            clean_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8", errors="ignore")
            sys.stdout.write(f"[+] Synced fresh token to VPS ({clean_url}): {resp.status} {data[:60]}\n")
            sys.stdout.flush()
            return resp.status == 200
    except Exception as e:
        sys.stderr.write(f"[!] Warning: Failed to send token to VPS ({vps_url}): {e}\n")
        return False


def solve_turnstile_locally(
    coolify_url: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Automates Turnstile solve:
    1. Connects to existing Chrome CDP (port 9222) if running,
       otherwise launches a background offscreen Chrome instance on port 9335.
    2. Performs solve for local machine to extract fresh tdl_pass.
    3. If coolify_url is configured:
       Clears cookies, intercepts fresh Turnstile token on next solve,
       and transmits it to VPS /vps-verify so VPS gets its own IP-matched tdl_pass.
    4. Returns (local_tdl_pass, vps_turnstile_token).
    """
    target_vps = coolify_url or DEFAULT_VPS_URL
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("[!] Playwright is not installed. Run: pip install playwright\n")
        return None, None

    cdp_port = 9222
    launched_process = None

    if not is_port_open(cdp_port):
        chrome_exe = find_chrome_executable()
        if not chrome_exe:
            sys.stderr.write("[!] Google Chrome executable not found.\n")
            return None, None

        cdp_port = 9335
        profile_dir = os.path.expandvars(r"%TEMP%\tb_solver_profile")
        cmd = [
            chrome_exe,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-position=-2500,-2500",
            "--window-size=900,700",
            "--disable-blink-features=AutomationControlled"
        ]
        try:
            launched_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(2)
        except Exception as e:
            sys.stderr.write(f"[!] Could not launch Chrome: {e}\n")
            return None, None

    local_tdl_pass = None
    vps_turnstile_token = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            ctx = browser.contexts[0]
            page = ctx.new_page()

            # Step 1: Solve for local machine
            page.goto("https://teraboxdl.site/", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1000)
            inp = page.locator('input[placeholder*="Terabox"]').first
            if inp.is_visible(timeout=5000):
                inp.fill(DEFAULT_TERABOX_TEST_URL)
                page.wait_for_timeout(500)
                btn = page.locator('form button[type="submit"]').first
                if btn.is_visible(timeout=2000):
                    btn.click()
                else:
                    page.keyboard.press("Enter")
            page.wait_for_timeout(4000)

            for c in ctx.cookies():
                if c.get("name") == "tdl_pass" and c.get("value") and "terabox" in c.get("domain", ""):
                    local_tdl_pass = c["value"]
                    break

            # Step 2: If target_vps is configured, solve for VPS
            if target_vps and "localhost" not in target_vps and "127.0.0.1" not in target_vps:
                ctx.clear_cookies()
                vps_tokens = []

                def on_route(route):
                    if "/api/verify" in route.request.url and route.request.method == "POST":
                        try:
                            data = json.loads(route.request.post_data)
                            tok = data.get("token")
                            if tok:
                                vps_tokens.append(tok)
                                route.abort()
                                return
                        except Exception:
                            pass
                    route.continue_()

                page.route("**/api/verify", on_route)
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                inp = page.locator('input[placeholder*="Terabox"]').first
                if inp.is_visible(timeout=5000):
                    inp.fill(DEFAULT_TERABOX_TEST_URL)
                    page.wait_for_timeout(500)
                    btn = page.locator('form button[type="submit"]').first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                    else:
                        page.keyboard.press("Enter")

                for _ in range(8):
                    page.wait_for_timeout(1000)
                    if vps_tokens:
                        break

                if vps_tokens:
                    vps_turnstile_token = vps_tokens[0]
                    send_token_to_vps(target_vps, vps_turnstile_token)

            try:
                page.close()
            except Exception:
                pass
            browser.close()
    except Exception as e:
        sys.stderr.write(f"[!] Turnstile solver exception: {e}\n")
    finally:
        if launched_process:
            try:
                launched_process.terminate()
                launched_process.wait(timeout=5)
            except Exception:
                pass

    return local_tdl_pass, vps_turnstile_token


import datetime

if __name__ == "__main__":
    coolify_target = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else DEFAULT_VPS_URL
    is_loop = "--loop" in sys.argv or "--daemon" in sys.argv

    if is_loop:
        print(f"[*] Starting recurring 5-minute Turnstile sync daemon (target: {coolify_target})...")
        while True:
            print(f"\n[*] [{datetime.datetime.now().strftime('%H:%M:%S')}] Solving Turnstile...")
            cookie, token = solve_turnstile_locally(coolify_url=coolify_target)
            print(f"[+] Local tdl_pass: {cookie[:30] if cookie else None}")
            print(f"[+] VPS token: {token[:30] if token else None}")
            print("[*] Waiting 5 minutes for next cycle...")
            time.sleep(300)
    else:
        print(f"[*] Running automated Turnstile solver (target: {coolify_target})...")
        cookie, token = solve_turnstile_locally(coolify_url=coolify_target)
        print(f"[+] Local tdl_pass: {cookie[:40] if cookie else None}")
        print(f"[+] VPS Turnstile token: {token[:40] if token else None}")
