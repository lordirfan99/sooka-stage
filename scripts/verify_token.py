"""Verify the stored Discord user token against the REST API.

    python verify_token.py

Prints the account username on success, or the HTTP status on failure. The token value
itself is never printed.

A 401 means the token is stale: refresh it with `sniff_token.py <port>`. Tokens are
usually invalidated when the Discord client restarts.
"""

import json
import sys

import requests

TOKEN_PATH = r"C:\Users\irfan\SookaStage\.user_token.json"
API = "https://discord.com/api/v9"


def main() -> int:
    try:
        with open(TOKEN_PATH, encoding="utf-8") as fh:
            token = json.load(fh)["discord_user_token"]
    except FileNotFoundError:
        print(f"no token file at {TOKEN_PATH} — run sniff_token.py <port>")
        return 2
    except (KeyError, ValueError) as exc:
        print(f"token file unreadable: {exc}")
        return 2

    headers = {"Authorization": token, "User-Agent": "Mozilla/5.0"}
    resp = requests.get(f"{API}/users/@me", headers=headers, timeout=15)

    if resp.status_code == 200:
        data = resp.json()
        print(f"OK  username={data.get('username')}  id={data.get('id')}")
        return 0

    print(f"FAIL  HTTP {resp.status_code} — refresh with sniff_token.py <port>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
