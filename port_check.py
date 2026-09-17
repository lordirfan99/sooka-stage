import json, urllib.request

for port in (9224, 9223):
    try:
        t = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5))
        for x in t:
            print(port, x.get("type"), (x.get("url") or "")[:70])
    except Exception as e:
        print(port, "ERR", str(e)[:80].encode("ascii", "replace").decode())
