# The Forest PS4 — Rewired scene graph and native selector, 2026-10-30

**Target:** CUSA12398 v1.15, Unity Player `5.6.6f2`. **Status:** verified offline serialized-file references, metadata fields, and native instruction windows. Game binaries and Unity serialized assets remain private. No console execution, PKG change, PS4 mod install, or hooks.

## 1. Evidence and reconstruction

The new [`scripts/inspect_unity_rewired_assets.py`](../scripts/inspect_unity_rewired_assets.py) reads Unity serialized **format 17, little-endian, type trees disabled**. It bounds metadata counts and every object range, builds `MonoScript` type names from `globalgamemanagers.assets`, decodes `MonoBehaviour` GameObject/script references, follows cross-file prefab pointers, and extracts bounded action-name/ID records. It refuses other versions/layouts instead of guessing.

| Private source | SHA-256 | Serialized objects |
| --- | --- | ---: |
| `Media/globalgamemanagers.assets` | `2518dad0f38f6357276d1e33b4653a907df82dc8b0eb56450b49cb3eb86af2a8` | 3,814 |
| `Media/sharedassets0.assets` | `f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321` | 194 |
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

**Critical distinction:** an action integer (e.g. `Select=58`) is **not** a physical DS4 button assignment. The actual controller map, assigned player, active manager, and focus/consumption policy are still unverified. Neither `L1+R1` nor `Cross` should be connected to a Rewired action by guesswork.

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
corresponda a un botón físico. En Rewired, las asignaciones específicas
dependen de `ControllerMap` / `ActionElementMap` realmente cargados y
habilitados en cada `Player`.

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

## Reproduction

```sh
python3 scripts/inspect_unity_rewired_assets.py --assets-root /private/unity-assets \
  --output /private/rewired-graph.json
python3 -m unittest discover -s tests -p 'test_*.py'
```

The input folder should contain the five private files named in §1. No proprietary data is included in the test fixtures; generated JSON contains derived names, IDs and cryptographic hashes only.
