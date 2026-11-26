"""Read-only queries over the demo Meraki organisation.

The fixture keeps Meraki Dashboard API v1 field names. Responses are simplified
(no pagination envelopes, no headers), so a live data source would need a thin
adapter in front of these methods; the MCP tools would not change.
"""

import ipaddress
import json
from datetime import datetime, timedelta
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "demo-org.json"

CHANNEL_UTILIZATION_ALERT = 70.0  # percent of airtime, any radio
EVENT_WINDOW = timedelta(hours=24)  # events older than this before the snapshot are ignored
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Radio-to-band mapping for the dual-band access points in the demo (inventory data, not from the API).
RADIO_BANDS = {"MR36": {"wifi0": "2.4 GHz", "wifi1": "5 GHz"}, "MR46": {"wifi0": "2.4 GHz", "wifi1": "5 GHz"}}

OFFLINE_ACTIONS = {
    "wireless": "Check PoE and link on the switch port that feeds it, then the cable; if the port is up, "
                "power-cycle the AP from the dashboard.",
    "switch": "Check power and the switch's uplink to the appliance; on-site hands may be needed.",
    "appliance": "Check power and the ISP handoff; the whole office may be cut off from the dashboard.",
}


def parse_time(value):
    """Parse a Meraki ISO 8601 timestamp (with Z or offset, any fractional precision)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class NetworkNotFound(ValueError):
    """Raised when a network name or id does not match exactly one network."""


class DemoOrg:
    def __init__(self, path=DATA_FILE):
        with open(path, encoding="utf-8") as handle:
            self._data = json.load(handle)

    # ---------------------------------------------------------------- lookups

    def organization(self):
        return self._data["organization"]

    def networks(self):
        return list(self._data["networks"])

    def snapshot_time(self):
        """Time of the newest device report: the 'now' of the demo data."""
        return max(parse_time(d["lastReportedAt"]) for d in self._data["devices"])

    def resolve_network(self, query):
        """Find one network by id, exact name, or unique part of its name (case-insensitive)."""
        text = str(query).strip().lower()
        networks = self._data["networks"]
        for network in networks:
            if network["id"].lower() == text:
                return network
        for network in networks:
            if network["name"].lower() == text:
                return network
        matches = [n for n in networks if text and text in n["name"].lower()]
        if len(matches) == 1:
            return matches[0]
        known = ", ".join(n["name"] for n in networks)
        if not matches:
            raise NetworkNotFound("No network matches '{}'. Known networks: {}.".format(query, known))
        names = ", ".join(n["name"] for n in matches)
        raise NetworkNotFound("'{}' matches several networks: {}. Be more specific.".format(query, names))

    def _network_ids(self, network=None):
        if network is None or str(network).strip() == "":
            return [n["id"] for n in self._data["networks"]]
        return [self.resolve_network(network)["id"]]

    # ---------------------------------------------------------------- queries

    def device_statuses(self, network=None, status=None):
        ids = set(self._network_ids(network))
        devices = [d for d in self._data["devices"] if d["networkId"] in ids]
        if status:
            devices = [d for d in devices if d["status"] == status.lower()]
        return devices

    def uplink_statuses(self, network=None):
        ids = set(self._network_ids(network))
        return [u for u in self._data["uplinkStatuses"] if u["networkId"] in ids]

    def clients(self, network):
        return list(self._data["clients"].get(self.resolve_network(network)["id"], []))

    def events(self, network, event_type=None):
        items = self._data["events"].get(self.resolve_network(network)["id"], [])
        if event_type:
            items = [e for e in items if e["type"] == event_type]
        return sorted(items, key=lambda e: parse_time(e["occurredAt"]), reverse=True)

    def channel_utilization(self, network):
        return list(self._data["channelUtilization"].get(self.resolve_network(network)["id"], []))

    def vlans(self, network):
        network_id = self.resolve_network(network)["id"]
        result = []
        for vlan in self._data["vlans"].get(network_id, []):
            item = dict(vlan)
            # Host addresses in the subnet, before the gateway and any DHCP exclusions are taken out.
            item["subnetHostCapacity"] = ipaddress.ip_network(vlan["subnet"]).num_addresses - 2
            result.append(item)
        return result

    # ---------------------------------------------------------------- health

    def health_summary(self, network=None):
        """Check each network and return findings with the evidence and a suggested next action.

        Findings describe what the data shows (a symptom or a likely cause), not a confirmed root cause.
        """
        return [self._network_health(network_id) for network_id in self._network_ids(network)]

    def _network_health(self, network_id):
        network = self.resolve_network(network_id)
        findings = []
        findings += self._wan_findings(network)
        findings += self._device_findings(network_id)
        findings += self._wireless_findings(network_id)
        findings += self._dhcp_findings(network_id)
        findings.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])

        if any(f["severity"] == "critical" for f in findings):
            status = "down"
        elif findings:
            status = "degraded"
        else:
            status = "healthy"
        return {"network": network["name"], "networkId": network_id, "status": status,
                "snapshotTime": self.snapshot_time().strftime("%Y-%m-%dT%H:%M:%SZ"), "findings": findings}

    def _wan_findings(self, network):
        """Judge internet access for the whole office, not per interface."""
        if "appliance" not in network.get("productTypes", []):
            return []
        appliances = self.uplink_statuses(network["id"])
        if not appliances:
            return [{
                "severity": "high",
                "area": "uplink",
                "detail": "No WAN uplink data for this office, so its internet access cannot be confirmed.",
                "suggestedAction": "Check that the MX appliance is online and reporting to the dashboard.",
            }]

        # In an HA pair, only the active (primary) appliance carries traffic.
        primaries = [a for a in appliances if (a.get("highAvailability") or {}).get("role", "primary") != "spare"]
        uplinks = [u for a in primaries for u in a["uplinks"]]
        active = [u for u in uplinks if u["status"] == "active"]
        circuits = {c["interface"]: c for c in network.get("ispCircuits", [])}

        if not active:
            states = ", ".join("{} {}".format(u["interface"], u["status"]) for u in uplinks)
            return [{
                "severity": "critical",
                "area": "uplink",
                "detail": "No active internet uplink ({}). The office is likely offline.".format(states),
                "suggestedAction": "Raise faults with every ISP listed for the office and check the appliance on site.",
            }]

        findings = []
        for uplink in uplinks:
            if uplink["status"] != "failed":
                continue
            circuit = circuits.get(uplink["interface"], {})
            findings.append({
                "severity": "high",
                "area": "uplink",
                "detail": "Uplink {} is failed; traffic is running on {}.".format(
                    uplink["interface"], ", ".join(u["interface"] for u in active)),
                "suggestedAction": "Raise a fault with {} for circuit {}, with the failure time and gateway {}; "
                                   "watch backup capacity meanwhile.".format(
                                       circuit.get("provider", "the ISP"),
                                       circuit.get("circuitId", "(unknown circuit)"),
                                       uplink.get("gateway") or "(unknown)"),
            })
        return findings

    def _device_findings(self, network_id):
        findings = []
        for device in self.device_statuses(network_id):
            if device["status"] == "offline":
                findings.append({
                    "severity": "high",
                    "area": "device",
                    "detail": "{} ({}, {}) is offline; last reported {}.".format(
                        device["name"], device["model"], device["serial"], device["lastReportedAt"]),
                    "suggestedAction": OFFLINE_ACTIONS.get(device["productType"],
                                                           "Check power and connectivity on site."),
                })
            elif device["status"] == "alerting":
                findings.append({
                    "severity": "medium",
                    "area": "device",
                    "detail": "{} ({}) is alerting.".format(device["name"], device["model"]),
                    "suggestedAction": "Open the device in the dashboard and review its active alerts.",
                })
        return findings

    def _wireless_findings(self, network_id):
        devices = {d["serial"]: d for d in self._data["devices"]}
        findings = []
        for ap in self.channel_utilization(network_id):
            name = devices.get(ap["serial"], {}).get("name", ap["serial"])
            bands = RADIO_BANDS.get(ap.get("model"), {})
            for radio in ("wifi0", "wifi1"):
                samples = ap.get(radio) or []
                if not samples:
                    continue
                latest = max(samples, key=lambda s: parse_time(s["endTime"]) if "endTime" in s else datetime.min)
                total = latest["utilizationTotal"]
                if total < CHANNEL_UTILIZATION_ALERT:
                    continue
                band = " ({})".format(bands[radio]) if radio in bands else ""
                window = " between {} and {}".format(latest["startTime"], latest["endTime"]) \
                    if "startTime" in latest and "endTime" in latest else ""
                findings.append({
                    "severity": "medium",
                    "area": "wireless",
                    "detail": "{} radio {}{} averaged {:.1f}% channel utilisation{} ({:.1f}% non-Wi-Fi "
                              "interference).".format(name, radio, band, total, window,
                                                      latest["utilizationNon80211"]),
                    "suggestedAction": "Spread clients to nearby APs (check that none of them is offline), review "
                                       "channel and band steering, and look for interference sources.",
                })
        return findings

    def _dhcp_findings(self, network_id):
        since = self.snapshot_time() - EVENT_WINDOW
        recent = [e for e in self.events(network_id, "dhcp_no_leases") if parse_time(e["occurredAt"]) >= since]
        by_vlan = {}
        for event in recent:  # newest first
            vlan_id = str((event.get("eventData") or {}).get("vlan", "unknown"))
            by_vlan.setdefault(vlan_id, []).append(event)

        vlans = {str(v["id"]): v for v in self.vlans(network_id)}
        findings = []
        for vlan_id, events in sorted(by_vlan.items()):
            vlan = vlans.get(vlan_id)
            size = "{} (subnet host capacity {})".format(vlan["subnet"], vlan["subnetHostCapacity"]) \
                if vlan else "unknown subnet"
            findings.append({
                "severity": "high",
                "area": "dhcp",
                "detail": "DHCP had no free leases {} times in the last 24 hours on VLAN {} {}; latest at {}.".format(
                    len(events), vlan_id, size, events[0]["occurredAt"]),
                "suggestedAction": "Check lease occupancy and reservations, then enlarge the subnet "
                                   "(for example to a /24) or shorten the lease time on that VLAN.",
            })
        return findings
