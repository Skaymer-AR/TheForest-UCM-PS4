# Ultimate Mod Menu DS4 hotkey — serialized input-overlap preflight

**Target:** The Forest PS4 CUSA12398 v1.15. This analysis reuses
`docs/REWIRED_CONTROLLER_MAPS_20261030.json`, derived from all six
SHA-256-verified private Unity assets. It never reads or uploads game files.

## Reproducible host-only check

```sh
python3 scripts/audit_rewired_menu_input_conflicts.py \
  --derived docs/REWIRED_CONTROLLER_MAPS_20261030.json \
  --output /private/ucm-menu-serialized-input-risk.json
python3 -m unittest discover -s tests -p 'test_*.py'
```

The script validates the game's source SHA-256, DS4 GUIDs, hardware element
names, map IDs, ActionElementMap counts and serialized player default flags.
It does **not** infer runtime state. The optional JSON is noncommercial,
derived data and no console input is performed.

## New specific finding for the proposed `L1+R1` menu hotkey

The initial `Player` serialized defaults include `Default/Default`
and `Menu/Default` for **both** Rewired prefabs. For each of the
two SonyDualShock4 hardware GUIDs under both prefabs, the map candidates
include *both* L1 and R1 assignments. The audit finds:

| Stored manager / DS4 GUID | Bindings to proposed menu buttons in enabled defaults | L1+R1 candidates |
| --- | ---: | --- |
| VR / `83b427e4-...` | 20 | Both |
| VR / `cd9718bf-...` | 25 | Both |
| XInput / `83b427e4-...` | 21 | Both |
| XInput / `cd9718bf-...` | 26 | Both |
| **Total** | **92** | **4 of 4 contexts** |

Examples: in VR's first serialized `Default` map, L1 contributes to
`Rotate`, `PreviousPage`, `Map`, while R1 contributes to
`AltFire`, `PreviousChapter` and `Equip`. In the second GUID's
`Default` map, Cross appears as `Take`, `Build`, `Save`.
Those are separate serialized entries, not proof that all fire together.
`MenuToggle` exists in the action catalogs but **has no serialized
DS4 ActionElementMap** for either manager.

**Engineering consequence:** a passive observer of DS4 element IDs cannot
promise that `L1+R1` will open the Ultimate Mod Menu without simultaneously
triggering normal gameplay actions. Rewired ActionElementMap enablement,
selected manager, live Player, active category/layout, focus and input
consumption are all unknown. A Future Unity provider must prove those
runtime properties and explicitly establish safe input policy; simply using
the saved default map settings as verified focus is prohibited.

This is a *risk audit*, not a recommendation to disable maps or hook
controller APIs. No ScePad writes, input injection, PRX, global API detours,
PKG modifications or on-console tests occurred.

## Independent rendering blockade

Even a confirmed runtime Rewired Player would **not** solve the separate
OnGUI host: there remains no verified title-owned registration, correct
IL2CPP ABI, Unity-frame ownership, and quiescent unregister path.
`docs/PLAYMAKER_VIRTUAL_DISPATCH_20261030.md` documents existing
PlayMaker OnGUI dispatch, not an external callback API. Keep PR #2 Draft.
