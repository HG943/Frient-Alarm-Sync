# Frient / Develco KEPZB-110 custom ZHA quirk

Target: Home Assistant 2026.9.x, used with Alarmo.

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
4. After restart, confirm entities using Developer Tools → Template
   rather than the device page's summary view, which groups entities
   into sections that can make some look absent when they're actually
   just disabled:
   ```
   {{ device_entities('<this device's device_id>') }}
   ```
   You should see a Tamper entity, alongside whatever standard ones
   (Battery, Identify, Firmware, LQI, RSSI) are always present
   regardless of any quirk. If Tamper is missing, check Settings →
   System → Logs for a quirk load error before going further — the
   blueprint will have nothing to listen to otherwise.

### 2. Blueprint

1. Settings → Automations & scenes → Blueprints → Import blueprint,
   and either paste the raw URL to
   `frient_kepzb110_alarmo_with_arm_response.yaml` or upload the file
   directly.
2. From the imported blueprint, select **Create automation**.
3. Fill in the inputs (see below for what each one means): Keypad
   device, Alarmo entity, and Keypad ID (leave at the default `1`
   unless you're setting up more than one keypad — see the Keypad ID
   note below).
4. Save and name the automation.
5. Test end to end: press an arm button on the keypad and confirm it
   both arms Alarmo and shows the correct LED response. If arming
   works in Alarmo but the keypad shows nothing, re-check step 4 of
   the quirk install above — that usually means the quirk isn't
   actually loaded, so nothing is answering the keypad's commands.

## What the quirk does

The native ZHA `alarm_control_panel` entity for this device is
suppressed. Instead, the quirk converts two incoming keypad commands
into `zha_event`:

- **Arm** (button press on the keypad) → `keypad_arm` event
- **Get Panel Status** (fired routinely to refresh the display — on
  proximity wake, after every Arm attempt, and before an Arm attempt
  only if the display was idle) → `keypad_get_panel_status` event

The blueprint listens for both, drives Alarmo accordingly, and replies
over Zigbee with the matching IAS ACE command (`ArmResponse`,
`PanelStatusChanged`, or `PanelStatusResponse`). Neither the blueprint
nor anything else depends on any entity beyond Tamper — see "Known
limitations" for why there isn't more.

## Entities

- Tamper binary sensor

No keypad-state diagnostic entities are exposed (see "Known
limitations"). The PIN is never exposed as an entity or written to any
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

### `keypad_emergency`

Fired when the keypad's Emergency (SOS) button is pressed — the only
SOS-style button this keypad has; fire and panic don't exist on this
hardware (see `keypad_unhandled_command` below for how that's covered
if that assumption is ever wrong). No IAS ACE response is defined for
this command (unlike `arm`/`get_panel_status`), so nothing needs to be
sent back to the keypad — it's fire-and-forget from the keypad's own
perspective. Wired into the blueprint's Emergency action input.

```yaml
command: keypad_emergency
transaction: <ZCL transaction sequence number>
```

### `keypad_unhandled_command`

Catch-all for any incoming IAS ACE command not covered above,
including fire/panic (this keypad has no buttons for either) as well
as the zone-management commands a fuller ACE client with a zone list/
display would use — `bypass`, `get_zone_id_map`, `get_zone_info`,
`get_bypassed_zone_list`, `get_zone_status`. This keypad has no screen
and the manufacturer's manual never mentions a bypass button, so all
of these are believed unreachable from the hardware — unverified,
which is exactly why this catch-all exists rather than leaving them
silently unhandled. If this event ever fires, one of those beliefs was
wrong; `zcl_command` names which command actually arrived.

```yaml
command: keypad_unhandled_command
zcl_command: <name of the received command, or unknown_0x.. if unrecognized>
transaction: <ZCL transaction sequence number>
```

## Companion blueprint: inputs

- **Keypad device** — the KEPZB-110 device entry.
- **Alarmo entity** — the `alarm_control_panel.*` entity from Alarmo.
- **Keypad ID** — a small integer unique to this blueprint instance.
  Passed to Alarmo as `context_id` so the resulting success/failure
  events can be matched back to the keypad that issued the request.
  Only matters if you run more than one instance (e.g. more than one
  physical keypad); each instance needs a different value.
- **Special code 1 / Special code 2, each with a forwarding toggle and
  an action** — optional. If the code entered on the keypad matches
  one of these exactly, the paired action always runs (e.g. a code
  that opens the garage door). Whether Alarmo also gets the code
  depends on the toggle:
  - **Off (default)**: Alarmo is never called at all — arming/
    disarming is skipped for that attempt, action only. A direct Arm
    Response reflecting Alarmo's actual, unchanged current status is
    sent back, so the keypad doesn't hang waiting for a reply to the
    Arm command it sent.
  - **On**: the code is also forwarded to Alarmo as normal, so a
    single code both arms/disarms *and* triggers the action — e.g. a
    duress-style code that disarms normally but silently alerts you.
    Alarmo's own reply drives the keypad's response in this case, same
    as any ordinary code.

  Leave a code blank to disable that slot; an empty code can never
  match, even if the real keypad also sends an empty code (e.g. when
  no code is required by Alarmo). If you'd rather duress work from
  *any* way of arming/disarming — not just this one keypad — Alarmo
  supports that natively via a dedicated user with its own code plus
  its own Actions; that's a broader-scoped alternative to using the
  toggle here, not a replacement for it.
- **Emergency action** — optional. Runs whenever the keypad's
  Emergency (SOS) button is pressed (the `keypad_emergency` event) —
  the only SOS-style button this keypad has. Fire-and-forget, same as
  the quirk's own handling of it — no IAS ACE response exists for this
  command, so nothing is sent back to the keypad. Leave empty to do
  nothing.

Alarmo's `armed_vacation` and `armed_custom_bypass`/`armed_custom`
states unconditionally map to "away" (arm_all_zones) everywhere in the
blueprint — there's no input for this, on purpose. An earlier version
had a per-mode selector for each, but the keypad only has a single red
LED for "armed", and the manufacturer's manual documents identical LED
behavior for all three arm modes — so which of the three values gets
sent has no visible or audible effect on this hardware. If a keypad
with per-mode indication is ever used with this blueprint, that's
worth reintroducing.

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

## Blueprint-authoring pitfalls hit along the way

Specific to writing blueprints with optional user-supplied actions
(like the Special code actions above) — not Alarmo-specific, but cost
real debugging time and will bite again if a new optional action input
is ever added:

- **An `!input` resolving to an action list cannot sit as one item in
  a `sequence:` list alongside other predefined actions.** Writing
  `- !input special_code_1_action` followed by more steps in the same
  sequence causes Home Assistant to mishandle it (a known, documented
  limitation — "Message malformed: Unable to determine action" in some
  versions, silently not running in others). It only works cleanly
  when the entire `sequence:` *is* the input with nothing else in it.
  To combine a user-supplied action with other steps, wrap it: `-
  sequence: !input special_code_1_action` as its own step — the native
  `sequence:` grouping action exists specifically for this.
- **A plain `text` selector doesn't guarantee its value stays a
  string.** If the user's input is all digits, it can end up stored as
  a YAML-native integer rather than a string, and `"1234" == 1234` is
  `False` in Jinja with no implicit coercion — so a code comparison
  can silently never match. Fix: coerce both sides explicitly with `|
  string` in the comparison (`keypad_code | string == special_code_1 |
  string`), regardless of which side actually ends up mistyped.

## Known limitations

- **No keypad-state diagnostic entities** (last action, panel state,
  delay remaining, alarm status) — an earlier version exposed these as
  manufacturer-specific attributes on a second, fabricated server-role
  cluster instance (needed because entity metadata can only attach to
  server-role clusters, but real ACE traffic only ever arrives on the
  client-role one). That fix was verified correct in isolation — a
  standalone simulation of this exact device signature, run through
  the real entity-discovery code, produced all 5 entities cleanly. But
  on the real device, only 1 of the 5 attributes ever showed up in
  ZHA's own diagnostics (`last_action`, and only after it had actually
  been set by a real keypad press — not even at its `__init__`
  default), and no entities beyond Tamper were ever created. Checked
  and ruled out: stale/duplicate quirk files, `zha`/`zha-quirks`
  version mismatch (both confirmed identical to the test environment
  at 2.2.2), and a missing/misconfigured cluster on the resolved
  device (confirmed present and correctly typed via device diagnostics
  and a from-scratch simulation). Not ruled out: an unpinned `zigpy`
  version mismatch, or something specific to the real HAOS container
  environment that a standalone simulation can't reproduce. Root cause
  not found; not worth chasing further since nothing actually depends
  on these entities. If revisiting: the diagnostic download from the
  device's own page (not the ZHA integration's page) is the most
  detailed source of truth — richer than logs or the device page UI.
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
