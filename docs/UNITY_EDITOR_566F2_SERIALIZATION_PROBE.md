# Unity Editor 5.6.6f2 synthetic serialization probe

## What this validates

`prototype/Unity56SerializationProject` is a small, noncommercial Unity
project pinned to **5.6.6f2**. It creates project-owned `GameObject`,
`Transform`, `MonoBehaviour`, object references, an enum, primitives,
`Vector3`, `Color`, an array of nested serializable state/action records, and
a separate reference target. It has no PlayMaker, Rewired, The Forest, or
other commercial code/assets.

The Editor driver creates one baseline plus nine variants. Each variant
changes exactly one declared serialized field relative to the baseline. The
driver saves a scene and prefab through Unity Editor APIs, imports and reloads
both, verifies the field snapshot and object references after reload, then
records the exact Editor version, target, file sizes, and SHA-256 hashes.

## Formats and supported import paths

- `EditorSceneManager.SaveScene` writes `.unity` scenes. `PrefabUtility.CreatePrefab`
  writes `.prefab` assets for this Unity 5.6 project. With
  `EditorSettings.serializationMode = ForceText`, those are Unity YAML files
  that the same Editor reimports through `AssetDatabase.ImportAsset`.
- The probe does **not** feed a hand-authored standalone `.assets` file to
  `AssetDatabase`. The Python format-17 fixtures are useful serialized-file
  fixtures, not project-source assets that Unity promises to import.
- The Editor also uses `BuildPipeline.BuildAssetBundles` to emit one
  uncompressed host-target AssetBundle per variant with embedded TypeTrees
  disabled. This gives AssetsTools.NET a supported Unity-generated container
  whose contained serialized file can be checked as format 17. The bundle is
  only an analysis artifact; it is not a PS4 bundle and is not loaded into
  The Forest.
- AssetsTools.NET extracts the bundle's contained `.assets` file. The existing
  Python `Asset` reader then checks the same bytes, object table, raw object
  hashes, and GameObject/Transform/MonoBehaviour base PPtrs. The Python report
  is compared against the independent AssetsTools.NET report. Unity's own
  save/reopen check verifies custom fields and nested references.

This separates Unity's supported project import from binary asset analysis;
it avoids treating arbitrary format-17 bytes as a Unity Editor import API.
The actual Editor output must report format 17 when AssetsTools.NET reads the
bundle. If this exact Editor/target emits another format, the validator fails
closed rather than relabeling it.

## Run with legitimate local tools

Obtain Unity 5.6.6f2 from Unity's official Download Archive under an account
and license that permit its use. Do not copy Unity license files, activation
tokens, or credentials into this repository or its logs. This probe needs a
desktop Editor target only; it does not require Unity's PS4 build module.

Install the pinned .NET SDK from Microsoft's official .NET download source.
The existing `global.json` selects 10.0.100 with latest-patch roll-forward.
AssetsTools.NET 3.0.5 is restored from NuGet by the existing project; no
package binary is committed.

Obtain `classdata.tpk` from the public UABEA v8 release archive. The pinned
Linux archive URL and both archive/TPK hashes are already specified in
`.github/workflows/offline-integration.yml` and
`docs/ASSETSTOOLS_FORMAT17_VALIDATION.md`; the probe checks the TPK SHA-256
before use. Do not replace it with a game-derived or unverified class
database.

Set these local paths, then run the repository script:

```sh
export UNITY_566F2_EDITOR="/path/to/Unity-5.6.6f2/Editor"
export CLASSDATA_TPK="/path/to/verified/classdata.tpk"
export UCM_UNITY_PROBE_OUTPUT="/tmp/theforest-ucm-unity56-probe"
sh scripts/run_unity56_editor_probe.sh
```

On macOS, `UNITY_566F2_EDITOR` should point to the Editor executable inside
the installed Unity application bundle. On Linux, point it to the installed
Unity executable. The Editor performs an exact version check; other versions
are rejected. Output is outside the project. The run script checks the YAML
outputs and hashes, builds the existing .NET validator, runs AssetsTools.NET
against every AssetBundle, and compares its results with the Python parser.

## Local PlayMaker compatibility without package redistribution

The initial run intentionally proves only Unity's general serialization
mechanism. A later private test may use a historical PlayMaker 1 package only
if the operator has a legitimate license and obtains the package from their
Unity Asset Store account or the vendor's authorized archive. Select a release
whose vendor documentation supports Unity 5.6.6f2; the first pass does not
need to match the version bundled with The Forest.

Import that package only into a private copy of this synthetic project. Record
the package version and local hash in a private test report; do not commit the
package, DLLs, source, license files, or credentials. Inspect the component
fields and ActionData types through Unity's serialization APIs, then compare
them with the existing Python PlayMaker codec. A historical compatible
package establishes only general serialization behavior. It does not validate
the The Forest schema until its exact fields, type codes, byte layouts,
references, defaults, and version-specific values have been checked against
the title's derived evidence.

## What remains unverified

The project does not write a complete PlayMaker FSM. The existing codec and
format-17 fixtures exercise a synthetic MonoBehaviour container and bounded
known PlayMaker fields, but the full `Fsm`, state/event/transition graph,
variables, action arrays, all PPtrs/dependencies, and unresolved opaque tail
still need a complete writer and independent Editor reload check using a
legitimately obtained compatible PlayMaker package. That validation must use
a new synthetic scene object and leave `CutSceneController`, Rewired, original
The Forest files, and all game packages untouched.

## Verification status in this workspace

The Unity Editor and .NET SDK are not installed in this Codex environment, so
no real Unity Editor save/reimport, AssetBundle build, or AssetsTools.NET read
of Editor output is claimed. The Editor scripts have a compile-only C# 4 stub
check; the stub creates no serialized files. Existing Python/format-17 tests
remain independent fixture tests. GitHub Actions can compile the Editor
scripts and run the existing AssetsTools.NET fixture job, but it does not
activate a Unity license or claim that Unity ran.
