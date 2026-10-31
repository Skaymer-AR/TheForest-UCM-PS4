#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

if [ -z "${UNITY_566F2_EDITOR:-}" ]; then
    echo "Set UNITY_566F2_EDITOR to an executable, licensed Unity 5.6.6f2 Editor." >&2
    exit 2
fi
if [ -z "${CLASSDATA_TPK:-}" ] || [ ! -f "$CLASSDATA_TPK" ]; then
    echo "Set CLASSDATA_TPK to the pinned UABEA v8 classdata.tpk file." >&2
    exit 2
fi
if [ -z "${UCM_UNITY_PROBE_OUTPUT:-}" ]; then
    echo "Set UCM_UNITY_PROBE_OUTPUT to an output directory outside the project." >&2
    exit 2
fi
if ! command -v dotnet >/dev/null 2>&1; then
    echo ".NET SDK 10.0.100 (latest patch) is required for AssetsTools.NET." >&2
    exit 2
fi

output=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$UCM_UNITY_PROBE_OUTPUT")
mkdir -p "$output"
if [ -n "$(find "$output" -mindepth 1 -print -quit)" ]; then
    echo "UCM_UNITY_PROBE_OUTPUT must be empty to prevent stale artifacts being accepted." >&2
    exit 2
fi
python3 scripts/run_unity56_editor_stage.py --editor "$UNITY_566F2_EDITOR" --output "$output"
generated="$output/generated"

dotnet build tools/UnityFormat17Validator/UnityFormat17Validator.csproj \
    --configuration Release
validator="$(pwd)/tools/UnityFormat17Validator/bin/Release/net10.0/UnityFormat17Validator.dll"
python3 scripts/validate_unity_editor_probe.py "$generated" \
    --classdata-tpk "$CLASSDATA_TPK" \
    --validator-dll "$validator" \
    --dotnet dotnet
echo "Complete Unity 5.6.6f2 → AssetsTools.NET → Python probe: PASS"
