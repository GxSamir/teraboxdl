# TeraBoxDL Scraper & Local API Server

Production-ready API server and scraper for TeraBox links with automated Cloudflare Turnstile bypass, auto-updating session tokens, IP privacy, and Coolify deployment support.

---

## 📁 Clean Project Structure

```
teraboxdl/
├── Dockerfile           # Optimized production Docker container (Alpine Python 3.11 with curl HTTP/2)
├── .dockerignore        # Docker ignore rules
├── server.py            # Local & Production API Server with Auto-Refresh Daemon & /vps-verify
├── auto_solver.py       # Automated Cloudflare Turnstile Solver (Chrome CDP / Offscreen Chrome)
├── main.py              # Command-Line Downloader & Scraper CLI
├── terabox_client.py    # Python Client module
├── terabox_client.js    # Node.js Client module (Node 18+)
├── latest_cookie.txt    # Persistent cache of latest working tdl_pass session token
├── requirements.txt     # Dependency information
└── README.md            # Documentation
```

---

## 🔄 Automated Token Refresh System (Refreshes Every 5 Minutes)

Upstream `teraboxdl.site` uses Cloudflare Turnstile and issues a session cookie (`tdl_pass`) that expires after **2 hours** (7,200 seconds) and is cryptographically bound to the client's IP.

To ensure your API never expires (even when your PC is turned off):

1. **Self-Sufficient VPS Docker Container (24/7 Autonomy)**:
   - The production `Dockerfile` (Debian-slim) includes Chromium, Xvfb, and Playwright.
   - When deployed on Coolify, the VPS runs its own background virtual display (`Xvfb :99`) and auto-refresh worker thread.
   - It solves Turnstile directly on the VPS every 5 minutes and updates its session tokens 24/7 without needing any external computer!

2. **Windows Background Sync Daemon (Silent & Automatic)**:
   - For your local machine, run `start_solver_daemon.bat` to launch the 5-minute solver daemon silently in the background (no black console window).
   - Run `install_startup_task.bat` to register a Windows Task Scheduler job that automatically starts the background sync daemon every time you turn on or log in to your computer.

3. **On-Demand Auto-Recovery**:
   - If upstream ever responds with `403 CHALLENGE_REQUIRED`, `server.py` catches it, immediately triggers `auto_solver.py`, updates the token, and automatically retries the user's request seamlessly.

---

## ⚡ 1. Run the Local API Server

```bash
python server.py
```
*(Runs on `http://127.0.0.1:8000`)*

### Endpoints:
- `GET /?url=<TERABOX_URL>` - Resolve file list, sizes, and direct download links.
- `POST /` - Accepts `{"url": "..."}` JSON payload.
- `GET /token-status` - Check current token, seconds remaining, and expiration time.
- `GET /auto-refresh` - Manually trigger an instant Turnstile solve and token refresh.
- `POST /vps-verify` - Accepts Turnstile token `{"token": "..."}` to sign a session for the server's IP.
- `GET /health` - Healthcheck endpoint.

---

## 🔗 2. Requesting the API

### GET Request:
```bash
curl "http://127.0.0.1:8000/?url=https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA"
```

### POST Request (JSON):
```bash
curl -X POST "http://127.0.0.1:8000/" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA"}'
```

---

## 🚀 3. Coolify Deployment

1. The project has been pushed to GitHub: [https://github.com/GxSamir/teraboxdl](https://github.com/GxSamir/teraboxdl).
2. In your Coolify dashboard:
   - Application URL: [http://201.18.200.27:8000/project/evrsjb269wkhmzgfz7as7foa/environment/suwwdz8onpbxsqhhkbjon41y/application/4gqy7obbm2xc5z1067zjb0y2](http://201.18.200.27:8000/project/evrsjb269wkhmzgfz7as7foa/environment/suwwdz8onpbxsqhhkbjon41y/application/4gqy7obbm2xc5z1067zjb0y2)
   - Click **Redeploy** to pull the latest changes.
3. Once deployed, the local server will continuously keep both local and Coolify tokens updated in the background.

---

## 📥 4. Command-Line Downloader (CLI)

```bash
# Print file metadata and direct links
python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA"

# Download the file to a folder
python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA" --download --output ./downloads/

# Output clean JSON
python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA" --json
```

---

## ⚡ 5. Node.js Client

```bash
node terabox_client.js "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA"
```
