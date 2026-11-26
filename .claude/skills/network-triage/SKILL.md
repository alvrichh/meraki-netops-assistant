---
name: network-triage
description: Step-by-step triage for an office network complaint (slow or dropping Wi-Fi, no internet, users can't get an IP). Use when someone reports a problem at a specific office and wants the cause and the next action.
---

# Office network triage

Work through the layers in order and stop as soon as you find the cause. Use the `meraki-demo` tools for every check; quote the device names, serials, numbers and times they return.

1. **Scope.** Ask, or infer from the request, which office and whether it is one user, one floor or everyone. Run `network_health_summary` for that office.
2. **Internet (WAN).** `get_uplink_statuses`. If an uplink is `failed`, the office is on its backup or down. Get the ISP and circuit id from `list_networks`, and write the fault report: circuit, failure time in local time, gateway, current backup link.
3. **Devices.** `get_device_statuses` for the office. An offline access point pushes its clients onto the neighbouring APs. Next action: check power and PoE on the switch port, then the cable.
4. **Wi-Fi capacity.** `get_channel_utilization`. Over 70% total on a band is congested; a high non-Wi-Fi share means interference rather than too many users. Cross-check with `get_network_clients` (how many clients sit on that AP) and `get_network_events` for `disassociation` bursts.
5. **IP addressing.** `get_network_events` with `dhcp_no_leases`, then `get_vlans` to see the subnet size. A /26 has 62 usable addresses; a busy guest VLAN can run out. Next action: larger subnet or shorter lease time.
6. **Report.** Finish with:
   - **Cause:** one sentence.
   - **Evidence:** the tool results that prove it.
   - **Next actions:** numbered, owner in brackets (IT, ISP, Facilities).
   - **User message:** two plain-language lines the service desk can send to affected staff.
