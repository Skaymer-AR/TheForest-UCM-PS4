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
cp -R "$GOLDHEN_TEMPLATE/." "$build_dir/"
template="$build_dir/plugin_src/plugin_template"
mkdir -p "$template/include"
cp source/plugin_main.c "$template/source/main.c"
cp src/menu.c src/overlay.c "$template/source/"
cp src/menu.h src/overlay.h "$template/include/"
mkdir -p "$build_dir/bin/plugins/prx_final" "$build_dir/bin/plugins/elf_final"
make -C "$template" DEBUG=0
install -m644 "$build_dir/bin/plugins/prx_final/plugin_template.prx" output/theforest_ucm_probe.prx
sha256sum output/theforest_ucm_probe.prx > output/sha256.txt
file output/theforest_ucm_probe.prx
cat output/sha256.txt
