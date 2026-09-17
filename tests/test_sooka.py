"""Tests for the parts of the SookaStage automation that are OS-independent.

The flow itself needs a live Discord client, but the transport, the target
picker, the netstat parser and the tile disambiguation are all pure enough to
test here -- and each one of them is a bug that actually bit us.

    python3 -m unittest discover -s tests -v
"""
import json
import os
import socket
import struct
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sooka_cdp import (  # noqa: E402
    CDP,
    CDPError,
    OP_PING,
    OP_TEXT,
    encode_frame,
    parse_netstat_pid,
    pick_page,
    read_frame,
)
from sookastage_prod import browser_identity, choose_tile, by_label, by_href  # noqa: E402


def server_frame(payload: bytes, opcode: int = OP_TEXT) -> bytes:
    """Server -> client frames are NOT masked."""
    n = len(payload)
    if n < 126:
        head = struct.pack("!BB", 0x80 | opcode, n)
    elif n < 65536:
        head = struct.pack("!BBH", 0x80 | opcode, 126, n)
    else:
        head = struct.pack("!BBQ", 0x80 | opcode, 127, n)
    return head + payload


class TestFraming(unittest.TestCase):
    def test_roundtrip_all_length_classes(self):
        for size in (0, 5, 125, 126, 1000, 70000):
            a, b = socket.socketpair()
            try:
                payload = b"x" * size
                a.sendall(encode_frame(payload))
                fin, op, data = read_frame(b)
                self.assertTrue(fin)
                self.assertEqual(op, OP_TEXT)
                self.assertEqual(data, payload, f"size {size} round-tripped wrong")
            finally:
                a.close()
                b.close()

    def test_client_frames_are_masked(self):
        frame = encode_frame(b"hello")
        self.assertTrue(frame[1] & 0x80, "client frames must set the MASK bit (RFC 6455)")


class TestTargetPicking(unittest.TestCase):
    TARGETS = [
        {"type": "background_page", "url": "chrome://x", "webSocketDebuggerUrl": "ws://a"},
        {"type": "page", "url": "https://discord.com/channels/@me", "webSocketDebuggerUrl": "ws://b"},
        {"type": "page", "url": "https://discord.com/channels/GUILD/999", "webSocketDebuggerUrl": "ws://c"},
        {"type": "page", "url": "https://discord.com/channels/GUILD/1477692113738137600", "webSocketDebuggerUrl": "ws://d"},
    ]

    def test_prefers_exact_channel(self):
        page = pick_page(self.TARGETS, "GUILD", "1477692113738137600")
        self.assertEqual(page["webSocketDebuggerUrl"], "ws://d")

    def test_falls_back_to_guild(self):
        page = pick_page(self.TARGETS, "GUILD", "does-not-exist")
        self.assertIn(page["webSocketDebuggerUrl"], ("ws://c", "ws://d"))

    def test_no_pages_returns_none_instead_of_indexerror(self):
        # the v1 code did `[...][0]` here and raised IndexError with no context
        self.assertIsNone(pick_page([{"type": "background_page"}]))

    def test_ignores_targets_without_a_ws_url(self):
        self.assertIsNone(pick_page([{"type": "page", "url": "https://discord.com/"}]))


class TestNetstat(unittest.TestCase):
    SAMPLE = """
  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:19223        0.0.0.0:0              LISTENING       4444
  TCP    127.0.0.1:9223         0.0.0.0:0              LISTENING       1234
  TCP    127.0.0.1:9223         127.0.0.1:55001        ESTABLISHED     1234
  TCP    10.0.0.5:51000         93.184.16.1:9223       ESTABLISHED     9999
  TCP    127.0.0.1:9225         0.0.0.0:0              LISTENING       5678
"""

    def test_exact_port_only(self):
        self.assertEqual(parse_netstat_pid(self.SAMPLE, 9223), 1234)
        self.assertEqual(parse_netstat_pid(self.SAMPLE, 9225), 5678)

    def test_does_not_match_19223_or_remote_port(self):
        # `findstr ":9223"` matched both of those and kept the LAST one -> 9999
        self.assertNotEqual(parse_netstat_pid(self.SAMPLE, 9223), 9999)
        self.assertNotEqual(parse_netstat_pid(self.SAMPLE, 9223), 4444)

    def test_absent_port(self):
        self.assertIsNone(parse_netstat_pid(self.SAMPLE, 9224))


class TestTileChoice(unittest.TestCase):
    TILES = [
        "Watch online Live Sports, sooka - Brave",
        "Watch online Live Sports, sooka - Chrome Beta",
        "Watch online Live Sports, sooka - Google Chrome",
        "Discord",
    ]

    def test_each_browser_resolves_to_its_own_tile(self):
        for browser, expected in (("Brave", 0), ("Chrome Beta", 1), ("Google Chrome", 2)):
            index, reason = choose_tile(self.TILES, browser)
            self.assertEqual(index, expected, f"{browser}: {reason}")

    def test_google_chrome_does_not_steal_chrome_beta(self):
        # the substring bug that put two streams on one window
        self.assertEqual(browser_identity("sooka - Chrome Beta"), "chrome beta")
        self.assertEqual(browser_identity("sooka - Google Chrome"), "google chrome")

    def test_chrome_beta_wins_when_label_also_contains_google_chrome(self):
        # Chrome Beta's own OS window title suffix on this machine is
        # "- Google Chrome" (no "Beta"), so a real Chrome Beta tile's label
        # contains BOTH phrases: "sooka - Chrome Beta - Google Chrome".
        # "google chrome" is the longer string but must NOT win here.
        self.assertEqual(
            browser_identity("sooka - Chrome Beta - Google Chrome"), "chrome beta")

    def test_ambiguous_browser_name_refuses(self):
        index, reason = choose_tile(self.TILES, "Chrome")
        self.assertIsNone(index)
        self.assertIn("unambiguous", reason)

    def test_duplicate_tiles_refuse_rather_than_guess(self):
        tiles = ["sooka - Brave", "something else - Brave"]
        index, reason = choose_tile(tiles, "Brave")
        self.assertIsNone(index)
        self.assertIn("refusing to guess", reason)

    def test_duplicate_tiles_resolved_by_sooka_title(self):
        tiles = ["Watch online Live Sports, sooka - Brave", "Gmail - Brave"]
        index, _ = choose_tile(tiles, "Brave")
        self.assertEqual(index, 0)

    def test_missing_tile_reports_what_was_offered(self):
        index, reason = choose_tile(["sooka - Brave"], "Firefox")
        self.assertIsNone(index)
        self.assertIn("brave", reason)


class TestPredicates(unittest.TestCase):
    def test_by_label_scopes_to_dialog(self):
        self.assertIn("closest('[role=dialog]')", by_label("go live", in_dialog=True))

    def test_by_label_is_case_insensitive_regex(self):
        self.assertIn("/go live/i", by_label("go live"))

    def test_by_href_anchors_on_the_end_of_the_href(self):
        js = by_href("1477692113738137600")
        self.assertIn(".endsWith('/1477692113738137600')", js)


class FakeDevTools(threading.Thread):
    """Minimal DevTools server: answers Runtime.evaluate, and deliberately
    interleaves a PING and an unsolicited event first."""

    def __init__(self, sock, value):
        super().__init__(daemon=True)
        self.sock = sock
        self.value = value
        self.methods = []
        self.pongs = 0

    def run(self):
        try:
            while True:
                fin, op, data = read_frame(self.sock)
                if op != OP_TEXT:
                    # the client PONGs our PING -- proof it handles opcodes
                    self.pongs += 1
                    continue
                msg = json.loads(data.decode())
                self.methods.append(msg["method"])
                self.sock.sendall(server_frame(b"ping-payload", OP_PING))
                self.sock.sendall(server_frame(json.dumps(
                    {"method": "Runtime.consoleAPICalled", "params": {}}).encode()))
                self.sock.sendall(server_frame(json.dumps(
                    {"id": msg["id"], "result": {"result": {"value": self.value}}}).encode()))
        except Exception:
            return


class TestEvaluate(unittest.TestCase):
    def _client(self, value):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        self.server = FakeDevTools(b, value)
        self.server.start()
        return CDP(a, port=0)

    def test_json_string_is_parsed_exactly_once(self):
        """The v1 regression: ev() parsed the JSON, then clipped_click parsed the
        resulting dict again, hit TypeError, swallowed it and returned None --
        so every click silently became a no-op."""
        cdp = self._client(json.dumps({"x": 10, "y": 20}))
        self.assertEqual(cdp.evaluate_json("whatever"), {"x": 10, "y": 20})

    def test_evaluate_json_is_idempotent_on_a_plain_string(self):
        cdp = self._client("hello")
        self.assertEqual(cdp.evaluate_json("whatever"), "hello")

    def test_ping_and_events_do_not_break_the_response(self):
        cdp = self._client(json.dumps({"ok": True}))
        # v1's _recv() ignored the opcode, so this PING crashed the run
        self.assertEqual(cdp.evaluate_json("x"), {"ok": True})
        self.assertEqual(cdp.evaluate_json("y"), {"ok": True})
        self.assertGreater(self.server.pongs, 0, "client never answered the PING with a PONG")

    def test_find_rejects_a_non_dict_result(self):
        cdp = self._client("not-json")
        with self.assertRaises(CDPError):
            cdp.find("true")

    def test_click_reports_not_found_instead_of_pretending(self):
        cdp = self._client(json.dumps({"count": 0, "candidates": []}))
        res = cdp.click("true")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not-found")


class TestEvaluateErrors(unittest.TestCase):
    def test_js_exception_raises(self):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)

        def serve():
            fin, op, data = read_frame(b)
            msg = json.loads(data.decode())
            b.sendall(server_frame(json.dumps({
                "id": msg["id"],
                "result": {"result": {"type": "object"},
                           "exceptionDetails": {"exception": {"description": "ReferenceError: nope"}}},
            }).encode()))

        threading.Thread(target=serve, daemon=True).start()
        cdp = CDP(a, port=0)
        with self.assertRaises(CDPError) as ctx:
            cdp.evaluate("nope()")
        self.assertIn("ReferenceError", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
