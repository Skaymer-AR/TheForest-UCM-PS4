# PlayMakerGUI native dispatch — verified IL2CPP virtual-slot cross-check

**Target:** The Forest PS4 CUSA12398 v1.15, Unity Player 5.6.6f2. Read-only binary analysis, no PRX or title changes.

**Inputs:** private plaintext IL2CPP ELF SHA-256 `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`, private global metadata SHA-256 `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`.

## 1. Exact native call graph

`PlayMakerGUI.OnGUI` is located at ELF link VA `0x0113FAF0` (native method index `31674`). The next distinct method starts at `0x011411F0`, so the disassembler inspected a **0x1700-byte bounded region**. It contains **151 direct call instructions**, **17 indirect call instructions**, and **18 direct calls** whose targets were resolved to known IL2CPP method names in the v23 metadata. These counts describe **static instructions**, not runtime execution frequency.

| Call site (link VA) | Direct target (link VA) | Resolved IL2CPP method |
| --- | --- | --- |
| `0x0113FD5D` | `0x019BC3F0` | `UnityEngine.GUI.set_skin` |
| `0x0113FE0B` | `0x019CC8D0` | `UnityEngine.GUI.set_color` |
| `0x0113FE65` | `0x019CCB10` | `UnityEngine.GUI.set_backgroundColor` |
| `0x0113FEBF` | `0x019CCD50` | `UnityEngine.GUI.set_contentColor` |
| `0x01140073` | `0x011411F0` | `PlayMakerGUI.DoEditGUI` |
| `0x01140142` | `0x01141320` | `PlayMakerGUI.CallOnGUI` |
| `0x01140430` | `0x01141320` | `PlayMakerGUI.CallOnGUI` |
| `0x01140CA0` | `0x019BD1F0` | `UnityEngine.GUI.DrawTexture` |

The `PlayMakerGUI.CallOnGUI` method (index `31675`, link VA `0x01141320`) iterates a collection of already-existing managed state/action objects, with an indirect virtual call at `0x0114139E`: `callq *0x320(%rax)`. Its presence does **not** imply that a native PRX can safely subscribe a callback to that list.

## 2. Three independent metadata-to-machine-code consistency checks

The `HutongGames.PlayMaker.FsmStateAction` metadata reports these virtual slots. Bounded disassembly of three **different** native methods finds the corresponding indirect dispatch instructions:

| FsmStateAction virtual method | Definition index | Slot | Calling native method | Indirect call site (link VA) | Operand |
| --- | ---: | ---: | --- | --- | --- |
| `OnEnter` | `34072` | `30` | `FsmState.ActivateActions` | `0x01118BA4` | `*0x2F0(%rax)` |
| `OnUpdate` | `34074` | `32` | `FsmState.OnUpdate` | `0x01123B33` | `*0x310(%rax)` |
| `OnGUI` | `34075` | `33` | `FsmState.OnGUI` | `0x01127713` | `*0x320(%rax)` |

All three match a common, **inferred** vtable base `0x110`, with a 16-byte `VirtualInvokeData` stride: `0x110+16*30=0x2F0`, `0x110+16*32=0x310`, and `0x110+16*33=0x320`. `PlayMakerGUI.CallOnGUI` uses the same `0x320` dispatch. This triangulates that the existing event path ultimately invokes `FsmStateAction.OnGUI` methods. The exact runtime class instance at each call and its lifetime are still unknown.

**Important:** This is **existing PlayMaker action dispatch**, not a native injection API. The base `FsmStateAction.OnGUI` implementation at `0x01130870` is a single `ret`; derived classes may override the method. Directly replacing the shared class vtable entry would not guarantee intercepting derived overrides and may affect many unrelated action instances. No such replacement was made.

## 3. What this changes in the PRX strategy

We now have real evidence that the **game itself** calls Unity GUI methods and PlayMaker actions during its `OnGUI` code. Therefore the rendering mechanism is not fictitious and we should stop investigating `DebugConsole.OnGUI` and global GNM hooks.

But these facts do **not** prove any of the following:

1. An externally loadable native-PRX function can be *registered* as a Unity/PlayMaker OnGUI action without regenerating managed/AOT code or altering live object structures.
2. The address of a method inside a memory-mapped module is safe to call outside an IMGUI event on the Unity main thread.
3. A vtable-pointer replacement can be installed with verified ownership, synchronization, reentrancy and a safe in-flight unload barrier on this GoldHEN loader.
4. The ABI for managed `Rect`, `GUIContent`, `MethodInfo` and the active `Event` is established for external native calls.
5. A graphical PRX has been linked, installed, or tested.

The next concrete research target—the owner and lifecycle of the existing action list—was checked against the exact title metadata and bounded native method windows below.

## 4. ActionData loading and live-action lifecycle

The relevant metadata surface does not expose an `AddAction`/`RegisterAction` API. `FsmState` exposes `get_Actions`, `set_Actions`, `LoadActions`, `SaveActions` and `ActivateActions`; `ActionData` exposes its serializer/deserializer methods (`LoadActions`, `CreateAction`, `LoadActionField`, `SaveActions`). The native implementations show the following path:

| Method | Definition / method index | Link VA | Verified behavior |
| --- | ---: | ---: | --- |
| `FsmState.get_Actions` | 34035 / 31259 | `0x01118D30` | Returns the array at `FsmState+0x60`; when null, calls `ActionData.LoadActions` with `FsmState.actionData` at `+0x68`, then stores the returned array at `+0x60`. |
| `FsmState.LoadActions` | 33997 / 31221 | `0x01122C00` | Calls the same `ActionData.LoadActions` method and assigns its result to the `actions` field. |
| `ActionData.LoadActions` | 33610 / 30680 | `0x010F2A20` | Iterates the serialized action count and calls `ActionData.CreateAction` once per record. It is the load/deserialization path. |
| `ActionData.CreateAction` | 33611 / 30681 | `0x010F2D80` | Called by the loader to materialize one serialized action record. No external registration call was found in this path. |
| `FsmState.set_Actions` | 34036 / 31260 | `0x011305B0` | Performs only `FsmState+0x60 = value` and returns. It does not validate, initialize, attach or activate any action. |
| `FsmState.ActivateActions` | 34001 / 31225 | `0x01118A30` | Reads the action array, checks `FsmStateAction.enabled` at `+0x18`, adds enabled objects to `activeActions` at `+0x70`, initializes them through virtual slot 26, marks them active and calls virtual `OnEnter` at slot 30. |
| `PlayMakerGUI.CallOnGUI` | 34351 / 31675 | `0x01141320` | Resolves the FSM active state, calls `get_Actions`, loops the array and dispatches slot 33 only when `FsmStateAction.active` at `+0x1A` is set. |

The `enabled` and `active` distinctions are confirmed by the native property accessors: `get_Enabled` reads `+0x18` (`0x01113490`), while `get_Active` reads `+0x1A` (`0x01127490`). Thus, changing the array pointer alone does not make a new action render. Calling `ActivateActions` to set up a new action also repeats the state-entry lifecycle for enabled actions; no rollback or safe in-flight detach path exists for an externally replaced array.

**Decision:** this is not a safe external registration mechanism. An instance-level array replacement is technically distinguishable from a global vtable patch, but the setter is only a raw pointer assignment. Using it would still require constructing valid IL2CPP managed objects from serialized `ActionData`, assigning the correct state/FSM owner, running lifecycle methods at the right point on Unity's thread, rooting the objects, avoiding concurrent `CallOnGUI`, and restoring the original state only after callbacks are quiescent. None of those contracts is exposed or verified for this PRX. Building or inserting a separate serialized FSM/action graph would change the integration architecture and remains outside the current authorization.

## 5. Reproduce against private files

```sh
python3 scripts/inspect_playmaker_dispatch.py \
  --module /private/il2cpp.elf \
  --metadata /private/global-metadata.dat \
  --output /private/playmaker-dispatch.json

python3 -m unittest discover -s tests -p 'test_*.py'
```

The inspector rejects different ELF or metadata hashes, changed native method pointer indices, changed virtual slots, missing call sites or unsupported disassembly. The synthetic tests contain no commercial code. Real game binary paths and disassembly dumps must remain private. **A PASS only confirms a particular static callgraph**, not title-owned callback execution or safe PRX integration.
