import unittest

from netops.data import DemoOrg, NetworkNotFound


class ResolveNetworkTest(unittest.TestCase):
    def setUp(self):
        self.org = DemoOrg()

    def test_by_partial_name_case_insensitive(self):
        self.assertEqual(self.org.resolve_network("dublin")["id"], "N_1001")

    def test_by_id(self):
        self.assertEqual(self.org.resolve_network("N_1003")["name"], "Barcelona")

    def test_unknown_network_lists_known_ones(self):
        with self.assertRaises(NetworkNotFound) as ctx:
            self.org.resolve_network("tokyo")
        self.assertIn("Dublin HQ", str(ctx.exception))

    def test_exact_name_beats_partial_match(self):
        self.org._data["networks"].append(dict(self.org._data["networks"][1], id="N_9999", name="London Lab"))
        self.assertEqual(self.org.resolve_network("london")["id"], "N_1002")

    def test_ambiguous_name(self):
        with self.assertRaises(NetworkNotFound):
            self.org.resolve_network("o")  # matches London and San Francisco, among others


class QueryTest(unittest.TestCase):
    def setUp(self):
        self.org = DemoOrg()

    def test_offline_devices(self):
        offline = self.org.device_statuses(status="offline")
        self.assertEqual([d["name"] for d in offline], ["DUB-AP-3F-02"])

    def test_events_newest_first_and_filtered(self):
        events = self.org.events("barcelona", "dhcp_no_leases")
        self.assertEqual(len(events), 3)
        self.assertGreater(events[0]["occurredAt"], events[-1]["occurredAt"])

    def test_vlan_subnet_host_capacity(self):
        guest = [v for v in self.org.vlans("barcelona") if v["id"] == "30"][0]
        self.assertEqual(guest["subnetHostCapacity"], 62)


class HealthSummaryTest(unittest.TestCase):
    def setUp(self):
        self.summary = {s["network"]: s for s in DemoOrg().health_summary()}

    def areas(self, network):
        return [f["area"] for f in self.summary[network]["findings"]]

    def test_dublin_offline_ap_and_busy_channel(self):
        self.assertEqual(self.summary["Dublin HQ"]["status"], "degraded")
        self.assertEqual(self.areas("Dublin HQ"), ["device", "wireless"])

    def test_london_on_backup_uplink_names_the_circuit(self):
        findings = self.summary["London"]["findings"]
        uplink = [f for f in findings if f["area"] == "uplink"][0]
        self.assertEqual(uplink["severity"], "high")
        self.assertIn("BT-LON-77310", uplink["suggestedAction"])

    def test_barcelona_dhcp_exhaustion(self):
        self.assertEqual(self.areas("Barcelona"), ["dhcp"])
        self.assertIn("subnet host capacity 62", self.summary["Barcelona"]["findings"][0]["detail"])

    def test_san_francisco_healthy(self):
        self.assertEqual(self.summary["San Francisco"]["status"], "healthy")
        self.assertEqual(self.summary["San Francisco"]["findings"], [])


class WanRuleTest(unittest.TestCase):
    """The WAN rule judges the whole office, so missing or idle uplinks never look healthy."""

    def setUp(self):
        self.org = DemoOrg()

    def uplinks(self, network_id):
        return next(u for u in self.org._data["uplinkStatuses"] if u["networkId"] == network_id)

    def test_all_uplinks_not_connected_is_down(self):
        for uplink in self.uplinks("N_1004")["uplinks"]:
            uplink["status"] = "not connected"
        summary = self.org.health_summary("san francisco")[0]
        self.assertEqual(summary["status"], "down")
        self.assertEqual(summary["findings"][0]["severity"], "critical")

    def test_missing_wan_telemetry_is_not_healthy(self):
        self.org._data["uplinkStatuses"] = [u for u in self.org._data["uplinkStatuses"] if u["networkId"] != "N_1004"]
        summary = self.org.health_summary("san francisco")[0]
        self.assertEqual(summary["status"], "degraded")
        self.assertIn("No WAN uplink data", summary["findings"][0]["detail"])

    def test_failed_spare_appliance_does_not_take_the_office_down(self):
        spare = {"networkId": "N_1004", "serial": "Q2KY-SF01-MX02", "model": "MX85",
                 "lastReportedAt": "2026-11-26T13:58:07Z", "highAvailability": {"enabled": True, "role": "spare"},
                 "uplinks": [{"interface": "wan1", "status": "failed", "gateway": "12.144.60.1"}]}
        self.org._data["uplinkStatuses"].append(spare)
        self.assertEqual(self.org.health_summary("san francisco")[0]["status"], "healthy")


class DhcpRuleTest(unittest.TestCase):
    def setUp(self):
        self.org = DemoOrg()
        self.events = self.org._data["events"]["N_1003"]

    def test_old_events_outside_the_window_are_ignored(self):
        for event in self.events:
            event["occurredAt"] = "2026-11-20T10:00:00Z"
        self.assertEqual(self.org.health_summary("barcelona")[0]["status"], "healthy")

    def test_events_are_grouped_per_vlan(self):
        self.events.append({"occurredAt": "2026-11-26T13:30:00Z", "type": "dhcp_no_leases", "category": "appliance",
                            "description": "DHCP server has no free leases", "eventData": {"vlan": "10"}})
        details = [f["detail"] for f in self.org.health_summary("barcelona")[0]["findings"]]
        self.assertEqual(len(details), 2)
        self.assertIn("1 times in the last 24 hours on VLAN 10", details[0])
        self.assertIn("3 times in the last 24 hours on VLAN 30", details[1])


if __name__ == "__main__":
    unittest.main()
