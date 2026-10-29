#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
: "${OO_PS4_TOOLCHAIN:?Set OpenOrbis toolchain path}"
: "${GOLDHEN_SDK:?Set GoldHEN SDK path}"
: "${GOLDHEN_TEMPLATE:?Set official GoldHEN Plugins Repository path}"

sh scripts/test.sh
make -C "$GOLDHEN_SDK" PRINTF=1
build_dir=$(mktemp -d)
mkdir -p output/diagnostics

# Each profile has GNM submission, rendering, framebuffer writes and game
# memory changes compiled out. These artifacts isolate the remaining API
# observers after the combined passive profile is tried first on hardware.
for profile in passive_all:0 videoout_only:1 pad_read_state_only:2 pad_read_only:3 no_hooks:4; do
  profile_name=${profile%%:*}
  profile_id=${profile#*:}
  profile_root="$build_dir/$profile_name"
  mkdir -p "$profile_root"
  cp -R "$GOLDHEN_TEMPLATE/." "$profile_root/"
  template="$profile_root/plugin_src/plugin_template"
  mkdir -p "$template/include"
  cp source/plugin_main.c "$template/source/main.c"
  cp source/ps4_backend.c "$template/source/"
  cp source/ps4_backend.h "$template/include/"

  python3 - "$template/Makefile" "$profile_id" <<'PY'
import pathlib
import sys

makefile = pathlib.Path(sys.argv[1])
profile_id = sys.argv[2]
lines = makefile.read_text().splitlines()
found_cflags = False
found_libs = False
for index, line in enumerate(lines):
    if line.startswith("CFLAGS      :="):
        lines[index] = f"{line} -DUCM_DIAG_PROFILE={profile_id}"
        found_cflags = True
    elif line.startswith("LIBS :="):
        lines[index] = (
            "LIBS := -lSceLibcInternal -lGoldHEN_Hook "
            "-lkernel -lSceSysmodule -lSceVideoOut -lScePad"
        )
        found_libs = True
if not found_cflags or not found_libs:
    raise SystemExit("GoldHEN template Makefile layout changed")
makefile.write_text("\n".join(lines) + "\n")
PY

  mkdir -p "$profile_root/bin/plugins/prx_final" \
    "$profile_root/bin/plugins/elf_final"
  make -C "$template" DEBUG=0
  install -m644 "$profile_root/bin/plugins/prx_final/plugin_template.prx" \
    "output/diagnostics/theforest_ucm_${profile_name}.prx"
done

(cd output/diagnostics && sha256sum theforest_ucm_*.prx > sha256.txt)
file output/diagnostics/*.prx
cat output/diagnostics/sha256.txt
