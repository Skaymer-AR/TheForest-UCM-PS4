# The Forest UCM PS4

## CRITICAL HARDWARE REGRESSION — v0.5 and v0.6 are quarantined

On October 29, 2026, the user confirmed a **full PS4 lockup** after installing
v0.6 `theforest_ucm_passive_all.prx`, with VideoOut and Pad API inline detours
enabled. The game could not close, and the system became unresponsive when trying
Rest Mode. The previous v0.5 GNM overlay had left the game on a black screen
while the PS4 shell stayed responsive.

**DO NOT INSTALL OR RECOMMEND** v0.5 `theforest_ucm.prx` or any of the four
v0.6 profiles using inline hooks: `passive_all`, `videoout_only`,
`pad_read_state_only`, or `pad_read_only`. A passing CI build does not make
these safe on PS4.

**Immediate rollback on the user's console:** after restarting, remove all
experimental UCM lines from the existing `[CUSA12398]` section of
`/data/GoldHEN/plugins.ini`. Restore the previous backup of that INI if
necessary. Restart once more before launching The Forest. Leave all game PKG,
updates and saves unchanged. The earlier v0.3 no-hook `theforest_ucm_probe.prx`
was physically demonstrated to load successfully; it is an optional known-good
reference, not required for playing normally.

**Issue:** [#4 — Critical PS4 lockup](https://github.com/Skaymer-AR/TheForest-UCM-PS4/issues/4).
**Project context:** [#3 — visual overlay](https://github.com/Skaymer-AR/TheForest-UCM-PS4/issues/3).

## v0.7 fail-closed source hotfix

The previous inline detours and their unbounded waits have been **removed from
the active compiled backend**. Unsafe code remains recoverable from Git history
for offline analysis; it is not built into the new artifact. The current
`source/ps4_backend.c` is a no-op, with a compile-time error if any former
hook-enabled profile is requested.

GitHub Actions now builds **one no-hook baseline**:
`theforest_ucm_safe_baseline.prx` in artifact
`theforest-ucm-safe-baseline-only`. It only loads and prints a notification.
It does **not** display a menu, monitor input or change gameplay. It is an
engineering fallback, **not a proven hardware fix** and no further PS4 trial is
needed until the architecture is reviewed.

## Investigation

Source review identified:
1. `wait_for_original` in v0.6 could spin **forever** on an unset trampoline.
2. `ps4_backend_stop` could wait **forever** for an active callback during
   unload, matching the reported inability to close the game.
3. The GoldHEN SDK's trampoline copies machine instructions. For arbitrary
   system library entries, RIP-relative instructions and concurrent patching
   may cause invalid control flow. This is a plausible risk, **not a confirmed
   root cause**.

A timer alone would not safely fix these paths; releasing trampolines while
threads are still executing them is also dangerous. Avoid intercepting shared
system libraries inline until a formally validated lifecycle and
relocation-safe strategy exists. Prefer an alternative overlay architecture
that does not patch system API entrypoints. Test offline with static analysis,
host simulations and CI before suggesting new PS4 experiments.

## Host test and CI

```sh
python3 scripts/assert-safe-build.py
sh scripts/test.sh
```

The portable overlay/menu code remains host-testable, but it is **not** wired
to a game renderer or real DS4 input in v0.7.

Target game: **The Forest PS4 CUSA12398 v1.15**, offline only.
Firmware from prior session: **12.02**, GoldHEN **2.4B18.9**.
