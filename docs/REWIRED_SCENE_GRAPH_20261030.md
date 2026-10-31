# The Forest PS4 — Rewired scene graph and native selector, 2026-10-30

**Target:** CUSA12398 v1.15, Unity Player `5.6.6f2`. **Status:** verified offline serialized-file references, metadata fields, and native instruction windows. Game binaries and Unity serialized assets remain private. No console execution, PKG change, PS4 mod install, or hooks.

## 1. Evidence and reconstruction

The new [`scripts/inspect_unity_rewired_assets.py`](../scripts/inspect_unity_rewired_assets.py) reads Unity serialized **format 17, little-endian, type trees disabled**. It bounds metadata counts and every object range, builds `MonoScript` type names from `globalgamemanagers.assets`, decodes `MonoBehaviour` GameObject/script references, follows cross-file prefab pointers, and extracts bounded action-name/ID records. It refuses other versions/layouts instead of guessing.

| Private source | SHA-256 | Serialized objects |
| --- | --- | ---: |
| `Media/globalgamemanagers.assets` | `2518dad0f38f6357276d1e33b4653a907df82dc8b0eb56450b49cb3eb86af2a8` | 3,814 |
| `Media/sharedassets0.assets` | `f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321` | 194 |
| `Media/sharedassets1.assets` | `d227ee3ac409b21bb956c2457d19b248006c212f58ecd4fb396f34ffc2a6e815` | 7,565 |
| `Media/level0` | `d2d1b170cb1494ecaba4616b1d46e9467fac007c60fe0ba18fa8924a0e0ee8aa` | 39 |
| `Media/level1` | `cbfff68d57c3cadd304cead6c5486f9eb427c368b443bf4bfedff9d16172e790` | 2,977 |
| `Media/level2` | `99fce056f65647f62ba52d9957317b4ed876e600f854f12e65a20897d37c396d` | 242,796 |

The `globalgamemanagers.assets` library exposes **3,801** `MonoScript` objects. Relevant resolved scripts include `TheForest.Utils.RewiredSpawner`, `Rewired.InputManager`, `TheForest.UI.VirtualCursor`, and `Rewired.Data.Mapping.HardwareJoystickMap`. These are decoded script identifiers, not string searches alone.

## 2. Verified scene → prefab graph

In each scene, the `Rewired Spawner` GameObject is marked active and its `RewiredSpawner` MonoBehaviour marked enabled **in the serialized scene**:

| Scene | Rewired Spawner GameObject path ID | Component path ID | First prefab ref | Second prefab ref |
| --- | ---: | ---: | --- | --- |
| `level0` (logo/start) | `8` | `38` | fileID `2` → `sharedassets0.assets:21` | fileID `2` → `sharedassets0.assets:22` |
| `level1` (title) | `744` | `2859` | fileID `6` → `sharedassets0.assets:21` | fileID `6` → `sharedassets0.assets:22` |
| `level2` (`ForestMain_v08`) | `3961` | `193462` | fileID `6` → `sharedassets0.assets:21` | fileID `6` → `sharedassets0.assets:22` |

Both targets resolve to actual Unity GameObjects in `sharedassets0.assets`:

| Unity GameObject path ID | Name | Rewired.InputManager MonoBehaviour path ID | Serialized state |
| --- | --- | ---: | --- |
| `21` | `Rewired Input Manager VR` | `192` | GameObject active; component enabled |
| `22` | `Rewired Input Manager XInput` | `193` | GameObject active; component enabled |

The asset component graph was checked against the external `MonoScript` library by path ID and class/namespace; a matching name alone was not treated as proof. **An active flag stored in a serialized prefab does not establish that the GameObject was instantiated or active at runtime.**

### Componentes adjuntos a cada gestor (referencias verificadas)

Además del `InputManager`, resolví todas las referencias `GameObject → MonoBehaviour → MonoScript` en ambos prefabs, incluidos los bits `enabled` serializados:

| Componente | Prefab VR (objeto) | Prefab XInput (objeto) | Estado en asset |
| --- | ---: | ---: | --- |
| `Rewired.InputManager` | 192 | 193 | Ambos habilitados |
| `TheForest.Utils.Input` | 187 | 188 | Ambos habilitados |
| `TheForest.Utils.InputMapping` | 190 | 191 | Ambos habilitados |
| `TheForest.UI.VirtualCursor` | 184 | 185 | Ambos habilitados |
| `TheForest.Utils.Mood` | 189 | 186 | Ambos habilitados |
| `TheForest.VR.VRCustomRewiredController` | 194 | — | Deshabilitado en prefab VR |

**Implicación:** el mismo gestor elegido por `RewiredSpawner` agrupa entrada, mapeo de acciones y el cursor virtual. Son candidatos reales para entender el ciclo de entrada y foco del futuro menú, pero **no son un bootstrap para registrar código AOT nuevo**. Tampoco sabemos si el objeto se instancia en una sesión PS4 determinada.

El objeto de escena llamado `PS4ControllerFeatures` no constituye por sí solo una prueba del método `PS4Controller.Update`. Su conjunto de componentes serializados incluye dos scripts de iluminación (`PS4Light` y `TheForestPS4Light`), por lo que sería incorrecto inferir de su nombre el origen del input de gameplay.

## 3. Rewired action catalog from both actual InputManager objects

The two InputManager objects contain length-prefixed records comprising an action integer and a string. The bounded parser validates `MenuToggle` (ID 2), finds the action-category boundary, and checks each candidate before using it.

- VR manager object 192: **52** action-name/ID records.
- XInput manager object 193: **55** action-name/ID records.
- **49** matching name/ID pairs are shared across both catalogs.
- Example IDs present in both: `MenuToggle=2`, `Back=43`, `Inventory=19`.
- **IDs that vary or are absent:**

| Action | VR (ID) | XInput (ID) |
| --- | ---: | ---: |
| `Select` | 57 | 58 |
| `Skip` | 56 | 57 |
| `Radial` | 58 | — |
| `RestoreDefaults` | — | 55 |
| `SaveBindings` | — | 56 |
| `Refresh` | — | 60 |
| `Search` | — | 61 |

**Critical distinction:** an action integer (e.g. `Select=58`) is **not** a physical DS4 button assignment. The serialized ControllerMap/ActionElementMap definitions and Player's default map flags are now decoded in §3C, but the runtime Player, active manager/map, live enable state, and focus/consumption policy remain unverified. Neither `L1+R1` nor `Cross` should be connected to a Rewired action by guesswork.

Object `133` in `sharedassets0.assets` is a `Rewired.Data.Mapping.HardwareJoystickMap` and contains the profile `SonyDualShock4`. That establishes the presence of a general hardware description; it does **not** establish the selected PS4 runtime controller map.

### Enlace GUID entre perfil Sony DualShock 4 y ambos InputManager

El objeto de perfil `HardwareJoystickMap` ID `133` contiene exactamente dos
identificadores de hardware en texto UUID:

- `83b427e4-086f-47f3-bb06-be266abd1ca5`
- `cd9718bf-a87a-44bc-8716-60a0def28a9f`

Ambas cadenas aparecen también en los datos serializados de **cada uno**
de los gestores `InputManager` (objetos `192` y `193`). El analizador
ahora calcula esas intersecciones y las registra de forma reproducible.

Es una **correspondencia entre datos de configuración**, no una prueba
de que el mando DS4 esté asignado al jugador o de que determinada acción
corresponda a un botón físico durante una sesión. §3C decodifica los
`ControllerMap_Editor` y `ActionElementMap` serializados en los dos
InputManager; todavía no prueba qué mapas se cargan o habilitan en un
`Player` real.

## 3B. Interfaz de controles de `sharedassets1.assets` (nuevo)

El archivo privado `Media/sharedassets1.assets` tiene **3.031**
`MonoBehaviour`; entre ellos hay **25 componentes**
`TheForest.Utils.InputMappingButton`, dos
`TheForest.Utils.InputMappingAction` y un
`TheForest.Utils.InputMappingButtonManager`.

Los 25 controles enlazan un `GameObject` (por ejemplo
`inputMapButton_run`) con un **nombre de acción** serializado. Todos los
nombres existen en los catálogos de los gestores VR y XInput, y los IDs
correspondientes coinciden en ambos.

| Acción comprobada | VR/XInput action ID | Ejemplo de componente UI |
| --- | ---: | --- |
| `Run` | 16 | `inputMapButton_run` |
| `Inventory` | 19 | `inputMapButton_inventory` |
| `Jump` | 9 | `inputMapButton_jump` |
| `SurvivalBook` | 28 | `inputMapButton_survivalbook` |
| `Horizontal` | 7 | `inputMapButton_horizontal_pos/neg` |
| `Vertical` | 8 | `inputMapButton_vertical_pos/neg` |
| `Build` | 38 | `inputMapButton_build` |
| `ItemSlot1` a `ItemSlot4` | 48–51 | cuatro controles de ranuras |

Otras acciones verificadas: `Take`, `Utility`, `Drop`,
`Rotate`, `Crouch`, `RestKey`, `Craft`, `Save`,
`PlayerList`, `Lighter`, `WalkyTalky` y `Map`.
El analizador `inspect_unity_rewired_assets.py` resuelve ahora
el script, `GameObject`, nombre de acción y su ID en ambos gestores
para cada uno de los 25 componentes, sin duplicar assets privados.

**Alcance:** los componentes son controles de una interfaz de
asignación; no constituyen la configuración física de cada botón
del mando en una sesión PS4. No deben utilizarse como prueba
de que, por ejemplo, `Jump` corresponda a Cross.

## 4. Native IL2CPP corroboration: two different prefab fields

The private ELF comparison against the previously retained IL2CPP reference is exact: SHA-256 `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`. The metadata is version 23; `TheForest.Utils.RewiredSpawner` (`TypeDefinition` index `11900`) has three successive fields:

| Field | Field definition index | Token |
| --- | ---: | --- |
| `_rewiredVRPrefab` | 64415 | `0x04007EB2` |
| `_rewiredXInputPrefab` | 64416 | `0x04007EB3` |
| `_rewiredPrefab` | 64417 | `0x04007EB4` |

The IL2CPP native method-pointer table at file offset `0x031738C0` yields:

| Method | Method index | Native RVA |
| --- | ---: | ---: |
| `RewiredSpawner.Awake` | 80419 | `0x01DD7830` |
| `RewiredSpawner.InstanceManager` | 80420 | `0x01DD79A0` |
| `RewiredSpawner.InstanceVRManager` | 80421 | `0x01DD7BD0` |

Bounded x86-64 disassembly confirms:

- `Awake` includes a **conditional** direct call at RVA `0x01DD78BB` → `InstanceManager` (`0x01DD79A0`). It is **not** asserted to run on every startup.
- `InstanceManager` loads the instance field at `this+0x20`, consistent with the **second** serialized pointer `_rewiredXInputPrefab`.
- `InstanceVRManager` loads the instance field at `this+0x18`, consistent with the **first** serialized pointer `_rewiredVRPrefab`.
- The exact runtime branch conditions, object instantiation results and selected controller bindings require further validation. This is **not** a call-injection target or an authorization to hook these routines.

## 5. Implications for our Ultimate Mod Menu

1. The next input provider should identify the live `Rewired.Player`/manager and resolve **action names against that manager**, not assume the VR and XInput integer IDs are interchangeable. Controller button mappings remain a separate proof gate.
2. The `prototype/Unity56/Assets/UCM` host stays disconnected from retail. The new scene graph does not add a class to `CodeRegistration` or provide a PS4-compatible IL2CPP rebuild pipeline.
3. A real AOT component still needs the title's Unity/PS4 project or an equivalently complete rebuild pipeline, with registered methods and startup creation. Neither modifying the PKG nor shipping a PRX is authorized.
4. Follow-up offline research should decode the **selected manager's actual Rewired controller-to-action map** and inspect Unity main-thread ownership/focus before preparing a provider. If all offline options are exhausted, present a single precise request for missing assets/toolchain or an explicitly authorized hardware test.

## Rewired runtime mapping model (upstream documentation)

Rewired's official docs confirm that a controller-to-action binding belongs
to a **Controller Map on a Player**, with category/layout and enabled state;
the hardware profile is distinct from the Player's active ActionElementMaps.
This is why the serialized `SonyDualShock4` profile and an InputManager
action ID cannot by themselves identify the real DS4 button or action owner.
See [Controller Maps](https://guavaman.com/projects/rewired/docs/ControllerMaps.html),
[Players](https://guavaman.com/projects/rewired/docs/Players.html)
and [read-only controller-map enumeration](https://guavaman.com/projects/rewired/docs/HowTos.html).

## 3C. Serialized ControllerMap / ActionElementMap (ZIP recovery, 2026-10-30)

`scripts/verify_unity_assets_in_archives.py` was run on the five supplied ZIP
archives (`Archivo.zip`, `Archivo(1).zip`, `Archivo 2.zip`,
`Archivo 2(1).zip`, and `Archivo 3.zip`). It found and SHA-256-verified all
six pinned Unity assets. `Archivo 3.zip` contains the exact pinned
`sharedassets0.assets` and `sharedassets1.assets`; all six were extracted to a
private `/tmp` directory for analysis. No Unity asset or game binary was added
to Git.

The bounded parser in
[`inspect_rewired_controller_maps.py`](../scripts/inspect_rewired_controller_maps.py)
decodes the `ControllerMap_Editor` list in the two existing InputManager
components in the hash-pinned `sharedassets0.assets`. It verifies the list
count before the first map, all UUID-backed records, 44-byte
`ActionElementMap` strides, contiguous map boundaries, and each mapped action
against that InputManager's own action catalog. It decodes the action catalog
and its `InputCategory` action-category table using their metadata field
orders, then resolves the distinct `InputMapCategory`, joystick `InputLayout`,
and serialized
`Player_Editor._defaultJoystickMaps` records through the `UserData` field
order. The IL2CPP v23 metadata field order for `Rewired.ActionElementMap`
matches all eleven 32-bit words of the 44-byte element record:
`_actionCategoryId`, `_actionId`, `_elementType`, `_elementIdentifierId`,
`_axisRange`, `_invert`, `_axisContribution`, `_keyboardKeyCode`, and three
modifier keys. The decoder validates and reports these enum/boolean fields.
The later `_enabled` field is outside this serialized record, so the runtime
enable state is not decoded.
The first word is resolved against the separate `InputCategory` table, and
the selected action's own `InputAction._categoryId` is reported separately.
Some serialized records carry different values in those fields; the inspector
preserves both and does not infer runtime effects or treat them as equivalent.
These action categories are distinct from the ControllerMap's
`InputMapCategory`. The official Rewired API defines
`ControllerElementType.Axis=0` and `Button=1`; the generic Sony profile
supplies the element-name lookup.

| Serialized InputManager | Map categories (ID → name) | Joystick layouts (ID → name) | Serialized `Player` defaults |
| --- | --- | --- | --- |
| VR (prefab 21, component 192) | `0 Default`, `1 Chat`, `2 Menu`, `3 RadialWorld`, `4 Inventory`, `5 Book` | `0 Default` | Player ID 1; startPlaying=true; Default, Menu, Inventory, RadialWorld and Book assigned enabled on Default layout |
| XInput (prefab 22, component 193) | `0 Default`, `1 Chat`, `2 Menu`, `3 Inventory`, `4 Book` | `0 Default`, `2 Lefty` | Player ID 1; startPlaying=true; Default and Menu enabled; Inventory and Book disabled on Default layout |

Both InputManagers also serialize the same Action Categories:
`0 Default`, `1 Menu`, `2 World`, `3 Build`, `4 Inventory`, `5 Book`,
`6 Movement`, and `7 Multiplayer`. The report keeps these separate from the
ControllerMap categories above.

For the same managers, there are 13 and 9 serialized ControllerMaps,
respectively. Of these, 4 VR maps (96 ActionElementMaps) and all 9 XInput
maps (195 ActionElementMaps) use one of the two GUIDs in the generic
`SonyDualShock4` profile. The enabled bits above come from the serialized
Player's category/layout defaults; they do not prove runtime activation.
Individual ActionElementMap enabled state is not decoded. The asset also does
not identify which DS4 GUID a PS4 session will expose.

The mappings show why action names must be resolved through the selected
manager and controller map, rather than mapped from Rewired IDs or guessed
from common DS4 layouts:

| Serialized action | DS4 hardware GUID | Binding in the decoded maps |
| --- | --- | --- |
| `Jump` | `83b427e4-086f-47f3-bb06-be266abd1ca5` | `Square` |
| `Jump` | `cd9718bf-a87a-44bc-8716-60a0def28a9f` | `Triangle` |
| `Back` (map category `Menu`, ID 2) | `83b427e4-086f-47f3-bb06-be266abd1ca5` | `R2` in both managers |
| `Back` (map category `Menu`, ID 2) | `cd9718bf-a87a-44bc-8716-60a0def28a9f` | `Circle` in both managers |
| `Vertical` (map category `Menu`, ID 2) | first GUID above | Left Stick Y plus D-pad Right/Left |
| `Vertical` (map category `Menu`, ID 2) | second GUID above | Left Stick Y plus D-pad Up/Down |
| `Select` (map category `Book`, ID 4, XInput manager) | first GUID above | `L2` |
| `Select` (map category `Book`, ID 4, XInput manager) | second GUID above | `Cross` |

These are selected bindings, not a complete listing: XInput also maps `Back`
to Touchpad Button / Options in Book maps, and `Vertical` appears in Default,
Menu, Inventory, Book and the second-GUID Lefty layout. The serialized Player
defaults enable Default and Menu in both managers but disable Inventory and
Book in XInput. Since `Vertical` is present in both enabled categories in the
static defaults, the assets do not establish whether gameplay receives the
same input as a visible menu or how the title prevents duplicate handling.
The full per-map listing is in
[`REWIRED_CONTROLLER_MAPS_20261030.md`](REWIRED_CONTROLLER_MAPS_20261030.md)
and the JSON report.

`MenuToggle` exists in both action catalogs but has no ActionElementMap in the
serialized DS4 maps. `Select` (catalog ID 57) likewise has no serialized DS4
binding in the VR manager; in the XInput manager its action ID is 58 and its
two GUID-specific bindings differ as shown above. Two records in the VR
manager and four in the XInput manager carry raw action ID `0xFFFFFFFF`,
which has no matching named action in their respective catalogs. These are
findings about serialized configuration only;
user-saved maps or runtime changes can differ.
The XInput `Select` entries are in its `Book` ControllerMap category, which
the serialized Player ID 1 default marks disabled; this still does not show
the effective map state in a running game.

The supplied `resources.assets` was independently checked: SHA-256
`9b28d330969eaf9f6ae5dc0fa5e83b022174720744c272f80ee887a46e063536`, Unity
serialized format 17, `5.6.6f2`, 133,191 objects. None of its 16,419 resolved
MonoBehaviours maps to a Rewired script, and none of its 43 TextAssets contains
the queried Rewired/controller-map identifiers. `resources.assets.resS` is a
299,305,404-byte raw resource stream (SHA-256
`521285d46383390607bbadd010c548b3a254909f0c47bda6adadaf3c1090ba4b`) with no
Unity serialized-object header; it does not expose a separately attributable
ControllerMap. All 30 `sharedassets0.assets`–`sharedassets29.assets` in
`Archivo 3.zip` were parsed privately. Both serialized InputManager
components and the DS4 map data are in `sharedassets0.assets`;
`sharedassets2.assets` contains one `Rewired.Dev.Tools.DebugInformation`
component. No additional InputManager component or controller-map collection
was identified in the other files.

The derived narrative is in
[`REWIRED_CONTROLLER_MAPS_20261030.md`](REWIRED_CONTROLLER_MAPS_20261030.md),
with full machine-readable output in
[`REWIRED_CONTROLLER_MAPS_20261030.json`](REWIRED_CONTROLLER_MAPS_20261030.json).
It contains decoded action, element, map-category, layout, and serialized
Player-default names/identifiers plus the source asset hash, not original
asset bytes.

**Runtime boundary:** Rewired documentation states that maps belong to a
Player, must be loaded/assigned and enabled to contribute input, and that
Joystick maps load when a compatible controller is assigned. See the official
[Controller Maps](https://guavaman.com/projects/rewired/docs/ControllerMaps.html),
[ActionElementMap](https://guavaman.com/projects/rewired/docs/api-reference/html/T_Rewired_ActionElementMap.htm),
and [ControllerElementType](https://guavaman.com/projects/rewired/docs/api-reference/html/T_Rewired_ControllerElementType.htm)
references. The static Player ID 1 configuration does not establish which
runtime Player is local, the connected DS4, selected VR/XInput manager,
actual loaded/enabled map or ActionElementMap, input focus, or whether
gameplay consumes the same input. No retail Rewired provider or safe Unity
callback registration mechanism was found by this analysis.

## Reproduction

```sh
python3 scripts/inspect_unity_rewired_assets.py --assets-root /private/unity-assets \
  --output /private/rewired-graph.json
python3 scripts/inspect_rewired_controller_maps.py --assets-root /private/unity-assets \
  --output /private/rewired-controller-maps.json
python3 -m unittest discover -s tests -p 'test_*.py'
```

The input folder should contain the six private files named in §1, including `sharedassets1.assets` for UI action controls. No proprietary data is included in the test fixtures; generated JSON contains derived names, IDs and cryptographic hashes only.
