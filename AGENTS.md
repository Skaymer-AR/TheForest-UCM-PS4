# Codex instructions — The Forest UCM PS4 (SAFETY HOLD)

Target: The Forest CUSA12398 v1.15, PS4 GoldHEN. User environment: firmware
12.02 and GoldHEN 2.4B18.9.

## Confirmed hardware history

- v0.3 no-hook probe loaded and allowed normal gameplay.
- v0.5 GNM/VideoOut/Pad prototype left the game black while the shell stayed
  responsive.
- v0.6 passive_all detours caused a full PS4 lockup.
- The user removed the experimental PRX and confirmed The Forest starts
  normally again.

Do not request or recommend another PS4 test during the current architecture
review. Do not install or publish hook-enabled v0.5/v0.6 PRXs.

## Primary current task (actual in-game menu, not a demo)

The user wants a **real graphical Ultimate Mod Menu in The Forest on PS4**.
See [`docs/CODEX_ACTUAL_INGAME_PRX_HANDOFF.md`](docs/CODEX_ACTUAL_INGAME_PRX_HANDOFF.md)
and [`docs/INGAME_PRX_HOST_GATE_20261030.md`](docs/INGAME_PRX_HOST_GATE_20261030.md)
for the latest scene-native `PlayMakerGUI.OnGUI` candidate, file hashes, safety
gates and actual required deliverable. Continue authorized offline work
autonomously; do not stop after each file to ask for confirmation. Avoid
browser demos, standalone-only mockups, notification-only PRXs and GoldHEN
cheat alternatives. Never claim a runnable in-game menu before its callback,
ABI, teardown and platform-build requirements are verified. The PS4 hardware
test and live hook installation remain subject to an explicit approval gate.

## New offline proof: PlayMaker action vtable

Read [`docs/PLAYMAKER_VIRTUAL_DISPATCH_20261030.md`](docs/PLAYMAKER_VIRTUAL_DISPATCH_20261030.md).
The real `PlayMakerGUI.OnGUI` calls `CallOnGUI` twice; the method traverses
existing PlayMaker actions, and the indirect call `*0x320(%rax)` matches
`FsmStateAction.OnGUI` virtual slot 33. Slot 30 (OnEnter, `*0x2f0`)
and slot 32 (OnUpdate, `*0x310`) provide independent corroboration.
**This is NOT a safe external callback registration API or permission to
patch global class vtables.** Investigate ownership and lifecycle before
suggesting any PRX/injection architecture. Avoid re-running unrelated
DebugConsole or web demo work.

## Required engineering approach

- This integration-research branch runs offline checks only. Do not build or
  publish another notification-only PRX here. Any future hook-enabled PRX is
  prohibited until the callback and teardown contract are independently proven.
- The current GoldHEN Detour SDK copies x64 instructions without general
  RIP-relative relocation, patches executable code without thread quiescence,
  and exposes the patched entry before v0.6 publishes its original-call
  pointer. See docs/SAFE_OVERLAY_DESIGN.md; distinguish evidence from
  hypotheses.
- No timeout followed by freeing a possibly active trampoline. Restore
  failure, missing quiescence proof, or active leases must retain resources.
  Do not use blocking waits on render, input, or teardown paths.
- Investigate a documented Unity or GoldHEN render callback that avoids
  patching shared system API entrypoints. Do not use the observed NULL
  DebugConsole instance or invent addresses/IL2CPP flags.
- Keep src/menu.*, src/overlay.*, and src/drawlist.* unchanged unless the user
  asks for UI work. They are host-side menu and renderer logic, not a working
  in-game overlay.
- Keep src/unity_host_adapter.* and src/pad_input_map.* host-only. They define
  and test an adapter boundary but do not implement a Unity or ScePad provider.
- Keep original game binaries, metadata, and generated decompiler output
  outside the repository. The offline analyzer must never upload those files.
- **Authorization update (2026-10-31):** the owner explicitly authorized
  modifying and rebuilding private working copies of the original CUSA12398
  1.15 PKG and Unity assets for offline analysis. This does not authorize
  installing a package, running hooks, writing console memory, or publishing
  game binaries/assets. Preserve the original source and keep every generated
  package and commercial asset outside GitHub.
- src/bridge_lifecycle.* is host-test-only and must not be included in the
  PRX build. The archived unsafe backends are for source review only.
- Do not modify save files or unknown game flags, install packages, or commit
  game binaries/assets. Do not claim CI is hardware verification.

## Verification

Run python3 scripts/assert-safe-build.py and SANITIZE=1 sh scripts/test.sh.
The tests simulate lifecycle errors and concurrency; they do not prove the
PS4/GoldHEN platform supplies the quiescence primitive required for safe
unload or an in-game Unity callback.

## Alternate implementation evidence

The original IL2CPP metadata contains precompiled GUIBox, GUIButton, GUILabel, GUILayoutButton and GUILayoutToggle actions. The evidence and serialization limitations are recorded in docs/PLAYMAKER_PRECOMPILED_GUI_EVIDENCE.md and docs/PLAYMAKER_ACTIONDATA_LAYOUT.json. An isolated PlayMaker FSM may provide an in-game graphical host without a new AOT class, but its actual Unity serialization, lifecycle and controller support remain unverified. Existing CutSceneController FSM components must remain untouched. The owner has authorized private offline scene/PKG copies; do not create an installable candidate until the serialized object, dependencies and package audit gates pass. Continue safe offline research and tests autonomously.
