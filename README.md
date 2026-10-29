# The Forest UCM PS4

Native GoldHEN PRX overlay work for **The Forest PS4 CUSA12398 v1.15**. The
active branch is `feature/visual-menu-foundation`; PR #2 carries the visual
menu foundation and this branch adds the GNM display-buffer renderer and
passive DualShock 4 adapter. Testing is for offline, single-player sessions.

## Current implementation

- The PRX hooks the runtime VideoOut registration and GNM submit/flip APIs. It
  appends a plugin-owned GNM command buffer to the game's submission and draws
  the panel into the registered output buffer.
- It reads the game's successful `scePadReadState` / `scePadRead` results
  without consuming or changing controller input.
- Menu title: **THE FOREST — ULTIMATE CHEATMENU**. L1+R1 opens/closes; D-pad
  navigates; X confirms; Circle closes; L1/R1 changes categories.
- The renderer supports a validated 32-bit VideoOut format in linear or tiled
  mode and skips unsupported layouts. It is opaque, so panel opacity is
  unavailable.
- Gameplay rows remain disabled until each action has a real implementation
  and has been checked in game. God Mode, stamina, hunger/thirst, inventory,
  free building, teleport, spawning, time and weather are not implemented.

The old probe was confirmed by the user to load and leave the game stable. That
does not verify the new in-game image or input route. The user supplied the
target environment as PS4 firmware **12.02** and GoldHEN **2.4B18.9**; hardware
confirmation of this implementation is still pending.

## Test and build

Run the portable suite on a host with a C compiler:

```sh
SANITIZE=1 sh scripts/test.sh
```

GitHub Actions runs these tests and cross-builds the PRX with OpenOrbis, the
GoldHEN plugin template, and OpenGNM pinned to commit
`4b295ca54c82c83acf308d1c646a2dfa9ae57350`. Download the
`theforest-ucm-prx` artifact from the successful workflow run. It contains:

- `theforest_ucm.prx`
- `sha256.txt`

The SVG host preview is a development aid, not a PS4 screenshot.

## Install and test on PS4

1. Download `theforest-ucm-prx` from the successful GitHub Actions run and run
   `shasum -a 256 -c sha256.txt` in the extracted artifact folder.
2. Copy `theforest_ucm.prx` to `/data/GoldHEN/plugins/theforest_ucm.prx`.
3. In `/data/GoldHEN/plugins.ini`, replace the old probe PRX entry in the
   `[CUSA12398]` section with `/data/GoldHEN/plugins/theforest_ucm.prx`. Keep
   the existing file's syntax and other plugin entries.
4. Restart the console or reload the plugin with GoldHEN. Use The Forest
   CUSA12398 v1.15, enter an **offline single-player** game, and press **L1 +
   R1**. Use the D-pad, X, Circle, and L1/R1 to navigate.
5. Confirm whether the panel appears at 1080p, whether selection moves with the
   controller, and whether the game remains responsive while opening/closing.
   Gameplay cheat rows are intentionally disabled.

If no panel appears, leave the game state untouched and report whether the
plugin notification appeared, output resolution, and any `[TF-UCM]` lines in
the GoldHEN plugin log.

## Rollback

Unload the PRX through GoldHEN, remove its line from `[CUSA12398]` in
`/data/GoldHEN/plugins.ini`, delete
`/data/GoldHEN/plugins/theforest_ucm.prx`, and restart the console. The PRX
restores its detours when unloaded. It does not modify eboot, PKG, saves, or
persistent game state.

See [docs/OVERLAY.md](docs/OVERLAY.md) for the API path, runtime guards, feature
status, and hardware-validation boundary. Historical `DebugConsole` findings
remain in [docs/RESULTADO.md](docs/RESULTADO.md); the renderer does not depend
on them.
