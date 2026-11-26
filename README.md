<p align="center">
  <img src="assets/logo.svg" width="120" alt="Meraki NetOps assistant logo">
</p>

<h1 align="center">Meraki NetOps assistant</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Cisco_Meraki-Dashboard_API_v1-1BA0D7?logo=cisco&logoColor=white" alt="Cisco Meraki Dashboard API v1">
  <img src="https://img.shields.io/badge/MCP-stdio_server-6E56CF" alt="MCP stdio server">
  <img src="https://img.shields.io/badge/Claude_Code-ready-D97757?logo=claude&logoColor=white" alt="Claude Code ready">
  <img src="https://img.shields.io/badge/Codex-ready-111111" alt="Codex ready">
  <img src="https://img.shields.io/badge/Gemini_CLI-ready-4285F4?logo=googlegemini&logoColor=white" alt="Gemini CLI ready">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/dependencies-none-2EA44F" alt="No dependencies">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT license">
</p>

Ask your AI coding agent (Claude Code, Codex or Gemini CLI) about your office networks in plain English and get the cause, the evidence and the next action, ready to paste into a ticket.

*Independent project, not affiliated with or endorsed by Cisco.*

```
> Users on the 3rd floor in Dublin say the Wi-Fi is slow. What's going on?
```

The repository connects an AI agent to Cisco Meraki network data through a small [MCP](https://modelcontextprotocol.io) server. It needs **no API keys and no dependencies**: the AI is the agent session you open in the repo, and the server is pure Python standard library.

> **Demo data.** The network is a simulated company, Northwind Labs, with four offices. The data in `data/demo-org.json` follows the field names of the [Meraki Dashboard API v1](https://developer.cisco.com/meraki/api-v1/), so the tools can later be pointed at a real organisation.

## What it finds in the demo

| Office | Problem | What the assistant suggests |
|---|---|---|
| Dublin HQ | One access point offline; the AP next to it at 86% channel use on 5 GHz | Check PoE and cabling on the offline AP's switch port; spread clients, review channels |
| London | Main internet line (wan1) down, office running on 4G backup | Raise a fault with the ISP, quoting the circuit id and failure time |
| Barcelona | Guest VLAN ran out of DHCP leases (a /26: 62 addresses) | Enlarge the subnet or shorten the lease time |
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
| [Gemini CLI](https://geminicli.com) / Antigravity CLI | `gemini` | `.gemini/settings.json` | `AGENTS.md` (set in `.gemini/settings.json`) |

All three start the same server and follow the same `AGENTS.md`, so the answers are consistent whichever AI you use. The Claude Code setup is tested end to end; the Codex and Gemini configs follow each tool's documented format and are checked by `tests/test_agent_configs.py`. Gemini CLI was succeeded by Antigravity CLI in June 2026; if your version does not pick up `.gemini/settings.json`, add the server from that file to its own config.

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

The tools only read data. Fixes are returned as recommendations for a person to apply in the Meraki dashboard.

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

The tests cover the queries, the health rules, a full MCP session over stdio (initialize, tools/list, tools/call and error cases) and the three agent configs.

## Roadmap

- Live mode: read from a real Meraki organisation with a read-only API key, kept outside the repo.
- Cloudflare Zero Trust checks (WARP client and access policy logs).
- Scheduled health report posted to Slack.

## License

MIT
