"""Frient/Develco KEPZB-110 IAS ACE keypad quirk for Alarmo (HA 2026.9.x).

Suppresses the native alarm_control_panel entity and bridges keypad
commands (Arm, Get Panel Status) out to zha_event, so an automation can
drive Alarmo and reply with the matching IAS ACE responses. See README.md
for the full protocol notes and the companion blueprint.

This quirk intentionally exposes no diagnostic sensor entities for the
keypad's own state (last action, panel state, delay remaining, alarm
status) — only the tamper binary sensor, which comes from the standard
IasZone cluster and needs no special handling. An earlier version did
expose those as manufacturer-specific attributes on a fabricated
server-role cluster, correct in isolation (verified against a
standalone simulation of this device's exact signature) but never
actually appeared as real entities. Root cause not found — dropped as
not worth chasing further; the blueprint never depended on them.
"""
from typing import Any

from zigpy.zcl import ClusterType, foundation
from zigpy.zcl.clusters.general import BinaryInput
from zigpy.zcl.clusters.security import IasAce, IasWd, IasZone
from zhaquirks.builder import BinarySensorDeviceClass, QuirkBuilder
from zhaquirks.clusters import CustomCluster


class FrientKepzb110AlarmoIasAce(CustomCluster, IasAce):
    """KEPZB-110 IAS ACE: bridges keypad commands to zha_event for Alarmo."""

    _ARM_ACTIONS = {
        int(IasAce.ArmMode.Disarm): "disarm",
        int(IasAce.ArmMode.Arm_Day_Home_Only): "arm_day_zones",
        int(IasAce.ArmMode.Arm_Night_Sleep_Only): "arm_night_zones",
        int(IasAce.ArmMode.Arm_All_Zones): "arm_all_zones",
    }

    def handle_cluster_request(self, hdr: foundation.ZCLHeader, args: Any, *, dst_addressing=None) -> None:
        if hdr.command_id == self.ServerCommandDefs.arm.id:
            raw_code = args.arm_disarm_code
            code = str(raw_code) if raw_code else ""
            mode = int(args.arm_mode)
            action = self._ARM_ACTIONS.get(mode, f"unknown_arm_mode_{mode:02x}")

            # ZCL transaction sequence number; this is not Zone ID.
            transaction = int(hdr.tsn)

            self.listener_event(
                "zha_send_event",
                "keypad_arm",
                {
                    "command": "keypad_arm",
                    "action": action,
                    "arm_mode": mode,
                    "code": code,
                    "transaction": transaction,
                },
            )
            return

        if hdr.command_id == self.ServerCommandDefs.get_panel_status.id:
            # Fired e.g. when the proximity sensor wakes the keypad and
            # it wants to refresh its status LED. With the native
            # alarm_control_panel entity suppressed, nothing answers
            # this unless we bridge it out to an event the way we do
            # for arm, so the automation can reply with a real
            # panel_status_response.
            transaction = int(hdr.tsn)

            self.listener_event(
                "zha_send_event",
                "keypad_get_panel_status",
                {
                    "command": "keypad_get_panel_status",
                    "transaction": transaction,
                },
            )
            return

        return super().handle_cluster_request(hdr, args, dst_addressing=dst_addressing)


(
    QuirkBuilder("frient A/S", "KEPZB-110")
    .replaces(
        FrientKepzb110AlarmoIasAce,
        endpoint_id=44,
        cluster_type=ClusterType.Client,
    )
    .prevent_default_entity_creation(
        endpoint_id=44, cluster_id=BinaryInput.cluster_id
    )
    .prevent_default_entity_creation(
        endpoint_id=44,
        cluster_id=IasZone.cluster_id,
        function=lambda entity: entity.translation_key == "ias_zone",
    )
    .prevent_default_entity_creation(
        endpoint_id=44,
        cluster_id=IasWd.cluster_id,
        function=lambda entity: entity.translation_key in (
            "default_siren_tone", "default_siren_level",
            "default_strobe_level", "default_strobe",
        ),
    )
    .prevent_default_entity_creation(
        endpoint_id=44, cluster_id=IasAce.cluster_id
    )
    .binary_sensor(
        endpoint_id=44, cluster_id=IasZone.cluster_id,
        attribute_name=IasZone.AttributeDefs.zone_status.name,
        device_class=BinarySensorDeviceClass.TAMPER,
        attribute_converter=lambda value: bool(
            value & IasZone.ZoneStatus.Tamper
        ),
        unique_id_suffix="tamper", fallback_name="Tamper",
    )
    .add_to_registry()
)
