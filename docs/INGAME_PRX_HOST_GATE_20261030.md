# The Forest v1.15 — native PRX route for an **in-game** graphical menu

**Purpose:** determine whether an actual Unity-rendered Ultimate Mod Menu can be
called from a title-specific PRX without rebuilding the commercial game's PKG.
This is not a browser/standalone demo. **Status: native integration hypothesis;
no runnable graphical PRX, no hook, and no console test in this PR.**

## 1. Evidence gathered directly from the actual game

The read-only script `scripts/inspect_ongui_scene_hosts.py` inspects *private*
Unity serialized scene files + the hash-verified IL2CPP ELF + v23 metadata,
resolves `MonoBehaviour.m_Script` to full class names, and traverses the
`Transform.m_Father` chain. It does not infer runtime execution from names.

Unity Player: **5.6.6f2**; IL2CPP module SHA-256
`0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`;
metadata SHA-256
`238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`.

### level2 (ForestMain_v08), components with native OnGUI

| Actual class and root hierarchy | Active in serialized hierarchy? | OnGUI native method index | Link VA (NOT ASLR) | Verdict |
| --- | --- | ---: | --- | --- |
| `PlayMakerGUI` → scene root `PlayMakerGUI` | **YES** | 31674 | `0x0113FAF0` | Best **candidate** for Unity IMGUI-context investigation, not a proven callback |
| `TheForest.Save.BrokenSaveChecker` → scene root `LoadSave` | **YES** | 78579 | `0x022C0AC0` | Alternate, save-screen functionality may be conditional |
| `MenuMain` → `Panel - Main` → **inactive `PauseMenu`** → `HudGui` | **NO**, by inactive parent | 61638 | `0x013C8B50` | Reject as always-on host; only relevant if pause menu activated |
| `UIInputOnGUI` → `Input Label` → **inactive `ChatBox`** → other HUD objects | **NO**, by inactive parent | 82548 | `0x00FE50D0` | Reject as always-on host |
| `LoadIcon` → `LoadingHolder` → **inactive `LoadCam`** | **NO** | 60976 | `0x0118B030` | Reject as always-on host |
| `TheForest.DebugConsole` → scene root | YES at asset level | 75395 | `0x005C37B0` | Already excluded: observed managed instance NULL in earlier PS4Debug study |

In `level1` only `DebugConsole` and `LoadIcon` have `OnGUI`; the
`LoadIcon` ancestry is inactive, so the proposed native GUI host is **not
expected to exist at the title screen**. This matters for bootstrap timing.
An active flag stored in an asset is not proof that Unity has instantiated
the object or invokes its callback in a current console session.

### Native method lifecycle: PlayMakerGUI

| Method | Method pointer table index | Link VA |
| --- | ---: | --- |
| `Awake` | 31672 | `0x0113F950` |
| `OnEnable` | 31673 | `0x0113FAE0` |
| `OnGUI` | 31674 | `0x0113FAF0` |
| `OnDisable` | 31676 | `0x01141550` |
| `OnApplicationQuit` | 31678 | `0x01141650` |

These are **ELF link VAs with module base zero**, not live PS4 memory
addresses. The verified file offset of `OnGUI` is `0x01143AF0`.
SHA-256 of its first 32 native bytes:
`d7f02de879025700814804e162862c6bef644d947f9bcb5c84620d766f8e4f32`.
There is a native method body; its presence does not establish a safe
external callback registration surface.

### Graphics API is present in the title's AOT metadata

The same native method table includes existing `UnityEngine.GUI.Label`,
`UnityEngine.GUI.Box`, `UnityEngine.Event.get_current`, etc. This means
the game's original build already contains **some required UI routines**.
Calling these APIs safely from a PRX requires proof of hidden IL2CPP
`MethodInfo` arguments, `Rect` struct calling convention, managed
string and exception handling, and Unity's correct IMGUI event/thread.
**Do not call these methods by guessed C function-pointer casts.**

## 2. Proposed title-specific architecture, not an implementation claim

A *possible* alternative to rebuilding IL2CPP AOT is:

1. The PRX identifies the exact title and module identity by checks not
   relying on stale ASLR addresses.
2. A proven, game-specific invocation mechanism calls our **own** native
   render adapter during a legitimate `PlayMakerGUI.OnGUI` event.
3. This adapter passes the existing `src/menu.*` state and
   `src/overlay.*` UI data into verified Unity GUI drawing calls
   (same thread, verified ABI, known managed objects). Only the UI is
   rendered; gameplay commands remain locked until independently validated.
4. Input is obtained from the assigned Rewired Player/controller in Unity,
   not by arbitrarily intercepting global ScePad APIs.
5. A complete callback lifetime contract ensures no unexpected code executes
   after PRX cleanup, including failure and game exit paths.

**Crucial limitation:** step 2 has **not** been demonstrated. In particular,
calling an IL2CPP `OnGUI` method from an unrelated thread does not establish
a GUI event context, and calling a native IL2CPP method pointer does not add
a new `MonoBehaviour`. The old `UnityHost` AOT prototype and this PRX
hypothesis are two different integration architectures.

## 3. Why we cannot immediately ship a safe PRX

The prior PS4 history is real:

- v0.5 GNM/VideoOut prototype: black game screen.
- v0.6 global detours: full console lockup.
- v0.8 no-hook PRX: game boots, **but it has no menu**.

The previously used GoldHEN SDK trampoline copies overwritten x86-64
instructions without general RIP-relative branch/data relocation; patch
publication is not thread-synchronized. That is disallowed for production
integration. Even if the first instructions of this particular method look
relocatable, **partial code writes, ASLR, original-call publication, live
callback leases, and unloaded-target teardown are unresolved**.

I also inspected the public PS4 ImGui plugin template
[Faultz/odyssey-game](https://github.com/Faultz/odyssey-game) and
[Faultz/liborbisrender](https://github.com/Faultz/liborbisrender).
They are real Orbis native renderer examples **but not an immediately safe
drop-in** for this game. They use graphics-driver flip hooks (including
`sceGnmSubmitAndFlipCommandBuffers`), MinHook, GPU direct-memory buffers,
and Sony ORBIS SDK/Visual Studio build dependencies. Their render path
includes a wait on a GPU completion label; copying it would revive the same
high-risk global hook class as the failed experiment. No proof of compatibility
with this specific title, firmware, or our teardown protocol is supplied.

A native PS4 PRX requires OpenOrbis + GoldHEN plugin build inputs *or* an
authorized official Orbis toolchain for SDK-dependent libraries. No existing
GitHub Actions job for this repository currently builds a graphical PRX.
Passing Python/C# fixture tests is not PS4 validation.

## 4. Exact acceptance gates for a **real in-game** test build

| Gate | Pass criterion | Current |
| --- | --- | --- |
| G1: static scene host | Exact title/module hash; OnGUI body; enabled object with active full ancestor chain | **PASS for candidate discovery, not runtime** |
| G2: live invocation | Demonstrated call route to `PlayMakerGUI.OnGUI` with correct Unity render context and scene lifecycle, no guessed address | **MISSING** |
| G3: hook/invocation safety | Reentrant-safe, correctly relocated/atomic or hook-free, no in-flight callback during cleanup; recovery on failure | **MISSING** |
| G4: Unity ABI | Calling convention, managed arguments, GUI event, exceptions, ownership and thread documented and tested | **MISSING** |
| G5: DS4 + UI focus | Verified connected local Player/controller and input focus, controls not duplicated with gameplay | **MISSING** |
| G6: reproducible PS4 build | Toolchain, link inputs, `.prx` + inspection and fail-closed fingerprint check | **MISSING** |
| G7: first hardware run | Only after gate review: backups, exact title, rollback instructions, user authorization | **NOT AUTHORIZED** |

**Decision:** continue only offline engineering toward a title-specific
PRX. Do not install the old global hooks, do not repackage the retail PKG, do
not call a "working graphical PRX" a successful deliverable until G2–G6
pass. If a new risk-bearing architecture is required, request explicit
approval before the first hardware deployment.

## 5. Repeatable private preflight

```sh
python3 scripts/inspect_ongui_scene_hosts.py \
  --assets-root /private/TheForest_Unity_Assets \
  --module /private/il2cpp.elf \
  --metadata /private/global-metadata.dat \
  --output /private/ongui_gate.json
```

Output contains only class names, object ancestry, IDs, pointer indices,
link VAs and hashes, **not proprietary game bytes**. The Python unit tests
use only synthetic Unity serialized objects/metadata/ELF fixtures and
reject inactive parents, invalid Transform hierarchies, invalid executable
ranges and unsupported metadata layouts.
