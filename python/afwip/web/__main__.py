"""
One-command launcher:  python -m afwip.web  [--port 8000] [--no-browser]

Starts the local FastAPI server and opens the browser at it.

Two-device play on the same network:  python -m afwip.web --lan
(shorthand for --host 0.0.0.0). The launcher then prints the exact
http://<your-ip>:<port> URL to share with the other player.
"""

from __future__ import annotations

import argparse
import socket
import threading
import webbrowser

# Hosts that only ever mean "this machine" — serving on one of these means no
# other device can connect, so we don't advertise a shareable URL.
_LOOPBACK = {"127.0.0.1", "localhost", "::1", ""}


def _lan_ip() -> str | None:
    """Best-effort local network IP of this machine (e.g. 192.168.1.42).

    Opens a UDP socket "toward" a public address and reads back which local
    interface the OS would route through — no packet is actually sent, so it
    works offline and needs no network round-trip. Returns None if it can't be
    determined (fall back to telling the user to look it up manually)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    # Fallback: resolve the hostname (can yield 127.0.0.1 on some setups).
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return None


def _print_share_banner(port: int) -> None:
    """Print the URLs to open on this machine and to share with the other
    player, for two-device network play."""
    line = "─" * 60
    local = f"http://127.0.0.1:{port}"
    ip = _lan_ip()
    print(f"\n{line}")
    print(" AFWIP is hosting a game on your network.")
    print(f"   On THIS computer:            {local}")
    if ip:
        print(f"   Share with the other player: http://{ip}:{port}")
        print("   (they must be on the same Wi-Fi / network)")
    else:
        print("   Share with the other player: http://<this-computer's-IP>:"
              f"{port}")
        print("   Find this computer's IP:")
        print("     macOS:    ipconfig getifaddr en0")
        print("     Windows:  ipconfig   (look for IPv4 Address)")
        print("     Linux:    hostname -I")
    print("   Can't connect? Guest/enterprise Wi-Fi often blocks this —")
    print("   see the two-device notes in the README (a phone hotspot works).")
    print(f"{line}\n", flush=True)   # flush: stdout is block-buffered when piped


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AFWIP local web game")
    parser.add_argument("--host", default="127.0.0.1",
                        help="interface to bind (default 127.0.0.1, this "
                             "machine only)")
    parser.add_argument("--lan", action="store_true",
                        help="host a two-device network game: bind all "
                             "interfaces (0.0.0.0) and print a URL to share")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true",
                        help="don't auto-open the browser")
    args = parser.parse_args(argv)

    host = "0.0.0.0" if args.lan else args.host
    # Serving beyond loopback -> another device can join; show the share URL.
    on_network = host not in _LOOPBACK

    import uvicorn
    from afwip.web.app import app

    if on_network:
        _print_share_banner(args.port)

    if not args.no_browser:
        # The host's own browser always opens on loopback (a bound-all host
        # like 0.0.0.0 isn't itself a reachable URL).
        browse_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        url = f"http://{browse_host}:{args.port}"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
