"""Static checks: every agent config must start the exact same MCP server.

These tests read the config files; they do not launch the agents. Claude Code and Codex
were also verified by hand against a live session (see README).
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = "meraki-demo"
EXPECTED = {"command": "python3", "args": ["netops/server.py"]}


def codex_server():
    text = (ROOT / ".codex" / "config.toml").read_text()
    section = re.search(r"^\[mcp_servers\.{}\]\n(.*?)(?=^\[|\Z)".format(SERVER), text, re.S | re.M).group(1)
    return {
        "command": re.search(r'^command\s*=\s*"([^"]+)"', section, re.M).group(1),
        "args": json.loads(re.search(r"^args\s*=\s*(\[.*?\])", section, re.M).group(1)),
    }


class AgentConfigTest(unittest.TestCase):
    def assert_expected(self, config, label):
        self.assertEqual(config["command"], EXPECTED["command"], label)
        self.assertEqual(config["args"], EXPECTED["args"], label)
        # Relative path: every agent must be started from the repository root (README says so).
        self.assertTrue((ROOT / config["args"][0]).is_file(), label)

    def test_claude_code(self):
        self.assert_expected(json.loads((ROOT / ".mcp.json").read_text())["mcpServers"][SERVER], ".mcp.json")

    def test_codex(self):
        self.assert_expected(codex_server(), ".codex/config.toml")

    def test_gemini_cli(self):
        settings = json.loads((ROOT / ".gemini" / "settings.json").read_text())
        self.assert_expected(settings["mcpServers"][SERVER], ".gemini/settings.json")
        self.assertEqual(settings["mcpServers"][SERVER].get("cwd"), ".")
        self.assertIn("AGENTS.md", settings["context"]["fileName"])

    def test_antigravity_cli(self):
        config = json.loads((ROOT / ".agents" / "mcp_config.json").read_text())["mcpServers"][SERVER]
        self.assert_expected(config, ".agents/mcp_config.json")

    def test_shared_skill_exists_where_agents_md_says(self):
        self.assertIn(".agents/skills/network-triage/SKILL.md", (ROOT / "AGENTS.md").read_text())
        self.assertTrue((ROOT / ".agents" / "skills" / "network-triage" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
