"""The three agent configs must start the same MCP server, and that server must exist."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = "meraki-demo"


class AgentConfigTest(unittest.TestCase):
    def assert_points_to_server(self, command, args):
        self.assertEqual(command, "python3")
        self.assertTrue((ROOT / args[0]).is_file(), "{} does not exist".format(args[0]))

    def test_claude_code(self):
        config = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"][SERVER]
        self.assert_points_to_server(config["command"], config["args"])

    def test_gemini(self):
        settings = json.loads((ROOT / ".gemini" / "settings.json").read_text())
        config = settings["mcpServers"][SERVER]
        self.assert_points_to_server(config["command"], config["args"])
        self.assertIn("AGENTS.md", settings["context"]["fileName"])

    def test_codex(self):
        text = (ROOT / ".codex" / "config.toml").read_text()
        section = re.search(r"\[mcp_servers\.{}\](.*?)(?:\n\[|\Z)".format(SERVER), text, re.S).group(1)
        command = re.search(r'command\s*=\s*"([^"]+)"', section).group(1)
        args = json.loads(re.search(r"args\s*=\s*(\[.*?\])", section).group(1))
        self.assert_points_to_server(command, args)

    def test_shared_skill_exists_where_agents_md_says(self):
        self.assertIn(".agents/skills/network-triage/SKILL.md", (ROOT / "AGENTS.md").read_text())
        self.assertTrue((ROOT / ".agents" / "skills" / "network-triage" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
