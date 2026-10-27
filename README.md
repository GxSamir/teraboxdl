# TeraBoxDL Scraper & Local API Server

Zero-dependency local API server and scraper for TeraBox links with IP privacy and rotating origin headers.

---

## 📁 Clean Project Structure

```
teraboxdl/
├── server.py            # Local API Server (Zero dependencies, IP privacy, ?url=<url>)
├── main.py              # Command-Line Downloader & Scraper CLI
├── terabox_client.py    # Python Client module
├── terabox_client.js    # Node.js Client module (Node 18+)
├── requirements.txt     # Requirements file (standard library only)
└── README.md            # Documentation
```

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
