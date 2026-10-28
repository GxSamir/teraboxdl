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

To prevent tokens from ever degrading or reaching expiration:

1. **5-Minute Continuous Auto-Refresh Worker**:
   - `server.py` runs a background monitor thread that automatically triggers a fresh solve **every 5 minutes (300 seconds)**.
   - It captures fresh Turnstile tokens and syncs them to `https://tbf-dl.teraboxfast.com/vps-verify` so your VPS session is continuously refreshed 24/7.
   - You can also run the standalone 5-minute sync daemon:
     ```bash
     python auto_solver.py --loop
     ```

2. **Automated Turnstile Solver (`auto_solver.py`)**:
   - Connects to an existing Chrome instance on port 9222 if open, or launches a background offscreen Chrome instance (`--window-position=-2500,-2500`).
   - Completes the Turnstile challenge in ~4 seconds without user interaction.
   - Updates `latest_cookie.txt` and memory cache.
   - Forwards a fresh Turnstile token to Coolify VPS (`/vps-verify`), allowing the VPS to call `POST https://teraboxdl.site/api/verify` from its own IP and obtain a VPS-signed token!

3. **On-Demand Auto-Recovery**:
   - If upstream ever responds with `403 CHALLENGE_REQUIRED`, `server.py` catches it, immediately triggers `auto_solver.py`, updates the token, and automatically retries the user's request.

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
