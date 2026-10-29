#!/bin/sh
set -eu
printf 'The Forest UCM PS4 - Catalina build preflight\n\n'
printf 'macOS: '; sw_vers -productVersion
printf 'CPU: '; uname -m
for tool in clang make git python3; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '%s: %s\n' "$tool" "$(command -v "$tool")"
  else
    printf '%s: NOT INSTALLED\n' "$tool"
  fi
done
printf 'Xcode CLT: '
xcode-select -p 2>/dev/null || printf 'NOT CONFIGURED\n'
printf 'OO_PS4_TOOLCHAIN: %s\n' "${OO_PS4_TOOLCHAIN:-NOT CONFIGURED}"
printf 'GOLDHEN_SDK: %s\n' "${GOLDHEN_SDK:-NOT CONFIGURED}"
printf 'No files or console memory were modified.\n'
