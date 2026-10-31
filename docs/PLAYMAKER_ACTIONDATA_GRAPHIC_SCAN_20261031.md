# PlayMaker ActionData graphics scan — 2026-10-31

## Scope and method

This read-only sweep used the private SHA-verified Unity 5.6.6f2 copies of
`resources.assets`, `globalgamemanagers.assets`, `level0`–`level29`, and
`sharedassets0.assets`–`sharedassets29.assets` (62 object-serialized files in
total). `resources.assets.resS` was not parsed as an object asset: it is a raw
resource stream and has no independent Unity object table. No commercial
asset, ELF, metadata, SELF, or PKG data is included in this repository.

Run `scripts/scan_playmaker_action_instances.py` with private source files to
reproduce the complete per-instance index. The scanner records the input
hashes and validates all of the following before calling a target string a
serialized action instance:

1. A bounded `ActionData.actionNames` list containing an exact known target
   action name. Other entries may use the title's custom action naming.
2. Per-action custom-name, packed boolean, start-index and hash arrays with
   matching counts and bounded values.
3. A uniquely parsed `FsmState` header that ends exactly at that ActionData
   list.
4. Where supported, the full ActionData body, AOT parameter names/types, and a
   byte-for-byte decode/encode comparison.

This avoids treating an AOT class name or an unrelated raw string as a
serialized instance. The compact JSONL index starts with a scan-summary
record (source hashes, counts and wire-schema notes), followed by one record
per matched action instance. Each instance records asset/object/FSM or
template/state, ActionData offset and action list, action index/hash,
parameter data/references, binary positions, and decode status:

- [`PLAYMAKER_ACTION_INSTANCE_INDEX_20261031.jsonl`](PLAYMAKER_ACTION_INSTANCE_INDEX_20261031.jsonl)

## Serialized instances found

| Action | Raw exact-name occurrences | Validated instances | Assets containing instances |
| --- | ---: | ---: | --- |
| `GUIBox` | 0 | 0 | — |
| `GUILabel` | 0 | 0 | — |
| `GUIButton` | 0 | 0 | — |
| `GUILayoutButton` | 0 | 0 | — |
| `GetButtonDown` | 14 | 14 | `resources.assets` |
| `SendEvent` | 438 | 438 | `level2`, `level7`, `resources.assets`, `sharedassets2.assets` |

The sweep identified 44 serialized `PlayMakerFSM` components and 13
`FsmTemplate` objects among these files. All 452 target names matched a
validated ActionData list; there were no unmapped raw occurrences and no
unresolved or ambiguous state-header matches. The title also contains
title-specific custom action names inside action lists; the scanner permits
those while still requiring an exact target action and state match.

### Representative `GetButtonDown`

In `resources.assets`, `FsmTemplate` path ID `116779`, template name
`player_controlFSM`, state `waitInput`, ActionData offset `156312`, action
name field offset `156408` (text begins at `156412`), action index `2` of `4`:

| Parameter | Type code | Type | Serialized reference/value |
| --- | ---: | --- | --- |
| `buttonName` | 18 | `FsmString` | `fsmStringParams[1]`, serialized record at component offset `156688`, size 28; value `Take` |
| `sendEvent` | 23 | `FsmEvent` | `byteData[26:38]`, value `toResetClimb` |
| `storeResult` | 17 | `FsmBool` | `byteData[38:40]`, retained opaque because this instance's variable-link encoding is not resolved |

The `buttonName` string is a Rewired action name. It does not identify a
physical DS4 control. The offline ControllerMap inventory does not give a
serialized DS4 binding for `MenuToggle`, and no active Player/map/focus state
is known.

### Representative `SendEvent`

In `resources.assets`, `FsmTemplate` path ID `116775`, template name
`male_creepy_action_combatFSM`, state `walkForward`, ActionData offset `1980`,
action name field offset `2036` (text begins at `2040`), action index `1` of `5`:

| Parameter | Type code | Type | Serialized reference/value |
| --- | ---: | --- | --- |
| `eventTarget` | 31 | `FsmEventTarget` | `fsmEventTargetParams[0]`, component offset `2388`, size 140; `target=2`, `fsmName=global_motorFSM`, owner option `0`, nested GameObject and FSM component PPtrs null, both nested booleans false |
| `sendEvent` | 23 | `FsmEvent` | `byteData[3:9]`, value `toWalk` |
| `delay` | 15 | `FsmFloat` | `byteData[9:14]`, value `0.0`, variable flag false |
| `everyFrame` | 1 | `System.Boolean` | `byteData[14:15]`, value false |

For each other occurrence, the JSON index carries the source asset hash, Unity
object path ID/class, GameObject name/ID where available, serialized FSM or
template name, state and transitions, ActionData/action-name offsets, all
action names in that list, per-action index/hash/custom-name flags, and
decoded parameter values or an explicit opaque/prefix-only status. PPtr
shape and nonnegative IDs are checked; this scanner does not resolve every
parameter PPtr across external Unity files.

## AOT presence is separate evidence

Exact title IL2CPP metadata and native code still confirm compiled AOT
implementations for the requested GUI actions. This scan found no serialized
instances of `GUIBox`, `GUILabel`, `GUIButton`, or `GUILayoutButton` in the
available object assets.

Metadata describes `GUIBox` and `GUILabel` fields using `FsmTexture`,
`FsmString`, `GUIContent`, `FsmRect`, `FsmFloat`, `FsmBool`, and `UnityEngine.Rect`.
`GUIButton` adds `FsmEvent` and `FsmBool` fields. `GUILayoutButton` also
inherits layout-option arrays (`GUILayoutAction` fields whose native metadata
type kind is `SZARRAY`). These are AOT field signatures only. There is no
serialized GUI ActionData sample in this title from which to validate its
parameter type codes, `FsmTexture`/`FsmRect`/`GUIContent` encodings, or layout
option arrays.

The native `ActionData.GetFsmTexture` helper at link VA `0x01101210` reads
`fsmObjectParams` at ActionData object offset `+0x90`; the already analyzed
`GetFsmEventTarget` helper at `0x01102E90` reads `fsmEventTargetParams` at
`+0x70`. `GetParamDataType` (`0x0110FB80`) and `SaveActionField`
(`0x010F40C0`) are also present. These are static runtime access/serialization
paths, not a verified Unity file encoding for a GUI action's texture. Without
a serialized GUI instance or a fully mapped field-specific writer path, they
do not close those encodings. No guessed texture, rectangle, or layout-option
encoding was added.

## Parser and round-trip result

The bounded ActionData parser now covers the title-observed header arrays and
the specialized `FsmString`, `FsmGameObject`, `FsmOwnerDefault`, and
`FsmEventTarget` arrays. It decodes the observed byte-data forms for
`System.Boolean`, `FsmFloat`, `FsmBool` where its variable link is understood,
`FsmEvent`, and `FsmColor`. Unknown parameter codes fail in strict mode;
the scanner's explicit salvage mode preserves their byte slices as opaque.
Invalid/truncated counts, bad packed booleans, out-of-range array references,
overlapping or out-of-range byteData slices, invalid PPtr shapes, and changed
encoded parameter sizes are rejected. Raw byteData for unsupported values is
preserved during a lossless round-trip; that does not make the value editable.

On the actual pinned `level2` `cameraFadeFSM` component, all three ActionData
blocks re-encode byte-for-byte: the zero-action `wait` sentinel (108 bytes),
`CameraFadeIn` (300 bytes), and `CameraFadeOut` (300 bytes). Across the 372
ActionData blocks containing target actions, 213 re-encoded byte-for-byte;
164 of those were fully semantic, while 49 retained one or more opaque
parameter fields. The other 159 were prefix-only because their body contains
unsupported arrays/types. No source asset was written.

New synthetic tests also build, decode, edit, and re-encode a `SendEvent`
ActionData containing `FsmEventTarget`, `FsmEvent`, `FsmFloat`, and
`System.Boolean`. They verify same-size semantic edits and rejection of
unknown parameter types in strict mode, invalid array references, negative
PPtr IDs, truncation, and payload-size changes. This is a tested ActionData
subset, not a complete PlayMaker component/Unity asset serializer.

## Independent FSM and integration gate

The independent menu FSM remains **pending**, not ready to serialize. The
existing two-state menu graph is still a normalized structural model; it does
not emit Unity ActionData for its GUI actions. Serialized `SendEvent` and
`GetButtonDown` examples now anchor the event and input action subsets, but the
actual draw-action parameters and layout arrays remain unproven. No complete
graphical FSM was fabricated from AOT presence alone.

| Architecture | Evidence and work still required | Current status |
| --- | --- | --- |
| New `PlayMakerFSM` in a scene/prefab | The title serializes inline FSM components and `FsmTemplate` references. A new uniquely identified object/action graph would require scene/prefab edits and dependency/reference updates; full GUI ActionData serialization and a reversible package workflow are still missing. | Structurally grounded; commercial asset edit not authorized or attempted. |
| Runtime content loader | No title-specific content loader that accepts an arbitrary FSM, and no safe PlayMaker component/list registration API, has been demonstrated. | No evidence of a usable loader. |
| Title AOT build | A new managed host/action would require the title's Unity/IL2CPP build and registration pipeline plus matching metadata/package integration. The existing AOT actions do not create or attach a new object by themselves. | No source/build pipeline or reproducible AOT rebuild available. |

The least speculative future asset architecture is a separate scene/prefab
object owning a new `PlayMakerFSM`, never either `CutSceneController` FSM.
Before any authorized edit, the next offline gate is to obtain an exact
Unity/PlayMaker serialization source or GUI ActionData fixture and establish
`FsmTexture`, `FsmRect`, `GUIContent`, `UnityEngine.Rect`, and GUILayout option
encodings, then round-trip a complete synthetic component and its references.
Input must separately use a nonconflicting Rewired action and a verified
runtime focus/input policy; `L1+R1` remains unsuitable because its stored
maps overlap gameplay controls.

**Verdict:** the AOT drawing classes exist, and the title's existing
serialized event/input ActionData is now substantially understood. A new
graphical FSM is still not demonstrated as fully serializable or loadable.
There is no proven loader/registration route. The Ultimate Mod Menu is not
ready for PS4 testing; no PRX, asset edit, PKG change, or console action was
performed.
