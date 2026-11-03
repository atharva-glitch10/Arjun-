"""Helpers for `scripts\\dev-up.ps1 -Phone`: parse the quick-tunnel URL and rewrite `.env`.

The phone needs an HTTPS origin for the microphone. `npx cloudflared tunnel` prints a
`https://<random>.trycloudflare.com` URL; this script finds it in the tunnel log and replaces ONLY the
`BASE_URL=` line in `.env`. Every other byte (comments, spacing, CRLF/LF endings, order) is kept as-is.

No third-party packages: the unit tests use the standard-library `unittest` runner.

Usage:
  python scripts/tunnel_url.py find <tunnel.log>
  python scripts/tunnel_url.py wait <tunnel.log> [--timeout 30] [--interval 0.5]
  python scripts/tunnel_url.py set-base-url <envfile> <url>
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

URL_RE = re.compile(r"https://[A-Za-z0-9-]+\.trycloudflare\.com")
BASE_LINE_RE = re.compile(r"^(?P<lead>[ \t]*BASE_URL[ \t]*=[ \t]*)")


def find_url(text: str) -> str | None:
    """The first quick-tunnel URL in cloudflared output, or None."""
    match = URL_RE.search(text)
    return match.group(0) if match else None


def replace_base_url(text: str, url: str) -> str:
    """Replace every active BASE_URL line, keeping all other bytes exactly as they were.

    Commented-out examples (`# BASE_URL=...`) are left alone. If there is no active line, one is appended
    using the file's existing newline style.
    """
    if URL_RE.fullmatch(url) is None:
        raise ValueError("not a https://*.trycloudflare.com URL")

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    replaced = False
    for line in lines:
        content = line.rstrip("\r\n")
        ending = line[len(content) :]
        if not content.lstrip(" \t").startswith("#"):
            match = BASE_LINE_RE.match(content)
            if match:
                out.append(f"{match.group('lead')}{url}{ending}")
                replaced = True
                continue
        out.append(line)

    if replaced:
        return "".join(out)

    eol = "\r\n" if "\r\n" in text else "\n"
    if out and not out[-1].endswith(("\n", "\r")):
        out[-1] += eol
    out.append(f"BASE_URL={url}{eol}")
    return "".join(out)


def read_log(path: Path) -> str:
    """Read a cloudflared log, tolerating the UTF-16 that Windows `Tee-Object` writes."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    return data.decode("utf-8", errors="replace")


def wait_for_url(path: Path, timeout: float = 30.0, interval: float = 0.5) -> str | None:
    """Poll a log file until a quick-tunnel URL appears, or return None after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while True:
        url = find_url(read_log(path))
        if url:
            return url
        if time.monotonic() >= deadline:
            return None
        time.sleep(max(0.05, interval))


def _read_env(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _write_env(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="cloudflared URL + .env BASE_URL helper")
    sub = parser.add_subparsers(dest="command", required=True)

    find = sub.add_parser("find", help="print the first tunnel URL in a log")
    find.add_argument("log")

    wait = sub.add_parser("wait", help="poll a log until a tunnel URL appears")
    wait.add_argument("log")
    wait.add_argument("--timeout", type=float, default=30.0)
    wait.add_argument("--interval", type=float, default=0.5)

    set_base = sub.add_parser("set-base-url", help="replace BASE_URL in .env")
    set_base.add_argument("env")
    set_base.add_argument("url")

    args = parser.parse_args(argv)

    if args.command == "find":
        url = find_url(read_log(Path(args.log)))
        if not url:
            return 1
        print(url)
        return 0

    if args.command == "wait":
        url = wait_for_url(Path(args.log), args.timeout, args.interval)
        if not url:
            return 1
        print(url)
        return 0

    try:
        env_path = Path(args.env)
        text = _read_env(env_path)
        _write_env(env_path, replace_base_url(text, args.url))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"tunnel_url: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
