# Overlay status — critical safety hold

**Do not load the original v0.5 or any hook-enabled v0.6 PRX on PS4.**

The user confirmed a full console lockup on October 29, 2026 using
`theforest_ucm_passive_all.prx` from v0.6. Earlier v0.5 showed a black
screen after startup but kept the shell responsive. See
[Critical Incident #4](https://github.com/Skaymer-AR/TheForest-UCM-PS4/issues/4).

## Source findings (not yet definitive causation)

- v0.6 `wait_for_original()` used an unbounded spin waiting for a
  trampoline pointer; in an unsuccessful publication race this never returns.
- v0.6 `ps4_backend_stop()` waited without deadline for callback count to
  reach zero, potentially blocking teardown and game closure.
- The upstream GoldHEN SDK `Detour_DetourFunction64()` copies prologue
  instructions into a stub. Its code does not implement a general relocation
  pass for RIP-relative instructions; concurrent rewriting of system APIs is
  a further risk.
- The exact function/phase causing the lockup cannot be established without
  logs, traces and careful offline binary/disassembly validation.

## Mitigation in source v0.7

- Removed all detours from compiled backend. `source/ps4_backend.c` is a
  pure no-op interface and explicitly rejects the old nonzero hooks profiles.
- Only the `no_hooks` baseline is built. Artifact:
  `theforest-ucm-safe-baseline-only`.
- No GNM, VideoOut, ScePad hook, framebuffer access, overlays, or game writes.
- The menu/overlay state machine and host tests are preserved separately.

This is a **build safety mitigation**, not an implementation of the menu.
Do not claim rendering or input is verified. Reintroducing in-process
interception requires a review of memory protection, relocation, concurrent
installation and teardown safety with nonblocking callbacks.

## Next implementation milestone

Codex should design a rendering/input path that avoids patching shared
system API code at startup, establish a tested lifecycle, and separate an
observable non-hook smoke test from any experimental hooks. No further PS4
trials are requested until this review is complete and the user explicitly
agrees to a new narrowly scoped test.
