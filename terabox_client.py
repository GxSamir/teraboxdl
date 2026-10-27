"""
TeraBoxDL Client - Python API Client and Scraper for TeraBox Link Resolution
Reverse-engineered from https://teraboxdl.site/
"""

import os
import sys
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.parse
import urllib.error


@dataclass
class FileInfo:
    fs_id: str
    file_name: str
    size: int
    formatted_size: str
    direct_link: Optional[str]
    stream_url: Optional[str]
    is_dir: bool
    path: str
    md5: Optional[str] = None
    duration: Optional[int] = None
    quality: Optional[int] = None
    thumbnails: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "FileInfo":
        thumbs = data.get("thumbs") or {}
        return cls(
            fs_id=str(data.get("fs_id", "")),
            file_name=data.get("server_filename") or data.get("file_name") or "unknown",
            size=int(data.get("size", 0)),
            formatted_size=data.get("formatted_size") or cls._format_size(data.get("size", 0)),
            direct_link=data.get("direct_link") or data.get("dlink") or data.get("download_url"),
            stream_url=data.get("stream_url"),
            is_dir=bool(data.get("isdir", 0)),
            path=data.get("path") or "",
            md5=data.get("md5"),
            duration=data.get("duration"),
            quality=data.get("quality"),
            thumbnails=thumbs
        )

    @staticmethod
    def _format_size(bytes_num: int) -> str:
        if not bytes_num:
            return "0 Bytes"
        units = ["Bytes", "KB", "MB", "GB", "TB"]
        idx = 0
        val = float(bytes_num)
        while val >= 1024.0 and idx < len(units) - 1:
            val /= 1024.0
            idx += 1
        return f"{val:.2f} {units[idx]}"


@dataclass
class TeraBoxResult:
    title: str
    total_size: str
    total_size_bytes: int
    files: List[FileInfo]
    share_id: Optional[int] = None
    uk: Optional[int] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)


class TeraBoxDLClient:
    """
    Client for interacting with the teraboxdl.site API.
    """
    DEFAULT_API_URL = "https://teraboxdl.site/api/proxy"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        tdl_pass: Optional[str] = None,
        cf_clearance: Optional[str] = None,
        user_agent: Optional[str] = None,
        api_url: Optional[str] = None
    ):
        """
        Initialize the client.
        :param tdl_pass: The session cookie 'tdl_pass'. Can be passed directly or set via env `TDL_PASS`.
        :param cf_clearance: Optional Cloudflare clearance cookie if needed.
        :param user_agent: Browser User-Agent header.
        :param api_url: Custom API proxy endpoint (default: https://teraboxdl.site/api/proxy).
        """
        self.api_url = api_url or self.DEFAULT_API_URL
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.tdl_pass = tdl_pass or os.getenv("TDL_PASS", "")
        self.cf_clearance = cf_clearance or os.getenv("CF_CLEARANCE", "")

    def _build_cookie_header(self) -> str:
        cookies = []
        if self.tdl_pass:
            cookies.append(f"tdl_pass={self.tdl_pass}")
            # Optional expiration cookie matching timestamp
            cookies.append("tdl_pass_exp=1793076677")
        if self.cf_clearance:
            cookies.append(f"cf_clearance={self.cf_clearance}")
        return "; ".join(cookies)

    def get_info(self, url: str, dir_path: str = "", page: int = 1) -> TeraBoxResult:
        """
        Resolves a TeraBox share link to file information and direct download links.
        :param url: The TeraBox / FreeTeraBox link (e.g. https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA).
        :param dir_path: Optional subdirectory path for folders.
        :param page: Optional page number for large directories.
        :return: TeraBoxResult object containing file details and download URLs.
        """
        url = url.strip()
        if not url:
            raise ValueError("URL cannot be empty")

        payload = {"url": url}
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
            "User-Agent": self.user_agent,
        }

        cookie_str = self._build_cookie_header()
        if cookie_str:
            headers["Cookie"] = cookie_str

        req = urllib.request.Request(self.api_url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                res_json = json.loads(body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            if e.code == 403:
                raise PermissionError(
                    f"403 Forbidden: API access blocked or cookie expired. "
                    f"Please update 'tdl_pass' or Cloudflare cookies. Details: {err_body}"
                )
            raise RuntimeError(f"HTTP Error {e.code}: {err_body}")
        except Exception as e:
            raise RuntimeError(f"Network error while connecting to TeraBoxDL: {e}")

        # Check for error status
        errno = res_json.get("errno")
        if errno is not None and errno != 0:
            msg = res_json.get("errmsg") or res_json.get("message") or f"API returned error code {errno}"
            raise RuntimeError(msg)

        raw_list = res_json.get("list") or []
        files = [FileInfo.from_dict(item) for item in raw_list]

        return TeraBoxResult(
            title=res_json.get("title") or (files[0].file_name if files else "TeraBox Files"),
            total_size=res_json.get("total_size") or (files[0].formatted_size if files else "0 Bytes"),
            total_size_bytes=res_json.get("total_size_bytes") or (files[0].size if files else 0),
            files=files,
            share_id=res_json.get("share_id"),
            uk=res_json.get("uk"),
            raw_response=res_json
        )

    def download(
        self,
        file_info: FileInfo,
        output_path: Optional[str] = None,
        chunk_size: int = 1024 * 512,
        progress_callback: Optional[Any] = None
    ) -> str:
        """
        Downloads the file from its direct_link.
        :param file_info: FileInfo object with direct_link.
        :param output_path: Destination file path or directory.
        :param chunk_size: Buffer size for downloading chunks.
        :param progress_callback: Optional callable(downloaded_bytes, total_bytes).
        :return: Final saved file path.
        """
        if not file_info.direct_link:
            raise ValueError(f"No direct download link available for '{file_info.file_name}'")

        if output_path is None or os.path.isdir(output_path):
            filename = file_info.file_name or "downloaded_file"
            dest = os.path.join(output_path or ".", filename)
        else:
            dest = output_path

        headers = {
            "User-Agent": self.user_agent,
            "Referer": "https://teraboxdl.site/"
        }

        # Check if partial file exists for resume support
        existing_size = 0
        if os.path.exists(dest):
            existing_size = os.path.getsize(dest)
            if existing_size > 0 and existing_size < file_info.size:
                headers["Range"] = f"bytes={existing_size}-"
            elif existing_size >= file_info.size and file_info.size > 0:
                print(f"[TeraBoxDL] File '{dest}' is already fully downloaded ({existing_size} bytes).")
                return dest

        req = urllib.request.Request(file_info.direct_link, headers=headers)
        mode = "ab" if existing_size > 0 else "wb"

        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, mode) as f:
            total_size = file_info.size
            downloaded = existing_size

            start_time = time.time()
            last_print = 0

            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                current_time = time.time()
                if progress_callback:
                    progress_callback(downloaded, total_size)
                elif current_time - last_print > 0.5 or downloaded == total_size:
                    last_print = current_time
                    percent = (downloaded / total_size * 100) if total_size > 0 else 0
                    elapsed = current_time - start_time
                    speed = (downloaded - existing_size) / (elapsed if elapsed > 0 else 1) / (1024 * 1024)
                    sys.stdout.write(
                        f"\rDownloading: {downloaded / (1024*1024):.2f}/{total_size / (1024*1024):.2f} MB "
                        f"({percent:.1f}%) @ {speed:.2f} MB/s"
                    )
                    sys.stdout.flush()

        print(f"\n[TeraBoxDL] Download complete: {dest}")
        return dest
