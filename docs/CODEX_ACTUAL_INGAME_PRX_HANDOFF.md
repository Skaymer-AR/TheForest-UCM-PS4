# Codex / ChatGPT Work handoff — build an actual **in-game PS4 PRX**, not a demo

**Repository:** `Skaymer-AR/TheForest-UCM-PS4`  
**Working branch:** `feature/visual-menu-foundation`  
**PR:** [#2](https://github.com/Skaymer-AR/TheForest-UCM-PS4/pull/2)  
**Title:** The Forest, **CUSA12398**, update **1.15**, Unity **5.6.6f2** / IL2CPP v23, PS4 GoldHEN.  
**Primary goal:** render and navigate **our graphical UCM while The Forest is running on a PS4**, using DualShock 4. The desired first hardware milestone is a visible, game-owned overlay; keep gameplay mutations disabled until individually validated.

## User workflow permission

Proceed autonomously through **all available offline research, coding, native-compilation attempts, tests, disassembly and re-testing** without asking permission for each file or task. Do not stop just to announce the next investigation. When something can be executed with your toolchain, execute it. Ask the user only for a true blocker (missing hardware/access) or approval for changes to the original safety restrictions.

**DO NOT** substitute a browser page, a standalone preview app, generic GoldHEN cheat JSON, a notification-only PRX, or further DebugConsole.OnGUI speculation. The user has expressly rejected those.

## Evidence that is already verified

- Extracted private ELF is SHA-256 `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`. Its metadata SHA-256 is `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`. **Do not commit original game assets or binary code.**
- `scripts/inspect_ongui_scene_hosts.py` (read only) and `docs/INGAME_PRX_HOST_GATE_20261030.md` identify a candidate **native `PlayMakerGUI.OnGUI`** in gameplay scene `level2` (ForestMain_v08). It is on an enabled root GameObject in the serialized scene; method-pointer index `31674`, link VA `0x0113FAF0`, first-32-byte SHA-256 `d7f02de879025700814804e162862c6bef644d947f9bcb5c84620d766f8e4f32`. Unity OnGUI **runtime execution is not yet proven**.
- Lifecycle methods: `Awake=0x0113F950`, `OnEnable=0x0113FAE0`, `OnDisable=0x01141550`, `OnApplicationQuit=0x01141650`, all link VA relative to this ELF, **not ASLR addresses**.
- The `MenuMain.OnGUI` native body exists but its `PauseMenu` ancestor is initially inactive; `UIInputOnGUI` has an initially inactive `ChatBox` ancestor. Do not select either as always-on render host.
- Earlier `DebugConsole` object had a NULL instance in ps4debug sessions; this avenue was rejected.
- The title's existing IL2CPP metadata contains Unity GUI label/box/event methods; their native ABI, hidden method info parameters, managed object lifetime and event context **have not** been validated for calls from a PRX.
- Rewired scene/prefab graphs and Sony DS4 hardware element IDs have been extracted. `src/menu.*`, `src/overlay.*` and `src/unity_host_adapter.*` already contain a tested menu/state core. `prototype/Unity56` is a **standalone Unity C# build fixture**, not injectable retail code.
- v0.5 global render hook black-screened the game; v0.6 global detours froze the console. The quarantined old source must **never** be reused for a live test.

## Updated native dispatch proof: do not repeat the same reverse engineering

Read [`PLAYMAKER_VIRTUAL_DISPATCH_20261030.md`](PLAYMAKER_VIRTUAL_DISPATCH_20261030.md)
and run `scripts/inspect_playmaker_dispatch.py` against the hash-verified
private ELF and metadata. Bounded disassembly demonstrates
`PlayMakerGUI.OnGUI → CallOnGUI` twice; `CallOnGUI` traverses preexisting
action objects and calls virtual slot `33` via `*0x320(%rax)`.
`FsmStateAction.OnEnter/OnUpdate/OnGUI` metadata slots `30/32/33`
match independent x64 indirections `*0x2f0/*0x310/*0x320`.
This is a real game-owned IMGUI path, but no plugin registration or safe
interception is demonstrated. In particular **do not** patch shared
`Il2CppClass` vtables as a shortcut: derived action overrides and
in-flight method calls make naive replacement both incomplete and unsafe.

## Concrete engineering steps (complete without interruptions)

1. **Assess title-owned callback feasibility.** Confirm the method/scene and inspect the native dispatch path for `PlayMakerGUI.OnGUI` and its lifecycle. Validate that any PRX callback would run only inside Unity's IMGUI event on the correct thread; consider non-inline pointer indirection only if runtime ownership and atomicity can be independently demonstrated. Do not treat a static OnGUI RVA as runtime invocation proof.
2. **Check native ABI.** Map the existing Unity `GUI.Label`/`GUI.Box` and `Event.get_current` method signatures, object/string layouts, calling conventions and exception behavior for **this exact build**. Use disassembly and bounded offline fixtures. Never cast guessed `void*` function pointers and call them on the console.
3. **Implement a title-specific guarded PRX source path** using the existing C menu core. It must check CUSA, module identity, ASLR-correct mapping, readable/executable ranges and the exact target instruction fingerprint before enabling anything. Reuse the host-only `src/native_playmaker_preflight.*` and its unit tests; it is a *read-only gate*, not a proven render connection.
4. **Prove hook or dispatch safety.** No old GoldHEN Detour implementation: it does not relocate arbitrary RIP-relative operands or synchronize partial entry writes. Prove instruction relocation, correct original-call publication, thread quiescence and concurrency, reentrancy, scene disappearance, and teardown. No timed wait followed by freeing possibly active code. If safe unload cannot be proven, fail closed and do not publish a runnable artifact.
5. **Controller integration.** Use the verified local Rewired player/controller mappings and DS4 hardware IDs, without consuming gameplay input or assuming the wrong manager. Put all unverified gameplay actions behind a hard lock; first in-game test should only display/navigate UI.
6. **Reproducible native PRX build.** Prefer a legal OpenOrbis/GoldHEN toolchain with a verified template and current linker. If a proposed ImGui library requires proprietary Sony ORBIS SDK, explicitly record the blocker; **do not** silently assume the SDK is available. Compile and test native code and check ELF/PRX headers, import symbols, W^X constraints and target CUSA before considering a hardware artifact.
7. **Rerun all tests and fix failures**, then record results in PR #2. Keep original game PKG/saves intact and never upload commercial binaries.

## External native reference assessed

[Faultz/odyssey-game](https://github.com/Faultz/odyssey-game) and
[Faultz/liborbisrender](https://github.com/Faultz/liborbisrender) include real
PS4 Dear ImGui rendering but use *global GNM/VideoOut hooks*, GPU direct-memory
buffers and Sony ORBIS SDK dependencies. Their direct use would reproduce the
risk class of the previous console freeze; **do not drop these hooks into PR
#2 as a shortcut**. If their draw/UI code inspires any component, preserve
license requirements and verify all platform assumptions independently.

## Required deliverable and stop condition

Deliver the **actual, reviewable native PRX integration implementation** if
the relevant callback, ABI, safety and build gates are demonstrably resolved.
Otherwise, provide exact failing gate(s), code/test results and what artifact
or authorization would unblock them. Do not mark PR #2 ready or ask for a
console test just because an offline script passed. A final PS4 hardware test,
hook activation and any PKG modification are **not authorized by this
handoff alone** and require explicit user approval after a bounded rollback
plan. The user must not be asked to compile or test things you can do yourself.
