# The Forest PS4 CUSA12398 v1.15 — DebugConsole findings

## Reproduced console observations

- IL2CPP module base during this session: `0x8029C000`.
- `DebugConsole.ToggleConsole` address `0x808676D0`: first 16 bytes matched offline.
- `DebugConsole.OnGUI` address `0x8085F7B0`: first 16 bytes matched offline.
- Static `DebugConsole` instance pointer `0x20949AD90` was `0x0` in both the game world and the main menu.
- `Awake` guard A at `0x2058BE721` read `00` after initialization.
- `Awake` guard B at `0x201A4F3F0` read `00` after initialization.

## Disassembly interpretation to validate further

- `Awake` RVA: `0x005C1C30`.
- At RVA `0x005C1C99`, `cmp byte ptr [rax+1], 0`; guard A=0 follows a branch to `0x005C1D2B`.
- At RVA `0x005C1E13`, `cmp byte ptr [rax+0x10],0`; guard B=0 follows the branch to `0x005C1CA3`.
- This branch exits without assigning a registered instance **if** those byte values were present during `Awake`.
- We read the guards **after** startup, so the observations do not prove their values at invocation.
- The semantic meaning of the guards remains unknown.

## Development choice

Do not change guard B or call `ToggleConsole` when the instance pointer is NULL.

The user confirmed that the non-hooking probe loads, The Forest enters a session,
and gameplay continues without freezes or crashes. The load milestone is complete.
The current task is diagnosing v0.5's startup hooks; no invocation hook or guard
patch is needed for that work.

No original game data, binary or raw memory dump is committed.

## Build and UI development evidence

The first diagnostic PRX compiled successfully in GitHub Actions run
[40957399526](https://github.com/Skaymer-AR/TheForest-UCM-PS4/actions/runs/40957399526)
for commit `68150e5`. This does not verify loading on hardware. The new visual
menu core has a host renderer and input/lifecycle tests, with an intentionally
detached PS4 adapter. See [OVERLAY.md](OVERLAY.md) for boundaries and pending
render/input integration. The observations above remain unchanged.

## PS4 load confirmation (2026-10-29)

The user confirmed that the PRX displayed `The Forest: UCM probe loaded (NO
HOOKS)` on their PS4, then The Forest entered a session and remained playable
without freezes or crashes. This confirms the probe load and basic game
stability only; it does not confirm that the menu is drawn or controlled by the
DualShock 4.

## v0.5 black-screen regression report (2026-10-29)

On v0.5 the notification appeared, but after the title screen the game stayed
black. The PS4 shell remained responsive; PS4Debug still saw `eboot.bin` and
memory maps, and the game could be closed normally. This is a game startup/render
regression, not a whole-console freeze. The earlier no-hook probe remained
playable.

Source review found that v0.5 installed the GNM submit/flip detour during
`plugin_load`, even while its menu was hidden, allocated a direct-memory command
buffer during load, and could append GPU work to the game's frame submission.
This is the first path being removed, but source review alone cannot confirm it
caused the black screen.

## v0.6 startup-hook diagnostic (2026-10-29)

The diagnostic build removes all GNM code/imports, rendering, framebuffer
access/writes, Unity calls and gameplay changes. Its first profile leaves
VideoOut, `scePadReadState` and `scePadRead` as passive observers. Additional
profiles enable each hook individually and provide a no-hook control. Callback
logs are replaced with atomic counters; the plugin logs the profile and
summary only from load/unload handling.

Portable tests and the v0.6 PRX profiles passed in GitHub Actions run
[40971740647](https://github.com/Skaymer-AR/TheForest-UCM-PS4/actions/runs/40971740647);
the `theforest-ucm-diagnostic-prx` artifact is available from that run. The
user's hardware tests are still pending, so the black-screen regression is
unresolved until a profile passes the title screen on PS4. No rendering or
controller integration is claimed functional. See [OVERLAY.md](OVERLAY.md) for
the profiles, ABI references, and exact feature boundary.
