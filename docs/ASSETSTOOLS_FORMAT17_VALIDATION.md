# Unity serialized format 17: independent synthetic validation

This check addresses a narrow tooling gap: the repository's Python reader and
fixture generator previously tested the same assumptions. A separate .NET
program now reads, edits, writes, and rereads a small generated serialized-file
graph with AssetsTools.NET. No The Forest asset, executable, metadata, or PKG is
an input to this workflow.

## Pinned inputs

- .NET SDK: `10.0.100`, fixed in `global.json` (latest patch roll-forward only).
- AssetsTools.NET: NuGet `3.0.5`, fixed in
  `tools/UnityFormat17Validator/UnityFormat17Validator.csproj`.
  NuGet lists no dependencies for its `netstandard2.0` target, which is the
  target consumed by this `net10.0` validator. NuGet listed `3.0.5` as the
  latest stable package on 2026-10-31 (updated 2026-07-22).
- Unity class database: `classdata.tpk` extracted from the Linux UABEA v8
  release archive. CI verifies the archive SHA-256
  `c542dd3b5b091b34645ee1c7180df7138f9f3fe5253222f151d7185e542402b2` and
  extracted TPK SHA-256
  `129e1f80f930415db6779fe6089afa75280cb51462bcee812beab6cd81a764c6` before
  loading it for Unity `5.6.6f2`. Neither download is committed.

AssetsTools.NET documents class databases for files without embedded type
trees and exposes serialized-file writing; the CI job exercises those APIs
against the fixture rather than treating API availability as compatibility
proof. References: [AssetsTools.NET 3.0.5](https://www.nuget.org/packages/AssetsTools.NET/3.0.5),
[reading assets](https://github.com/nesrak1/AssetsTools.NET/wiki/Getting-Started:-Assets-file-reading),
[writing assets](https://github.com/nesrak1/AssetsTools.NET/wiki/Getting-Started:-Assets-file-writing),
and the [UABEA v8 release](https://github.com/nesrak1/UABEA/releases/tag/v8).

## Fixture graph

`scripts/unity_format17_fixture.py` deterministically generates two files. Both
declare Unity `5.6.6f2`, serialized format `17`, little-endian data, and no
embedded TypeTree.

| File | Synthetic objects | Relevant links |
| --- | --- | --- |
| `synthetic_scene.assets` | GameObject PathID 100; Transform 200; generic MonoBehaviour 300 | GameObject component PPtrs target 200 and 300; Transform and MonoBehaviour point back to GameObject 100; MonoBehaviour script PPtr is external fileID 1 / PathID 900 |
| `synthetic_library.assets` | MonoScript PathID 900 | Synthetic class, namespace, and assembly names only |

The scene's type table, script-type table, external dependency, object offsets,
and PathIDs are generated together. The Transform includes fixed position and
scale values and a root hierarchy. The MonoBehaviour contains only the Unity
base fields understood by this fixture and a synthetic MonoScript reference.
It intentionally has no PlayMaker payload and does not encode or guess the
unresolved 40-byte `Fsm` tail.

## MonoScript class database schema

The independently downloaded UABEA v8 `classdata.tpk`, loaded for Unity
`5.6.6f2`, reports this `MonoScript` field order: `m_Name`,
`m_ExecutionOrder`, `m_PropertiesHash` (16 bytes), `m_ClassName`,
`m_Namespace`, `m_AssemblyName`, and the final `m_IsEditorScript` boolean.
The first AssetsTools.NET run exposed an omitted terminal boolean in the initial
synthetic payload as `EndOfStreamException` while reading `m_IsEditorScript`.
The fixture now serializes that byte as `false`; the independent reader checks
the field, while the Python reader rejects a missing/invalid flag or trailing
bytes. This schema evidence comes from the pinned class database and is limited
to its Unity 5.6.6f2 entry; it does not identify a PlayMaker package version.

## Automated validation

The `assetstools-format17` GitHub Actions job:

1. Verifies and loads the pinned `classdata.tpk` for Unity `5.6.6f2`.
2. Generates the fixture and checks it with the repository's Python reader.
3. Loads both files through AssetsTools.NET and resolves GameObject,
   Transform, MonoBehaviour, MonoScript, component PPtrs, script PPtr, script
   type index, and external dependency.
4. Checks format/version, metadata/data offsets, file size, object bounds,
   type indices, unique PathIDs, and the expected serialized field values.
5. Changes only the synthetic GameObject name via `SetNewData`, writes both
   files with `AssetsFile.Write`, and rereads them through AssetsTools.NET.
6. Checks the rewritten files again with the Python reader, including the
   expected name and references.

Python unit tests also verify deterministic generation and reject a truncated
file, an invalid data offset, an out-of-bounds object descriptor, duplicate
PathIDs, a dangling component PPtr, and an out-of-range dependency index. These
negative tests exercise the repository parser and validator; the positive
round-trip is independently performed by AssetsTools.NET.

## Evidence boundary

The successful CI job demonstrates that the pinned AssetsTools.NET build can
parse the generated format-17 header, deserialize the listed built-in fields
using its class database, rewrite serialized files, and preserve the checked
graph on reread. Python then independently checks that the generated output
still matches the expected graph.

It does **not** demonstrate that Unity Editor accepts or imports these files.
The `MonoScript` identifies a fixture-only class and assembly that are not
provided, and the MonoBehaviour carries no corresponding executable script
payload. This is a structural reader/writer fixture, not an importable Unity
component.

This base fixture does **not** validate a PlayMakerFSM. The workflow now also
runs the separate synthetic PlayMaker container probe documented in
[`PLAYMAKER_FORMAT17_CONTAINER_PROBE_20261031.md`](PLAYMAKER_FORMAT17_CONTAINER_PROBE_20261031.md).
That probe embeds the repository's synthetic PlayMakerFSM payload and shows
that AssetsTools.NET can preserve its bytes through a format-17 rewrite; the
Python codec independently accepts the synthetic payload. AssetsTools.NET's
class database still does not decode PlayMaker's private schema.

Neither fixture demonstrates Unity Editor import/save, PlayMaker execution,
loading in The Forest, a runtime registration path, or DualShock 4 input. A
Unity `5.6.6f2` Editor round-trip using an authorized, compatible PlayMaker
package is still required before claiming editor-importable PlayMaker data.
Even that would not prove runtime loading in the game.
