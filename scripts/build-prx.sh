#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
: "${OO_PS4_TOOLCHAIN:?Set OpenOrbis toolchain path}"
: "${GOLDHEN_SDK:?Set GoldHEN SDK path}"
: "${GOLDHEN_TEMPLATE:?Set official GoldHEN Plugins Repository path}"
sh scripts/test.sh
make -C "$GOLDHEN_SDK" PRINTF=1
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
opengnm_revision=4b295ca54c82c83acf308d1c646a2dfa9ae57350
opengnm_dir="$build_dir/opengnm"
if [ -n "${OPENGNM_SOURCE:-}" ]; then
  cp -R "$OPENGNM_SOURCE" "$opengnm_dir"
else
  git clone --no-checkout https://github.com/PS4-OpenGNM/opengnm.git "$opengnm_dir"
  git -C "$opengnm_dir" checkout --detach "$opengnm_revision"
fi
actual_revision=$(git -C "$opengnm_dir" rev-parse HEAD)
if [ "$actual_revision" != "$opengnm_revision" ]; then
  printf 'OpenGNM revision mismatch: expected %s, got %s\n' \
    "$opengnm_revision" "$actual_revision" >&2
  exit 1
fi
cp "$opengnm_dir/config.orbis.mak" "$opengnm_dir/config.mak"
make -C "$opengnm_dir" PLATFORM=orbis \
  "TOOLCHAIN=$OO_PS4_TOOLCHAIN" CC=clang AR=llvm-ar \
  "CFLAGS=--target=x86_64-pc-freebsd12-elf -std=c11 -Wall -Wextra -fPIC -O2 -g -DOPENGNM_ORBIS -I$opengnm_dir/include -I$opengnm_dir/src -isysroot $OO_PS4_TOOLCHAIN -isystem $OO_PS4_TOOLCHAIN/include"
cp -R "$GOLDHEN_TEMPLATE/." "$build_dir/"
template="$build_dir/plugin_src/plugin_template"
mkdir -p "$template/include"
cp source/plugin_main.c "$template/source/main.c"
cp source/ps4_backend.c "$template/source/"
cp src/menu.c src/overlay.c src/drawlist.c "$template/source/"
cp source/ps4_backend.h src/menu.h src/overlay.h src/drawlist.h \
  "$template/include/"
python3 - "$template/Makefile" "$opengnm_dir" <<'PY'
import pathlib
import sys

makefile = pathlib.Path(sys.argv[1])
opengnm = pathlib.Path(sys.argv[2])
lines = makefile.read_text().splitlines()
for index, line in enumerate(lines):
    if line.startswith("CFLAGS      :="):
        lines[index] = f"{line} -I{opengnm / 'include'}"
    elif line.startswith("LIBS :="):
        lines[index] = (
            "LIBS := -lSceLibcInternal -lGoldHEN_Hook "
            f"-L{opengnm} -lopengnm -lkernel -lSceSysmodule "
            "-lSceGnmDriver -lSceVideoOut -lScePad"
        )
makefile.write_text("\n".join(lines) + "\n")
PY
mkdir -p "$build_dir/bin/plugins/prx_final" "$build_dir/bin/plugins/elf_final"
make -C "$template" DEBUG=0
install -m644 "$build_dir/bin/plugins/prx_final/plugin_template.prx" output/theforest_ucm.prx
(cd output && sha256sum theforest_ucm.prx > sha256.txt)
file output/theforest_ucm.prx
cat output/sha256.txt
