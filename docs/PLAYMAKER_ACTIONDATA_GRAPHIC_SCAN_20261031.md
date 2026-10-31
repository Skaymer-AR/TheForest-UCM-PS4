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
type kind is `SZARRAY`). These are AOT field signatures only. A separate
`GetEventInfo` scan provides serialized examples of the shared `FsmTexture`
and `FsmRect` wrapper encodings; it does not provide GUI-action payloads, nor
a `GUIContent`, direct `UnityEngine.Rect`, or GUILayout-option encoding.

| AOT action | Metadata fields relevant to drawing | Serialization evidence |
| --- | --- | --- |
| `GUIBox` / `GUILabel` | `image:FsmTexture`, `text/tooltip/style:FsmString`, `content:UnityEngine.GUIContent`, `screenRect:FsmRect`, `left/top/width/height:FsmFloat`, `normalized:FsmBool`, `rect:UnityEngine.Rect` | Shared `FsmTexture`, `FsmRect`, and `FsmString` wrappers have examples in other actions; `GUIContent`, direct Rect, and these actions' complete parameter list are not serialized in available assets. |
| `GUIButton` | `sendEvent:FsmEvent`, `storeButtonState:FsmBool`, then the `GUIBox` drawing fields | `FsmEvent` appears in serialized actions; exact GUIButton field-to-ActionData mapping is not observed. |
| `GUILayoutButton` | `sendEvent:FsmEvent`, `storeButtonState:FsmBool`, `image:FsmTexture`, `text:FsmString`, `tooltip:FsmString`, `style:FsmString`; inherited `GUILayoutAction.layoutOptions` and `options` are arrays | Element types resolve from native metadata; serialized layout-option records are unavailable. |

The exact native type table resolves those two `SZARRAY` elements as
`HutongGames.PlayMaker.LayoutOption[]` and `UnityEngine.GUILayoutOption[]`.
The resolver follows only a bounded chain of `SZARRAY` element type pointers;
this is AOT metadata evidence, not a Unity ActionData serializer. A separate
scan of all 31 metadata types named `HutongGames.PlayMaker.Actions.GUILayout*`
across the same 62 assets found zero raw action-name occurrences and zero
validated serialized instances. Its summary and source hashes are in
[`PLAYMAKER_GUILAYOUT_ACTION_SCAN_20261031.jsonl`](PLAYMAKER_GUILAYOUT_ACTION_SCAN_20261031.jsonl).

The native `ActionData.GetFsmTexture` helper at link VA `0x01101210` reads
`fsmObjectParams` at ActionData object offset `+0x90`; the already analyzed
`GetFsmEventTarget` helper at `0x01102E90` reads `fsmEventTargetParams` at
`+0x70`. `GetParamDataType` (`0x0110FB80`) and `SaveActionField`
(`0x010F40C0`) are also present. These are static runtime access/serialization
paths, not a verified Unity file encoding for a GUI action's texture. Without
a serialized GUI instance or a fully mapped field-specific writer path, they
do not establish a loadable GUI ActionData record. No guessed GUIContent,
direct-Rect, or layout-option encoding was added.

## Serialized shared graphic-parameter witnesses

The optional scan `--action GetEventInfo` found three serialized occurrences,
all in `resources.assets` FsmTemplates. This is distinct from the zero
serialized instances of the four requested drawing actions. The detailed
per-instance JSONL is
[`PLAYMAKER_GRAPHIC_PARAMETER_EXAMPLES_20261031.jsonl`](PLAYMAKER_GRAPHIC_PARAMETER_EXAMPLES_20261031.jsonl).

| Asset object | FsmTemplate / embedded FSM / state | ActionData offset / size | ActionData result |
| --- | --- | ---: | --- |
| `resources.assets`, FsmTemplate path ID `116776` | `mutant_action_encounterFSM` / `action_encounterFSM` / `disabled` | `8752` / `4748` | `GetEventInfo` action 0 of 18; byte-round-trip, some fields opaque |
| `resources.assets`, FsmTemplate path ID `116777` | `mutant_action_sleepingFSM` / `action_sleepingFSM` / `getname` | `36292` / `1012` | sole action; byte-round-trip, some fields opaque |
| `resources.assets`, FsmTemplate path ID `116778` | `mutant_global_brainFSM` / `global_brainFSM` / `setSleeping` | `13968` / not decoded | action 4 of 5; prefix only because nonempty `functionCallParams` is unsupported |

The first two records match `GetEventInfo`'s 15 AOT fields, in order. For
specialized references, `paramDataPos` is the array index and
`paramByteDataSize=0`; the table gives those array indices and record offsets.
It directly demonstrates these wire forms:

| Parameter/type | Type code | Serialized location and encoding | Observed value / reference |
| --- | ---: | --- | --- |
| `sentByGameObject : FsmGameObject` | 19 | `fsmGameObjectParams[0]`, 32-byte record | offsets `9932` / `36392`; variable placeholder, null PPtr |
| `fsmName : FsmString` | 18 | `fsmStringParams[0]`, 32-byte aligned string/flag record | offsets `10564` / `36488`; variable placeholder, empty value |
| `getBoolData : FsmBool` | 17 | `byteData[0:2]`, 2 bytes | retained opaque |
| `getIntData : FsmInt` | 16 | `byteData[2:7]`, little-endian `i32` plus variable byte | value `0`, flag true |
| `getFloatData : FsmFloat` | 15 | `byteData[7:12]`, 5 bytes | retained opaque (variable link is incomplete) |
| `getVector2Data : FsmVector2` | 37 | `byteData[12:21]`, two little-endian `f32` values and one variable byte | zero vector, flag true |
| `getVector3Data : FsmVector3` | 28 | `byteData[21:34]`, three little-endian `f32` values and one variable byte | zero vector, flag true |
| `getStringData : FsmString` | 18 | `fsmStringParams[1]`, 24-byte aligned string/flag record | offsets `10596` / `36520`; variable placeholder, empty value |
| `getGameObjectData : FsmGameObject` | 19 | `fsmGameObjectParams[1]`, 32-byte record | offsets `9964` / `36424`; variable placeholder, null PPtr |
| `getRectData : FsmRect` | 30 | `byteData[34:51]`, four little-endian `f32` values plus one variable byte | object offsets `11086` / `36758`; `[0,0,0,0]`, flag true |
| `getQuaternionData : FsmQuaternion` | 35 | `byteData[51:68]`, four little-endian `f32` values and one variable byte | all zero, flag true |
| `getMaterialData : FsmMaterial` | 32 | `fsmObjectParams[0]`, 56-byte `FsmObject` record; `typeName` plus `PPtr<i32,i64>` | offsets `10876` / `36548`; generic `UnityEngine.Object`, null PPtr |
| `getTextureData : FsmTexture` | 33 | `fsmObjectParams[1]`, same 56-byte `FsmObject` record | offsets `10932` / `36604`; generic `UnityEngine.Object`, null PPtr |
| `getColorData : FsmColor` | 25 | `byteData[68:85]`, four little-endian `f32` values and one variable byte | `(0,0,0,1)`, flag true |
| `getObjectData : FsmObject` | 24 | `fsmObjectParams[2]`, same 56-byte `FsmObject` record | offsets `10988` / `36660`; generic `UnityEngine.Object`, null PPtr |

Both decoded blocks also contain `sentByGameObject` and `fsmName` references
through the specialized `fsmGameObjectParams` and `fsmStringParams` arrays.
Their `FsmBool` and `FsmFloat` slots use variable-link forms that this parser
does not yet understand; salvage mode preserves those byte slices as opaque.
The third `GetEventInfo` occurrence has no decoded parameter table because
the containing ActionData includes a nonempty function-call array.

The third block gives a partial witness for that unsupported array: its
`functionCallParams` count is `1` at component offset `14452`, and the first
record begins at `14456`. The exact metadata type
`HutongGames.PlayMaker.FunctionCall` declares `FunctionName:System.String` and
`parameterType:System.String` first; aligned strings at offsets `14456` and
`14476` decode to `setRepathRate` and `float`. The remaining FunctionCall
payload (typed Fsm parameter fields) and record boundary are not yet decoded,
so the surrounding ActionData remains prefix-only. This partial string match
does not establish the full record serializer.

These observations prove wrapper type codes and serialization shapes in
`GetEventInfo`. They do not prove the exact `GUIBox`/`GUILabel`/`GUIButton`
action records, usable texture references, values for the drawing actions,
or that these placeholder records can be loaded as a new FSM. Applying the
same type codes to the matching GUI fields is an inference from their shared
AOT wrapper type, not a serialized GUI instance.

## Parser and round-trip result

The bounded ActionData parser now covers the title-observed header arrays and
the specialized `FsmString`, `FsmGameObject`, `FsmObject` (including
`FsmTexture`/`FsmMaterial` references), `FsmOwnerDefault`,
and `FsmEventTarget` arrays. It decodes the observed byte-data forms for
`System.Boolean`, `FsmFloat`, `FsmBool` where its variable link is understood,
`FsmEvent`, `FsmColor`, `FsmInt`, `FsmRect`, `FsmVector2`, `FsmVector3`, and
`FsmQuaternion`. Unknown parameter codes fail in strict mode;
the scanner's explicit salvage mode preserves their byte slices as opaque.
Invalid/truncated counts, bad packed booleans, out-of-range array references,
overlapping or out-of-range byteData slices, invalid PPtr shapes, and changed
encoded parameter sizes are rejected. Raw byteData for unsupported values is
preserved during a lossless round-trip; that does not make the value editable.
For each fully decoded scanner candidate, validation now performs
decode → encode → byte comparison → decode again, then compares the normalized
decoded structures while ignoring only absolute source offsets.

On the actual pinned `level2` `cameraFadeFSM` component, all three ActionData
blocks re-encode byte-for-byte: the zero-action `wait` sentinel (108 bytes),
`CameraFadeIn` (300 bytes), and `CameraFadeOut` (300 bytes). Across the 372
ActionData blocks containing the six default target actions, 225 re-encoded
byte-for-byte; 183 were fully semantic, while 42 retained one or more opaque
parameter fields. The other 147 were prefix-only because their body contains
unsupported arrays/types. The separate `GetEventInfo` scan re-encoded two of
its three enclosing ActionData blocks byte-for-byte; those two retained the
opaque `FsmBool`/`FsmFloat` slots described above. No source asset was written.

New synthetic tests also build, decode, edit, and re-encode a `SendEvent`
ActionData containing `FsmEventTarget`, `FsmEvent`, `FsmFloat`, and
`System.Boolean`. They verify same-size semantic edits and rejection of
unknown parameter types in strict mode, invalid array references, negative
PPtr IDs, truncation, and payload-size changes. This is a tested ActionData
subset, not a complete PlayMaker component/Unity asset serializer.

## Independent FSM and integration gate

The independent menu FSM remains **pending**, not ready to serialize. The
existing two-state menu graph is still a normalized structural model; it does
not emit Unity ActionData for its GUI actions. Serialized `SendEvent`,
`GetButtonDown`, and `GetEventInfo` examples now anchor the event, input, and
shared wrapper subsets. The drawing-action records, GUIContent/direct-Rect
fields, and layout arrays remain unproven. No complete graphical FSM was
fabricated from AOT presence alone.

| Architecture | Evidence and work still required | Current status |
| --- | --- | --- |
| New `PlayMakerFSM` in a scene/prefab | The title serializes inline FSM components and `FsmTemplate` references. A new uniquely identified object/action graph would require scene/prefab edits and dependency/reference updates; full GUI ActionData serialization and a reversible package workflow are still missing. | Structurally grounded; commercial asset edit not authorized or attempted. |
| Runtime content loader | No title-specific content loader that accepts an arbitrary FSM, and no safe PlayMaker component/list registration API, has been demonstrated. | No evidence of a usable loader. |
| Title AOT build | A new managed host/action would require the title's Unity/IL2CPP build and registration pipeline plus matching metadata/package integration. The existing AOT actions do not create or attach a new object by themselves. | No source/build pipeline or reproducible AOT rebuild available. |

The least speculative future asset architecture is a separate scene/prefab
object owning a new `PlayMakerFSM`, never either `CutSceneController` FSM.
Before any authorized edit, the next offline gate is to establish the exact
GUI action parameter codes/arrays from a trustworthy GUI ActionData fixture
or verified field-specific serialization path, resolve `GUIContent`, direct
`UnityEngine.Rect`, and GUILayout-option array encoding, and round-trip a
complete synthetic component and its references. `FsmTexture`/`FsmRect` wrapper
wire forms are now witnessed in `GetEventInfo`, but the exact GUI action data
is not. Input must separately use a nonconflicting Rewired action and a verified
runtime focus/input policy; `L1+R1` remains unsuitable because its stored
maps overlap gameplay controls.

**Verdict:** the AOT drawing classes exist, and the title's existing
serialized event/input and shared `FsmTexture`/`FsmRect` ActionData subsets are
better understood. A new graphical FSM is still not demonstrated as fully
serializable or loadable.
There is no proven loader/registration route. The Ultimate Mod Menu is not
ready for PS4 testing; no PRX, asset edit, PKG change, or console action was
performed.
