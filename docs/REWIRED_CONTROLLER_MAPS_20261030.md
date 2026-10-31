# Rewired serialized DS4 maps — derived offline findings

**Target:** The Forest PS4, CUSA12398 v1.15, Unity 5.6.6f2. This report
contains derived names, IDs, mappings and hashes only. Original assets were
kept in private temporary directories and are not part of the repository.

## Asset recovery and scope

`scripts/verify_unity_assets_in_archives.py` scanned `Archivo.zip`,
`Archivo(1).zip`, `Archivo 2.zip`, `Archivo 2(1).zip` and `Archivo 3.zip`.
All six pinned Unity assets matched their expected SHA-256 values. In
particular, `Archivo 3.zip` contains the verified `sharedassets0.assets`
(`f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321`)
and `sharedassets1.assets`
(`d227ee3ac409b21bb956c2457d19b248006c212f58ecd4fb396f34ffc2a6e815`).
They were extracted privately for inspection.

The separately supplied `resources.assets` was parsed as Unity serialized
format 17 / Unity 5.6.6f2: SHA-256
`9b28d330969eaf9f6ae5dc0fa5e83b022174720744c272f80ee887a46e063536`,
133,191 objects, 16,419 MonoBehaviours and 43 TextAssets. Resolving its
MonoBehaviours through the pinned `globalgamemanagers.assets` MonoScripts
found no Rewired script; none of its TextAssets contained the searched Rewired,
ControllerMap, ActionElementMap or DS4-GUID identifiers.

`resources.assets.resS` is 299,305,404 bytes with SHA-256
`521285d46383390607bbadd010c548b3a254909f0c47bda6adadaf3c1090ba4b`.
It has no Unity serialized-object header, so this inspection did not treat it
as a separate object database or infer any ControllerMap from it.

All 30 `sharedassets0.assets`–`sharedassets29.assets` files in `Archivo 3.zip`
parsed with the repository's bounded Unity 5.6 reader. Both Rewired
`InputManager` components (path IDs 192 and 193) are in
`sharedassets0.assets`. `sharedassets2.assets` has one
`Rewired.Dev.Tools.DebugInformation` component; no other shared asset exposed
an InputManager component or another serialized map collection.

## What the decoder verifies

[`inspect_rewired_controller_maps.py`](../scripts/inspect_rewired_controller_maps.py)
pins the `sharedassets0.assets` hash, resolves the two InputManagers through
their MonoScript references, and validates the serialized list counts, GUID
backed ControllerMap records, contiguous bounds, 44-byte ActionElementMap
strides, action names/IDs and controller-element type IDs. The input action
catalog and its eight `InputCategory` records are decoded using the metadata
field order. Controller map categories (`InputMapCategory`) and joystick
layouts are a separate table. The report keeps these category namespaces
separate.

The 44-byte record contains eleven 32-bit words. They align with the first
eleven instance fields of `Rewired.ActionElementMap` in the verified IL2CPP v23
metadata (`global-metadata.dat` SHA-256
`238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`):
`_actionCategoryId`, `_actionId`, `_elementType`,
`_elementIdentifierId`, `_axisRange`, `_invert`, `_axisContribution`,
`_keyboardKeyCode`, and `_modifierKey1` through `_modifierKey3`. The last seven
words are therefore decoded as AxisRange (`Full=0`, `Positive=1`, `Negative=2`),
invert (`false/true`), Pole (`Positive=0`, `Negative=1`), and keyboard key plus
three modifiers. In these joystick maps, the keyboard key is always
`None=0` and the modifiers are always `None=0`; other values are rejected by
the pinned decoder. Rewired documents that `axisRange` describes the bound
axis portion, while `axisContribution` controls the sign contributed by a
button or split-axis binding when queried as an axis. `invert` applies to a
full-axis binding. See the official [Axis Range](https://guavaman.com/projects/rewired/docs/api-reference/html/P_Rewired_ActionElementMap_axisRange.htm),
[Axis Contribution](https://guavaman.com/projects/rewired/docs/api-reference/html/P_Rewired_ActionElementMap_axisContribution.htm),
and [CreateElementMap](https://guavaman.com/projects/rewired/docs/api-reference/html/M_Rewired_ControllerMapWithAxes_CreateElementMap.htm)
references. The 44-byte record does not include the later `_enabled` field;
runtime ActionElementMap enablement remains unknown.

For each ActionElementMap, the JSON includes the stored action-category
selector and name, the action ID/name, the InputAction catalog category ID/name,
the element type, and the DS4 hardware element ID/name. The two stored category
IDs are retained separately because the serialized data contains records
where they differ; the decoder does not equate them or infer runtime effects
from that difference. Rewired's documentation describes Action Categories as
organizational for editor/UI lists, and its Editor lists an Action Category
and Action for element assignments; neither category ID is a physical button
or proof of runtime map activation. See [Actions](https://guavaman.com/projects/rewired/docs/Actions.html),
[Rewired Editor](https://guavaman.com/projects/rewired/docs/RewiredEditor.html)
and [ActionElementMap](https://guavaman.com/projects/rewired/docs/api-reference/html/T_Rewired_ActionElementMap.htm).
`ActionElementMap.enabled` is not present in the 44-byte serialized map record,
so its runtime value is not decoded. The decoded axis range, inversion and
contribution fields describe the stored binding; they do not prove that its
ControllerMap is active or that Rewired is currently evaluating it.

The two GUIDs in the generic `SonyDualShock4` profile are
`83b427e4-086f-47f3-bb06-be266abd1ca5` and
`cd9718bf-a87a-44bc-8716-60a0def28a9f`. These are serialized hardware-profile
identifiers; this does not establish which ID a PS4 session will expose.

## Serialized manager and Player defaults

| InputManager | ControllerMaps | DS4 GUID maps / ActionElementMaps | Controller map categories | Joystick layouts | Serialized Player ID 1 defaults |
| --- | ---: | ---: | --- | --- | --- |
| VR (prefab 21, component 192) | 13 | 4 / 96 | `0 Default`, `1 Chat`, `2 Menu`, `3 RadialWorld`, `4 Inventory`, `5 Book` | `0 Default` | `startPlaying=true`; Default, Menu, Inventory, RadialWorld, Book enabled on Default layout |
| XInput (prefab 22, component 193) | 9 | 9 / 195 | `0 Default`, `1 Chat`, `2 Menu`, `3 Inventory`, `4 Book` | `0 Default`, `2 Lefty` | `startPlaying=true`; Default and Menu enabled; Inventory and Book disabled on Default layout |

Across the DS4 ControllerMaps, VR has 95 `Full` and 1 `Positive` axis-range
bindings; XInput has 191 `Full` and 4 `Positive`. All decoded `invert` fields
are false. `axisContribution` is `Positive` on 90 VR / 188 XInput entries and
`Negative` on 6 / 7. All entries have `KeyboardKeyCode.None` and three
`ModifierKey.None` values. Positive axis-range bindings are `L2`/`R2` for
`PreviousChapter`/`NextChapter` in the Default map for the second GUID: one
pair in XInput Default and another in XInput Lefty; VR has `R2` for
`NextChapter` in Default. These are stored as `Axis` elements with `Positive`
range. The counts are static map data and do not indicate which map is active.

Both managers have the same eight Action Categories: `0 Default`, `1 Menu`,
`2 World`, `3 Build`, `4 Inventory`, `5 Book`, `6 Movement`, `7 Multiplayer`.
These are not the ControllerMap categories above.

## Selected bindings in serialized DS4 ControllerMaps

| Action | Serialized ControllerMap categories/layouts | `83b427e4-086f-47f3-bb06-be266abd1ca5` | `cd9718bf-a87a-44bc-8716-60a0def28a9f` |
| --- | --- | --- | --- |
| `Jump` | Default in both managers; XInput also has a Lefty layout map for the second GUID | Square | Triangle; also Triangle in XInput Lefty |
| `Back` | Menu in both managers; XInput also has Book maps | R2; Touchpad Button in XInput Book | Circle; Options in XInput Book |
| `Vertical` | Default and Menu in both managers; XInput also has Inventory and Book maps, plus a Lefty layout for the second GUID | Left Stick Y in Default and Menu; Menu also D-pad Right/Left | Left Stick Y in Default and Menu; Menu also D-pad Up/Down; Lefty uses Right Stick Y in Default |
| `Select` | Book in XInput only | L2 | Cross |

`MenuToggle` is present in both action catalogs but has no ActionElementMap in
the serialized DS4 maps. `Select` is also unbound in the VR manager. Although
XInput contains `Select` mappings in its Book ControllerMap, the serialized
Player default has Book disabled. That configuration alone does not show
whether any of these maps is active during gameplay; saved user data and
runtime changes may differ. The Player defaults mark Default and Menu enabled
in both managers, and XInput also serializes `Vertical` in both categories.
This reveals overlapping bindings in the static configuration; it does not
show whether gameplay and menu input are both evaluated at runtime or how the
game prevents duplicated input.

The full machine-readable derived output is
[`REWIRED_CONTROLLER_MAPS_20261030.json`](REWIRED_CONTROLLER_MAPS_20261030.json).
Its synthetic-only regression tests do not contain game assets.

## Runtime and integration boundary

Rewired documents that ControllerMaps are assigned to Players and controller
maps/categories/layouts have enabled state. The serialized Player_Editor
defaults are not evidence of the active local Player, connected controller,
selected VR/XInput manager, effective runtime maps, ActionElementMap enabled
state, focus, or input consumption. Static button mappings also do not solve
the separate missing PlayMaker/Unity callback registration and teardown
contract. No PS4 provider, PRX rendering path, PKG modification or console test
is established by this report.
