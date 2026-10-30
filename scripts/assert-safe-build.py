#!/usr/bin/env python3
"""Prevent accidental regeneration of dangerous v0.5/v0.6 hook artifacts."""
from pathlib import Path
backend = Path("source/ps4_backend.c").read_text()
build = Path("scripts/build-prx.sh").read_text()
workflow = Path(".github/workflows/build-prx.yml").read_text()
plugin_main = Path("source/plugin_main.c").read_text()
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
assert "archive/" not in build, "Archived unsafe code must never enter PRX build"
assert 'make -C "$GOLDHEN_SDK" crt' in build, \
    "Safe build must compile only the template CRT target"
assert "nm \"$elf\"" in build and "Detour_|sceKernelMprotect" in build, \
    "Post-link gate must reject detour and patch symbols"
assert "theforest_ucm_safe_baseline.prx" in build
assert "theforest-ucm-safe-baseline-only" in workflow
assert "output/safe/" in workflow
assert "output/safe/theforest_ucm_safe_baseline.prx" in workflow
assert "output/safe/*.prx" not in workflow, "Artifact upload must name only the safe PRX"
assert "NO HOOKS" in plugin_main
assert "sceKernelGetAppInfo" in plugin_main
assert "sys_sdk_proc_info" not in plugin_main
assert "hooks restored" not in plugin_main, "No-hook unload must not claim hooks restored"
for forbidden in ("passive_all", "videoout_only", "pad_read_state_only",
                  "theforest-ucm-diagnostic-prx"):
    assert forbidden not in workflow, f"Unsafe profile found in Actions: {forbidden}"
print("Safe build gate: PASS (no hooks, one PRX baseline artifact)")
