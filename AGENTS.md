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

## Required engineering approach

- Default CI may build only the no-hook PRX baseline. Do not add a hook-enabled
  artifact or a profile that can be installed by default.
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
- src/bridge_lifecycle.* is host-test-only and must not be included in the
  PRX build. The archived unsafe backends are for source review only.
- Do not modify the PKG, save files, unknown game flags, or commit game
  binaries/assets. Do not claim CI is hardware verification.

## Verification

Run python3 scripts/assert-safe-build.py and SANITIZE=1 sh scripts/test.sh.
The tests simulate lifecycle errors and concurrency; they do not prove the
PS4/GoldHEN platform supplies the quiescence primitive required for safe
unload.
