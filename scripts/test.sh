#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p output
${CC:-cc} -std=c99 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -Isrc src/menu.c tests/test_menu.c -o output/test_menu
output/test_menu
${CC:-cc} -std=c99 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -Isrc src/menu.c src/overlay.c tests/test_overlay.c -o output/test_overlay
output/test_overlay
${CC:-cc} -std=c99 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -Isrc src/menu.c src/overlay.c tests/preview_overlay.c -o output/preview_overlay
output/preview_overlay > output/overlay-preview.svg
