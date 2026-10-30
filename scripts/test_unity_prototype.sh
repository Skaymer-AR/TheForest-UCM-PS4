#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if ! command -v mcs >/dev/null 2>&1 || ! command -v mono >/dev/null 2>&1; then
    echo "Mono C# compiler and runtime required (mcs, mono)" >&2
    exit 2
fi
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM
model=prototype/Unity56/Assets/UCM/UcmMenuModel.cs
host=prototype/Unity56/Assets/UCM/UltimateMenuHost.cs
mcs -nologo -warnaserror -langversion:4 -out:"$tmpdir/menu-tests.exe" \
    "$model" tests/csharp/UcmMenuModelTests.cs
mono "$tmpdir/menu-tests.exe"
# Compiles the Unity host with synthetic engine symbols, in and out of EDITOR mode.
# Does NOT prove compilation against real Unity 5.6/PS4 assemblies or IL2CPP AOT.
mcs -nologo -warnaserror -langversion:4 -target:library \
    -out:"$tmpdir/host.dll" "$model" "$host" tests/csharp/UnityEngineStub.cs
mcs -nologo -warnaserror -langversion:4 -define:UNITY_EDITOR -target:library \
    -out:"$tmpdir/editor-host.dll" "$model" "$host" tests/csharp/UnityEngineStub.cs
echo "UCM Unity-host stub compilation: PASS (standalone + UNITY_EDITOR)"
