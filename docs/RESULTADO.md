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

First establish that a non-hooking diagnostic PRX loads on the actual game. Only then study a bounded read-only hook for `Awake`, with module-base/ABI verification. A standalone DualShock 4 menu avoids depending entirely on an inactive debug console.

No original game data, binary or raw memory dump is committed.

## Build and UI development evidence

The first diagnostic PRX compiled successfully in GitHub Actions run
[40957399526](https://github.com/Skaymer-AR/TheForest-UCM-PS4/actions/runs/40957399526)
for commit `68150e5`. This does not verify loading on hardware. The new visual
menu core has a host renderer and input/lifecycle tests, with an intentionally
detached PS4 adapter. See [OVERLAY.md](OVERLAY.md) for boundaries and pending
IL2CPP integration checks. The observations above remain unchanged.
