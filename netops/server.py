"""Minimal MCP server over stdio, using only the Python standard library.

Claude Code starts it from .mcp.json and talks JSON-RPC 2.0, one message per
line. It implements the parts of the Model Context Protocol a tools-only
server needs: initialize, tools/list, tools/call and ping.
"""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Allow "python3 netops/server.py" as well as "python3 -m netops.server".
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from netops import __version__
from netops.data import DemoOrg, NetworkNotFound

SERVER_NAME = "meraki-demo"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

NETWORK_ARG = {
    "type": "string",
    "description": "Network name (or part of it, e.g. 'dublin') or network id (e.g. 'N_1001').",
}

TOOLS = [
    {
        "name": "list_networks",
        "description": "List every network (office) in the Meraki organisation, with its time zone, tags and ISP circuits.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "network_health_summary",
        "description": "Check one network, or all of them, and return its status (healthy, degraded or down) "
                       "with findings sorted by severity and a suggested next action for each.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}},
    },
    {
        "name": "get_device_statuses",
        "description": "Status of Meraki devices (MX appliances, MS switches, MR access points): online, offline, "
                       "alerting or dormant, with last report time and IPs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "network": NETWORK_ARG,
                "status": {"type": "string", "enum": ["online", "offline", "alerting", "dormant"]},
            },
        },
    },
    {
        "name": "get_uplink_statuses",
        "description": "WAN uplink status of each MX appliance (wan1, wan2, cellular): active, ready, failed or not connected.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}},
    },
    {
        "name": "get_network_clients",
        "description": "Clients seen on a network, with IP, VLAN, SSID, the device they are connected to and usage in KB.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}, "required": ["network"]},
    },
    {
        "name": "get_network_events",
        "description": "Event log of a network, newest first. Optional filter by event type "
                       "(e.g. dhcp_no_leases, disassociation, uplink_change, device_offline).",
        "inputSchema": {
            "type": "object",
            "properties": {"network": NETWORK_ARG, "event_type": {"type": "string"}},
            "required": ["network"],
        },
    },
    {
        "name": "get_channel_utilization",
        "description": "Wi-Fi channel utilisation per access point and band (wifi0 = 2.4 GHz, wifi1 = 5 GHz), "
                       "split into Wi-Fi traffic and non-Wi-Fi interference, in percent.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}, "required": ["network"]},
    },
    {
        "name": "get_vlans",
        "description": "VLANs configured on a network's MX appliance, with subnet, gateway IP and number of usable host addresses.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}, "required": ["network"]},
    },
]

TOOL_NAMES = {tool["name"] for tool in TOOLS}


def call_tool(org, name, arguments):
    """Run one tool and return its result as a JSON-serialisable object."""
    args = arguments or {}
    if name == "list_networks":
        return {"organization": org.organization(), "networks": org.networks()}
    if name == "network_health_summary":
        return org.health_summary(args.get("network"))
    if name == "get_device_statuses":
        return org.device_statuses(args.get("network"), args.get("status"))
    if name == "get_uplink_statuses":
        return org.uplink_statuses(args.get("network"))
    if name == "get_network_clients":
        return org.clients(args["network"])
    if name == "get_network_events":
        return org.events(args["network"], args.get("event_type"))
    if name == "get_channel_utilization":
        return org.channel_utilization(args["network"])
    if name == "get_vlans":
        return org.vlans(args["network"])
    raise ValueError("Unknown tool: {}".format(name))


def handle(org, message):
    """Handle one JSON-RPC message. Returns the response dict, or None for notifications."""
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    if msg_id is None:
        return None  # Notification (e.g. notifications/initialized): no reply.

    if method == "initialize":
        result = {
            "protocolVersion": params.get("protocolVersion", DEFAULT_PROTOCOL_VERSION),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": "Demo Meraki organisation (simulated data). Use network_health_summary first, "
                            "then the specific tools to dig into a finding.",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = params.get("name")
        if name not in TOOL_NAMES:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32602, "message": "Unknown tool: {}".format(name)}}
        try:
            data = call_tool(org, name, params.get("arguments"))
            result = {"content": [{"type": "text", "text": json.dumps(data, indent=2)}], "isError": False}
        except KeyError as missing:
            text = "Missing required argument: {}".format(missing)
            result = {"content": [{"type": "text", "text": text}], "isError": True}
        except NetworkNotFound as error:
            result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found: {}".format(method)}}

    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def main():
    org = DemoOrg()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = handle(org, message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
