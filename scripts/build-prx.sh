#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
: "${OO_PS4_TOOLCHAIN:?Set OpenOrbis toolchain path}"
: "${GOLDHEN_SDK:?Set GoldHEN SDK path}"
: "${GOLDHEN_TEMPLATE:?Set official GoldHEN Plugins Repository path}"

python3 scripts/assert-safe-build.py
sh scripts/test.sh
# Build only the CRT object required by the official template. Do not build or
# link the GoldHEN hook library for this no-hook baseline.
if [ ! -f "$GOLDHEN_SDK/build/crtprx.o" ]; then
  make -C "$GOLDHEN_SDK" crt
fi
build_dir=$(mktemp -d)
mkdir -p output/safe

# No hook library is linked. The host lifecycle model and tests are excluded.
profile_root="$build_dir/no_hooks"
mkdir -p "$profile_root"
cp -R "$GOLDHEN_TEMPLATE/." "$profile_root/"
template="$profile_root/plugin_src/plugin_template"
mkdir -p "$template/include"
cp source/plugin_main.c "$template/source/main.c"
cp source/ps4_backend.c "$template/source/"
cp source/ps4_backend.h "$template/include/"

python3 - "$template/Makefile" <<'PY'
import pathlib
import sys

makefile = pathlib.Path(sys.argv[1])
lines = makefile.read_text().splitlines()
found_cflags = False
found_libs = False
for index, line in enumerate(lines):
    if line.startswith("CFLAGS      :="):
        lines[index] = f"{line} -DUCM_DIAG_PROFILE=4"
        found_cflags = True
    elif line.startswith("LIBS :="):
        lines[index] = "LIBS := -lSceLibcInternal -lkernel -lSceSysmodule"
        found_libs = True
if not found_cflags or not found_libs:
    raise SystemExit("GoldHEN template Makefile layout changed")
makefile.write_text("\n".join(lines) + "\n")
PY

mkdir -p "$profile_root/bin/plugins/prx_final" \
  "$profile_root/bin/plugins/elf_final"
make -C "$template" DEBUG=0
elf="$profile_root/bin/plugins/elf_final/plugin_template.elf"
if nm "$elf" | grep -E '(^|[[:space:]])(Detour_|sceKernelMprotect)' >/dev/null; then
  echo "Unsafe detour/patch symbol reached the no-hook PRX ELF" >&2
  exit 1
fi
install -m644 "$profile_root/bin/plugins/prx_final/plugin_template.prx" \
  "output/safe/theforest_ucm_safe_baseline.prx"

(cd output/safe && sha256sum theforest_ucm_safe_baseline.prx > sha256.txt)
file output/safe/*.prx
cat output/safe/sha256.txt
