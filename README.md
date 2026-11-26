# Meraki NetOps assistant

Ask Claude Code about your office networks in plain English and get the cause, the evidence and the next action, ready to paste into a ticket.

```
> Users on the 3rd floor in Dublin say the Wi-Fi is slow. What's going on?
```

The repository connects Claude Code to Cisco Meraki network data through a small [MCP](https://modelcontextprotocol.io) server. It needs **no API keys and no dependencies**: the AI is the Claude Code session you open in the repo, and the server is pure Python standard library.

> **Demo data.** The network is a simulated company, Northwind Labs, with four offices. The data in `data/demo-org.json` follows the field names of the [Meraki Dashboard API v1](https://developer.cisco.com/meraki/api-v1/), so the tools can later be pointed at a real organisation.

## What it finds in the demo

| Office | Problem | What the assistant suggests |
|---|---|---|
| Dublin HQ | One access point offline; the AP next to it at 86% channel use on 5 GHz | Check PoE and cabling on the offline AP's switch port; spread clients, review channels |
| London | Main internet line (wan1) down, office running on 4G backup | Raise a fault with the ISP, quoting the circuit id and failure time |
| Barcelona | Guest VLAN ran out of DHCP leases (a /26: 62 addresses) | Enlarge the subnet or shorten the lease time |
| San Francisco | Healthy | Nothing to do |

## Run it

Requirements: Python 3.9 or newer and [Claude Code](https://code.claude.com).

```bash
git clone https://github.com/alvrichh/meraki-netops-assistant.git
cd meraki-netops-assistant
claude
```

Claude Code reads `.mcp.json`, asks you once to approve the `meraki-demo` server, and the tools are ready. Try:

- "How are all the offices doing?"
- "Why can't guests in Barcelona connect?"
- "Write the fault report for the London ISP."
- "Run the network triage for Dublin, 3rd floor."

Without Claude, the same checks in the terminal:

```bash
python3 -m netops.cli            # every office
python3 -m netops.cli london     # one office
```

## How it works

```
Claude Code ──stdio / JSON-RPC──▶ netops/server.py (MCP) ──▶ netops/data.py ──▶ data/demo-org.json
     │
     ├─ CLAUDE.md                         how to answer: evidence first, no invented data
     └─ .claude/skills/network-triage     step-by-step triage: WAN → devices → Wi-Fi → DHCP → report
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

The tests cover the queries, the health rules and a full MCP session over stdio (initialize, tools/list, tools/call and error cases).

## Roadmap

- Live mode: read from a real Meraki organisation with a read-only API key, kept outside the repo.
- Cloudflare Zero Trust checks (WARP client and access policy logs).
- Scheduled health report posted to Slack.

## License

MIT
