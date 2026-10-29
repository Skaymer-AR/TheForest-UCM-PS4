# In-game menu adapter status

The user confirmed that the PRX displayed `The Forest: UCM probe loaded (NO
HOOKS)`, The Forest entered a session, and gameplay remained stable. The load
probe is complete. This branch still does **not** draw or control a menu on the
PS4.

## Portable menu code

`src/overlay.c` requests a 1280x720 logical panel with the title
`THE FOREST — ULTIMATE CHEATMENU`, categories, a selection highlight, and DS4
navigation. The UI model is compiled into the PRX but remains detached because
no PS4 render/input adapter is active.

Gameplay rows show `[UNVERIFIED]`. `menu_key` permits selection but refuses to
change their values or dispatch a command. Only UI-local settings are enabled.
The UI core does no game-memory reads/writes and makes no Unity calls.

## Verified API research

- GoldHEN's official `frame_logger` plugin declares the ABI for
  `sceGnmSubmitAndFlipCommandBuffers` and hooks it as a frame boundary. That is
  a candidate timing point, not a renderer or evidence that The Forest invokes
  that exact path on the user's firmware. [Source](https://github.com/GoldHEN/GoldHEN_Plugins_Repository/blob/main/plugin_src/frame_logger/source/main.c)
- OpenOrbis declares `scePadReadState`, `scePadGetHandle`, and the `OrbisPadData`
  layout. The project does not yet read or open a controller handle. A safe
  source for one coherent DS4 sample per frame still needs to be selected.
  [API header](https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain/blob/master/include/orbis/Pad.h)
- A flip hook alone does not identify a render target or provide synchronized
  draw commands. A public PS4 renderer prototype inspected during this work
  reads private `libSceVideoOut` state using byte-pattern scans and an internal
  structure layout. Those values are not verified for the user's firmware and
  are not used here.

The next implementation step is a reproducible OpenOrbis-compatible GNM path
that resolves the active output target from documented runtime calls, draws
into a plugin-owned command buffer, preserves the game's submission and return
value, and can detach safely. No The Forest game function or `DebugConsole`
method should be called for this route. The observed `DebugConsole` instance is
NULL; do not use it. Do not reuse the old `0x8029C000` module base as an address.

## Current validation

Run `sh scripts/test.sh` for the C99 menu and overlay tests. Use
`SANITIZE=1 sh scripts/test.sh` to run AddressSanitizer and
UndefinedBehaviorSanitizer builds where supported. `output/overlay-preview.svg`
is generated from the host renderer callbacks; it is not a PS4 screenshot.

GitHub Actions cross-compiles the PRX and uploads `theforest_ucm_probe.prx` plus
its SHA-256 file. The current artifact still has no attached menu adapter, so
installing it will not display the panel. To roll back the already installed
probe, remove its line from `/data/GoldHEN/plugins.ini` and restart the console.

No game PKG, save, binary, or raw memory dump is committed. Hardware testing is
offline/single-player only. No gameplay action is available until it has a real,
version-checked implementation.
