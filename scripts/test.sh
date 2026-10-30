#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p output
${CC:-cc} -std=c11 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -Isrc src/menu.c tests/test_menu.c -o output/test_menu
output/test_menu
${CC:-cc} -std=c11 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -Isrc src/menu.c src/overlay.c tests/test_overlay.c -o output/test_overlay
output/test_overlay
${CC:-cc} -std=c11 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -Isrc src/menu.c src/overlay.c tests/preview_overlay.c -o output/preview_overlay
output/preview_overlay > output/overlay-preview.svg
${CC:-cc} -std=c11 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -Isrc src/drawlist.c tests/test_drawlist.c -lm -o output/test_drawlist
output/test_drawlist
${CC:-cc} -std=c11 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -pthread -Isrc src/bridge_lifecycle.c tests/test_bridge_lifecycle.c -o output/test_bridge_lifecycle
output/test_bridge_lifecycle
${CC:-cc} -std=c11 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -pthread -Isrc src/menu.c src/overlay.c src/pad_input_map.c src/unity_host_adapter.c tests/test_unity_host_adapter.c -o output/test_unity_host_adapter
output/test_unity_host_adapter
${CC:-cc} -std=c11 -Wall -Wextra -Werror ${TEST_CFLAGS:-} -Isrc src/native_playmaker_preflight.c tests/test_native_playmaker_preflight.c -o output/test_native_playmaker_preflight
output/test_native_playmaker_preflight
python3 -m unittest discover -s tests -p 'test_*.py'
if [ "${SANITIZE:-0}" = "1" ]; then
  ${CC:-cc} -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -Isrc src/native_playmaker_preflight.c tests/test_native_playmaker_preflight.c -o output/test_native_playmaker_preflight_sanitized
  output/test_native_playmaker_preflight_sanitized
  ${CC:-cc} -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -Isrc src/menu.c tests/test_menu.c -o output/test_menu_sanitized
  output/test_menu_sanitized
  ${CC:-cc} -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -Isrc src/menu.c src/overlay.c tests/test_overlay.c -o output/test_overlay_sanitized
  output/test_overlay_sanitized
  ${CC:-cc} -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -Isrc src/drawlist.c tests/test_drawlist.c -lm -o output/test_drawlist_sanitized
  output/test_drawlist_sanitized
  ${CC:-cc} -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -pthread -Isrc src/bridge_lifecycle.c tests/test_bridge_lifecycle.c -o output/test_bridge_lifecycle_sanitized
  output/test_bridge_lifecycle_sanitized
  ${CC:-cc} -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -pthread -Isrc src/menu.c src/overlay.c src/pad_input_map.c src/unity_host_adapter.c tests/test_unity_host_adapter.c -o output/test_unity_host_adapter_sanitized
  output/test_unity_host_adapter_sanitized
fi
