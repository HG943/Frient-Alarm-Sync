from zigpy.zcl import ClusterType
from zigpy.zcl.clusters.general import BinaryInput
from zigpy.zcl.clusters.security import IasAce, IasWd, IasZone
from zhaquirks.builder import BinarySensorDeviceClass, QuirkBuilder
from .common import FrientKepzb110IasAce


class FrientKepzb110AlarmoIasAce(FrientKepzb110IasAce):
    """Intercept keypad Arm commands and status queries for Alarmo."""

    def handle_cluster_request(self, hdr, args, *, dst_addressing=None):
        if hdr.command_id == self.ServerCommandDefs.arm.id:
            raw_code = args.arm_disarm_code
            code = str(raw_code) if raw_code else ""
            mode = int(args.arm_mode)
            action = self._ARM_ACTIONS.get(
                mode, f"unknown_arm_mode_{mode:02x}"
            )
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

        return super().handle_cluster_request(
            hdr, args, dst_addressing=dst_addressing
        )


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
