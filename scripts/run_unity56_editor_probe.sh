#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

if [ -z "${UNITY_566F2_EDITOR:-}" ] || [ ! -x "$UNITY_566F2_EDITOR" ]; then
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

project="$(pwd)/prototype/Unity56SerializationProject"
output=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$UCM_UNITY_PROBE_OUTPUT")
mkdir -p "$output"
if [ -n "$(find "$output" -mindepth 1 -print -quit)" ]; then
    echo "UCM_UNITY_PROBE_OUTPUT must be empty to prevent stale artifacts being accepted." >&2
    exit 2
fi
export UCM_UNITY_PROBE_OUTPUT="$output"

"$UNITY_566F2_EDITOR" -batchmode -quit -projectPath "$project" \
    -executeMethod UcmUnitySerializationProbe.SyntheticSerializationDriver.RunBatch \
    -logFile "$output/unity-editor.log"

python3 scripts/validate_unity_editor_probe.py "$output"

dotnet build tools/UnityFormat17Validator/UnityFormat17Validator.csproj \
    --configuration Release
validator="$(pwd)/tools/UnityFormat17Validator/bin/Release/net10.0/UnityFormat17Validator.dll"
python3 scripts/validate_unity_editor_probe.py "$output" \
    --classdata-tpk "$CLASSDATA_TPK" \
    --validator-dll "$validator" \
    --dotnet dotnet
