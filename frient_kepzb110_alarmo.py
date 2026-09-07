"""Frient/Develco KEPZB-110 IAS ACE keypad quirk for Alarmo (HA 2026.8.x).

Suppresses the native alarm_control_panel entity and bridges keypad
commands (Arm, Get Panel Status) out to zha_event, so an automation can
drive Alarmo and reply with the matching IAS ACE responses. See README.md
for the full protocol notes and the companion blueprint.
"""
from typing import Any, Final

import zigpy.types as t
from zigpy.zcl import ClusterType, foundation
from zigpy.zcl.clusters.general import BinaryInput
from zigpy.zcl.clusters.security import IasAce, IasWd, IasZone
from zigpy.zcl.foundation import ZCLAttributeDef
from zhaquirks.builder import BinarySensorDeviceClass, QuirkBuilder
from zhaquirks.clusters import CustomCluster


class FrientKepzb110AlarmoIasAce(CustomCluster, IasAce):
    """KEPZB-110 IAS ACE: local diagnostic attributes + Alarmo bridging."""

    class AttributeDefs(IasAce.AttributeDefs):
        last_action: Final = ZCLAttributeDef(
            id=0xFF00, type=t.CharacterString, access="r",
            is_manufacturer_specific=True,
        )
        panel_state: Final = ZCLAttributeDef(
            id=0xFF02, type=t.CharacterString, access="r",
            is_manufacturer_specific=True,
        )
        seconds_remaining: Final = ZCLAttributeDef(
            id=0xFF03, type=t.uint8_t, access="r",
            is_manufacturer_specific=True,
        )
        alarm_status_text: Final = ZCLAttributeDef(
            id=0xFF04, type=t.CharacterString, access="r",
            is_manufacturer_specific=True,
        )
        audible_notification: Final = ZCLAttributeDef(
            id=0xFF05, type=t.uint8_t, access="r",
            is_manufacturer_specific=True,
        )

    _ARM_ACTIONS = {
        int(IasAce.ArmMode.Disarm): "disarm",
        int(IasAce.ArmMode.Arm_Day_Home_Only): "arm_day_zones",
        int(IasAce.ArmMode.Arm_Night_Sleep_Only): "arm_night_zones",
        int(IasAce.ArmMode.Arm_All_Zones): "arm_all_zones",
    }

    _PANEL_STATES = {
        int(IasAce.PanelStatus.Panel_Disarmed): "disarmed",
        int(IasAce.PanelStatus.Armed_Stay): "armed_stay",
        int(IasAce.PanelStatus.Armed_Night): "armed_night",
        int(IasAce.PanelStatus.Armed_Away): "armed_away",
        int(IasAce.PanelStatus.Exit_Delay): "exit_delay",
        int(IasAce.PanelStatus.Entry_Delay): "entry_delay",
        int(IasAce.PanelStatus.Not_Ready_To_Arm): "not_ready",
        int(IasAce.PanelStatus.In_Alarm): "alarm",
        int(IasAce.PanelStatus.Arming_Stay): "arming_stay",
        int(IasAce.PanelStatus.Arming_Night): "arming_night",
        int(IasAce.PanelStatus.Arming_Away): "arming_away",
    }

    _ALARM_STATES = {
        int(IasAce.AlarmStatus.No_Alarm): "no_alarm",
        int(IasAce.AlarmStatus.Burglar): "burglar",
        int(IasAce.AlarmStatus.Fire): "fire",
        int(IasAce.AlarmStatus.Emergency): "emergency",
        int(IasAce.AlarmStatus.Police_Panic): "police_panic",
        int(IasAce.AlarmStatus.Fire_Panic): "fire_panic",
        int(IasAce.AlarmStatus.Emergency_Panic): "emergency_panic",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._update_attribute(self.AttributeDefs.last_action.id, "")
        self._update_attribute(self.AttributeDefs.panel_state.id, "unknown")
        self._update_attribute(self.AttributeDefs.seconds_remaining.id, 0)
        self._update_attribute(self.AttributeDefs.alarm_status_text.id, "no_alarm")
        self._update_attribute(self.AttributeDefs.audible_notification.id, 0)

    def _set_action(self, action: str) -> None:
        self._update_attribute(self.AttributeDefs.last_action.id, action)

    def _set_panel_status(self, panel_status, seconds_remaining, audible_notification, alarm_status) -> None:
        ps = int(panel_status)
        als = int(alarm_status)
        self._update_attribute(
            self.AttributeDefs.panel_state.id,
            self._PANEL_STATES.get(ps, f"unknown_{ps:02x}"),
        )
        self._update_attribute(self.AttributeDefs.seconds_remaining.id, int(seconds_remaining))
        self._update_attribute(
            self.AttributeDefs.alarm_status_text.id,
            self._ALARM_STATES.get(als, f"unknown_{als:02x}"),
        )
        self._update_attribute(
            self.AttributeDefs.audible_notification.id,
            int(audible_notification),
        )

    def handle_cluster_request(self, hdr: foundation.ZCLHeader, args: Any, *, dst_addressing=None) -> None:
        if hdr.command_id == self.ServerCommandDefs.arm.id:
            raw_code = args.arm_disarm_code
            code = str(raw_code) if raw_code else ""
            mode = int(args.arm_mode)
            action = self._ARM_ACTIONS.get(mode, f"unknown_arm_mode_{mode:02x}")
            self._set_action(action)

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

        if hdr.command_id == self.ServerCommandDefs.emergency.id:
            self._set_action("emergency")
        elif hdr.command_id == self.ServerCommandDefs.fire.id:
            self._set_action("fire")
        elif hdr.command_id == self.ServerCommandDefs.panic.id:
            self._set_action("panic")
        elif hdr.command_id in (
            self.ClientCommandDefs.panel_status_changed.id,
            self.ClientCommandDefs.panel_status_response.id,
        ):
            self._set_panel_status(
                args.panel_status,
                args.seconds_remaining,
                args.audible_notification,
                args.alarm_status,
            )

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
    .sensor(
        FrientKepzb110AlarmoIasAce.AttributeDefs.last_action.name,
        FrientKepzb110AlarmoIasAce.cluster_id, endpoint_id=44,
        cluster_type=ClusterType.Client, translation_key="last_action",
        fallback_name="Last keypad action",
    )
    .sensor(
        FrientKepzb110AlarmoIasAce.AttributeDefs.panel_state.name,
        FrientKepzb110AlarmoIasAce.cluster_id, endpoint_id=44,
        cluster_type=ClusterType.Client, translation_key="keypad_state",
        fallback_name="Keypad state",
    )
    .sensor(
        FrientKepzb110AlarmoIasAce.AttributeDefs.seconds_remaining.name,
        FrientKepzb110AlarmoIasAce.cluster_id, endpoint_id=44,
        cluster_type=ClusterType.Client, translation_key="delay_remaining",
        fallback_name="Keypad delay remaining",
    )
    .sensor(
        FrientKepzb110AlarmoIasAce.AttributeDefs.alarm_status_text.name,
        FrientKepzb110AlarmoIasAce.cluster_id, endpoint_id=44,
        cluster_type=ClusterType.Client, translation_key="alarm_status",
        fallback_name="Keypad alarm status",
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
