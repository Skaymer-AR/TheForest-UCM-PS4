# CUSA12398 v1.15 — prior PS4 IL2CPP research (recovering verified results)

**Source and scope:** this table is a structured restatement of the earlier offline analysis performed in the user's ChatGPT project using the privately provided `Il2CppUserAssemblies.prx` and `global-metadata.dat`, and the associated report `TheForest_CUSA12398_115_Direcciones_Para_Verificar.csv`. The original game binaries are **not** included in GitHub and must stay private. This document is not a substitute for re-disassembling the exact game files and is not an authorization for hooking or invoking functions.

## Why this exists

The earlier `docs/IL2CPP_INTEGRATION_RESEARCH.md` contained stale wording because the private binaries were not present in that Cloud checkout. The user's prior analysis had already produced 42 PS4 method-address candidates, and the user physically verified the first 16 instruction bytes at two functions via PS4Debug. This evidence is now restored and analyzed in `docs/PS4_IL2CPP_ANALYSIS.md`.

Offline method address correlation used a PRX IL2CPP method-pointer table at file offset `0x31738C0`, and a module base observed in one console session of `0x8029C000`. **Absolute RAM addresses from that session are not valid for other launches without checking the loaded module base.** RVAs below are not proofs of a valid native ABI, an instantiated object, or a safe callback registration mechanism.

## PS4Debug read-only signature confirmation

- `TheForest.DebugConsole.OnGUI`: RVA **`0x005C37B0`**; one-session RAM `0x8085F7B0`. Expected and **user-confirmed** first 16 bytes: `55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 E4`.
- `TheForest.DebugConsole.ToggleConsole`: RVA **`0x005CB6D0`**; one-session RAM `0x808676D0`. Expected and **user-confirmed** first 16 bytes: `31 F6 80 7F 5A 00 40 0F 94 C6 E9 21 F1 FF FF 90`.
- `ToggleConsole` is a tiny tailcall beginning `xor esi,esi; cmp byte ptr [rdi+0x5a],0; sete sil`. Its `rdi` requires a valid object `this`. **Never invoke on NULL.**
- In a read-only singleton check, a populated IL2CPP class reference and static-fields pointer led to a **NULL instance** at `0x20949AD90`; reproduced in game and main menu.
- Prior `DebugConsole.Awake` RVA `0x005C1C30` and an instance-registration instruction near `0x005C1EA2`. Two later guard reads were `0` (`0x2058BE721`, `0x201A4F3F0`), but they were obtained **after** Awake ran; don't assume values at entry.

## Offline candidate method RVA table (42 entries)

Status `offline candidate` means **not hardware byte-checked** even though the RVA was extracted from actual PS4 analysis. Only the two marked signatures above were directly matched to PS4Debug readings.

| IL2CPP method | RVA | Validation status |
| --- | --- | --- |
| `TheForest.DebugConsole.OnGUI` | `0x005C37B0` | **confirmed 16-byte signature on PS4** |
| `TheForest.DebugConsole.ToggleConsole` | `0x005CB6D0` | **confirmed 16-byte signature on PS4** |
| `TheForest.DebugConsole.GetInstance` | `0x005CB690` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._spawnitem` | `0x005CE4F0` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._additem` | `0x005D3D90` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._godmode` | `0x005D8E80` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._goto` | `0x005DF170` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._speedyrun` | `0x005E5CA0` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._setCurrentDay` | `0x005EFE90` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._buildhack` | `0x005DA920` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._buildallghosts` | `0x005DA420` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._spawnmutant` | `0x005D0AE0` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._timescale` | `0x005DB2F0` | offline candidate (not tested on PS4) |
| `TheForest.DebugConsole._showDevConsole` | `0x005DBB80` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.InitModding` | `0x01DC1140` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.ResetModding` | `0x01DC14E0` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.UnlimitedItems` | `0x01DC15B0` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.AddItem` | `0x01DC1620` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.AddItemsByType` | `0x01DC16A0` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.Goto` | `0x01DC18B0` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.Goto` | `0x01DC29A0` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.GotoCave` | `0x01DC2750` | offline candidate (not tested on PS4) |
| `TheForest.Utils.LocalPlayer.GotoArea` | `0x01DC2920` | offline candidate (not tested on PS4) |
| `CheatsBridge.SetCreative` | `0x0147D5C0` | offline candidate (not tested on PS4) |
| `CheatsBridge.SetGodMode` | `0x0147D620` | offline candidate (not tested on PS4) |
| `CheatsBridge.SetInfiniteEnergy` | `0x0147D680` | offline candidate (not tested on PS4) |
| `CheatsBridge.SetNoSurvival` | `0x0147D740` | offline candidate (not tested on PS4) |
| `TheForest.Tools.DllModLoader.Awake` | `0x022CEF10` | offline candidate (not tested on PS4) |
| `TheForest.Tools.DllModLoader.LoadDllMod` | `0x022CF050` | offline candidate (not tested on PS4) |
| `TheForest.Modding.UI.ModList.OnEnable` | `0x017D5390` | offline candidate (not tested on PS4) |
| `TheForest.Modding.UI.ModList.Refresh` | `0x017D53A0` | offline candidate (not tested on PS4) |
| `TheForest.Modding.UI.ModList.ClearUI` | `0x017D53B0` | offline candidate (not tested on PS4) |
| `TheForest.UI.VirtualCursor.LateUpdate` | `0x01F65960` | offline candidate (not tested on PS4) |
| `TheForest.UI.VirtualCursor.SetCursorType` | `0x01F67130` | offline candidate (not tested on PS4) |
| `TheForest.UI.VirtualCursor.set_OverridingPosition` | `0x01F67770` | offline candidate (not tested on PS4) |
| `TheForest.UI.VirtualCursor.get_IsVisibleSoftwareCursorActive` | `0x01F67000` | offline candidate (not tested on PS4) |
| `PS4Controller.Update` | `0x00476080` | offline candidate (not tested on PS4) |
| `PS4Controller.ProcessGamePads` | `0x004761A0` | offline candidate (not tested on PS4) |
| `PS4Controller.SetMouseEnabled` | `0x00477330` | offline candidate (not tested on PS4) |
| `PS4Controller.SetJoystickEnabled` | `0x00477040` | offline candidate (not tested on PS4) |
| `PlayerStats.Update` | `0x00C22810` | offline candidate (not tested on PS4) |
| `PlayerStats.setStamina` | `0x00C21D50` | offline candidate (not tested on PS4) |

## Research implications for Codex

1. Use the two confirmed PS4 RVAs as anchors for *offline* inspection, not to patch or call code.
2. In particular, check candidate `TheForest.UI.VirtualCursor.LateUpdate` at RVA `0x01F65960`, `PS4Controller.Update` at `0x00476080`, `TheForest.Tools.DllModLoader.Awake` at `0x022CEF10`, and `TheForest.Modding.UI.ModList.OnEnable` at `0x017D5390`. **Their RVAs are candidate extractions, not user-confirmed signatures.** `ModList.OnEnable` is likely a stub based on extracted `C3 90...` bytes, not evidence of a usable extension.
3. The PS4 console scene bundle analysis had found enabled `DebugConsole` objects in menu and gameplay scenes, but the static instance pointer was still NULL at runtime. A scene object name is not evidence of a reachable active callback.
4. **No safe in-game overlay or DS4 route has been established.** Don't revive the experimental v0.5/v0.6 GNM/VideoOut/ScePad inline detours: they caused a black screen and a full console hang, respectively.
5. If more private binary analysis is needed, request a local read-only script run by the user against their own retained files, not another upload of copyrighted binaries into a public repo. Generated method tables, bounded hex signatures and validation results can be checked in.

## Reanalysis tooling

The read-only analyzer in [`scripts/analyze_ps4_il2cpp_candidates.py`](../scripts/analyze_ps4_il2cpp_candidates.py) reads this table, validates both confirmed entry prefixes against a private local ELF, disassembles bounded windows for the focus methods and can scan direct `call`/`jmp` xrefs. It refuses to disassemble if either anchor mismatches. Analysis conclusions and invocation examples are in [`PS4_IL2CPP_ANALYSIS.md`](PS4_IL2CPP_ANALYSIS.md). Neither the ELF nor its generated full disassembly belongs in this repository.
