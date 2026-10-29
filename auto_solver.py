"""
TeraBoxDL Autonomous Cloudflare Turnstile Solver
Autonomous 24/7 Turnstile resolution engine designed to run directly inside
Linux Docker containers (Coolify VPS under Xvfb) and on local host machines.

Uses Chrome DevTools Protocol (CDP) to eliminate `navigator.webdriver` bot detection,
blocks Google Ads / Funding Choices overlays that intercept pointer events,
and extracts verified `tdl_pass` session cookies directly on the VPS IP address.
"""

import os
import sys
import time
import socket
import subprocess
import tempfile
import shutil
import json
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, Tuple

DEFAULT_TERABOX_TEST_URL = "https://1024terabox.com/s/1t2m3ENR75NinLa_v6FM2pg"
DEFAULT_VPS_URL = os.getenv("COOLIFY_SYNC_URL", "https://tbf-dl.teraboxfast.com")


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a TCP port is open and accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def find_chrome_executable() -> Optional[str]:
    """Finds Google Chrome or Chromium executable on Windows or Linux."""
    candidates = [
        # Linux standard locations (VPS Docker container)
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/snap/bin/chromium",
        # Windows standard locations
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    for name in ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"]:
        p = shutil.which(name)
        if p:
            return p

    return None


def send_token_to_vps(vps_url: str, turnstile_token: str) -> bool:
    """Sends fresh Turnstile token to VPS /vps-verify endpoint if needed."""
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
    coolify_url: Optional[str] = None,
    timeout_seconds: int = 40
) -> Tuple[Optional[str], Optional[str]]:
    """
    Autonomous Turnstile solver:
    1. Launches real Chromium/Chrome with --remote-debugging-port to bypass
       Playwright's navigator.webdriver automation flags.
    2. Connects via Playwright CDP.
    3. Blocks Google AdSense and Funding Choices overlays that intercept clicks.
    4. Triggers the challenge on https://teraboxdl.site/.
    5. Captures the issued tdl_pass session cookie directly.
    6. Returns (tdl_pass_cookie, turnstile_token).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("[!] Playwright is not installed. Run: pip install playwright\n")
        return None, None

    chrome_exe = find_chrome_executable()
    if not chrome_exe:
        sys.stderr.write("[!] Chrome or Chromium executable not found on this system.\n")
        return None, None

    # Choose an available CDP port
    cdp_port = 9455
    for p in range(9450, 9470):
        if not is_port_open(p):
            cdp_port = p
            break

    profile_dir = tempfile.mkdtemp(prefix=f"tb_cdp_profile_{cdp_port}_")
    cmd = [
        chrome_exe,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,1024",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu"
    ]
    if os.name == "nt":
        cmd.append("--window-position=-2500,-2500")

    sys.stdout.write(f"[*] Starting Chromium process ({chrome_exe}) on CDP port {cdp_port}...\n")
    sys.stdout.flush()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(20):
        if is_port_open(cdp_port):
            break
        time.sleep(0.25)

    if not is_port_open(cdp_port):
        sys.stderr.write(f"[!] Could not connect to Chrome CDP port {cdp_port}.\n")
        try:
            proc.terminate()
        except Exception:
            pass
        shutil.rmtree(profile_dir, ignore_errors=True)
        return None, None

    local_tdl_pass = None
    turnstile_token = None
    browser = None

    try:
        with sync_playwright() as p:
            sys.stdout.write(f"[*] Connecting to CDP at http://127.0.0.1:{cdp_port}...\n")
            sys.stdout.flush()
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            ctx = browser.contexts[0]
            page = ctx.new_page()

            # Abort all ad networks and popup scripts that block Turnstile
            page.route("**/*", lambda r: r.abort() if any(k in r.request.url.lower() for k in [
                "doubleclick", "googlesyndication", "pagead2", "fundingchoicesmessages",
                "google-analytics", "googletagmanager"
            ]) else r.continue_())

            # Listen for verify response
            def on_response(res):
                nonlocal turnstile_token
                if "/api/verify" in res.url:
                    try:
                        req_data = res.request.post_data_json
                        if req_data and isinstance(req_data, dict) and req_data.get("token"):
                            turnstile_token = req_data.get("token")
                    except Exception:
                        pass
                    sys.stdout.write(f"[*] Intercepted upstream verify response: {res.status}\n")
                    sys.stdout.flush()

            page.on("response", on_response)

            sys.stdout.write("[*] Loading https://teraboxdl.site/...\n")
            sys.stdout.flush()
            page.goto("https://teraboxdl.site/", wait_until="domcontentloaded", timeout=25000)
            time.sleep(1.5)

            # Save initial debug screenshot
            shot_file = os.path.join(tempfile.gettempdir(), "solver_view.png")
            try:
                page.screenshot(path=shot_file)
            except Exception:
                pass

            # Trigger Turnstile challenge by filling input and pressing Enter
            try:
                inp = page.locator('input[placeholder*="Terabox"]').first
                inp.wait_for(state="visible", timeout=12000)
                inp.fill(DEFAULT_TERABOX_TEST_URL)
                time.sleep(0.4)
                page.keyboard.press("Enter")
                sys.stdout.write("[*] Form submitted, challenge triggered.\n")
                sys.stdout.flush()
            except Exception as e:
                sys.stderr.write(f"[!] Input interaction note: {e}\n")

            # In case interactive checkbox is required, locate and click
            time.sleep(2)
            for frame in page.frames:
                if any(k in frame.url for k in ["cloudflare", "challenges.cloudflare.com"]):
                    try:
                        cb = frame.locator('input[type="checkbox"], .ctp-checkbox-label, #challenge-stage')
                        if cb.is_visible():
                            cb.click(timeout=3000)
                            sys.stdout.write("[+] Clicked Turnstile checkbox inside frame.\n")
                            sys.stdout.flush()
                    except Exception:
                        pass

            # Explicit coordinate click on Turnstile checkbox at (513, 464)
            sys.stdout.write("[*] Dispatching click to Turnstile checkbox at (513, 464)...\n")
            sys.stdout.flush()
            try:
                page.mouse.move(513, 464)
                time.sleep(0.1)
                page.mouse.down()
                time.sleep(0.08)
                page.mouse.up()
            except Exception as e:
                sys.stderr.write(f"[!] Coordinate click note: {e}\n")

            # Poll for tdl_pass cookie
            start_t = time.time()
            click_retried = False
            while time.time() - start_t < timeout_seconds:
                for c in ctx.cookies():
                    if c.get("name") == "tdl_pass" and c.get("value"):
                        local_tdl_pass = c["value"]
                        sys.stdout.write(f"[+] Successfully captured tdl_pass: {local_tdl_pass[:30]}...\n")
                        sys.stdout.flush()
                        break
                if local_tdl_pass:
                    break

                # If cookie not captured yet after 3.5s, retry click at slightly shifted coordinates
                if time.time() - start_t > 3.5 and not click_retried:
                    click_retried = True
                    try:
                        page.mouse.move(518, 464)
                        time.sleep(0.05)
                        page.mouse.down()
                        time.sleep(0.08)
                        page.mouse.up()
                    except Exception:
                        pass

                time.sleep(1)

            # Save post-solve screenshot
            try:
                page.screenshot(path=shot_file)
            except Exception:
                pass

            try:
                page.close()
            except Exception:
                pass

    except Exception as e:
        sys.stderr.write(f"[!] Turnstile solver exception: {e}\n")
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(profile_dir, ignore_errors=True)

    # Save captured cookie to latest_cookie.txt
    if local_tdl_pass:
        cookie_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_cookie.txt")
        try:
            with open(cookie_file, "w", encoding="utf-8") as f:
                f.write(local_tdl_pass.strip())
            sys.stdout.write(f"[+] Saved fresh session token to {cookie_file}\n")
            sys.stdout.flush()
        except Exception:
            pass

    # If running on a client machine with a remote VPS URL configured, sync token
    target_vps = coolify_url or DEFAULT_VPS_URL
    if local_tdl_pass and target_vps and "localhost" not in target_vps and "127.0.0.1" not in target_vps:
        # Check if we are running on the VPS itself or external
        is_vps_internal = os.getenv("HOST") == "0.0.0.0" and os.path.exists("/app")
        if not is_vps_internal:
            try:
                update_url = f"{target_vps.rstrip('/')}/update-token?token={urllib.parse.quote(local_tdl_pass)}"
                req = urllib.request.Request(update_url, headers={"User-Agent": "TeraBoxDL-Sync/1.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    sys.stdout.write(f"[+] Synced captured token to remote VPS ({r.status})\n")
                    sys.stdout.flush()
            except Exception as e:
                sys.stderr.write(f"[!] Note: Remote token sync to {target_vps}: {e}\n")

    return local_tdl_pass, turnstile_token


if __name__ == "__main__":
    coolify_target = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else DEFAULT_VPS_URL
    is_loop = "--loop" in sys.argv or "--daemon" in sys.argv

    if is_loop:
        print(f"[*] Starting recurring Turnstile solver daemon (target: {coolify_target})...")
        while True:
            try:
                print(f"\n[*] [{time.strftime('%H:%M:%S')}] Solving Turnstile...")
                cookie, token = solve_turnstile_locally(coolify_url=coolify_target)
                print(f"[+] Local tdl_pass: {cookie[:30] if cookie else 'None'}")
                print(f"[+] Turnstile token: {token[:30] if token else 'None'}")
                print("[*] Waiting 5 minutes for next cycle...")
                time.sleep(300)
            except Exception as loop_err:
                sys.stderr.write(f"[!] Daemon loop cycle error: {loop_err}\n[*] Retrying in 30 seconds...\n")
                time.sleep(30)
    else:
        print(f"[*] Running Turnstile solver once (target: {coolify_target})...")
        cookie, token = solve_turnstile_locally(coolify_url=coolify_target)
        print(f"[+] Captured tdl_pass: {cookie[:40] if cookie else 'None'}")
