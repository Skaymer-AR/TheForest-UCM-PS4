# Overlay status

**Safety hold: no active PS4 hooks or in-game rendering.**

The user reports that removing the experimental PRX restored normal startup. v0.5 produced a black game screen; v0.6 passive_all caused a full console lockup. Do not install or recommend any v0.5/v0.6 hook-enabled artifact.

The menu state machine, categories, normalized controller actions, overlay rendering interface, and draw-list generator remain in the repository. They are host-side components only. The currently built PRX uses sceKernelGetAppInfo to check the title ID, then shows a no-hook notification; it does not validate the game version, render, or read the DualShock 4.

The earlier PS4 backend is retained under archive/unsafe-v0.5 and archive/unsafe-v0.6 for source review only. The build uses only source/plugin_main.c and the no-op source/ps4_backend.c. scripts/assert-safe-build.py checks that boundary.

The host lifecycle model in src/bridge_lifecycle.* exercises bounded callback entry, restoration failure, active leases, stale leases, and explicit quiescence requirements. Passing those tests does not prove that GoldHEN, Unity, or the PS4 loader provides the required runtime callback/unload guarantees.

See [SAFE_OVERLAY_DESIGN.md](SAFE_OVERLAY_DESIGN.md) for the trampoline/ABI audit, root-cause assessment, alternative integration paths, test matrix, and remaining research questions. No PS4 trial is requested.
