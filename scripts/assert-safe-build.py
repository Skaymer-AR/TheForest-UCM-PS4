#!/usr/bin/env python3
"""Guard the hook-free source and offline-only workflow boundary."""
from pathlib import Path
backend = Path("source/ps4_backend.c").read_text()
build = Path("scripts/build-prx.sh").read_text()
workflow = Path(".github/workflows/offline-integration.yml").read_text()
plugin_main = Path("source/plugin_main.c").read_text()
adapter = Path("src/unity_host_adapter.c").read_text()
assert "Detour_" not in backend, "A detour was reintroduced into safe backend"
assert "sceKernelMprotect" not in backend, "Memory patching in safe backend"
for forbidden in ("sceGnm", "sceVideoOut", "scePad",
                  "sceKernelMapDirectMemory", "sceKernelAllocateDirectMemory",
                  "sceGnmDrawCmdFillMemory"):
    assert forbidden not in backend, f"Unsafe backend reference found: {forbidden}"
assert '#error "Unsafe hook profile disabled' in backend
assert "profile_root=\"$build_dir/no_hooks\"" in build, \
    "Build must emit only the no-hooks backend"
assert "UCM_DIAG_PROFILE=4" in build, "Build must reject hook profiles"
assert "Detour.c" not in build, "Safe build must not compile detour source"
assert "-lGoldHEN_Hook" not in build, "Safe PRX must not link hook SDK"
assert "-lSceVideoOut" not in build and "-lScePad" not in build
assert "src/bridge_lifecycle" not in build and "tests/" not in build, \
    "Host lifecycle model/tests must never enter PRX build"
assert "src/unity_host_adapter" not in build and "src/pad_input_map" not in build, \
    "Host-only Unity adapter and pad mapper must never enter PRX build"
for forbidden in ("Detour_", "sceGnm", "sceVideoOut", "scePadOpen",
                  "scePadReadState", "scePadClose", "UnityEngine"):
    assert forbidden not in adapter, \
        f"Host adapter must not call or detour platform/game APIs: {forbidden}"
assert "archive/" not in build, "Archived unsafe code must never enter PRX build"
assert '"$GOLDHEN_SDK/crt/crtprx.c"' in build, \
    "Safe build must compile only the official template CRT source"
assert 'make -C "$GOLDHEN_SDK"' not in build, \
    "Safe build must not run the aggregate hook SDK build"
assert "nm \"$elf\"" in build and "Detour_|sceKernelMprotect" in build, \
    "Post-link gate must reject detour and patch symbols"
assert "theforest_ucm_safe_baseline.prx" in build
assert "offline-integration.yml" in workflow
assert "SANITIZE=1 sh scripts/test.sh" in workflow
assert "scripts/build-prx.sh" not in workflow, "This workflow must not emit a notification-only PRX"
assert "upload-artifact" not in workflow, "Offline analysis workflow must not publish PRX artifacts"
assert "theforest-ucm-safe-baseline-only" not in workflow
assert "compile-prx:" not in workflow
assert "NO HOOKS" in plugin_main
assert "sceKernelGetAppInfo" in plugin_main
assert "sys_sdk_proc_info" not in plugin_main
assert "hooks restored" not in plugin_main, "No-hook unload must not claim hooks restored"
for forbidden in ("passive_all", "videoout_only", "pad_read_state_only",
                  "theforest-ucm-diagnostic-prx"):
    assert forbidden not in workflow, f"Unsafe profile found in Actions: {forbidden}"
print("Safe build gate: PASS (hook-free source; offline-only CI; no PRX artifact)")
