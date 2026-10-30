# Rewired: reused offline evidence and exact remaining gates (2026-10-30)

**Title:** The Forest PS4, CUSA12398 v1.15. **Authority:** older private
Unity asset inspections already documented in
`docs/REWIRED_SCENE_GRAPH_20261030.md` and
`docs/PLAYMAKER_VIRTUAL_DISPATCH_20261030.md`. This page **does not**
claim new extraction or live console proof. No installation/hook is authorized.

## Evidence already acquired — do not redo

| Source | Pinned SHA-256 | Prior extraction evidence |
| --- | --- | --- |
| `globalgamemanagers.assets` | `2518dad0f38f6357276d1e33b4653a907df82dc8b0eb56450b49cb3eb86af2a8` | 3,801 MonoScripts resolved |
| `sharedassets0.assets` | `f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321` | Two Rewired InputManager prefabs; generic SonyDualShock4 hardware profile |
| `sharedassets1.assets` | `d227ee3ac409b21bb956c2457d19b248006c212f58ecd4fb396f34ffc2a6e815` | 25 InputMappingButton controls (action *names*, not live key bindings) |
| `level0` | `d2d1b170cb1494ecaba4616b1d46e9467fac007c60fe0ba18fa8924a0e0ee8aa` | RewiredSpawner in start scene |
| `level1` | `cbfff68d57c3cadd304cead6c5486f9eb427c368b443bf4bfedff9d16172e790` | RewiredSpawner in title scene |
| `level2` | `99fce056f65647f62ba52d9957317b4ed876e600f854f12e65a20897d37c396d` | RewiredSpawner in main gameplay scene |

Source-derived data: InputManager prefab path IDs 192 (VR) and 193
(XInput); 52 vs 55 action/name records, with 49 shared action/name/ID pairs.
Names such as `Select` have *different IDs* (VR 57; XInput 58).
Do **not** use an action ID as a DualShock physical key. Hardware element
IDs `Cross=6`, `Circle=7`, `L1=10`, `R1=11`, D-pad `18–21`
are from the generic `SonyDualShock4` hardware profile; the profile is
not a verified controller assignment for the active Player. The asset
profile contains 24 known elements numbered 0 through 23.

## Which gates remain open

| Gate | Offline evidence now | Still missing |
| --- | --- | --- |
| Serialized scene and prefab links | Verified previously for `level0`–`level2` | Runtime-created scene and object identity |
| Rewired action name/ID catalog | Verified in two InputManager prefabs | Selected manager and active Player |
| SonyDualShock4 hardware-element IDs | Previously derived from `sharedassets0` | Active ControllerMap/ActionElementMap, layout/category, effective player-to-controller assignment |
| Unity input focus and scene owner | No live provider; host contracts require both | Runtime snapshot consistent with a specific Unity frame |
| Graphics host | PlayMaker virtual call graph and object lifecycle statically inspected | Safe title-owned OnGUI registration/teardown + ABI + render-thread proof |

These are **independent gates**. Even complete controller-map extraction
would not demonstrate an installable graphical Ultimate Mod Menu.

## Incremental improvement with no missing files

The host-side `src/unity_host_adapter.h` already requires
`input_focus_verified` and `scene_owner_verified`.
The offline C# `UcmDs4HardwareInput` contract now requires matching
`InputFocusVerified` and `SceneOwnerVerified` assertions from the future
live provider, plus rejection of any set hardware element ID outside 0–23.
This is deliberately a fail-closed check, **not** a discovered retail API.
C#4 synthetic tests exercise both focus and scene loss and invalid bits.

## Existing archives and next defensible analysis

Two ZIP uploads were provided in the current conversation under generic
names. Their **contents have not been inspected** in this runtime, so
neither an absence of these assets nor their presence may be inferred.
Do not identify an unrelated previously inspected archive as one of them
without verifying its contents.

Before asking the user for new PS4 extraction, first inspect *these ZIPs*
privately for any `Media/{globalgamemanagers.assets,sharedassets0.assets,
sharedassets1.assets,level0,level1,level2}`. If found, hash and
reuse matching files. Then decode active Rewired controller map data
where the serialized layout supports it; distinguish saved defaults
from live PlayStation input assignment.

If the originals remain unavailable, preserve this verified derived
evidence, continue the independent graphical host ABI/ownership analysis,
and make only a narrowly scoped read-only transfer request if it unlocks
a specific remaining check. No new PRX or console test is implied.

## New ZIP-first option (no FTP required when originals are present)

The standalone read-only archive checker `scripts/verify_unity_assets_in_archives.py`
inspects only whitelisted `Media/<filename>` members (including nested
`<prefix>/Media/<filename>` entries), checks the **original six file hashes**
without creating new files, and prints a metadata-only JSON report:

```sh
python3 scripts/verify_unity_assets_in_archives.py \
  /private/Archivo.zip '/private/Archivo(1).zip'
```

The default has no file write, console operation or connection. If matches
are verified, run the *separately authorized local* extraction mode:

```sh
python3 scripts/verify_unity_assets_in_archives.py \
  /private/Archivo.zip '/private/Archivo(1).zip' \
  --extract-dir /private/PS4_CUSA12398_UnityAssets
```

Only exact six-file SHA-256 matches may be published to the private output.
Malformed ZIPs, path traversal, mismatched hashes and oversized entries
fail without publishing an unverified asset. Tests use synthetic ZIP fixtures.
No commercial binary is stored in this repository.

**Status of user-supplied ZIPs:** They were received in the conversation,
but due to local container execution failure their ZIP entries have not yet
been inspected by this assistant. CI validates the scanner against synthetic
fixtures only. Work can execute this scanner directly on the actual private
attachments, if they are available in its cloud computer. Do not conflate
simulated tests with actual archive inspection.
