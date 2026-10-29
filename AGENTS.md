# Codex implementation instructions — TheForest-UCM-PS4

Target: **The Forest on PS4 CUSA12398, update v1.15**, GoldHEN. Local user hardware is an Intel Mac running **macOS Catalina 10.15.7**; do not assume Windows or modern macOS tooling.

## Scope and priorities

- Build and validate a **game-specific GoldHEN PRX**, with game title/update validation, and start with a **no-hook, no-memory-write** smoke test.
- A working notification does **not** mean the Ultimate Cheatmenu is implemented.
- Next: read-only instrumentation of `TheForest.DebugConsole.Awake` at invocation (observe guards and registration) with bounded logs, safe exit/unload, and confirmed ASLR module base.
- Then implement an **in-game controller-friendly menu** and only wire verified actions. The 10 categories in `src/menu.h` are a UI prototype, not proof of gameplay functionality.
- Do **not** modify the game PKG/update/saves or embed game binaries. Never commit uploaded `eboot.bin`, `Il2CppUserAssemblies.prx`, `global-metadata.dat`, full memory dumps or third-party game assets.
- Avoid hard-coded absolute runtime addresses across sessions; validate module base and signed binaries before any hook.
- A `NULL` `DebugConsole` instance has been observed; do not call its methods on that NULL pointer. The guard values were captured *after* Awake and must not be treated as confirmed values at invocation.
- Implement and run tests, report PRX build outcome truthfully. Do not claim PS4 hardware behavior without user's confirmation.
- GitHub Actions uses the official GoldHEN plugin template plus OpenOrbis on Linux. If the first CI build fails, debug the exact job logs, fix the workflow, and re-run.
- Keep README status and installation instructions accurate. Offline/single-player testing first.

## Known observations

Read `docs/RESULTADO.md` for exact 1.15 addresses/offsets and limitations. The observed in-session IL2CPP base was `0x8029C000`; **this is not a universal fixed address**.

## Deliverables

- Reproducible CI that builds `theforest_ucm_probe.prx`.
- Separate tests for the platform-independent menu state machine.
- A clearly documented rollback path.
- An incremental plan to convert the smoke test into a real Unity/IL2CPP overlay and controller menu, not a rebranding of GoldHEN cheats.
