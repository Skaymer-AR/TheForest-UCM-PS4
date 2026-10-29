# Codex implementation instructions — TheForest-UCM-PS4

Target: **The Forest PS4 CUSA12398 v1.15**, PS4 firmware 12.02 and GoldHEN
2.4B18.9. The user has already confirmed that the earlier no-hook probe loaded
and left a game session stable; do not make loader validation the milestone.

## Scope

- Continue the existing `feature/visual-menu-foundation` branch and PR #2.
- The current priority is a real PS4 framebuffer overlay and passive DualShock 4
  input. The UI model or host SVG preview is not evidence of an in-game menu.
- Use runtime-linked PS4 APIs and registered output buffers. Validate reported
  formats, dimensions, modes and pitches before drawing. Do not invent
  addresses, signatures, render contexts, or `DebugConsole` flags.
- Keep gameplay options disabled until an action has a version-checked,
  implemented path and has been confirmed on hardware. Do not show placeholders
  as working features.
- Preserve input when the menu is closed. Prefer offline, single-player use.
- Implement detour rollback and wait for plugin-owned GPU buffers before free.

## Restrictions

- Do not modify eboot.bin, PKG/update files, save files, or game binaries.
- Do not commit `eboot.bin`, `Il2CppUserAssemblies.prx`,
  `global-metadata.dat`, game memory dumps, or game assets.
- Do not use old absolute addresses across sessions. The recorded IL2CPP base
  `0x8029C000` is historical only.
- Do not depend on the observed NULL `DebugConsole` instance.
- Keep README installation and feature status exact. Never claim PS4 rendering
  or controls are verified until the user confirms the hardware test.

## Validation and deliverables

- Run portable tests and the PRX cross-build when changing the adapter.
- GitHub Actions must upload `theforest_ucm.prx` and `sha256.txt` as the
  `theforest-ucm-prx` artifact.
- Report exact test/build results and distinguish source/API validation from a
  test on the user's PS4.
- Give the user exact install, control, offline test and rollback steps.
