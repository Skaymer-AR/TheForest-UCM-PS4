# CUSA12398 v1.15 — Native DebugConsole.OnDestroy recovered (offline)

**Status:** confirmed from original user-provided PS4 `Il2CppUserAssemblies.prx` and `global-metadata.dat`, analyzed read-only on 2026-10-30. This resolves the specific OnDestroy methodIndex/RVA and body gap described in Codex commit `8b4dc16`. **No PS4 test and no PRX plugin build.**

## Identical original inputs and mapping

- Module SHA-256: `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`.
- IL2CPP metadata v23 SHA-256: `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`.
- Metadata type `TheForest.DebugConsole`, method `OnDestroy`, metadata definition index **82470**, `methodIndex=75393`, method token `0x0600777D`.
- Private PRX IL2CPP method-pointer table at file offset `0x31738C0`: `methodIndex=75393 → native RVA 0x005C3340`. Here executable segment uses file offset `RVA+0x4000`, so method entry file offset is `0x005C7340`.
- Disassembly command (local private copy only): `llvm-objdump -d --x86-asm-syntax=intel --start-address=0x5c3340 --stop-address=0x5c3580 Il2CppUserAssemblies.prx`.
- Next method `DebugConsole.Update` begins at `0x005C3580`, so that bounded window contains the complete analyzed `OnDestroy` routine ending at `0x005C3578` or throwing along a no-return path.

## Relevant native instruction facts

| Native RVA | Extracted instruction/behavior | Meaning/limit |
| --- | --- | --- |
| `0x005C3369`–`0x005C3384` | Load class-ref slot `0x33F0A60` → `static_fields` at `+0xA0`; compare `[static_fields+0x08]` to `[this+0xF8]`. If equal, write **zero** to `[static_fields+0x08]` at `0x005C3384`. | A **different** static field (`Counters` in the matching decompiled reference) is cleared; **this is not `Instance` at `+0x10`**. |
| `0x005C338C`–`0x005C33F4` | Read `[static_fields+0x10]`, pass it and current object to `0x02163510`; a zero result jumps to function epilogue `0x005C3570`. | Cleanup body is conditional on matching the current `DebugConsole.Instance`. The called helper's name/ABI is not independently proven by this short window; compare with PC source only as corroboration. |
| `0x005C33FA`–`0x005C3559` | Multiple delegate / event registration data accesses and calls; some conditional paths can terminate at `0x005C3579` (throw). | Consistent with unlinking event handlers, but individual delegate/callback identities require further metadata joins. |
| **`0x005C355E`–`0x005C356C`** | Load class-ref slot `0x33F0A60`, load `static_fields` at `+0xA0`, then **`mov qword ptr [rax + 0x10], r14`** at `0x005C356C`. | **Writes the original `this` back to `DebugConsole.Instance`** on the matching-instance cleanup path. It does **not** clear that pointer to zero. |
| `0x005C3570`–`0x005C3578` | Restore registers and `ret` | Successful normal exit. |

At the function entry `0x005C3351`, `mov r14,rdi` preserves the incoming object `this`. Thus the final write **stores `this`**, not NULL.

`DebugConsole.GetInstance` at `0x005CB6B0`–`0x005CB6C2` reads that exact class-ref slot (`0x33F0A60`), `static_fields + 0x10` and returns its value. `DebugConsole.Awake` at `0x005C1EA2` writes `this` to the exact same field. Therefore the three method paths agree.

**Independent corroboration only (PC reference, not substituted for PS4 evidence):** `TheForest.DebugConsole.OnDestroy` in [Blightbuster/The-Forest decompiled PC source, commit be0a628](https://github.com/Blightbuster/The-Forest/blob/be0a628b4c0260f4d24e7b34e4fc509bd4dc3b5a/Assembly-CSharp/TheForest/DebugConsole.cs) literally has `DebugConsole.Instance = this;` at the end of the matching-instance branch, and clears `Counters` earlier. This counterintuitive behavior matches the PS4 machine code.

## Meaning for observed NULL singleton

- `OnDestroy` **does not unconditionally clear `Instance`**; when the current object matches `Instance`, a normal cleanup path writes `this` to the field. That could leave a stale pointer to a destroyed Unity object. Caution: Unity's managed object identity, fake-null semantics, other object lifecycles, and other writers must be studied before predicting a live runtime value.
- The original **NULL** observed in PS4Debug main menu/gameplay is therefore **not explained by a claim that OnDestroy always sets Instance=null**. A prior `Awake` path reads the `Cheats.DebugConsole` guard and can destroy the component before assigning `Instance`. This remains **plausible, not proven causally**, because the flag was never read in that session.
- This remains **NO-GO** for an external IMGUI bridge: neither `OnDestroy` nor `GetInstance` registers a standalone PRX callback or creates a valid Unity object.

## Corroboration on the remaining type-ref slot

- The type-reference slot `0x33EB300` that `DebugConsole.Awake` examines as `class.static_fields+0x01` is also read in the original PS4 native method `<LoadingDone>c__Iterator0.MoveNext` at `0x01894698`–`0x018946C4`, where the byte `[static_fields+0x01]` is compared with zero. That generated iterator belongs to the `CoopPeerStarter` code area, and metadata includes `CoopPeerStarter.DedicatedHost` as a field.
- This provides an **independent contextual native reference supporting the hypothesis** that `0x33EB300` is `CoopPeerStarter` and `+0x01` is `DedicatedHost`. **It is not yet an exact class/type-registration mapping**; keep the slot as candidate pending direct registration evidence.
- The Rewired interface/type slot `0x33EF3E8` remains unresolved; `ProcessGamePads` at `0x00476279` loads this slot for interface-map lookup and calls indirectly at `0x004762D6`/`0x00476315`. A branch into a virtual-dispatch table is not proof of a particular method or ScePad function.

## Follow-up status

The manifest [`PS4_ONDESTROY_EXPECTATIONS.json`](PS4_ONDESTROY_EXPECTATIONS.json)
and the unified offline pipeline now record the method index/RVA and distinguish
the `Counters=0` store from the `Instance=this` store. Synthetic tests verify
that a zero source at the Instance site is rejected as the documented
write-back. They do not replace the original-binary analysis or verify runtime
invocation.

The remaining integration decision is explicit in
[`INTEGRATION_DECISION.md`](INTEGRATION_DECISION.md): no AOT component loader,
Unity callback registration route, or safe title-owned host has been
demonstrated from the GoldHEN PRX under the current constraints. No hook-enabled
PRX or console trial is part of that decision. Rewired type registration and
the exact input methods remain unresolved.

**Evidence classification:** OnDestroy RVA/index and assembly instructions were verified against the original private PS4 PRX + metadata. Only `OnGUI` and `ToggleConsole` entry signatures were previously physically verified in a real PS4Debug session. Nothing above verifies Unity runtime state or makes a new hardware test safe.
