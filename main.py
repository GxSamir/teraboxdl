"""
TeraBoxDL Command-Line Interface (CLI)
Usage:
    python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA"
    python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA" --download
    python main.py "https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA" --json
"""

import sys
import os
import argparse
import json
from terabox_client import TeraBoxDLClient

# Default working tdl_pass extracted from network session
DEFAULT_TDL_PASS = "1793069477.1793076677.cb3cd45025054afe.a0001d2f83b6e0b7f5079cd399b22c9d18b37d7619f5ccdcb53ab9802f16606b"


def parse_args():
    parser = argparse.ArgumentParser(
        description="TeraBoxDL Link Scraper & Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python main.py https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA
  python main.py https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA --download
  python main.py https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA --download --output ./downloads/
  python main.py https://freeterabox.com/s/1ZtWhQTzbztneHLVWEbZ2uA --json
"""
    )
    parser.add_argument("url", help="TeraBox share link (freeterabox.com, terabox.com, 1024tera.com, etc.)")
    parser.add_argument("--download", "-d", action="store_true", help="Download the resolved file(s)")
    parser.add_argument("--output", "-o", default=".", help="Destination path or folder to save downloaded file")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON data")
    parser.add_argument("--stream", "-s", action="store_true", help="Display video stream URL (m3u8)")
    parser.add_argument("--cookie", "-c", default=DEFAULT_TDL_PASS, help="Custom tdl_pass cookie value")
    return parser.parse_args()


def main():
    args = parse_args()

    client = TeraBoxDLClient(tdl_pass=args.cookie)

    if not args.json:
        print(f"\n[+] Resolving link: {args.url}")

    try:
        result = client.get_info(args.url)
    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            print(f"\n[!] Error resolving link: {e}")
        sys.exit(1)

    if args.json:
        out = {
            "success": True,
            "title": result.title,
            "total_size": result.total_size,
            "total_size_bytes": result.total_size_bytes,
            "file_count": len(result.files),
            "files": [
                {
                    "fs_id": f.fs_id,
                    "file_name": f.file_name,
                    "size": f.size,
                    "formatted_size": f.formatted_size,
                    "direct_link": f.direct_link,
                    "stream_url": f.stream_url,
                    "quality": f.quality,
                    "duration": f.duration,
                    "thumbnails": f.thumbnails,
                    "is_dir": f.is_dir,
                    "path": f.path
                }
                for f in result.files
            ]
        }
        print(json.dumps(out, indent=2))
        return

    # User-friendly console display
    print("=" * 60)
    print(f"Title:       {result.title}")
    print(f"Total Size:  {result.total_size} ({result.total_size_bytes:,} bytes)")
    print(f"File Count:  {len(result.files)}")
    print("=" * 60)

    for idx, f in enumerate(result.files, 1):
        print(f"\n[{idx}] {f.file_name}")
        print(f"    Size:        {f.formatted_size}")
        if f.quality:
            print(f"    Quality:     {f.quality}p")
        if f.duration:
            mins, secs = divmod(f.duration, 60)
            hours, mins = divmod(mins, 60)
            dur_str = f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"
            print(f"    Duration:    {dur_str}")
        if f.direct_link:
            print(f"    Direct Link: {f.direct_link[:90]}... (truncated)")
        if f.stream_url and args.stream:
            print(f"    Stream URL:  {f.stream_url}")

    # Handle download action
    if args.download:
        print("\n" + "=" * 60)
        print("[+] Starting download...")
        os.makedirs(args.output, exist_ok=True)
        for f in result.files:
            if f.is_dir or not f.direct_link:
                continue
            client.download(f, output_path=args.output)


if __name__ == "__main__":
    main()
