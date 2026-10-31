# PlayMaker FSM serialization and independent-menu feasibility — 2026-10-31

## Scope and provenance

This read-only audit uses the SHA-pinned Unity `level2`,
`globalgamemanagers.assets`, and `sharedassets2.assets` files, plus the exact
IL2CPP v23 ELF and metadata. The commercial source files stay in private
temporary paths. The PR contains only the analyzer, synthetic tests, and this
derived report.

| Input | SHA-256 |
| --- | --- |
| `level2` | `99fce056f65647f62ba52d9957317b4ed876e600f854f12e65a20897d37c396d` |
| `globalgamemanagers.assets` | `2518dad0f38f6357276d1e33b4653a907df82dc8b0eb56450b49cb3eb86af2a8` |
| `sharedassets2.assets` | `806d65aa19fd86cbd20ac8cb3f7e5a11cd6a4bd9c9438f0e243b38580303c105` |
| IL2CPP module | `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969` |
| `global-metadata.dat` | `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3` |

Reproduce with private copies:

```sh
python3 scripts/inspect_playmaker_fsm_assets.py \
  --level2 /private/level2 \
  --globalgamemanagers /private/globalgamemanagers.assets \
  --sharedassets2 /private/sharedassets2.assets \
  --module /private/il2cpp-user-assemblies.elf \
  --metadata /private/global-metadata.dat \
  --output /private/playmaker-fsm-audit.json
```

The parser requires the exact source hashes, bounds all component sizes,
strings, state/event/action counts and data slices, resolves scene PPtrs into
`sharedassets2`, and rejects malformed references. It supports only the
narrow pinned `cameraFadeFSM` ActionData forms documented here. It never
rewrites a Unity asset.

## Scene components and real `FsmTemplate` references

`level2` contains two enabled `PlayMakerFSM` MonoBehaviours on the active
`CutSceneController` GameObject (path ID `40654`). Both component records end
with a serialized `fsmTemplate` PPtr. `fileID=3` resolves through the scene's
external table to `sharedassets2.assets`:

| Component | Path ID | Serialized Fsm name | `fsmTemplate` PPtr | Referenced template |
| --- | ---: | --- | --- | --- |
| `PlayMakerFSM` | `223934` | `FSM` | `(fileID=3, pathID=12112)` at byte `14936` | `cutSceneController`, embedded Fsm `cutFSM`, start `init`, 20 states |
| `PlayMakerFSM` | `223935` | `cameraFadeFSM` | `(fileID=3, pathID=12111)` at byte `1260` | `cameraFadeFSM`, embedded Fsm `cameraFadeFSM`, start `wait`, 3 states |

The target metadata resolves the component fields as
`PlayMakerFSM.fsm : Fsm` at `+0x18` and `PlayMakerFSM.fsmTemplate :
FsmTemplate` at `+0x20`. `FsmTemplate` contains `category : String` and
`fsm : Fsm`. The first PPtr inside serialized `Fsm` data is
`Fsm.usedInTemplate`, not `Fsm.owner`: the component's value is null, while
the `cameraFadeFSM` template's value points back to its own asset. `Fsm.owner`
is a separate runtime field at `+0x10`. This corrects the first-pass report,
which mislabeled that PPtr as the owner.

The real `cameraFadeFSM` component and the embedded Fsm in template path ID
`12111` have the same states, events, transitions, ActionData and variables.
The only semantic difference found is editor layout: the `wait` state
rectangle is `(205,105,100,48)` in the component and `(216,106,100,48)` in
the template. This is direct evidence that the title serializes both a
PlayMakerFSM component and a corresponding FsmTemplate asset. It does not
establish a runtime loader for a newly introduced asset.

The other template link points to an asset named `cutSceneController` whose
embedded Fsm is named `cutFSM`; the component itself is named `FSM`. The names
are not interchangeable, and this audit does not infer a one-to-one copy of
that complex cutscene graph.

`sharedassets2.assets` also contains 13 serialized `PlayMakerFSM` components
on prefab objects. All 13 have a null trailing `fsmTemplate` PPtr, showing
that this asset set also stores inline Fsm graphs without a template link.
That is evidence for an asset-owned component format, not for external
runtime registration.

## Reconstructed scene ActionData

The selected `cameraFadeFSM` component is path ID `223935`, size 1,272 bytes.
Its Fsm's serialized `usedInTemplate` pointer is `(0,0)`; the `owner` field is
not assigned by that asset pointer. Its graph is:

| State | Serialized transitions | ActionData action |
| --- | --- | --- |
| `wait` | `off → camOff`, `on → camOn` | none |
| `camOn` | `off → camOff` | `CameraFadeIn` |
| `camOff` | `on → camOn` | `CameraFadeOut` |

The local event table contains `off` and `on`; both have
`isSystemEvent=false`, `isGlobal=true`. There are no global transitions. The
FsmVariables block contains one float named `time`, value `2.0`; twelve other
typed variable arrays are empty. One leading word in that variable record is
preserved without assigning it an unsupported meaning.

The zero-action `wait` state's ActionData is a 27-word zero sentinel. The
`camOn` ActionData begins at component offset `404`, occupies 300 bytes, and
has one action name, `CameraFadeIn`, with stored hash `0xCF3E5806`. The
parameter slices match the first four fields of the exact AOT type metadata:

| Parameter | Serialized type code | IL2CPP field type | byteData position / size | Value |
| --- | ---: | --- | ---: | --- |
| `color` | 25 | `FsmColor` | `0 / 17` | RGBA `(0,0,0,1)`, variable flag false |
| `time` | 15 | `FsmFloat` | `17 / 9` | value `0`, variable flag true, name `time` |
| `finishEvent` | 23 | `FsmEvent` | `26 / 0` | empty payload |
| `realTime` | 1 | `System.Boolean` | `26 / 1` | false |

`CameraFadeOut` has the same four values and serialized fields, at ActionData
offset `796` and byteData offset `940`. The remaining 40 bytes of the pinned
Fsm tail stay opaque; the final 12 bytes of a PlayMakerFSM component are
decoded as its `fsmTemplate` PPtr.

## Native lifecycle and ownership

The expanded exact-build owner audit verifies IL2CPP field offsets, method
pointers and instruction bytes for these lifecycle relationships:

1. `PlayMakerFSM.Awake` enters `PlayMakerFSM.Init`. `Init` reads its embedded
   Fsm from component field `+0x18` and passes both that Fsm and the component
   to `Fsm.Init`. `Fsm.Init` stores the component in `Fsm.owner` at `+0x10`.
2. `Fsm.Init` assigns itself to each `FsmState`, then enters `Fsm.InitData`.
   `InitData` calls `ActionData.LoadActions` and resolves transition event
   names. This is the AOT deserialization path for an already serialized
   component.
3. `FsmTemplate.OnEnable` stores the template object in
   `Fsm.usedInTemplate` at `+0x18`; this is distinct from the component owner.
   `PlayMakerFSM.SetFsmTemplate` resets and reinitializes the component's Fsm.
4. `PlayMakerFSM.Start` and `OnEnable` delegate to Fsm lifecycle methods;
   `OnDisable` stops the Fsm; `OnDestroy` calls `Fsm.OnDestroy` and the
   existing PlayMaker list-removal path.
5. `PlayMakerGUI.CallOnGUI` resolves the active state and calls virtual
   `FsmStateAction.OnGUI` (slot 33) only for active action objects. Actions
   are materialized and activated through `ActionData.LoadActions` and
   `FsmState.ActivateActions`.

| Native method | Link VA | Verified relationship |
| --- | ---: | --- |
| `PlayMakerFSM.Awake` / `Init` | `0x01139A80` / `0x01139A90` | Component Fsm is passed to `Fsm.Init` with the component as owner |
| `Fsm.Init` / `InitData` | `0x01120E50` / `0x01120F80` | Stores owner, assigns state parents, loads ActionData |
| `FsmTemplate.OnEnable` | `0x010EC780` | Writes `usedInTemplate` at `Fsm+0x18` |
| `PlayMakerFSM.Start` / `OnEnable` | `0x0113AF50` / `0x0113AFD0` | Delegate to Fsm lifecycle |
| `PlayMakerFSM.OnDisable` / `OnDestroy` | `0x0113B130` / `0x0113B200` | Stops the Fsm, then calls Fsm destruction and list removal |

These are static code paths. They show how Unity-owned serialized components
are initialized; they do not prove the runtime calls them in a particular
session, that a native PRX can add an entry to PlayMaker's Fsm lists, or that
removal waits for in-flight OnGUI callbacks. No safe external registration,
focus transfer, or quiescent teardown contract was found. Replacing a
component's action pointer or a global vtable is not an acceptable shortcut.

## Synthetic menu graph

The analyzer builds and validates a normalized two-state graph using the
title's precompiled `GUIBox`, `GUILabel`, `GUIButton`, `GetButtonDown`, and
`SendEvent` AOT types:

- `Closed`: `GetButtonDown(MenuToggle)` emits `Open`; transition `Open → Main`.
- `Main`: GUIBox and GUILabel draw a panel and title. GUIButton and
  `GetButtonDown(MenuToggle)` emit `Close`; transition `Close → Closed`.
  `SendEvent(Self, MenuVisible)` is represented symbolically.

The validator checks state/event references, event-producing action routes,
metadata field names and types for every supplied field, AOT virtual slots,
and the explicit symbolic status of the `SendEvent` target. It rejects
malformed typed fields, unresolved transitions and invalid event routes.

This graph is still **not** a complete serialized Unity FSM. The full-asset
scans provide real `FsmEventTarget`, `GetButtonDown`, and `GetEventInfo`
instances. The two decoded `GetEventInfo` blocks witness shared `FsmTexture`
(type code 33, `fsmObjectParams`) and `FsmRect` (type code 30, 17-byte
`byteData`) formats; their references are null placeholders. These are not
GUI action instances. A separate native writer audit now emits complete
synthetic `GUIBox` and `GUILabel` `ActionData` blocks, validated against the
exact public-instance metadata fields and ActionData type hash. The normalized
menu graph does not yet embed these blocks into a serialized Fsm. `GUIContent`
and the GUI action's cached `UnityEngine.Rect` are internal fields excluded by
the native reflection flags. Direct Rect's 16-byte encoding is code-derived,
but is not used by GUIBox/GUILabel. Serialized GUILayout option arrays and
runtime `DelayedEvent` remain unmodeled. Their AOT array element types resolve
to `HutongGames.PlayMaker.LayoutOption[]` and `UnityEngine.GUILayoutOption[]`,
but no such action is serialized in the scanned assets. The per-instance parameter records are in
[`PLAYMAKER_GRAPHIC_PARAMETER_EXAMPLES_20261031.jsonl`](PLAYMAKER_GRAPHIC_PARAMETER_EXAMPLES_20261031.jsonl).
Therefore the graph is still a structural prototype and cannot yet be
inserted into an asset.

## Rewired and graphics limits

`GetButtonDown.OnUpdate` is an existing AOT action that calls
`Rewired.Player.GetButtonDown`; its `buttonName` is a Rewired action name, not
a physical DS4 button. The six-asset ControllerMap audit found no serialized
DS4 `ActionElementMap` for `MenuToggle`, and the live Player, active manager,
map enablement and focus are unverified. Serialized VR/XInput defaults also
show overlap for L1 and R1, so no `L1+R1` chord is proposed.

The AOT GUI actions prove that Unity IMGUI calls exist inside PlayMaker
actions. `GUIButton` does not prove controller focus/navigation or input
consumption. No DS4 navigation provider or gameplay-input suppression policy
is established.

## Inclusion boundary and decision

The demonstrated inclusion path is static Unity serialization: a scene or
prefab references a `PlayMakerFSM` component, with its Fsm inline and an
optional `FsmTemplate` PPtr. A separate new FSM could reuse existing AOT
actions without adding a new IL2CPP action class, but it would still need to
be serialized into a scene/prefab or supplied through a proven runtime asset
loader. No title-specific loader or external component-registration API for
an arbitrary graph was demonstrated. No scene/PKG editing, IL2CPP rebuild,
PRX, or PS4 action was performed.

| Route | What is evidenced | Missing contract | Assessment |
| --- | --- | --- | --- |
| A. New serialized scene/prefab object | Unity scenes/prefabs already own inline `PlayMakerFSM` components and optional `FsmTemplate` links; GUIBox/GUILabel ActionData now round-trips against the title-native field schema. | Full Fsm/component and object-table serializer; dependency/PPtr generation; Unity import/reload validation; an authorized separate-object asset change. | Continue this route as the lowest-unknown architecture; no commercial asset is ready. |
| B. Runtime component registration | Existing PlayMaker lifecycle has `Awake`/`Init`, active GUI dispatch, and destruction paths. | Supported Unity-thread GameObject/component creation, PlayMaker-list registration and ownership, focus handling, and quiescent callback teardown. No arbitrary-FSM loader/API was found. | Defer; no safe runtime route demonstrated. |

The least speculative future asset proposal is a separate scene/prefab object
with a new `PlayMakerFSM`, never a modification of either `CutSceneController`
FSM. Follow-up results, full-scan counts, per-instance data, ActionData parser
coverage and remaining full-Fsm/component gaps are in
[`PLAYMAKER_ACTIONDATA_GRAPHIC_SCAN_20261031.md`](PLAYMAKER_ACTIONDATA_GRAPHIC_SCAN_20261031.md).
The field-specific serializer and metadata now justify a complete
format-level `ActionData` block for `GUIBox`/`GUILabel`, with synthetic
byte-identical round-trip. This is not an original GUI action witness or a
Unity load test. The containing `Fsm` and component writer, 40-byte opaque Fsm
tail, scene/prefab object and dependency references, and Unity import/reload
validation still need offline work. GUILayout option arrays are not needed
for the selected GUI actions and remain unsupported.
Delivery would then require rebuilding the affected Unity asset files and a
valid game-package installation path; this is outside the present
authorization. A runtime path would need an independently proven
object-creation, PlayMaker-list registration, Unity-thread, focus and
safe-destruction contract.

### Proposed gates if asset integration is authorized later

- **Changes:** add a uniquely identified root/prefab object and separate
  `PlayMakerFSM`; either embed a complete inline Fsm or add a new
  `FsmTemplate`. Update only the required scene/prefab object and dependency
  tables. Do not edit `CutSceneController`, Rewired maps, or native code in
  the first isolated build.
- **Risks:** malformed ActionData or PPtrs can break scene loading; the
  normalized menu graph still does not embed the new GUIBox/GUILabel
  ActionData blocks into a full Fsm; GUIButton is not proven to accept DS4
  navigation; a new component's insertion into the live PlayMaker GUI list
  is not verified; modifying assets may require a valid signed package
  workflow.
- **Acceptance:** implement a serializer for every field used by the selected
  GUI/input actions, including the special `FsmEventTarget` payload; round-trip
  its generated component and template through a strict parser; prove unique
  object IDs and dependency references; demonstrate that the two existing
  `CutSceneController` component and template hashes/bytes are unchanged; and
  document a nonconflicting input action before considering any runtime test.
- **Recovery:** keep the user's original assets and package read-only; create
  a separate private output plus a manifest of changed object IDs and hashes.
  Any authorized deployment must have a tested restore path to the original
  package and confirm the original hashes after rollback. No installation or
  PS4 test is authorized by this proposal.

**Verdict:** the drawing `ActionData` layer is now **native-schema complete for
GUIBox/GUILabel**, while an independent asset-owned FSM remains **pending**
because the containing Unity object serialization and inclusion path are not
complete. Continue only on the isolated scene/prefab architecture; runtime
registration still has no safe, demonstrated path. We are not ready to test
an Ultimate Mod Menu on PS4.

## Verification and limits

Thirty-six targeted PlayMaker tests cover serialized component parsing,
ActionData boundaries and same-size semantic round-trips, variable/event/state
references, FsmTemplate headers, malformed tails, typed graph fields, event
routes, `FsmTexture`/`FsmRect` payloads, native field-attribute filtering,
synthetic GUIBox/GUILabel ActionData, and decode/encode/re-decode equivalence.
The exact-source inspector also
verifies all five input hashes, both scene-to-template references, the
cameraFade component/template semantic match, the 13 inline prefab components,
and the extended native lifecycle audit.

`ASAN_OPTIONS=detect_leaks=0 SANITIZE=1 sh scripts/test.sh` passed 194 Python
tests and the native C, ASan, and UBSan suites. `scripts/assert-safe-build.py`
passed. The exact-source inspector matched all five hashes and validated both
synthetic GUI ActionData blocks. The local Unity C# fixture could not run
because `mcs` and `mono` are absent; GitHub Actions supplies the Mono-backed
check.

These checks establish the static serialized relationships and native
method path described above. They do not prove that a newly serialized
component is loaded from a modified package, that it renders in The Forest,
that Rewired routes a safe DS4 binding to it, or that callbacks can be safely
removed during unload.

No scene, asset, PKG, ELF, metadata, PRX, or console state was modified.

## 2026-10-31 — Bounded PlayMakerFSM container codec and tail gate

This section updates the earlier status above. The previously missing
container encoder now covers the observed `Fsm` graph subset, component
wrapper, and `FsmTemplate` wrapper. It deliberately does **not** claim a
complete semantic map of every field in Unity's serialized `Fsm` object.

### The 40-byte tail: `resources.assets` adds six distinct values, semantics still unknown

The new `scripts/audit_playmaker_fsm_tails.py` rechecks the pinned SHA-256 of
each input before scanning. The earlier scan covered the 60 level/sharedassets
files and found only 19 PlayMaker objects. This pass also recovered
`resources.assets` from the previously supplied private file, verified its
registered size (380,657,240 bytes) and expected SHA-256
`9b28d330969eaf9f6ae5dc0fa5e83b022174720744c272f80ee887a46e063536`, then
scanned it read-only:

| Asset | `PlayMakerFSM` | `FsmTemplate` |
| --- | ---: | ---: |
| `level2` | 2 | 0 |
| `level7` | 2 | 0 |
| `sharedassets2.assets` | 13 | 2 |
| `resources.assets` | 27 | 11 |
| **Total** | **44** | **13** |

The complete audit used 62 hash-pinned inputs: those 61 serialized Unity
assets plus `globalgamemanagers.assets`, which supplies the MonoScript map.

For a `PlayMakerFSM`, the 40 bytes are the interval immediately before its
trailing 12-byte `fsmTemplate` PPtr. For an embedded `Fsm` in `FsmTemplate`,
they are the final 40 bytes. There are 57 tails. Fifty-one retain the prior
digest `fd31410c401d1624d966bd279d6e3aa6f8ba288610811d85d428772aa9ef7345`;
the remaining six are six distinct values, each on a `PlayMakerFSM` component
of the `player_BASE` GameObject in `resources.assets`:

| FSM | States | Tail SHA-256 prefix |
| --- | ---: | --- |
| `controlFSM` | 75 | `0aa9c4f5` |
| `damageFSM` | 6 | `143eec48` |
| `tempBlockManagerFSM` | 3 | `3876e307` |
| `noiseDetectFSM` | 7 | `480581b1` |
| `rotatePlayerFSM` | 12 | `d3e22db8` |
| `staminaFSM` | 8 | `f6246371` |

Across all 57 samples, byte offsets 4, 12, 16, 24, and 28–39 vary (offsets are
zero-based); the other offsets are constant. The complete derived report,
including each sample's type, asset, path ID, decoded identity where supported,
digest group, and per-offset distinct-value counts, is
`docs/PLAYMAKER_FSM_TAIL_AUDIT_20261031.json`. The tool never writes tail
bytes or commercial objects to the report. It resolves 10 of the 13 template
headers; three `resources.assets` template wrappers remain outside the bounded
header parser, although their object type and final 40-byte interval are still
identified and hashed.

IL2CPP v23 metadata yields 18 public-instance or `[SerializeField]` Fsm field
candidates, in metadata declaration order:

| Candidate field | Metadata evidence |
| --- | --- |
| `usedInTemplate`, `name`, `startState`, `states`, `events`, `globalTransitions`, `variables`, `description`, `docUrl`, `showStateLabel`, `maxLoopCount`, `watermark` | private fields marked `UnityEngine.SerializeField` |
| `version`, `ExposedEvents`, `RestartOnEnable`, `EnableDebugFlow`, `StepFrame` | public instance fields |
| `activeStateName` | private field marked `UnityEngine.SerializeField` |

The bounded type resolver cannot resolve `ExposedEvents`' generic-instantiated
type (`IL2CPP_TYPE_GENERICINST`, kind `0x15`). Metadata declaration order is
not evidence of Unity's binary field order. The six distinct samples correlate
with six FSMs on `player_BASE`, but their different state counts and object
identity do not identify any tail field. No candidate has been assigned to an
individual byte. The title's AOT metadata and existing native analysis expose
no verified `Fsm.Save`/`Fsm.Serialize` writer that maps these offsets to the
candidate fields. The Unity assets have type trees disabled. The exact missing
evidence is a compatible Unity 5.6.6f2
deserialization/type-tree view of these serialized objects, or controlled
serializer outputs where candidate fields are varied one at a time. The
current environment has no Unity Editor, Mono, .NET runtime, Wine, UABEA, or
AssetStudio CLI installed, and this pass did not verify a third-party format-17
read/write tool. No tool was used to claim a successful Unity import. Until
field mapping and a compatible writer are demonstrated, a new tail must not be
fabricated; existing source tails remain opaque preservation data.

### Round-trip and synthetic object-graph results

`encode_fsm_component`, `parse_fsm_template`, and `encode_fsm_template` now
reuse the existing bounded ActionData codec. They support the observed
camera-fade data subset: one optional `FsmFloat`, empty remaining variable
arrays, empty global transitions, bounded states/events/transitions and
verified ActionData shapes. The 40-byte tail and the 32-byte MonoBehaviour
header are carried as explicit opaque bytes. The encoder reparses its output
to reject duplicate state/event names, unresolved transitions or variable
links, invalid counts, malformed pointers, and unsupported tails.

On the private exact-hash source copies, both the real `cameraFadeFSM`
component and its real `FsmTemplate` encode back to exactly their original
bytes, then parse again with equivalent graphs. This verifies the codec for
those two observed objects; it is not a Unity Editor import/reload test and
does not validate a newly authored tail.

`build_synthetic_graphic_playmaker_component` creates a 1,324-byte synthetic
component containing one `DrawMenu` state with both existing AOT `GUIBox` and
`GUILabel` ActionData records. The merged action table contains 20 parameters
and rebased references to the shared byteData and specialized arrays. The
strict parser accepts it and the encoder returns byte-identical output when
given the same explicit opaque tail. A synthetic Unity object-graph validator
also checks unique PathIDs, GameObject/Transform/component membership, the
MonoScript external PPtr, dependency membership, and null or external
`FsmTemplate` references.

These bytes and graph are test fixtures only. The validator does not serialize
Unity's complete `.assets` header, type records, object table, external-file
table, dependency metadata, or asset bundle. A strict parser round-trip does
not show that Unity or PlayMaker accepts or activates the component. The
synthetic FSM draws only; it does not define DS4 navigation or gameplay input
isolation.

### Architecture status and minimum next proof

Route A, a separate object owned by a scene or prefab, remains the only
promising route that reuses PlayMaker's AOT GUI actions without an arbitrary
runtime registration API. It remains pending, because neither the 40-byte
tail semantics nor the complete Unity object-table writer/import validation
is established. Route B, runtime creation/registration, still lacks a
demonstrated Unity-thread entry point, PlayMaker list ownership, focus, and
quiescent destruction contract; no new evidence changes that assessment.

An authorized future asset integration would add an independent root
`GameObject`, `Transform`, and `PlayMakerFSM` to the selected title/gameplay
scene (`levelN` not yet selected from a verified scene-load map), or add a
separate prefab in a `sharedassetsN.assets` file and reference it from the
chosen scene. The necessary commercial outputs would therefore be the chosen
scene file, or the prefab asset plus its scene references/dependency tables.
`level2` contains the existing CutSceneController, so its FSM components must
remain byte-identical; the current work does not select it as the integration
scene. No commercial file was modified.

The minimum next offline experiment is a separate, noncommercial Unity
5.6.6f2 project with the exact PlayMaker package version, creating one
`PlayMakerFSM` with controlled values for the unresolved candidates and
exporting a type-tree or equivalent serialized object view. Then a compatible
asset tool must deserialize and reserialize the synthetic GameObject graph,
confirm all PPtrs/dependencies, and round-trip it. The required Unity Editor,
matching PlayMaker package, and compatible asset writer are not present in
this environment. Until that evidence exists, do not build an installable
asset, package, or PRX.

The tail audit result is in
[`PLAYMAKER_FSM_TAIL_AUDIT_20261031.json`](PLAYMAKER_FSM_TAIL_AUDIT_20261031.json).

Local verification for this update: 46 targeted PlayMaker parser/codec tests
passed; the complete offline suite passed 204 Python tests plus native C,
ASan, and UBSan checks; `scripts/assert-safe-build.py`,
`node tests/js/test_ps4_browser_demo.js`, Python compilation, the exact-hash
cameraFade component/template inspector, and the 60-asset tail audit passed.
The local Unity C#4 fixture was skipped because Unity/Mono tools are absent.
These results validate static byte preservation and synthetic graph rules,
not Unity import, runtime loading, graphics, DS4 input, or PS4 behavior.

## 2026-10-31 — PlayMaker version evidence and external validation gate

### Version layers

The exact-hash IL2CPP v23 metadata identifies assembly image index 19 as
`PlayMaker.dll`; its `AssemblyDefinition` version tuple is **1.6.0.0**. The
same record advertises `AssemblyProductAttribute`,
`AssemblyInformationalVersionAttribute`, and `AssemblyFileVersionAttribute`.
The exact AOT user-assemblies ELF also contains the PlayMaker-associated
version strings `1.7.7.f6` and `1.7.7.6`. These are evidence of the compiled DLL
or build metadata, but this inspection did not map either string to a specific
attribute argument or Unity package release.

That distinction matters: Hutong Games support documented that PlayMaker
**1.7.8** could still report DLL version **1.7.7f6**, because the DLL had not
been rebuilt for that product release
([official support thread](https://hutonggames.com/playmakerforum/index.php?topic=9710.45)).
Therefore the target's assembly version is proven as 1.6.0.0, and the DLL build
marker is present, but the exact product release is **not** identified. The
serialized-schema compatibility version is also **not** identified: none of
these version labels proves the wire layout of this title's PlayMaker data.

### External tool availability

| Tool | Published capability | Result in this environment |
| --- | --- | --- |
| Unity Editor 5.6.6f2 | Unity's [official archive](https://unity.com/es/releases/editor/whats-new/5.6.6f2) lists manual Editor installers for Windows and macOS. | Host is Ubuntu 24.04 x86_64. No native Linux Editor is offered on that page; Wine is absent. It cannot be run here. |
| AssetRipper | The [upstream README](https://github.com/AssetRipper/AssetRipper) advertises Unity 3.5.0–6000.4.X analysis and conversion/export into a Unity project. | Not installed. Exporting a project is not evidence of writing the original serialized file and reimporting it byte- or structurally correctly. |
| AssetsTools.NET / UABEA | [AssetsTools.NET](https://github.com/nesrak1/AssetsTools.NET) advertises read/write support for Unity assets and bundles; [UABEA releases](https://github.com/nesrak1/UABEA/releases) include Linux builds and require .NET Runtime 6 plus glibc 2.29 or newer. | Host glibc is 2.39, but .NET 6 is absent. The environment status tool and network-policy snapshot are unavailable, so no external runtime/editor binary was installed. No UABEA/AssetsTools.NET format-17 read/write fixture was run. |

The existing Python reader in this repository recognizes the title's Unity
5.6.6f2 / serialized-file format 17 header and a bounded set of object types.
It is not an independent serializer and cannot import a complete synthetic
GameObject/Transform/PlayMakerFSM graph into Unity. AssetRipper and
AssetsTools.NET remain candidates for separate evaluation; their published
feature descriptions are not validation of this exact file version, type-tree
state, or PlayMaker schema.

### Integration decision

No new importable PlayMakerFSM was produced. The existing 1,324-byte graphic
component is still a parser fixture inside the repository's narrow codec; it
does not include a complete Unity format-17 asset file and has not been loaded
by Unity or PlayMaker. Route A, adding a distinct scene/prefab object, remains
plausible but unvalidated. Runtime registration (route B) has no new evidence
and remains out of scope.

The next required experiment is a noncommercial Unity 5.6.6f2 project on a
supported Windows or macOS host, using the exact PlayMaker package available
to the title owner. It must create one graphic-only FSM, save it, and expose
the serialized object data. A separate format-17 reader/writer must then
round-trip a synthetic GameObject/Transform/MonoBehaviour graph before it is
considered as an integration tool. Until those dependencies are available,
the 40-byte tail remains opaque and no installable asset, PKG, or PRX should
be produced.
