# The Forest UCM PS4

## Current status: safety review, no hooks

The user removed the experimental PRX and confirmed that The Forest CUSA12398 v1.15 launches normally again. Earlier results remain: v0.5 left the game black while the PS4 shell remained responsive; v0.6 passive_all caused a full console lockup.

Do not install or recommend historical v0.5/v0.6 PRXs or their hook-enabled profiles. Passing CI did not make them safe. The hardware incident and no-hook recovery are tracked in [Issue #4](https://github.com/Skaymer-AR/TheForest-UCM-PS4/issues/4).

This branch keeps the active PS4 backend hook-free. The no-hook PRX checks the title ID with sceKernelGetAppInfo and shows a notification; it does not validate v1.15, display the menu, read the controller, render, or modify gameplay. It is not an in-game menu build and has not been asked for a new PS4 trial.

## Architecture work in this branch

- The menu categories, normalized DualShock navigation, overlay state machine, and draw-list renderer remain in src/ and are exercised on the host.
- The v0.5 PS4 render/input backend and v0.6 diagnostic detours are preserved as source-only quarantines under archive/; the PRX build does not compile them.
- src/bridge_lifecycle.c is a host-only model for bounded callback leases, detach outcomes, and fail-closed resource retention. It is not linked into the PRX and does not claim that GoldHEN supplies a safe unload barrier.
- docs/SAFE_OVERLAY_DESIGN.md records the source audit, ABI notes, risk matrix, alternatives, lifecycle contract, tests, and unresolved integration questions.

The exact instruction/thread that caused the v0.5/v0.6 symptoms is not known. The GoldHEN trampoline copies instructions without general relative-address relocation and exposes the patched entry before v0.6 publishes the call-through pointer. Both versions also lack a trustworthy platform quiescence barrier for teardown. These are evidenced hazards, not a proven root cause.

## Host checks

Run the portable tests:

    python3 scripts/assert-safe-build.py
    sh scripts/test.sh

Run UI and lifecycle tests with AddressSanitizer and UndefinedBehaviorSanitizer:

    SANITIZE=1 sh scripts/test.sh

GitHub Actions builds and uploads only one PRX artifact: the no-hook baseline, named theforest-ucm-safe-baseline-only. It also uploads a separate host UI preview. It does not publish an enabled-hook PRX. A CI artifact is not evidence that a menu is visible or that a hook is safe on PS4.

Target context: The Forest CUSA12398 v1.15, PS4 firmware 12.02, GoldHEN 2.4B18.9. No PKG, save data, unknown flags, or hard-coded runtime addresses are modified.
