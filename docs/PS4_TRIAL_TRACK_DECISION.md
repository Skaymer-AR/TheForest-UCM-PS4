# Decision: fastest safe PS4 visual test vs. real in-game menu

Date: 2026-10-30. Target: CUSA12398 1.15, Unity Player 5.6.6f2.
**Only the already authorized offline research and non-invasive UI trial are in scope.**

## Three technically different tests

| Candidate | Runs on PS4? | Runs inside The Forest? | Can read physical DS4 buttons? | What is required | Decision |
| --- | --- | --- | --- | --- | --- |
| **PS4 browser-only demo** | Can be opened by the PS4 Internet Browser; actual PS4 launch still unverified | **NO** | **NO**: Sony's PS4 browser does not expose raw DS4 buttons; D-pad navigation and browser click only | Mac on same LAN with Python HTTP server; no console installation | **Prepared now**, CI-tested ES5 state model, 10 categories and 13 UI items |
| Independent PS4 homebrew application | Plausible with OpenOrbis; not built or proven here | **NO** | Potentially, by using ScePad APIs with an appropriate runtime | Standalone homebrew compilation, separate PKG/signing/install, device test | Research candidate only; **not** a solution for in-game overlay |
| Actual Unity graphical UCM inside retail title | Requires the game runtime to host new code | **YES** (target) | Potentially through existing Rewired Player and active ControllerMap | Reproducible IL2CPP/PS4 title build or independently proven game-specific integration mechanism | **Blocked** by missing build/integration path; no safe loader demonstrated |

## Why the browser demo is legitimate but limited

Sony's [Web Content Guidelines for PlayStation 4, v12.00](https://www.sie.com/content/dam/corporate/jp/guideline/PS4_Web_Content-Guidelines_e.pdf) list `Gamepad` among features unavailable to web content (page 5) and explain generic mouse/keyboard events, D-pad focus traversal and console browser Enter (Cross or Circle region dependent) (page 11). Therefore **do not** emulate the actual L1+R1 chord in JavaScript, invent hardware input IDs in the browser, or imply this screen overlays a game.

The single-file HTML demo in `prototype/ps4-browser/index.html` mirrors the C menu's **13 entry IDs in order** but all game-mutating actions are locked. The browser script never reads or writes game memory, never communicates with a PS4 system service, and makes no network request. `start-mac.command` is a local Python static-file server, not a process injector. No cryptographic payloads or proprietary title assets are bundled.

## Path toward genuine in-game functionality

Existing findings:
- Validated the current code ELF, global IL2CPP register (85,372 method targets) and Unity 5.6.6f2 Player version.
- Recovered all 30 scenes, identified `RewiredSpawner` and both input manager prefabs, recovered 24 Sony DS4 hardware element IDs and mapped 25 in-game UI InputMappingButton elements to action names.
- Built and tested a standalone C# Unity IMGUI `UltimateMenuHost` **for an independent Unity project only**.
- Showed that adding just a partial new `CodeRegistration` does not merge types with the retail game.
- Previous broad native detours froze the PS4 and remain disallowed.

The **in-game** blocking requirement is still a valid method for injecting/registering the new MonoBehaviour and creating its GameObject at the correct Unity lifecycle phase. Existing retail assets provide names and references, **not** generated AOT code, a class registration API, a full title build or a safe live callback. OpenOrbis standalone homebrew cannot add a MonoBehaviour to the commercial game's IL2CPP registration by itself.

## Engineering next gate

**No new installable PKG, global hook or PRX is justified by the browser test.**
Further offline research may evaluate game-specific native callbacks with robust relocation/teardown and game lifecycle evidence, but publishing a runtime payload, changing the title PKG or performing a live console test requires a new, explicit permission and a validated failure/rollback plan. If that proof cannot be obtained, say so; do not pretend the browser experiment is the missing integration.

## Evidence validation

Local independent smoke checks completed:
- Browser ES5 state model: locked gameplay actions, category wrapping, only UI-local hints and close commands.
- Desktop Chromium: click, keyboard navigation, open/close, reset and no console JavaScript exceptions at 1280×720, 1540×754, 1920×1080 and 740×900.
- The exact GitHub HTML file has git blob SHA `f182ee6f72270e3342b507898546e55ab4b2b530`, matching the locally packaged HTML.

These checks do **not** validate the PS4 browser, DS4 focus, in-game graphical rendering, Unity v5.6.6f2 AOT compilation or The Forest gameplay.
