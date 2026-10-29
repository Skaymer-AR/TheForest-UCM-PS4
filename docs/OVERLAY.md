# Startup-hook diagnostic (v0.6)

## Hardware report and safety scope

The user reported that v0.5's PRX notification appeared but The Forest stayed
black after its title screen. The PS4 shell remained responsive, and the
previous no-hook probe had entered a playable session. Because v0.5 installed
the GNM submit hook on every load, allocated a direct-memory command buffer,
and could append GPU work at frame submission, GNM is the first path removed
for diagnosis. That source finding makes GNM a leading suspect; only the
hardware profile tests can establish causation.

This v0.6 diagnostic has no GNM include, import, hook, command buffer, or
rendering path. It does not capture or dereference the registered framebuffer
addresses. It makes no Unity calls or gameplay changes. The build has five
compile-time profiles:

| Profile | VideoOut | PadReadState | PadRead | GNM / render / framebuffer |
| --- | --- | --- | --- | --- |
| `passive_all` | On | On | On | Off |
| `videoout_only` | On | Off | Off | Off |
| `pad_read_state_only` | Off | On | Off | Off |
| `pad_read_only` | Off | Off | On | Off |
| `no_hooks` | Off | Off | Off | Off |

The `passive_all` profile is the first test. If the black screen remains, the
single-hook builds separate VideoOut, `scePadReadState`, and `scePadRead`.
The `no_hooks` profile is an additional control. None of these PRXs is meant
to display the menu.

## ABI and detour checks

The observer signatures match the public OpenOrbis declarations:

- `sceVideoOutRegisterBuffers(int32_t, int32_t, void *const *, int32_t,
  const OrbisVideoOutBufferAttribute *)` from
  `include/orbis/VideoOut.h`.
- `scePadReadState(int32_t, OrbisPadData *)` and
  `scePadRead(int32_t, OrbisPadData *, int32_t)` from
  `include/orbis/Pad.h`.
- `OrbisPadData.buttons` and `.connected` from
  `include/orbis/_types/pad.h`.
- VideoOut attribute field order and types from
  `include/orbis/_types/video.h`. Because the OpenOrbis header includes a
  C++-only fixed-underlying-type enum, the C backend mirrors this struct and
  statically asserts its 0x28-byte size and key offsets.

The function addresses are the linked `libSceVideoOut` and `libScePad` imports;
there are no hard-coded game addresses. GoldHEN SDK `Detour_DetourFunction`
returns `Detour.StubPtr`, the copied original instructions plus a jump back;
`Detour.TrampolinePtr` is the entrypoint's jump relay, not the call-through.
The backend checks that the returned pointer, target, hook, mode and allocated
detour fields agree before accepting installation.

There is a small publication race inherent in the GoldHEN API: the detour
patches the target before returning its original-call stub. The hook callbacks
atomically wait for that stub to be published before calling the original, so
they cannot call a null pointer if another game thread reaches the new entry
immediately. If a later hook fails to install, earlier entrypoints are
restored in reverse order. On unload, entrypoints are restored first, the
callback count drains, and then the stub and jump-relay mappings are released.

## Callback and logging behavior

Every observer calls the original API with the same arguments and returns its
result unchanged. Afterward it updates only atomic counters and the latest
result/sample fields. It never logs from a VideoOut or pad callback, allocates,
waits on a lock, stores output-buffer addresses, or blocks on graphics work.
The PRX prints one bounded profile line at load and one callback summary at
unload through the plugin-management path.

## Feature status

| Capability | v0.6 diagnostic status |
| --- | --- |
| Show in-game UCM panel | Disabled; no renderer in the diagnostic build |
| GNM submit/flip hook | Disabled in every profile |
| Framebuffer reads/writes | Disabled in every profile |
| VideoOut observation | Enabled only by profiles above |
| ScePad observation | Enabled only by profiles above |
| Menu input/control | Disabled; this build is not an in-game menu |
| God Mode, stamina, hunger/thirst, inventory, free building, teleport, spawn, time/weather | Not implemented; no gameplay writes |

Portable tests and cross-compilation check the source/build only. The PS4
black-screen regression remains unverified until the user reports the result
of each required profile on firmware 12.02 / GoldHEN 2.4B18.9. No renderer is
claimed functional at this stage.

## Install and remove

Download the `theforest-ucm-diagnostic-prx` Actions artifact, check
`sha256.txt`, and install one PRX at a time under
`/data/GoldHEN/plugins/theforest_ucm_diag.prx`. The `[CUSA12398]` entry in
`/data/GoldHEN/plugins.ini` must point to that path. Start with
`passive_all`, then use each isolated profile if needed. Use an offline
single-player session.

Unload from GoldHEN, remove the entry from `plugins.ini`, delete the installed
PRX, and restart to roll back. The PRX does not modify eboot, PKG, saves, game
memory, or unknown `DebugConsole` flags.
