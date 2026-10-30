# CUSA12398 v1.15 — IL2CPP native helper resolution from original private module

**Analysis date:** 2026-10-29. **Scope:** offline, read-only, no PS4 runtime code execution, no hook, no PKG/save modifications.

## Source and verification

- Input: user's previously supplied original `Modules/Il2CppUserAssemblies.prx` and `Metadata/global-metadata.dat`, recovered from a private conversation attachment, **not committed**.
- PRX SHA-256: `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`.
- Metadata SHA-256: `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`.
- IL2CPP metadata v23; **90,987 methods, 12,963 types** parsed.
- Method pointer table starts at PRX file offset `0x31738C0`. Each `Il2CppMethodDefinition.methodIndex` selects an 8-byte RVA pointer at `table + methodIndex * 8` for this build.
- Verified **42 of 42** recorded 16-byte method prefixes **directly against the privately supplied PRX bytes**. In this PRX the first executable `PT_LOAD` uses file offset `0x4000`, virtual address `0`, so these addresses map as `file_offset = RVA + 0x4000` within the segment.
- This is an **offline byte-for-byte check**. **Only two** function prefixes (`DebugConsole.OnGUI` and `ToggleConsole`) were previously verified physically in PS4Debug RAM. Do not conflate those evidence levels.
- The analysis used `llvm-objdump -d --x86-asm-syntax=intel` on private bounded windows and joined direct `call`/`jmp` RVAs against method-pointer table + metadata names. Target instructions and private binaries are not redistributed.

## Resolved previously unnamed helpers

| RVA | Exact metadata method name | Relationship confirmed in original PRX |
| --- | --- | --- |
| `0x005CA800` | `TheForest.DebugConsole.ShowConsole` | Target of `ToggleConsole` tail-`jmp` at `0x005CB6DA` |
| `0x005C8E00` | `TheForest.DebugConsole.HandleInput` | Called by `DebugConsole.OnGUI` at `0x005C383C` |
| `0x005C2FE0` | `TheForest.DebugConsole.CheckDisplayState` | Tail target from `ShowConsole` at `0x005CA96A`; also called from `HandleInput` |
| `0x005CA980` | `TheForest.DebugConsole.HandleConsoleInput` | Called by `HandleInput` at `0x005C926A` |
| `0x00934F40` | `Rewired.ReInput.get_players` | Called by `PS4Controller.ProcessGamePads` at `0x00476207` |
| `0x00476DD0` | `PS4Controller.UpdateConnectionMap` | Called by `PS4Controller.Update` at `0x0047617E` |
| `0x01DADDD0` | `TheForest.Utils.Input.SetState` | Called by `ShowConsole` at `0x005CA911` |
| `0x01DADCD0` | `TheForest.Utils.Input.GetState` | Called by `Input.SetState` in the inspected body |
| `0x02166EB0` | `UnityEngine.Object.op_Implicit` | Called by `ShowConsole` and `VirtualCursor.LateUpdate` |
| `0x01FB2160` | `TheForest.UI.Multiplayer.ChatBox.SetEnabled` | Called by `ShowConsole` at `0x005CA843` |
| `0x01F66C60` | `TheForest.UI.VirtualCursor.GetAdjustedGamepadSensitivity` | Called by `VirtualCursor.LateUpdate` at `0x01F6599E` |
| `0x01F67000` | `TheForest.UI.VirtualCursor.get_IsVisibleSoftwareCursorActive` | Called by `LateUpdate` at `0x01F65B25` |

## Critical observation: there is a compiled Unity IMGUI console drawing path

The physical PS4-confirmed `TheForest.DebugConsole.OnGUI` at RVA `0x005C37B0`, in its inspected private disassembly window, directly calls:

| Callsite RVA | Resolved method |
| --- | --- |
| `0x005C3828` | `UnityEngine.GUI.get_color` |
| `0x005C383C` | `TheForest.DebugConsole.HandleInput` |
| `0x005C38B1` | `UnityEngine.GUIUtility.CheckOnGUI` |
| `0x005C3B11` | `UnityEngine.GUILayout.BeginHorizontal` |
| `0x005C3BFE` | `UnityEngine.GUILayout.DoLabel` |
| `0x005C3C17` | `UnityEngine.GUI.set_color` |
| `0x005C3D32` | `UnityEngine.GUILayout.Label` |
| `0x005C3E61` | `UnityEngine.GUI.TextField` |

These are **direct callsite relationships confirmed in actual PS4 IL2CPP code**. They demonstrate that the DebugConsole's GUI implementation was compiled into the PS4 module, not that Unity currently executes it or exposes an extension registration API. A prior **read-only hardware check found its singleton instance pointer NULL both at main menu and during gameplay**. Never call `OnGUI`, `ToggleConsole` or `ShowConsole` with a NULL/guessed `this` pointer.

The tail-target of `ToggleConsole` is not an anonymous helper: metadata resolves `0x005CA800` as **`TheForest.DebugConsole.ShowConsole`**. That function writes state at `this+0x5A`, and calls `ChatBox.SetEnabled`, `TheForest.Utils.Input.SetState` and `CheckDisplayState`. `HandleInput` calls `ShowConsole` twice (RVA `0x005C9202` and `0x005C9274`) and also calls `PS4Controller.SetMouseEnabled` at `0x005C92A7`. This is an existing input→visibility→GUI flow, but without proof of a live `DebugConsole` object, it cannot safely be invoked.

## Input and mod loader findings

- `PS4Controller.Update` calls `ProcessGamePads` at `0x00476179`, and calls `UpdateConnectionMap` at `0x0047617E`; `ProcessGamePads` calls `Rewired.ReInput.get_players` at `0x00476207`. This shows **Rewired player-state use**, not direct ScePad API ownership. `ProcessGamePads` also makes indirect virtual calls; unverified targets are **not** attributed to ScePad.
- `TheForest.Tools.DllModLoader.Awake` includes `System.IO.MonoIO.ExistsDirectory` at `0x022CEF9D`, `DirectoryInfo.GetFiles` at `0x022CEFE0`, and `LoadDllMod` at `0x022CF01D`. The native compiled body of `LoadDllMod` contains `System.IO.File.ReadAllBytes` at `0x022CF0EC` and `System.AppDomain.Load` at `0x022CF10F`. **This does not establish that loading arbitrary managed DLLs works under PS4 IL2CPP/AOT or from a GoldHEN PRX**, nor that it can present a Unity overlay.
- `TheForest.Modding.UI.ModList.OnEnable` (`0x017D5390`) and `Refresh` (`0x017D53A0`) are confirmed immediate `ret` entries in this specific PRX.

## Safety and next steps

### Update from the later private analysis (2026-10-30)

- `DebugConsole.Awake` (`0x005C1C30`) reads the `Cheats.DebugConsole` field at native static storage `+0x10`; the zero branch reaches `UnityEngine.Object.Destroy` (`0x02176930`). It stores `this` into `DebugConsole.Instance` at native static storage `+0x10` (`0x005C1EA2`) only after its guards. The live flag value is unknown.
- `GetInstance` (`0x005CB690`) reads that same singleton and returns it; it does not construct or activate the component.
- The other `Awake` guard at `0x005C1C92` references data RVA `0x33EB300` plus static byte `+0x01`. `CoopPeerStarter.DedicatedHost` remains only a candidate name; its PS4 metadata class registration has not been independently resolved.
- The static metadata field names `Cheats.DebugConsole` and `DebugConsole.Instance` were matched against the reported PS4 metadata v23. `scripts/verify_il2cpp_static_fields.py` now checks field identity/static declaration against a local `dump.cs`, and requires the recorded metadata SHA-256 when using the repository manifest. The checker cannot prove a native type-reference RVA or runtime field value.
- `ProcessGamePads` has an IL2CPP interface lookup/vtable dispatch sequence at `0x00476279..0x004762D6` and again at `0x004762F0..0x00476315`, keyed by a static type reference at `0x033EF3E8`. The type, methods, and physical ScePad relationship remain unresolved.
- `DebugConsole.OnDestroy` was not in the available native windows. Its RVA/body and singleton-clear behavior remain unknown; see [`DEBUGCONSOLE_LIFECYCLE.md`](DEBUGCONSOLE_LIFECYCLE.md) for the local workflow and no-go decision.

**Architecture decision: no-go for a GoldHEN-only Unity IMGUI adapter under the evidence and restrictions currently established.** The compiled callback is not a registration API, and no AOT-capable title-scoped loader or callback has been demonstrated. Continue only with private offline resolution of `OnDestroy`, native type-reference initializers, and Rewired interface targets. Do not modify flags, instantiate objects, invoke game methods, or enable hooks. The earlier v0.5 black screen and v0.6 console lock remain reasons not to request another hook-enabled PRX test.

**Confidence:** Static method names, direct call sites, field identities, and 42 matching offline prefixes are recorded from the exact supplied PS4 PRX/metadata. The `Awake` flow is partially recovered, but live flag values, `OnDestroy`, complete ABI, type-name resolution of the Rewired dispatch, safe render/input integration and plugin unloading remain **unverified**.
