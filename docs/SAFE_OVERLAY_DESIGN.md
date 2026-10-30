# Safe overlay architecture review

## Decision

Keep the PS4 plugin on the **no-hook safety baseline**. Do not enable the
v0.5/v0.6 detours, GNM rendering, framebuffer writes, controller interception,
or gameplay writes. This review has not established a supported callback into
The Forest's Unity render thread, nor a GoldHEN barrier that proves callback
and trampoline quiescence during unload.

The menu model, categories, normalized DualShock controls, draw-list renderer,
and overlay state machine remain in the repository. The host UI is not wired
to the running game. The PS4 rendering experiment is preserved as quarantined
source under archive/unsafe-v0.5; it is not a build input.

The host lifecycle model in src/bridge_lifecycle.* is executable test code
only. It describes conditions a future bridge must satisfy. It is not a PS4
hook implementation and does not make the GoldHEN detour API safe.

## Incident evidence and root-cause assessment

Issue [#4](https://github.com/Skaymer-AR/TheForest-UCM-PS4/issues/4) records a
v0.5 black game screen with a responsive PS4 shell, followed by a v0.6
passive_all full-console lockup. Issue
[#5](https://github.com/Skaymer-AR/TheForest-UCM-PS4/issues/5) confirms that
the game launches normally again after removal of the experimental plugin.
These are the hardware observations. The exact faulting instruction and
thread are unknown because no crash dump, target prologue bytes, or trace was
captured. The causes below are risks and plausible mechanisms, not a proven
single root cause.

| Finding | Source evidence | Assessment |
| --- | --- | --- |
| GoldHEN x64 detour does not relocate copied instructions | The pinned SDK decoder only finds whole instruction lengths; Detour_DetourFunction64 copies those bytes into a new stub and appends a jump back. No RIP-relative or relative-branch fixups are present. | High risk for arbitrary system-library prologues. Whether the exact target prologue contained such an instruction is unverified. |
| Entry patch is visible before original-call pointer publication | The SDK writes the target jump before returning the stub. v0.6 stores the returned pointer after that call returns. v0.5 assigns g_*_original only after Detour_DetourFunction returns. | A concurrent caller can enter the hook in the publication window. v0.6 spins until publication; v0.5 can call through a null pointer. |
| Code patch is not synchronized with executing threads | The SDK changes page protection, fills the target with NOPs, and copies a 14-byte jump. It does not stop other threads, apply an atomic patch protocol, or check mprotect results. Restore is also a void operation. | A thread may execute a partially rewritten prologue; exact timing is unknown. |
| v0.6 has unbounded waits | wait_for_original() loops until the pointer is non-null. ps4_backend_stop() sleeps and then loops until the active-callback count reaches zero. | Can pin an app or teardown thread indefinitely. A counter cannot see a thread paused before its first increment. |
| v0.5 has an unbounded lock on the render path | The GNM callback takes g_output_lock with a spin loop. It also submits a custom command buffer that writes to the current display buffer. | A preempted or reentrant lock owner can stall rendering. An invalid address, surface-layout, cache/order, or command-submission assumption can explain a black screen or GPU stall; no target trace confirms which. |
| v0.5 installs all detours during plugin startup | VideoOut, Pad, and GNM detours are installed from ps4_backend_start() during plugin_load. | This mutates shared API entrypoints at a sensitive startup phase, before the game/render lifecycle is understood. |
| Reentrancy is not guarded | Callbacks call original functions and, in the GNM path, call other GNM/GPA helpers. There is no per-thread recursion guard. | Recursive entry or interaction with another hook/plugin can corrupt assumptions or deadlock. No collision was captured. |
| Inspected plugin-loader source has no normal unload handshake | At the pinned template commit, the loader calls plugin_unload only after plugin_load returns nonzero. Successful loads are retained; this code does not provide a normal callback-quiescence or unload-veto protocol. | A future design cannot assume plugin_unload can defer PRX destruction safely. module_stop is not a substitute for a barrier. |

### ABI review

- v0.6 scePadReadState(int32_t, OrbisPadData *) and scePadRead(int32_t,
  OrbisPadData *, int32_t) match the OpenOrbis public prototypes.
- The VideoOut function argument types match its public declaration. Its C
  mirror of OrbisVideoOutBufferAttribute has static checks for total size
  0x28, width offset 0x0c, and reserved offset 0x18.
- The v0.5 sceGnmSubmitAndFlipCommandBuffers declaration has nine arguments
  and matches the public GoldHEN frame-logger prototype in width and register
  placement, but declares the final 64-bit flipArg as uint64_t where the
  reference uses int64_t. That signedness does not change the x86-64 integer
  register width, but it is still a prototype mismatch and must be corrected
  before any callback is considered ABI-verified. Argument order and the
  exact target module export were not verified against The Forest's runtime.
- Matching source-level signatures do not establish that the detour's copied
  prologue is relocatable, that the target is the expected module instance,
  or that the call is made on a suitable thread.

There is no single demonstrated explanation for the two different symptoms.
For v0.5, investigate its GNM command submission, direct framebuffer writes,
lock path, and null-original installation window. For v0.6, investigate
shared-entrypoint patching, the publication spin, and teardown's callback
drain. Recovery after removing the PRX implicates the experimental integration
path, but does not identify which mechanism fired.

## GoldHEN trampoline findings

The audit is pinned to GoldHEN SDK commit
[bcea3c7](https://github.com/GoldHEN/GoldHEN_Plugins_SDK/tree/bcea3c7ef01dac6d7f9f49ebf9e90fe66d86f5f7):

1. Detour_GetInstructionSize() uses HDE64 to reach a minimum byte count; it
   does not rewrite instruction operands.
2. Detour_DetourFunction64() allocates a relay, copies original bytes into
   StubPtr, appends an absolute jump to FunctionPtr + InstructionSize, and
   replaces the target prologue with a NOP-filled 14-byte jump.
3. A copied RIP-relative load/store/call still computes its address from the
   new stub's RIP. A relative branch also keeps its old displacement. Either
   can target the wrong address after relocation.
4. The 14-byte target write is a normal memcpy, with no thread suspension or
   atomic hot-patch protocol. Its bytes can straddle an alignment boundary.
5. Restore does not report success to its caller and the write-protection
   result is not checked. The SDK Detour_Destroy() path does not establish a
   general thread-quiescence protocol.

The v0.6 publication order compounds this: the target points at the callback
before the function returns the original stub to install_detour(). An atomic
store after return cannot close that interval. A spin loop merely hides the
null pointer if the installer keeps running; it does not make a blocked or
preempted installer safe.

The review did not inspect runtime prologue bytes from CUSA12398, so it does
not assert that a specific instruction was mis-relocated. Kernel, game, and
plugin traces are unavailable in this repository.

## Alternatives for reaching Unity rendering and DS4

| Route | What it would provide | Constraint / status |
| --- | --- | --- |
| Unity native rendering extension callback (UnityRenderingExtEvent) | Unity invokes native extension work at an explicit render event, on the render thread. | Preferred documented Unity route when a game-owned native plugin is loaded and managed code schedules the event. This GoldHEN PRX is not a Unity plugin; IssuePluginEvent needs a Unity-side caller. No PKG changes are allowed, and no existing The Forest callback/plugin was demonstrated. Not currently reachable. |
| Public GoldHEN arbitrary-overlay callback | A supported compositor could draw without detouring game APIs. | No public arbitrary drawing/compositor callback was found in the pinned GoldHEN plugin SDK or plugin template. GoldHEN's main source is not public. Do not bind to private overlay internals. |
| Existing Unity lifecycle methods (`DebugConsole.OnGUI`, `VirtualCursor.LateUpdate`, `ModList.OnEnable`, `DllModLoader.Awake`) | Could provide an existing title-owned callback if a live component or mod loader were reachable. | Prior PS4 analysis recovered RVA candidates; PS4Debug confirmed 16-byte entry prefixes only for `DebugConsole.OnGUI` and `ToggleConsole`. The `DebugConsole` instance observed by the user was NULL. No safe registration path is available. `OnGUI` remains the closest rendering candidate; see [PS4 IL2CPP analysis](PS4_IL2CPP_ANALYSIS.md). |
| Per-title import/GOT slot replacement | Narrows the patch to one module's call site instead of rewriting a shared function prologue. | Still races import resolution and concurrent calls, needs a stable callback and unload proof, and does not create a Unity render callback by itself. Not approved as a shortcut. |
| Open a separately owned DS4 handle and poll it | Could avoid intercepting the game's scePadRead* calls. | OpenOrbis signatures and button masks are verified from public headers; whether the game's open handle can coexist and how an already-open handle is owned remain unverified. The host adapter consumes snapshots only; no handle is opened in this build. |
| External HDMI compositor | Would avoid in-process code patching. | Requires separate hardware/capture/latency work and is outside this GoldHEN PRX architecture. |

The practical architecture boundary is: keep menu input/state and draw-list
generation independent; the new host-only adapter requires an explicit provider
for a Unity callback, render context, renderer, and atomic input snapshot. No
provider is implemented for the game. Validate ownership of a separately opened
pad handle before using it. Do not use sceVideoOut*, scePadRead*, or GNM
entrypoint detours as generic startup hooks.

The focused lifecycle and Rewired dispatch map is in
[DEBUGCONSOLE_LIFECYCLE.md](DEBUGCONSOLE_LIFECYCLE.md). It confirms a compiled
IMGUI path and `ProcessGamePads → ReInput.get_players`, but the `Awake` and
`GetInstance` windows are not in the bounded dump. The two Rewired virtual
dispatch targets remain unresolved, so this evidence adds no active game
provider or callback registration API.

Official references:

- [Unity low-level native plug-in rendering extensions](https://docs.unity.com/en-us/engine/6000.0/manual/programming-environment/plug-ins/native-plugin-interface/low-level-native-plugin-rendering-extensions)
- [Offline Unity/IL2CPP method research and local analyzer](IL2CPP_INTEGRATION_RESEARCH.md)
- [GoldHEN Plugins SDK](https://github.com/GoldHEN/GoldHEN_Plugins_SDK)
- [GoldHEN Plugins Repository](https://github.com/GoldHEN/GoldHEN_Plugins_Repository)
- [GoldHEN issue #130: VideoOut hook conflict with Game Overlay FPS counter](https://github.com/GoldHEN/GoldHEN/issues/130) (evidence of a real hook interaction, not evidence for this incident's root cause)

## Lifecycle and rollback contract

The host model defines these phases:

```text
EMPTY → PREPARING → PUBLISHING → ARMED → ACTIVE
                                  │         │
                                  └────┬────┘
                                       ↓
QUIESCING → DETACHED → RELEASED
     └──── restore failure ─────────→ RETAINED
```

- Build and validate callback data before publishing an entrypoint. Publish
  the non-null original-call path before any callback can be exposed. A
  callback in an armed or quiescing phase is pass-through only.
- Callback acquisition is a fixed-size atomic scan over 32 lease slots. It
  has no spin wait, sleep, allocation, logging, or lock. Exhaustion fails
  closed in the model.
- Shutdown marks the bridge quiescing, restores/detaches the target, then
  requires independent platform proof that **no thread is paused before the
  callback's first instruction or executing callback/trampoline code**. A
  zero in-flight count by itself is not such proof.
- If restoration fails, retain all executable resources and the original
  pointer; callbacks remain pass-through only. If quiescence is not proven or
  leases remain, return immediately without freeing anything. There is no
  timeout-then-free path.
- Only after successful restoration, platform quiescence, and zero leases may
  a future implementation release trampoline, callback state, GPU command
  storage, or the module itself. GPU work would additionally require a
  documented completion/fence before releasing its memory.
- The current GoldHEN SDK and inspected plugin-loader path do not provide the
  needed proof or a normal unload veto. Therefore this contract cannot be
  satisfied by the present inline detours, and the PRX remains hook-free.

The v0.8 PRX source calls a no-op backend. `plugin_unload` owns no callbacks or
trampolines and returns immediately. The bridge lifecycle model, Unity host
adapter, and pad mapper are compiled only into host tests; the PRX build script
excludes them. The branch's GitHub Actions workflow runs offline tests only and
does not build or publish a notification-only PRX artifact.

## Host fault-injection coverage

sh scripts/test.sh runs the portable UI and lifecycle tests.
It also runs the host Unity adapter/DS4 mapper tests and synthetic metadata/dump
parser tests. `SANITIZE=1 sh scripts/test.sh` runs the C tests with ASan and
UBSan.

| Scenario | Expected result |
| --- | --- |
| Missing original pointer | Entry rejects immediately; no wait/spin. |
| Initialization stopped before original publication | No-exposure path releases only after explicit proof. |
| Initialization stopped after publication but before activation | Callback is pass-through; staged pointer remains until explicit detach and proof. |
| Concurrent install, callback and unload | Install publishes before activation; unload returns without waiting; trampoline remains while proof/lease conditions are unmet. |
| Callback held during shutdown | Release returns BUSY while its lease is held. |
| Failed target restoration | State becomes RETAINED; original pointer/resources remain; release count stays zero. |
| Missing quiescence proof | Release returns NO_QUIESCENCE_PROOF; original pointer remains. |
| Duplicate/stale lease | Second leave cannot decrement another callback's lease or release resources. |
| Entry after release | Rejected; no original pointer is returned. |
| Unity host registration fails | Adapter returns to EMPTY; no callback state is exposed. |
| Callback is invoked during registration | It sees REGISTERING and performs no input read or draw. |
| Frame arrives outside the provider's render context | No input read or draw occurs. |
| Adapter stop during a callback | Stop returns PENDING immediately and retains adapter state. |
| Host detach reports failure | Adapter enters RETAINED and keeps callback state. |

These tests establish behavior of this host-side state model under the tested
schedules. They do **not** test GoldHEN, PS4 scheduling, executable page
patching, game ABI, GPU fences, Unity thread affinity, or whether the model's
required platform proof exists. ASan/UBSan are not target-hardware evidence.

## Build and release guardrails

- GitHub Actions runs static guards, host C tests, and Python analyzer tests.
  It does not compile or upload a PRX artifact.
- The no-hook v0.8 PRX source and build script remain available for source
  review, but this research workflow does not invoke them. That source only
  shows a notification; it is not an in-game menu.
- No hook library, GNM, VideoOut, ScePad, Unity provider, or host-only adapter
  code is linked into a PRX by this workflow.
- Historical v0.5/v0.6 artifacts and archived source remain quarantined; do
  not install or recommend them.
- Original game binaries, metadata, and generated dumps are ignored and must
  stay outside the public repository.
- No PKG, save data, framebuffer, unknown flags, or hard-coded session
  addresses are changed.

## Remaining questions before any future console experiment

1. Can any identified Unity callback, especially `DebugConsole.OnGUI`, be
   reached in this PS4 build without patching shared system entrypoints? The
   local IL2CPP dump must first establish exact PS4 methods/RVAs.
2. Can GoldHEN or the loader keep a PRX resident until a real callback and GPU
   quiescence proof is available, or is unloading unsupported for this use?
3. Can a verified non-patching registration mechanism expose a title-scoped
   callback with correct IL2CPP ABI/thread context? No guessed addresses or
   DebugConsole flags are acceptable.
4. Can a separately opened DS4 handle coexist with the game's handle without
   stealing input or requiring interception?
5. Can target module exports and instruction bytes be captured for offline
   ABI/relocation analysis without changing the game image?

No PS4 test is requested by this change. Any later hardware trial requires a
separate review and explicit user approval, one reviewed bridge change at a
time, a known no-hook rollback, and proof that the proposed callback/unload
contract exists. A passing CI job alone is not grounds for a trial.
