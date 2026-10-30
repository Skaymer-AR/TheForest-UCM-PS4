# Rewired: verified serialized maps and remaining runtime gates (2026-10-30)

**Title:** The Forest PS4, CUSA12398 v1.15. This page consolidates verified
ZIP recovery, serialized input maps, and remaining runtime gates documented
in `docs/REWIRED_SCENE_GRAPH_20261030.md` and
`docs/PLAYMAKER_VIRTUAL_DISPATCH_20261030.md`. No live console proof,
installation, or hook is authorized.

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
profile contains 24 known elements numbered 0 through 23. The serialized
ControllerMap/ActionElementMap findings, including different bindings for
the two DS4 hardware GUIDs, are in
[`REWIRED_CONTROLLER_MAPS_20261030.md`](REWIRED_CONTROLLER_MAPS_20261030.md).

## Which gates remain open

| Gate | Offline evidence now | Still missing |
| --- | --- | --- |
| Serialized scene and prefab links | Verified previously for `level0`–`level2` | Runtime-created scene and object identity |
| Rewired action name/ID catalog | Verified in two InputManager prefabs | Selected manager and active Player |
| SonyDualShock4 hardware-element IDs | IDs and serialized ControllerMap/ActionElementMap records decoded for both InputManagers | Active Player/controller assignment, map and ActionElementMap enabled state, runtime layout/category, input focus/consumption |
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

## ZIP recovery and current offline evidence

Five user-supplied archives were scanned privately by
`scripts/verify_unity_assets_in_archives.py`. All six exact pinned assets
matched, including `sharedassets0.assets` and `sharedassets1.assets` from
`Archivo 3.zip`; matching copies were extracted under `/tmp`. No asset or
commercial binary was committed. The run reported `all_six_verified: true`.

The recovered `sharedassets0.assets` supplied the serialized maps: 13
ControllerMap records (4 DS4-GUID maps, 96 ActionElementMaps) in the VR
manager, and 9 ControllerMap records (all 9 DS4-GUID maps, 195
ActionElementMaps) in the XInput manager. The parser also resolves each
manager's map category names, joystick layouts, and the serialized Player ID 1
default category/layout enable flags. It separately decodes the eight
`InputCategory` action categories and the ActionElementMap category selector;
that selector is kept distinct from the action's own catalog category and
from the ControllerMap category. These remain configuration data, not proof
of the live local Player. See
[`REWIRED_CONTROLLER_MAPS_20261030.md`](REWIRED_CONTROLLER_MAPS_20261030.md)
for key bindings and category namespaces, and
[`REWIRED_CONTROLLER_MAPS_20261030.json`](REWIRED_CONTROLLER_MAPS_20261030.json)
for the full derived output. The supplied `resources.assets` was also parsed
and contained no resolved Rewired MonoBehaviours or matching identifiers in
its TextAssets; its companion `.resS` is a raw resource stream, not a separate
serialized object database.

## ZIP-first reproduction (no FTP required)

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
No commercial binary is stored in this repository. The actual archive scan
verified the supplied files; synthetic tests exercise checker behavior.
