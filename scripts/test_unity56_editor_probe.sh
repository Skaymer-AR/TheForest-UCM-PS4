#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if ! command -v mcs >/dev/null 2>&1 || ! command -v mono >/dev/null 2>&1; then
    echo "Mono C# compiler and runtime required (mcs, mono)" >&2
    exit 2
fi
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM
project=prototype/Unity56SerializationProject
mcs -nologo -warnaserror -langversion:4 -target:library \
    -out:"$tmpdir/unity56-editor-probe-stubs.dll" \
    tests/csharp/Unity56EditorProbeStubs.cs \
    "$project/Assets/Scripts/SyntheticProbeState.cs" \
    "$project/Assets/Scripts/SyntheticProbeTarget.cs" \
    "$project/Assets/Scripts/SyntheticMenuHost.cs" \
    "$project/Assets/Editor/SyntheticSerializationDriver.cs"
echo "Unity 5.6.6f2 Editor probe: C# 4 stub compilation PASS (not an Editor run)"
