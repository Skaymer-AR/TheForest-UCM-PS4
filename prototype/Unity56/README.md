# Unity 5.6 AOT host — offline prototype only

**This is source for a separate Unity test project, NOT an installable PS4 mod.**
It is intentionally absent from the retail IL2CPP `CodeRegistration` and from
`global-metadata.dat`. It is NOT linked to any GoldHEN plugin or PKG.

## What this prototype demonstrates

- `UltimateMenuHost` uses `RuntimeInitializeOnLoadMethod(AfterSceneLoad)`
  to create a single, persistent `GameObject` and add a `MonoBehaviour`.
- `Update` consumes a **logical** controller snapshot from
  `UcmInputRegistry.Source`; `OnGUI` draws a basic Unity IMGUI menu.
- `UcmMenuModel` mirrors the 13 menu entries from `src/overlay.c` in the
  same order and the existing logical masks from `src/overlay.h`.
- L1+R1 opens/closes, L1/R1 changes categories, D-pad navigates, Cross
  confirms **only** the local hints toggle and close, Circle closes.
- Gameplay-changing menu items remain **locked**. They do not call any game
  code, patch addresses, or dispatch commands. The prototype should not
  be used to control gameplay in PS4.
- A neutral input sample is required before the first action and after
  controller disconnect. Input is never consumed from Rewired/the game.

## Running in a separate editor

The Unity **Player** version **5.6.6f2** is confirmed from the game's
serialized assets. A compatible PS4 **Editor/SDK/toolchain and original project**
are still unavailable here. In a compatible *separate* Unity Editor project,
copy the C# files under `Assets/UCM/`. The editor-only keyboard adapter uses:

- `Q+E`: L1+R1 menu chord; `Q`/`E`: previous/next category
- Arrow keys: navigation; `Return`: Cross; `Escape`: Circle

These keys do **not** represent the real PS4 Rewired action IDs or
controller ownership. Without the editor define, the host has no input
source, closes the menu safely and performs no game actions.

## Offline validation

```sh
sh scripts/test_unity_prototype.sh
python3 -m unittest tests.test_unity_proto_alignment
```

The CI job compiles both the regular and `UNITY_EDITOR` variants with Mono's
C# 4 compiler using **synthetic UnityEngine stubs**, and executes the menu
state-machine and guarded Sony DS4 hardware-input tests. This checks C# syntax and pure model behavior, **not**
actual Unity 5.6 API binary compatibility, PS4 IL2CPP output or rendering.

## Remaining build blockers

1. The Unity Player 5.6.6f2 version is confirmed; obtain a matching,
   authorized Unity/PS4 Editor + build toolchain and a rebuildable title project.
2. Generate and link a compatible AOT host and registration tables.
3. Prove `UltimateMenuHost` appears in CodeRegistration and metadata and
   is bootstrapped by the title.
4. The asset profile's 24 Sony DS4 hardware element IDs and both Rewired
   action catalogs are documented. Still missing: the actual assigned Player,
   runtime ControllerMap and focus policy. `UcmDs4HardwareInput.cs` is a
   fail-closed, unit-tested input boundary; it has **no actual Rewired
   runtime snapshot provider**. See
   [`docs/SONY_DS4_HARDWARE_ELEMENTS.md`](../../docs/SONY_DS4_HARDWARE_ELEMENTS.md).
5. Bridge the original C menu/draw functions via a proven static C ABI or
   port the renderer after separately validating correctness. The C# model
   is a **behavioral mirror**, not yet native binary integration.
6. Any test on PS4 or modification/repacking of a PKG requires **fresh,
   explicit authorization** after the offline build gates are met.
