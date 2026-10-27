/**
 * TeraBoxDL Node.js Client
 * Reverse engineered from https://teraboxdl.site/
 * 
 * Works in Node.js 18+ (uses native global fetch)
 * 
 * Usage:
 *   node terabox_client.js "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA"
 */

const DEFAULT_TDL_PASS = "1793079162.1793090308.cb3cd45025054afe.2445650a2f6ed29f24dade96b0526db9d75c4b0012a69a1e5b7d16d3f9c3235d";

class TeraBoxClient {
  constructor(options = {}) {
    this.apiUrl = options.apiUrl || "https://teraboxdl.site/api/proxy";
    this.tdlPass = options.tdlPass || process.env.TDL_PASS || DEFAULT_TDL_PASS;
    this.userAgent = options.userAgent || "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";
  }

  async getInfo(url, dir = "", page = 1) {
    if (!url) throw new Error("URL is required");

    const payload = { url };
    if (dir) payload.dir = dir;
    if (page > 1) payload.page = page;

    const cookieHeader = `tdl_pass=${this.tdlPass}; tdl_pass_exp=1793090308`;

    const response = await fetch(this.apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://teraboxdl.site",
        "Referer": "https://teraboxdl.site/",
        "User-Agent": this.userAgent,
        "Cookie": cookieHeader,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`API returned ${response.status}: ${errText}`);
    }

    const data = await response.json();
    if (data.errno !== 0 && data.errno !== undefined) {
      throw new Error(data.errmsg || data.message || `API error code: ${data.errno}`);
    }

    const files = (data.list || []).map(item => ({
      fsId: String(item.fs_id),
      fileName: item.server_filename || item.file_name || "unknown",
      sizeBytes: item.size,
      formattedSize: item.formatted_size || this.formatSize(item.size),
      directLink: item.direct_link || item.dlink,
      streamUrl: item.stream_url || null,
      isDir: item.isdir === 1,
      path: item.path || "",
      quality: item.quality ? `${item.quality}p` : null,
      duration: item.duration || null,
      thumbnails: item.thumbs || {}
    }));

    return {
      title: data.title || (files[0] ? files[0].fileName : ""),
      totalSize: data.total_size || (files[0] ? files[0].formattedSize : "0 Bytes"),
      totalSizeBytes: data.total_size_bytes || (files[0] ? files[0].sizeBytes : 0),
      files,
      raw: data
    };
  }

  formatSize(bytes) {
    if (!bytes) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }
}

// If run directly from CLI
if (require.main === module) {
  const targetUrl = process.argv[2] || "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA";
  console.log(`[+] Resolving: ${targetUrl}`);

  const client = new TeraBoxClient();
  client.getInfo(targetUrl)
    .then(result => {
      console.log("\n============================================================");
      console.log(`Title:      ${result.title}`);
      console.log(`Total Size: ${result.totalSize}`);
      console.log(`Files:      ${result.files.length}`);
      console.log("============================================================");
      result.files.forEach((f, i) => {
        console.log(`\n[${i + 1}] ${f.fileName} (${f.formattedSize})`);
        if (f.quality) console.log(`    Quality:     ${f.quality}`);
        if (f.directLink) console.log(`    Direct Link: ${f.directLink.substring(0, 90)}...`);
        if (f.streamUrl) console.log(`    Stream URL:  ${f.streamUrl}`);
      });
    })
    .catch(err => {
      console.error("[!] Error:", err.message);
      process.exit(1);
    });
}

module.exports = { TeraBoxClient };
