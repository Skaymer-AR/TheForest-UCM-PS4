#!/usr/bin/env python3
"""Prevent accidental regeneration of dangerous v0.5/v0.6 hook artifacts."""
from pathlib import Path
backend = Path("source/ps4_backend.c").read_text()
build = Path("scripts/build-prx.sh").read_text()
workflow = Path(".github/workflows/build-prx.yml").read_text()
assert "Detour_" not in backend, "A detour was reintroduced into safe backend"
assert "sceKernelMprotect" not in backend, "Memory patching in safe backend"
assert '#error "Unsafe hook profile disabled' in backend
assert "for profile in no_hooks:4; do" in build, "Build must emit only no-hooks"
assert "theforest_ucm_safe_baseline.prx" in build
assert "theforest-ucm-safe-baseline-only" in workflow
assert "output/safe/" in workflow
print("Safe build gate: PASS (no hooks, one baseline artifact)")
