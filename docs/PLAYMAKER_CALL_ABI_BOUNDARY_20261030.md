# PS4 PlayMaker → Unity GUI / Rewired native calling evidence

**Verified offline against the original CUSA12398 v1.15 IL2CPP ELF and
global metadata, with matching SHA-256. No game memory or PKG was changed.**
Run `scripts/verify_playmaker_call_contract.py --module <private-elf>
--metadata <private-global-metadata>`.

The verifier checks **six exact managed method definitions** (owner,
methodIndex, native VA, explicit managed parameter count and virtual slot
where applicable) and **18 native instruction sites**. The following
three observations were checked in the actual reconstructed title ELF:

| Observed site | Native evidence | What it establishes |
| --- | --- | --- |
| `0x01141397` + `0x0114139E` | `CallOnGUI` loads an existing action vtable's `MethodInfo` at `+0x328` and invokes its OnGUI pointer at `+0x320` | IL2CPP virtual action calls require a valid managed instance and method metadata; the indirection is **not** an external registration mechanism |
| `0x02383DDF`–`0x02383DF6`, callee `0x019BE766`–`0x019BE773` | Compiled `GUIButton.OnGUI` passes the two Rect halves in XMM0/XMM1; `UnityEngine.GUI.Button` immediately preserves both XMM arguments and reads pointer registers. The metadata overload has **three explicit managed parameters**. | Demonstrates a **specific in-title caller/callee convention**, not an ABI safe to synthesize from a PRX |
| `0x02537567`–`0x0253757B` | `GetButtonDown.OnUpdate` obtains a Player reference via a runtime static slot and calls `Rewired.Player.GetButtonDown`, which metadata reports as a **one-parameter** overload | The compiled game can reach Rewired from PlayMaker; it does **not** prove who owns the Player, which controller map is selected or the physical DS4 bindings |

## Engineering decision

A call to `PlayMakerGUI.CallOnGUI` is **not** an insertion API for native
PRX code. Its action and vtable method-info pointers belong to IL2CPP
managed objects. Adding a foreign function without a registered, game-owned
action, valid lifetime, Unity event/thread, method-info and safe detachment
would be an unsafe new architecture. None of that is authorized or proved.

The host-only `src/unity_host_adapter.*` now refuses raw ScePad snapshots;
its ABI v2 requires live verified local Rewired Player ownership, ControllerMap,
focus and scene ownership. This contract is covered by synthetic C tests.
No title-owned provider of it exists yet.

**Next concrete prerequisite:** a verified title-owned mechanism to
create/register an isolated managed action or frame callback without
editing the commercial PKG or patching shared native code; otherwise the
original complete IL2CPP rebuild pipeline is needed. This remains G2/G3/G4,
not a PS4-ready PRX. Tests do not attest actual game runtime behavior.
