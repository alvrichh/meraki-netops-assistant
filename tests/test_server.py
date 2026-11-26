"""End-to-end check: start the MCP server as Claude Code would and talk to it over stdio."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class McpServerTest(unittest.TestCase):
    def exchange(self, messages):
        payload = "".join(json.dumps(m) + "\n" for m in messages)
        proc = subprocess.run(
            [sys.executable, "netops/server.py"], input=payload, capture_output=True,
            text=True, cwd=str(ROOT), timeout=20, check=True,
        )
        return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]

    def test_handshake_list_and_call(self):
        replies = self.exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "network_health_summary", "arguments": {"network": "london"}}},
        ])
        self.assertEqual([r["id"] for r in replies], [1, 2, 3])  # the notification gets no reply
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "meraki-demo")
        tool_names = {t["name"] for t in replies[1]["result"]["tools"]}
        self.assertIn("network_health_summary", tool_names)
        summary = json.loads(replies[2]["result"]["content"][0]["text"])
        self.assertEqual(summary[0]["network"], "London")

    def test_errors(self):
        replies = self.exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_vlans", "arguments": {"network": "tokyo"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_vlans", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "reboot_everything"}},
            {"jsonrpc": "2.0", "id": 4, "method": "no/such/method"},
        ])
        self.assertTrue(replies[0]["result"]["isError"])
        self.assertIn("No network matches", replies[0]["result"]["content"][0]["text"])
        self.assertIn("Missing required argument", replies[1]["result"]["content"][0]["text"])
        self.assertEqual(replies[2]["error"]["code"], -32602)
        self.assertEqual(replies[3]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
