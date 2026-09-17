import json, urllib.request

for port in (9223, 9224, 9225):
    try:
        t = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=4))
        pages = [x.get("url", "")[:60] for x in t if x.get("type") == "page"]
        print(port, "UP", pages[:2])
    except Exception as e:
        print(port, "DOWN", str(e)[:50])
