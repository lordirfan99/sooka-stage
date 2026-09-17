"""Refresh the Discord user token from live client traffic over CDP.

Why this exists
---------------
`localStorage.token` is stale on current Discord desktop builds and returns HTTP 401.
Scanning webpack modules for `getToken` yields nothing usable on 1.0.9258 / 1.0.1220 /
1.0.1177. The only authoritative source is the `Authorization` header of a request the
app itself makes, which is what this script captures.

Usage
-----
    python sniff_token.py 9224        # PTB;  9223 = stable, 9225 = Canary

Output
------
    C:\\Users\\irfan\\SookaStage\\.user_token.json   -> {"discord_user_token": "...", "src": "9224"}

The token value is never printed.

Notes
-----
* One persistent WebSocket, closed at the end (the stable client's /json endpoint
  wedges under interleaved sessions).
* `suppress_origin=True` is required: PTB answers the handshake with HTTP 403 when an
  Origin header is present and the client was not launched with --remote-allow-origins.
* Navigating to the channel URL is what forces the app to emit authorised requests.
"""

import json
import sys
import time
import urllib.request

import websocket

CHANNELS = {
    "9223": "https://discord.com/channels/1251553669644816518/1477692113738137600",
    "9224": "https://ptb.discord.com/channels/1251553669644816518/1481359453759475876",
    "9225": "https://canary.discord.com/channels/1251553669644816518/1481358977584599283",
}

TOKEN_PATH = r"C:\Users\irfan\SookaStage\.user_token.json"
TIMEOUT_S = 30


def main(port: str) -> int:
    if port not in CHANNELS:
        print(f"port must be one of {sorted(CHANNELS)}")
        return 2

    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5))
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        print("no page target on this port — client not running with --remote-debugging-port?")
        return 1

    ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"], timeout=TIMEOUT_S, suppress_origin=True)
    msg_id = 0

    def cmd(method, params=None):
        nonlocal msg_id
        msg_id += 1
        ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            resp = json.loads(ws.recv())
            if resp.get("id") == msg_id:
                return resp

    tokens = set()
    try:
        cmd("Network.enable")
        cmd("Page.navigate", {"url": CHANNELS[port]})

        ws.settimeout(8)
        deadline = time.time() + TIMEOUT_S
        while time.time() < deadline and not tokens:
            try:
                msg = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
            headers = (msg.get("params") or {}).get("headers") or {}
            for key, value in headers.items():
                if key.lower() == "authorization":
                    tokens.add(value)
    finally:
        ws.close()

    if not tokens:
        print("no Authorization header seen — is the client logged in?")
        return 1

    token = sorted(tokens)[0]
    with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
        json.dump({"discord_user_token": token, "src": port}, fh)

    print(f"stored token (len={len(token)}) -> {TOKEN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "9224"))
