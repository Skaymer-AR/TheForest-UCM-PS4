# PlayMaker built-in GUI actions — The Forest PS4 1.15

**Read-only findings:** recovered from exact SHA-matched Unity 5.6.6f2 IL2CPP ELF, metadata v23, and `level2` scene. No PKG/PRX was changed.

- Native `GUIBox.OnGUI`: link VA `0x02383880`.
- Native `GUILabel.OnGUI`: `0x02384A20`.
- Native `GUIButton.OnGUI`: `0x02383D30`.
- Native `GUILayoutButton.OnGUI`: `0x02386870`.
- Native `GUILayoutToggle.OnGUI`: `0x02389640`.
- Native `GUILayoutLabel.OnGUI`: `0x02388790`.
- All these existing action classes have `FsmStateAction.OnGUI` virtual slot **33**, so they are compiled AOT for this title.
- `GUIButton.OnGUI` has a direct call to `UnityEngine.GUI.Button` at `0x019BE750` and a conditional direct call to `Fsm.Event` at `0x011172B0`.
- `GUILayoutButton.OnGUI` has calls to `UnityEngine.GUILayout.Button` at `0x019CF470` and `Fsm.Event` at `0x011172B0`.
- Fields for `GUIButton`: `sendEvent` offset `0xA8`, `storeButtonState` offset `0xB0`. For `GUILayoutButton`: `sendEvent` `0x50`, `storeButtonState` `0x58`, `text` `0x68`, `style` `0x78`.

## Scene reality

`level2` contains **two** serialized `PlayMakerFSM` components, IDs `223934` and `223935`, both attached to the `CutSceneController` GameObject (ID `40654`). Their serialized action type names represent camera fades, waits, events and cutscene logic, **not a ready-to-use graphical cheat menu**. `PlayMakerGUI` itself is a different enabled GameObject (ID `42421`).

This creates a useful alternative research direction: an asset-owned FSM made from **already AOT-compiled graphical actions** could theoretically be built without adding a managed IL2CPP class. It is **not yet a proven playable design**. The live input/focus path, action-data serialization format, scene persistence, and a way to include the new FSM are unresolved.

**Authorization boundary:** The user has not authorized modifying or repacking The Forest's retail PKG, installing a graphical PRX or applying live hooks. Continue only read-only analysis and synthetic/offline tests. Do not modify `CutSceneController`'s two gameplay FSMs as a shortcut; that risks damaging scripted sequences.

**Important:** an asset-only approach is a **different architecture** from the original AOT/PRX plan and would require explicit user authorization before changing game files. It may eliminate the unsafe native callback hook requirement, but does not by itself solve packaging and DS4 navigation.
