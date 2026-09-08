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

## Installation

Install the quirk first, restart, confirm the device looks right, then
set up the blueprint automation — in that order, since the automation
needs the device already reporting through the new quirk.

### 1. Quirk

1. Find your ZHA custom quirks folder. Default is
   `<config>/custom_zha_quirks/`; if you've overridden it, check
   Settings → Devices & services → ZHA → Configure → the
   "custom quirks path" option.
2. Copy `frient_kepzb110_alarmo.py` into that folder (create the
   folder first if it doesn't exist yet).
3. Restart Home Assistant. Quirks are only loaded at ZHA startup —
   reloading the ZHA integration alone is not enough.
4. After restart, open the KEPZB-110 device page and confirm: no
   native `alarm_control_panel` entity, and the five entities listed
   below (Last keypad action, Keypad state, Keypad delay remaining,
   Keypad alarm status, Tamper) are present. If they're missing,
   check Settings → System → Logs for a quirk load error before going
   further — the blueprint will have nothing to listen to otherwise.

### 2. Blueprint

1. Settings → Automations & scenes → Blueprints → Import blueprint,
   and either paste the raw URL to
   `frient_kepzb110_alarmo_with_arm_response.yaml` or upload the file
   directly.
2. From the imported blueprint, select **Create automation**.
3. Fill in the inputs (see below for what each one means): Keypad
   device, Alarmo entity, Vacation mode, Custom mode, and Keypad ID
   (leave at the default `1` unless you're setting up more than one
   keypad — see the Keypad ID note below).
4. Save and name the automation.
5. Test end to end: press an arm button on the keypad and confirm it
   both arms Alarmo and shows the correct LED response. If arming
   works in Alarmo but the keypad shows nothing, re-check step 4 of
   the quirk install above — that usually means the quirk isn't
   actually loaded, so nothing is answering the keypad's commands.

## What the quirk does

The native ZHA `alarm_control_panel` entity for this device is
suppressed. Instead, the quirk converts two incoming keypad commands
into `zha_event`, and exposes a handful of diagnostic sensors updated
from whatever IAS ACE responses the device receives:

- **Arm** (button press on the keypad) → `keypad_arm` event
- **Get Panel Status** (fired routinely to refresh the display — on
  proximity wake, after every Arm attempt, and before an Arm attempt
  only if the display was idle) → `keypad_get_panel_status` event

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

Fired routinely to refresh the keypad's display: on proximity wake,
after every `keypad_arm` attempt, and before an attempt only if the
display was already idle. Not solely a proximity-wake event.

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
- The keypad sends a `keypad_get_panel_status` query just before every
  `keypad_arm` attempt only when its display is currently idle/blank —
  if the display is already active (e.g. LED already lit from a recent
  interaction), it skips that leading query and sends `keypad_arm`
  directly. A trailing `keypad_get_panel_status` reliably follows the
  arm attempt (~300ms later), and this is not independent timing: with
  the automation disabled entirely (so no Arm Response is ever sent),
  the trailing query never fires either — confirming the keypad sends
  it *in reaction to receiving* the Arm Response, presumably because
  Arm Response alone can't carry richer fields like
  `seconds_remaining`. This means our reply to that follow-up query is
  what the keypad treats as authoritative for its display, and it will
  always supersede whatever the Arm Response's blink pattern was
  showing. If a failed attempt's "invalid code" indication is answered
  too quickly by a mundane `panel_status_response` (e.g. "still just
  disarmed"), the blink animation gets cut short before finishing.
- The blueprint uses `mode: queued` (not `parallel`) specifically so
  that, per keypad instance, only one trigger's run executes at a
  time, in the order events arrived on the HA bus. Combined with
  `zha.issue_zigbee_cluster_command` apparently blocking until the
  Zigbee-level ack (unconfirmed for certain, but consistent with
  observed behavior), this makes the `keypad_get_panel_status` →
  `alarmo_success`/`alarmo_failed` ordering a structural guarantee
  rather than a timing guess — the get_panel_status run cannot even
  start until the prior Arm Response run has fully sent. No artificial
  delay is used for this any more (an earlier version used a 500ms,
  then 1000ms delay under `parallel` mode as a workaround, confirmed
  by observation: a wrong-code attempt's LED went from 1 blink → 2 →
  3, matching the manual's pattern, as that delay was raised). The
  delay was removed on the theory that `queued` mode alone is
  sufficient. If a wrong-code attempt ever regresses to fewer than 3
  blinks, that theory is what to re-check first — the blueprint
  briefly had temporary `system_log.write` debug logging in each
  reply branch while chasing this; it's since been removed, but adding
  it back per-branch is a quick way to see exactly what each trigger
  computed and sent, if needed again.
  Trade-off worth knowing: `queued` means a slow/stuck Zigbee send for
  one trigger delays *all* subsequent interactions with that keypad
  until it clears, unlike `parallel` where branches were independent.
  For one keypad with human-paced button presses this is a low risk,
  but is a real change in failure behavior versus before.
- The `alarmo_state` → Panel Status Changed branch's delay was removed
  too, but its justification was always weaker than the one above and
  was never actually confirmed: it assumed Alarmo fires its own state
  change before firing `alarmo_command_success`, which was never
  verified against Alarmo's source — the original evidence for a race
  here turned out to be the separate `mode`/`arm_mode` field bug, not
  timing. With no delay as a hedge any more, if that firing-order
  assumption is wrong, Panel Status Changed could beat Arm Response
  for a fresh arm/disarm confirmation. Not observed in testing so far,
  but if arm/disarm confirmation ever looks visually wrong, check this
  assumption first before adding a delay back.
- A brief green "disarmed" LED flash right when an arm button is
  pressed, just before the exit-delay red pattern starts, is expected
  and accepted as correct rather than fixed: the keypad's leading
  `keypad_get_panel_status` query (sent only when its display was
  idle) now — under `queued` mode — is fully answered with the
  genuinely-still-disarmed status before `keypad_arm` even starts
  processing, since nothing has been sent back to the keypad for the
  new arm request yet at that point. The reply is factually correct
  for the instant it was sent; the flash is just visible because
  ordering is now strict. Not present under the old `parallel` mode,
  where the arm command usually won the race to the keypad instead.

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
