# Codex instructions — The Forest UCM PS4 (SAFETY HOLD)

Target: **The Forest CUSA12398 v1.15**, PS4 GoldHEN.

## CRITICAL 2026-10-29 hardware incident

- v0.5 native GNM overlay PRX: black screen after splash, PS4 shell still
  responsive.
- v0.6 `passive_all` PRX: **full console lockup**. The game could not close
  and Rest Mode attempt also hung. This is worse than a normal game crash.
- Earlier v0.3 NO-HOOK probe: normal gameplay and notification confirmed.

**STOP** requesting any additional user hardware tests involving old v0.5/v0.6
inline API detours. See issue #4 and README.md.

## Required engineering approach

- Start from this v0.7 no-hook hotfix. It compiles a single no-hook baseline.
- Audit the upstream GoldHEN Detour implementation:
  `Detour_DetourFunction64` copies x86-64 instructions to a stub without
  general RIP-relative relocation handling. Validate ABI and code
  relocation before reusing any hook.
- Resolve the v0.6 unbounded `wait_for_original` spin and unbounded
  `ps4_backend_stop` callback-drain design. Simply adding a timeout while
  freeing an active trampoline is unsafe. No blocking waits on graphics,
  input or plugin teardown thread.
- Investigate an alternative overlay route that does NOT patch the
  entrypoints of shared system libraries; establish safe startup and teardown
  behavior, and prove it through offline tests before requesting hardware.
- Do not change PKG, save files, unknown IL2CPP flags, or make calls using
  the observed NULL DebugConsole instance.
- No copyrighted game executable, metadata or assets in this repo.
- `src/menu.*`, `src/overlay.*`, `src/drawlist.*` are host-only menu
  logic/prototypes, **not** working in-game drawing.
- Status reporting must separate **CI builds** from **verified hardware**.

## Next deliverable

A documented fault tree / root-cause investigation and a redesigned
render/input integration, with demonstrable bounds, safe unload, and
tests of the error paths. Keep any future invasive experiment behind a
compile-time opt-in; do not publish default artifacts that hook game
or system libraries.
