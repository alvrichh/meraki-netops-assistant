"""End-to-end checks: start the MCP server as an agent would and talk to it over stdio."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INITIALIZE = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def call(msg_id, name, arguments=None):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": params}


class McpServerTest(unittest.TestCase):
    def exchange(self, messages):
        lines = [m if isinstance(m, str) else json.dumps(m) for m in messages]
        proc = subprocess.run(
            [sys.executable, "netops/server.py"], input="\n".join(lines) + "\n", capture_output=True,
            text=True, encoding="utf-8", cwd=str(ROOT), timeout=20, check=True,
        )
        return {r["id"]: r for r in (json.loads(line) for line in proc.stdout.splitlines() if line.strip())}

    def test_handshake_list_and_call(self):
        replies = self.exchange([
            INITIALIZE, INITIALIZED,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            call(3, "network_health_summary", {"network": "london"}),
        ])
        self.assertEqual(sorted(replies), [0, 2, 3])  # the notification gets no reply
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "meraki-demo")
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        tool_names = {t["name"] for t in replies[2]["result"]["tools"]}
        self.assertIn("network_health_summary", tool_names)
        summary = json.loads(replies[3]["result"]["content"][0]["text"])
        self.assertEqual(summary[0]["network"], "London")

    def test_unsupported_protocol_version_gets_a_supported_one(self):
        request = json.loads(json.dumps(INITIALIZE))
        request["params"]["protocolVersion"] = "1999-01-01"
        replies = self.exchange([request])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")

    def test_tools_before_initialize_are_refused(self):
        replies = self.exchange([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        self.assertEqual(replies[1]["error"]["code"], -32002)

    def test_tool_errors_after_handshake(self):
        replies = self.exchange([
            INITIALIZE, INITIALIZED,
            call(1, "get_vlans", {"network": "tokyo"}),
            call(2, "get_vlans", {}),
            call(3, "get_vlans", {"network": 42}),
            call(4, "get_device_statuses", {"status": "broken"}),
            call(5, "reboot_everything"),
            {"jsonrpc": "2.0", "id": 6, "method": "no/such/method"},
        ])
        self.assertIn("No network matches", replies[1]["result"]["content"][0]["text"])
        self.assertIn("Missing required argument: network", replies[2]["result"]["content"][0]["text"])
        self.assertIn("must be a string", replies[3]["result"]["content"][0]["text"])
        self.assertIn("must be one of", replies[4]["result"]["content"][0]["text"])
        for msg_id in (1, 2, 3, 4):
            self.assertTrue(replies[msg_id]["result"]["isError"])
        self.assertEqual(replies[5]["error"]["code"], -32602)
        self.assertEqual(replies[6]["error"]["code"], -32601)

    def test_malformed_messages_do_not_end_the_session(self):
        replies = self.exchange([
            INITIALIZE, INITIALIZED,
            "this is not json",
            "[1, 2, 3]",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": "not an object"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_vlans", "arguments": ["x"]}},
            {"jsonrpc": "2.0", "id": None, "method": "tools/list"},
            call(3, "list_networks"),  # still answered after all of the above
        ])
        self.assertEqual(replies[None]["error"]["code"], -32600)  # last of the id-less errors
        self.assertEqual(replies[1]["error"]["code"], -32602)
        self.assertTrue(replies[2]["result"]["isError"])
        self.assertFalse(replies[3]["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
