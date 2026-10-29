# The Forest UCM PS4 — research and build

**Target:** The Forest PS4 **CUSA12398 v1.15**, GoldHEN, offline testing.

The first milestone is a **GoldHEN PRX load probe**, not a finished menu. Its purpose is to verify that a game-specific plugin loads and shows a notification. It installs **no hooks**, writes **no game RAM**, invokes **no Unity functions**, and changes **no PKG or saves**.

## Current state

- Verified on user's PS4: `Il2CppUserAssemblies.prx` was readable, and the code bytes at `DebugConsole.ToggleConsole` and `DebugConsole.OnGUI` matched the offline analysis.
- Read-only pointer chain ended in a **NULL DebugConsole instance** in both the world and main menu.
- The two observed `Awake` guard values were `00`, but they were read **after** initialization; this does not prove their values at entry.
- Portable menu navigation core passes a local C99 test.
- **PRX build and real-console plugin loading remain unverified.** Never call `ToggleConsole` on NULL or flip unknown guard bytes blindly.

## Local test on macOS Catalina

```sh
clang -std=c99 -Wall -Wextra -Werror -Isrc src/menu.c tests/test_menu.c -o /tmp/theforest_menu_tests
/tmp/theforest_menu_tests
```

The code is ordinary C99 and uses no third-party dependencies for these tests.

## Build a PRX on GitHub Actions

Open **Actions** → **Test and build The Forest PS4 diagnostic PRX** → **Run workflow** on `main`. A push to code/workflow files also triggers the build. On success, download the artifact named `theforest-ucm-probe-prx`. It is expected to contain `theforest_ucm_probe.prx`.

The workflow uses OpenOrbis, LLVM and the official GoldHEN plugin template in Linux. The end-to-end build has not yet been verified; if it fails, inspect the specific GitHub Actions step.

## Install the probe on your PS4 (only after successful build)

1. Back up `/data/GoldHEN/plugins.ini` with FTP.
2. Copy the built `theforest_ucm_probe.prx` to `/data/GoldHEN/plugins/`.
3. Under the **existing** `[CUSA12398]` section in `plugins.ini`, append:
   `/data/GoldHEN/plugins/theforest_ucm_probe.prx`
4. Ensure GoldHEN plugin loading is enabled. Launch The Forest **offline**.
5. Look for the single startup notification. If the game does not load, remove the added INI line and restart; keep the original INI backup.

Do not install another experimental plugin simultaneously.

## Roadmap

1. Verify safe PRX loading (no hooks).
2. Instrument `DebugConsole.Awake` **read-only** at invocation time, after validating module base and method ABI.
3. Add an in-game overlay and DualShock 4 navigation.
4. Integrate independently verified game actions one by one.

## References

- [GoldHEN Plugins SDK](https://github.com/GoldHEN/GoldHEN_Plugins_SDK)
- [GoldHEN official plugins and templates](https://github.com/GoldHEN/GoldHEN_Plugins_Repository)
- [OpenOrbis PS4 toolchain](https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain)

Do not commit game binaries, copyrighted game assets or third-party mod payloads. The source project is separate from private game files and research data.
