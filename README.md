<p align="center">
  <img src="assets/logo.svg" width="120" alt="Meraki NetOps assistant logo">
</p>

<h1 align="center">Meraki NetOps assistant</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Cisco_Meraki-Dashboard_API_v1-1BA0D7?logo=cisco&logoColor=white" alt="Cisco Meraki Dashboard API v1">
  <img src="https://img.shields.io/badge/MCP-stdio_server-6E56CF" alt="MCP stdio server">
  <img src="https://img.shields.io/badge/Claude_Code-tested-D97757?logo=claude&logoColor=white" alt="Claude Code tested">
  <img src="https://img.shields.io/badge/Codex-tested-111111" alt="Codex tested">
  <img src="https://img.shields.io/badge/Gemini_%2F_Antigravity-configured-4285F4?logo=googlegemini&logoColor=white" alt="Gemini CLI and Antigravity CLI configured">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/dependencies-none-2EA44F" alt="No dependencies">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT license">
</p>

Ask your AI coding agent (Claude Code, Codex, Gemini CLI or Antigravity CLI) about your office networks in plain English and get the likely cause, the evidence behind it and the next action, ready to paste into a ticket.

*Independent project, not affiliated with or endorsed by Cisco.*

```
> Users on the 3rd floor in Dublin say the Wi-Fi is slow. What's going on?
```

The repository connects an AI agent to Cisco Meraki network data through a small [MCP](https://modelcontextprotocol.io) server. It needs **no API keys and no dependencies**: the AI is the agent session you open in the repo, and the server is pure Python standard library.

> **Demo data.** The network is a simulated company, Northwind Labs, with four offices. The data in `data/demo-org.json` uses the field names of the [Meraki Dashboard API v1](https://developer.cisco.com/meraki/api-v1/) (checked against v1.76.0), with simplified responses: no pagination envelopes and a few inventory fields such as ISP circuits. Pointing the tools at a real organisation would need a small adapter in front of `netops/data.py`; the MCP tools would stay the same.

## What it finds in the demo

| Office | Problem | What the assistant suggests |
|---|---|---|
| Dublin HQ | One access point offline; the AP next to it at 86% channel use on 5 GHz | Check PoE and cabling on the offline AP's switch port; spread clients, review channels |
| London | Main internet line (wan1) down, office running on 4G backup | Raise a fault with the ISP, quoting the circuit id and failure time |
| Barcelona | Guest VLAN ran out of DHCP leases 3 times in 24 hours (a /26: 62 host addresses) | Check lease use, then enlarge the subnet or shorten the lease time |
| San Francisco | Healthy | Nothing to do |

## Run it

Requirements: Python 3.9 or newer and one of the agents below.

```bash
git clone https://github.com/alvrichh/meraki-netops-assistant.git
cd meraki-netops-assistant
```

Then start the agent you use, from the repository root:

| Agent | Command | Reads the MCP server from | Reads the instructions from |
|---|---|---|---|
| [Claude Code](https://code.claude.com) | `claude` | `.mcp.json` (approve `meraki-demo` once) | `CLAUDE.md` → `AGENTS.md` |
| [OpenAI Codex](https://developers.openai.com/codex) | `codex` | `.codex/config.toml` (trust the project once) | `AGENTS.md` |
| [Gemini CLI](https://geminicli.com) | `gemini` | `.gemini/settings.json` | `AGENTS.md` (set in `.gemini/settings.json`) |
| [Antigravity CLI](https://antigravity.google/docs/cli/gcli-migration/) | `agy` | `.agents/mcp_config.json` | `AGENTS.md` |

All four start the same server with the same command, follow the same `AGENTS.md` and share the triage skill in `.agents/skills`, so the answers are consistent whichever AI you use. **Claude Code and Codex are tested end to end**: both start the server, call the tools and diagnose the four offices. The Gemini CLI and Antigravity CLI configs follow each tool's documentation and are checked statically by `tests/test_agent_configs.py`, but have not been run against a live session. Google is moving Gemini CLI users to Antigravity CLI; see its [migration guide](https://antigravity.google/docs/cli/gcli-migration/).

Try:

- "How are all the offices doing?"
- "Why can't guests in Barcelona connect?"
- "Write the fault report for the London ISP."
- "Run the network triage for Dublin, 3rd floor."

Without an AI agent, the same checks in the terminal:

```bash
python3 -m netops.cli            # every office
python3 -m netops.cli london     # one office
```

## How it works

```
Claude Code ─┐
Codex ───────┼─stdio / JSON-RPC─▶ netops/server.py (MCP) ──▶ netops/data.py ──▶ data/demo-org.json
Gemini CLI ──┘
     │
     ├─ AGENTS.md                         how to answer: evidence first, no invented data (shared by all agents)
     └─ .agents/skills/network-triage     step-by-step triage: WAN → devices → Wi-Fi → DHCP → report
```

| Tool | Meraki API equivalent |
|---|---|
| `list_networks` | `GET /organizations/{orgId}/networks` (+ ISP circuits from IT inventory) |
| `get_device_statuses` | `GET /organizations/{orgId}/devices/statuses` |
| `get_uplink_statuses` | `GET /organizations/{orgId}/appliance/uplink/statuses` |
| `get_network_clients` | `GET /networks/{networkId}/clients` |
| `get_network_events` | `GET /networks/{networkId}/events` |
| `get_channel_utilization` | `GET /networks/{networkId}/networkHealth/channelUtilization` |
| `get_vlans` | `GET /networks/{networkId}/appliance/vlans` |
| `network_health_summary` | Combines the above and ranks findings by severity |

The tools only read data. Findings describe what the data shows, a symptom or a likely cause, not a confirmed root cause; fixes are returned as recommendations for a person to apply in the Meraki dashboard.

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

The tests cover the queries and health rules (including WAN with no active uplink or no data, HA spares and DHCP per VLAN within 24 hours), MCP sessions over stdio (version negotiation, calls before `initialize`, argument validation, malformed messages that must not end the session) and static checks that the four agent configs start the same server.

The code was reviewed by OpenAI Codex as an independent code review; its findings (request validation, protocol version negotiation, false "healthy" WAN results, DHCP grouping, timestamps on RF samples, exact name matching and the Antigravity setup) are fixed and covered by tests.

## Roadmap

- Live mode: read from a real Meraki organisation with a read-only API key, kept outside the repo.
- Cloudflare Zero Trust checks (WARP client and access policy logs).
- Scheduled health report posted to Slack.

## License

MIT
