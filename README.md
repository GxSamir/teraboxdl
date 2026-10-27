# TeraBoxDL Scraper & Local API Server

Zero-dependency local API server and scraper for TeraBox links with IP privacy and rotating origin headers.

---

## 📁 Clean Project Structure

```
teraboxdl/
├── Dockerfile           # Optimized production Docker container (Alpine Python 3.11)
├── .dockerignore        # Docker ignore rules
├── server.py            # Local & Production API Server (Zero dependencies, IP privacy)
├── main.py              # Command-Line Downloader & Scraper CLI
├── terabox_client.py    # Python Client module
├── terabox_client.js    # Node.js Client module (Node 18+)
├── requirements.txt     # Standard library documentation
└── README.md            # Documentation
```

---

## 🚀 Coolify Deployment Guide (Auto-Deploy on Push)

This repository includes a production-ready `Dockerfile` optimized for Coolify on Ubuntu VPS.

### 1. Connect Private GitHub Repo to Coolify:
1. In Coolify: Go to **Projects** -> Select your Project / Environment -> **+ New Resource** -> **Private Repository (with deploy key)**.
2. Coolify will show you an **SSH Public Key**. Copy it.
3. Open GitHub: [https://github.com/GxSamir/teraboxdl/settings/keys](https://github.com/GxSamir/teraboxdl/settings/keys) -> Click **Add deploy key**.
   - Title: `Coolify VPS`
   - Key: Paste the public key from Coolify.
   - Click **Add key**.
4. In Coolify: Enter `git@github.com:GxSamir/teraboxdl.git` and Branch `main`.

### 2. Port & Domain:
- In Coolify Application Settings:
  - **Port Exposes**: `8000`
  - **Domains**: Set your domain (e.g. `https://terabox.yourdomain.com`) or port mapping (e.g. `8080:8000`).
  *(Note: Since Coolify's dashboard runs on host port 8000, use Traefik domain or an alternate external port like 8080).*

### 3. Auto-Deploy on Git Push:
1. In Coolify: Go to your App -> **Webhooks** tab -> Copy the **GitHub Webhook URL**.
2. In GitHub: [https://github.com/GxSamir/teraboxdl/settings/hooks](https://github.com/GxSamir/teraboxdl/settings/hooks) -> Click **Add webhook**.
   - Payload URL: Paste the URL from Coolify.
   - Content type: `application/json`
   - Events: `Just the push event`
3. Click **Add webhook**. Now every `git push` automatically rebuilds and deploys!

---

## ⚡ 1. Run the Local API Server

The server runs on Python's built-in standard library with **zero dependencies**:

```bash
python server.py
```
*(Default runs on `http://127.0.0.1:8000`)*

### IP Privacy & Anti-Blocking Features Included:
- **Randomized Origin IP Headers**: Every request dynamically rotates `X-Forwarded-For`, `X-Real-IP`, and `Client-IP` to prevent the platform from blocking or tracking your real IP address.
- **Rotating User-Agents**: Cycles across realistic modern Windows, Mac, and Linux browser agents.
- **Dynamic Session Expiry**: Generates forward-dated expiration timestamps automatically.
- **Optional Network Proxy**: Route all TCP connections through your own HTTP/SOCKS proxy:
  ```bash
  python server.py --proxy http://username:password@ip:port
  ```

---

## 🔗 2. Requesting the API

### GET Request:
```text
http://127.0.0.1:8000/?url=<ANY_TERABOX_URL>
```

### Example:
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

## 📥 3. Command-Line Downloader (CLI)

You can also resolve or download files directly from the command line:

```bash
# Print file metadata and direct links
python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA"

# Download the file to a folder
python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA" --download --output ./downloads/

# Output clean JSON
python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA" --json
```

---

## ⚡ 4. Node.js Client

```bash
node terabox_client.js "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA"
```
