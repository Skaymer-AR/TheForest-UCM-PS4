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

This graph is **not** valid Unity ActionData output. It leaves some metadata
fields unmodeled (`FsmTexture`, `FsmRect`, Unity `GUIContent`/`Rect`,
`DelayedEvent`) and does not serialize `FsmEventTarget`. Therefore it is a
structural prototype only; it cannot yet be inserted into an asset.

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

The only defensible next architecture proposal is a separate scene/prefab
object with a new `PlayMakerFSM`, never a modification of either
`CutSceneController` FSM. Before any asset integration is considered, the
ActionData encodings for the actual GUI/input actions (especially
`FsmEventTarget`, `FsmTexture`, and `FsmRect`) and the scene/prefab reference
graph must be completed offline. Delivery would then require rebuilding the
affected Unity asset files and a valid game-package installation path; this
is outside the present authorization. A runtime path would need an independently
proven object-creation, PlayMaker-list registration, Unity-thread, focus and
safe-destruction contract.

### Proposed gates if asset integration is authorized later

- **Changes:** add a uniquely identified root/prefab object and separate
  `PlayMakerFSM`; either embed a complete inline Fsm or add a new
  `FsmTemplate`. Update only the required scene/prefab object and dependency
  tables. Do not edit `CutSceneController`, Rewired maps, or native code in
  the first isolated build.
- **Risks:** malformed ActionData or PPtrs can break scene loading; the
  current synthetic graph omits action fields; GUIButton is not proven to
  accept DS4 navigation; a new component's insertion into the live PlayMaker
  GUI list is not verified; modifying assets may require a valid signed
  package workflow.
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

**Verdict:** an independent asset-owned FSM is **structurally promising but
still pending**. We are not ready to test an Ultimate Mod Menu on PS4.

## Verification and limits

Twelve synthetic-only tests cover serialized component parsing, ActionData
boundaries, variable/event/state references, FsmTemplate headers, malformed
tails, typed graph fields and event routes. The exact-source inspector also
verifies all five input hashes, both scene-to-template references, the
cameraFade component/template semantic match, the 13 inline prefab components,
and the extended native lifecycle audit.

These checks establish the static serialized relationships and native
method path described above. They do not prove that a newly serialized
component is loaded from a modified package, that it renders in The Forest,
that Rewired routes a safe DS4 binding to it, or that callbacks can be safely
removed during unload.

No scene, asset, PKG, ELF, metadata, PRX, or console state was modified.
