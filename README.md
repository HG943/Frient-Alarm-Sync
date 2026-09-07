# Frient / Develco KEPZB-110 custom ZHA quirk

Target: Home Assistant 2026.8.x, used with Alarmo.

The supplied device signature is:

- manufacturer: `frient A/S`
- model: `KEPZB-110`
- endpoint 44
- IAS ACE client cluster `0x0501`

## Files

- `frient_kepzb110_alarmo.py` — the quirk. Single file, no variants to
  choose between.
- `frient_kepzb110_alarmo_with_arm_response.yaml` — companion HA
  automation blueprint. The quirk only bridges device commands into
  events; this blueprint is what actually drives Alarmo and replies to
  the keypad. Install both, or arming will appear to do nothing.

## What the quirk does

The native ZHA `alarm_control_panel` entity for this device is
suppressed. Instead, the quirk converts two incoming keypad commands
into `zha_event`, and exposes a handful of diagnostic sensors updated
from whatever IAS ACE responses the device receives:

- **Arm** (button press on the keypad) → `keypad_arm` event
- **Get Panel Status** (fired e.g. when the proximity sensor wakes the
  keypad, wanting to refresh its display) → `keypad_get_panel_status`
  event

The blueprint listens for both, drives Alarmo accordingly, and replies
over Zigbee with the matching IAS ACE command (`ArmResponse`,
`PanelStatusChanged`, or `PanelStatusResponse`).

## Entities

- Last keypad action
- Keypad state
- Keypad delay remaining
- Keypad alarm status
- Tamper binary sensor

The PIN is deliberately not exposed as an entity or written to any
entity state.

## Entity cleanup

The default IAS Zone entity and the IAS Warning Device siren/strobe
configuration entities are suppressed. The tamper entity is retained.

## Events

### `keypad_arm`

Fired when the keypad sends an Arm/Disarm command.

```yaml
command: keypad_arm
action: disarm | arm_day_zones | arm_night_zones | arm_all_zones
arm_mode: <raw IAS ACE arm mode integer, 0-3>
code: "<PIN as entered, or empty string>"
transaction: <ZCL transaction sequence number>
```

### `keypad_get_panel_status`

Fired when the keypad queries current status without an arm/disarm
attempt (e.g. proximity wake).

```yaml
command: keypad_get_panel_status
transaction: <ZCL transaction sequence number>
```

## Companion blueprint: inputs

- **Keypad device** — the KEPZB-110 device entry.
- **Alarmo entity** — the `alarm_control_panel.*` entity from Alarmo.
- **Vacation mode / Custom mode** — since the keypad only has three
  physical arm buttons (home/night/away), these pick which of the
  three the `armed_vacation` and `armed_custom_bypass` Alarmo states
  are represented as on the keypad's LEDs.
- **Keypad ID** — a small integer unique to this blueprint instance.
  Passed to Alarmo as `context_id` so the resulting success/failure
  events can be matched back to the keypad that issued the request.
  Only matters if you run more than one instance (e.g. more than one
  physical keypad); each instance needs a different value.

## Alarmo integration notes

Details that weren't obvious from Alarmo's own docs and cost real
debugging time — worth checking here first if either side of this
integration needs touching again:

- Alarmo only ever fires **two** events on the HA event bus:
  `alarmo_command_success` and `alarmo_failed_to_arm` (the latter
  carries a `reason` of `open_sensors`, `not_allowed`, or
  `invalid_code`). Event names matching Alarmo's MQTT topic
  naming (e.g. `alarmo_invalid_code_provided`) do **not** exist as HA
  bus events — that naming is MQTT-only.
- The mode field on `alarmo_command_success` is `mode`, **not**
  `arm_mode` as Alarmo's README documents — confirmed against a live
  captured event. Templating against `arm_mode` silently fails and
  falls through to a default, with no error raised.
- Alarmo's `custom` arm mode is literally `"custom"`, not
  `"custom_bypass"` (that string is the Alarmo *state* name, not the
  service/event mode value).
- The `context_id` field Alarmo's `alarmo.arm`/`alarmo.disarm`
  services accept must be an **integer**. Passing HA's own automatic
  context ID (a ULID-like string) fails schema validation.
- Alarmo's `delay` entity attribute (exit/entry delay remaining) is
  real and only set during the `arming`/`pending` states — confirmed
  against Alarmo's own docs, unlike the `arm_mode` field above.

## Known limitations

- The ~30 second solid-red LED confirmation the keypad shows
  immediately after any arm button press appears to be a fixed local
  firmware timeout. Nothing in the technical manual, the ZCL spec, or
  this quirk's manufacturer-specific attributes suggests it's
  controllable over Zigbee — it does not seem to respond to how
  quickly `ArmResponse`/`PanelStatusChanged` are sent back.
- Battery reporting uses ZHA's default Power Configuration handling;
  this quirk applies no correction to it. No KEPZB-110-specific
  reporting bug is currently confirmed — only a general reputation for
  occasional erratic battery reporting across other Develco devices.
