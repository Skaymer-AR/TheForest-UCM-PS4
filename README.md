# The Forest UCM PS4

Diagnostic work for **The Forest PS4 CUSA12398 v1.15**, on PS4 firmware
12.02 and GoldHEN 2.4B18.9. The user confirmed that the earlier no-hook probe
loaded and allowed a session to run. Version v0.5 displayed its notification,
then left the game black after the title screen; the PS4 shell remained
responsive. This branch now prepares a v0.6 diagnostic PRX to isolate the
startup hooks.

## v0.6 diagnostic build

The diagnostic PRX has no GNM hook or GNM library dependency. Rendering,
framebuffer access/writes, Unity calls, game-state changes, and cheat actions
are compiled out. It installs only the profile's pass-through observers and
records bounded counters and the latest API sample with atomics. It does not
print from a game or graphics callback.

The first profile to try is `theforest_ucm_passive_all.prx`: GNM is disabled;
VideoOut, `scePadReadState`, and `scePadRead` are observed. The artifact also
contains single-hook profiles and a no-hook control:

| PRX | Hooks active |
| --- | --- |
| `theforest_ucm_passive_all.prx` | VideoOut, PadReadState, PadRead |
| `theforest_ucm_videoout_only.prx` | VideoOut |
| `theforest_ucm_pad_read_state_only.prx` | PadReadState |
| `theforest_ucm_pad_read_only.prx` | PadRead |
| `theforest_ucm_no_hooks.prx` | None |

All five have **GNM=OFF, rendering=OFF, framebuffer writes=OFF**. No menu is
expected to appear in this diagnostic build. The single-hook profiles let the
hardware test distinguish VideoOut from each ScePad hook if the first profile
still causes a black screen.

## Build and artifact

GitHub Actions runs the portable C tests, cross-compiles each profile with the
OpenOrbis 0.5.4 toolchain and pinned GoldHEN SDK/template, and uploads the
`theforest-ucm-diagnostic-prx` artifact. It contains the five PRXs and
`sha256.txt`. Use the artifact from the latest successful Actions run on PR
#2. The host SVG preview is not a PS4 screenshot.

## Install and test on PS4

1. Download and extract `theforest-ucm-diagnostic-prx`; verify it from that
   directory with `shasum -a 256 -c sha256.txt`.
2. Unload the v0.5 plugin in GoldHEN if it is still loaded. In
   `/data/GoldHEN/plugins.ini`, replace its `[CUSA12398]` entry so it points to
   exactly one diagnostic PRX at a time.
3. Copy `theforest_ucm_passive_all.prx` to
   `/data/GoldHEN/plugins/theforest_ucm_diag.prx`, and set the plugin entry to
   `/data/GoldHEN/plugins/theforest_ucm_diag.prx`. Preserve the existing file
   syntax and other plugin entries.
4. Start The Forest CUSA12398 v1.15 in **offline single-player** and note
   whether it passes the title screen. This profile should show the
   notification `The Forest: UCM diagnostic (GNM/render OFF)`; it will not
   draw a menu.
5. If it still turns black, close the game and test `videoout_only`,
   `pad_read_state_only`, and `pad_read_only`, one PRX per launch. Test
   `no_hooks` as the control if needed. Do not load more than one profile at a
   time. Unload the plugin through GoldHEN before replacing its file.
6. After each run, unload the PRX and save the `[TF-UCM-DIAG]` lines from the
   GoldHEN log. The load line lists the exact active hooks; the unload line
   reports how many times each observer ran and the last result/sample.

The black-screen regression is not considered resolved until the user
confirms in hardware that the relevant profile passes the title screen. This
diagnostic does not claim the game overlay or controller navigation works.

## Rollback

Unload the PRX through GoldHEN, remove its line from `[CUSA12398]` in
`/data/GoldHEN/plugins.ini`, delete `/data/GoldHEN/plugins/theforest_ucm_diag.prx`,
and restart the console. Each profile restores its installed detours during
unload. No PKG, eboot, save, persistent game data, or unknown console flags
are modified.

See [docs/OVERLAY.md](docs/OVERLAY.md) for the API and detour checks, and
[docs/RESULTADO.md](docs/RESULTADO.md) for prior `DebugConsole` observations
and the v0.5 regression report.
