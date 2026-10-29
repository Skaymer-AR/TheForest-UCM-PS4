# The Forest UCM PS4 — in-game menu work

**Target:** The Forest PS4 **CUSA12398 v1.15**, GoldHEN, offline testing.

The PRX load probe has been tested on the user's PS4. The current milestone is the first real render and controller adapter. Offline/single-player testing comes first.

## Current state

- User confirmed on PS4: the PRX displayed `The Forest: UCM probe loaded (NO HOOKS)`, The Forest entered a session, and gameplay continued without freezes or crashes. The load probe is complete and will not be repeated as the main milestone.
- Read-only pointer chain ended in a **NULL DebugConsole instance** in both the world and main menu.
- The two observed `Awake` guard values were `00`, but they were read **after** initialization; this does not prove their values at entry.
- PR #2 contains a portable menu/render model with normalized DualShock buttons. The PRX still does **not** attach that model to a game frame or PS4 renderer, so no panel appears in-game yet.
- Gameplay entries display as `[UNVERIFIED]` and cannot mutate state or dispatch commands.
- The upstream GNM flip signature and ScePad APIs have been checked. They establish available APIs, not a verified The Forest rendering backend. See [adapter findings](docs/OVERLAY.md).
- Never call `ToggleConsole` through the observed NULL instance or change unknown guard bytes.

## Local test on macOS Catalina

```sh
sh scripts/test.sh
```

The code is ordinary C99 and uses no third-party dependencies for these tests. `SANITIZE=1 sh scripts/test.sh` also runs AddressSanitizer and UndefinedBehaviorSanitizer builds. Tests generate `output/overlay-preview.svg`, a host rendering of the menu (not a console screenshot).

## Build a PRX on GitHub Actions

Every pull request runs the portable tests and OpenOrbis cross-build. On success, download `theforest-ucm-probe-prx`, containing `theforest_ucm_probe.prx` and its SHA-256 file. The current PRX includes the visual model but has no attached render/input adapter, so installing it will not show a menu yet.

The workflow uses OpenOrbis, LLVM and the official GoldHEN plugin template in Linux. The first diagnostic build succeeded in the run linked above. Updated branches and pull requests run the portable suites and build the UI core into the same probe artifact using `scripts/build-prx.sh`. The new overlay adapter is not active on PS4.

## Current PS4 test and rollback

The user has already installed and tested the load probe. The current branch
artifact has no render/input adapter, so installing it again will not show a
menu. To roll back the existing install, back up
`/data/GoldHEN/plugins.ini`, remove
`/data/GoldHEN/plugins/theforest_ucm_probe.prx` from the existing
`[CUSA12398]` section, and restart the console. Keep tests offline/single-player.

## Roadmap

1. Implement a reproducible GNM path that resolves the active output target and can detach safely.
2. Add a verified read-only DualShock sample source and connect it to the render frame.
3. Draw and test the menu on the target PS4 while keeping game actions disabled.
4. Integrate independently verified game actions one by one.

The old PRX load has already been verified on hardware. A new installation is not needed to repeat that check. The visible renderer/input bridge is still pending; the current artifact is useful for build verification only. See [OVERLAY.md](docs/OVERLAY.md).

## References

- [GoldHEN Plugins SDK](https://github.com/GoldHEN/GoldHEN_Plugins_SDK)
- [GoldHEN official plugins and templates](https://github.com/GoldHEN/GoldHEN_Plugins_Repository)
- [OpenOrbis PS4 toolchain](https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain)

Do not commit game binaries, copyrighted game assets or third-party mod payloads. The source project is separate from private game files and research data.
