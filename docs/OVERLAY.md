# Native PS4 overlay

## Implementation

The PRX now connects the existing menu core to two public PS4 paths:

- `sceVideoOutRegisterBuffers` is detoured to capture the game's registered
  framebuffer pointers and `OrbisVideoOutBufferAttribute` at runtime.
- `sceGnmSubmitAndFlipCommandBuffers` is detoured using the same signature and
  frame-boundary pattern used by GoldHEN's official `frame_logger` plugin. The
  plugin appends its own GNM draw command buffer to the game's submission,
  before the requested flip.
- The added command buffer uses GNM `DMA_DATA` fill packets and an EOP label to
  paint the UI into the selected registered display buffer. It does not call
  Unity or touch gameplay state. The label prevents reuse while the GPU still
  owns the command buffer.
- For tiled output, the adapter uses OpenGNM's GPU-address surface functions to
  select a 32-bit display mode and map coordinates. It accepts the surface only
  when the runtime format is `0x80002200`, dimensions are within the 720p–1080p
  range, and the calculated pitch equals the registered `pixelPitch`. Linear
  output uses the reported pitch directly. Unknown formats, modes, dimensions,
  and inconsistent pitches skip drawing.
- The current renderer is opaque. GNM fill packets do not alpha blend, so
  `Panel opacity` is shown as unavailable. The panel, selection, text, and
  control hints are rasterized at the registered output size from a 1280×720
  logical layout.

The ABI sources are the OpenOrbis headers for `sceGnmSubmitAndFlipCommandBuffers`,
`sceVideoOutRegisterBuffers`, `scePadReadState`, `scePadRead`, `OrbisPadData`,
and `OrbisVideoOutBufferAttribute`, plus GoldHEN's official frame logger and
Detour SDK. OpenGNM is built from pinned commit
`4b295ca54c82c83acf308d1c646a2dfa9ae57350`. Runtime targets come from linked
exports and registered buffers; no saved absolute game address is used.

## DualShock 4 input

The plugin hooks the game's `scePadReadState` and `scePadRead` calls and copies
the returned button sample after the original function returns. It does not
open a second pad handle, consume buttons, or alter the game's pad data. The
menu core receives normalized buttons at the GNM frame boundary. With the menu
closed, input is passed through unchanged.

| Input | Action |
| --- | --- |
| L1 + R1 | Open or close |
| D-pad up/down | Select an item |
| D-pad left/right | Change an available value |
| X | Confirm |
| Circle | Close / back |
| L1/R1 while open | Change category |

## Feature status

Only UI-local behavior is enabled. Gameplay entries stay locked and display
`[UNVERIFIED]`; they do not write memory or dispatch placeholder commands.

| Feature | Status |
| --- | --- |
| Menu panel, categories, selection highlight, text and hints | Implemented in PRX; pending user's PS4 visual test |
| DualShock 4 navigation | Implemented as passive read hooks; pending user's PS4 input test |
| Show/hide control hints | Available |
| Close menu | Available |
| Panel opacity | Unavailable; renderer is opaque |
| God Mode | Disabled, no implementation |
| Infinite Stamina | Disabled, no implementation |
| Hunger and Thirst | Disabled, no implementation |
| Add Inventory Item | Disabled, no implementation |
| Build without materials | Disabled, no implementation |
| Teleport | Disabled, no implementation |
| Spawn enemy/object | Disabled, no implementation |
| Time and weather | Disabled, no implementation |

## Unload and rollback

Unload restores the original function entries before releasing the GoldHEN
trampolines, waits for entered callbacks, and checks the GPU EOP label before
releasing the plugin-owned command buffer. If the GPU does not signal completion
within five seconds, its 2 MiB direct-memory block is intentionally retained so
the GPU cannot access freed memory. This timeout is logged.

To remove the plugin, unload it through GoldHEN or remove
`/data/GoldHEN/plugins/theforest_ucm.prx` from the existing
`[CUSA12398]` section of `/data/GoldHEN/plugins.ini`, then restart the console.
The plugin does not modify eboot, PKG, save files, or persistent game data.

## Validation boundary

Portable menu, input-state, draw-list, sanitizer, and PRX cross-build checks run
in GitHub Actions. The code is ready for the user's firmware 12.02 / GoldHEN
2.4B18.9 offline test, but the in-game panel and controller response are not
claimed as hardware-verified until the user confirms them. The earlier probe
load confirmation only established that the old no-hook PRX loaded safely.
