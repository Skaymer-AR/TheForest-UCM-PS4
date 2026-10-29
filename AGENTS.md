# Codex implementation instructions — TheForest-UCM-PS4

Target: **The Forest PS4 CUSA12398 v1.15**, PS4 firmware 12.02 and GoldHEN
2.4B18.9. The user confirmed the previous no-hook probe loaded and left the game
stable. They also reported that v0.5 showed its notification but left the game
black after the title screen; the PS4 shell stayed responsive.

## Current task

- Continue `feature/visual-menu-foundation` and PR #2.
- Diagnose startup hooks before attempting another renderer. The v0.6
  diagnostic must have GNM/rendering/framebuffer access fully disabled.
- Build a passive-all profile first, plus single-hook VideoOut,
  `scePadReadState`, `scePadRead` and no-hook control profiles so the user can
  isolate startup behavior on hardware.
- Call through to the original APIs with the same ABI and arguments. Verify
  GoldHEN detour state before accepting install; restore installed hooks on
  failure/unload and drain callbacks before freeing stubs.
- Keep callback work bounded and free of logging, allocation and blocking
  graphics operations. Report counters from the plugin management path.
- Do not claim the menu or graphics integration works until the user confirms
  the game passes the title screen and the display is tested on PS4.

## Restrictions

- Do not modify eboot.bin, PKG/update files, save files, game binaries, or
  unknown `DebugConsole` flags.
- Do not commit `eboot.bin`, `Il2CppUserAssemblies.prx`,
  `global-metadata.dat`, game memory dumps, or game assets.
- Do not reuse historical absolute addresses; the recorded IL2CPP base
  `0x8029C000` is historical only.
- Do not depend on the observed NULL `DebugConsole` instance.
- Keep feature status exact. God Mode, stamina, hunger/thirst, inventory, free
  building, teleport, spawning, time and weather remain unavailable until each
  has a real version-checked implementation and hardware validation.
- Prefer offline, single-player testing.

## Validation and deliverables

- Run portable tests and the PRX cross-build when changing the adapter.
- GitHub Actions must publish five diagnostic PRXs and `sha256.txt` as
  `theforest-ucm-diagnostic-prx`.
- Report test/build results separately from hardware results.
- Give exact install, profile selection, offline test and rollback steps.
