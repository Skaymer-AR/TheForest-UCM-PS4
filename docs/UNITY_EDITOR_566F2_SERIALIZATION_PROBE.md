# Unity Editor 5.6.6f2 synthetic serialization probe

## What the probe checks

`prototype/Unity56SerializationProject` is a noncommercial project pinned to
Unity **5.6.6f2**. It uses only authored C# and contains synthetic GameObjects,
Transforms, MonoBehaviours, primitive/enum/Vector3/Color fields, object
references, and nested serializable state/action records. It includes no
PlayMaker, Rewired, The Forest, or commercial files.

The Editor driver makes ten cases: one baseline and nine variants, each
changing one declared field. Unity saves a scene and prefab, imports them,
reloads them, and compares the snapshots and references. It then builds one
uncompressed host-target AssetBundle per case with TypeTrees disabled. The
report records the exact Editor version, build target, snapshots, bundle
dependencies, file sizes, and SHA-256 hashes.

This does not import a hand-authored standalone `.assets` file through
`AssetDatabase`. Unity's supported project import route is used for `.unity`
and `.prefab`; generated AssetBundles provide serialized files for offline
inspection. The bundles are not PS4 bundles and are never loaded into the
game.

AssetsTools.NET extracts each bundle's internal `.assets` file. Python and
AssetsTools.NET compare the object table, PathIDs, class IDs, raw object hashes,
external-file dependency tables, and base PPtrs for GameObject components,
Transform ownership/hierarchy, and MonoBehaviour owner/script references.
Unity's own reload checks custom field values and the synthetic
`referenceTarget` object reference. The current type-tree-free parser does
not independently decode that custom MonoBehaviour field tail to compare its
serialized target PathID; that remains an explicit limitation.

If Unity's generated payload is not format 17, or its metadata disagrees with
the parser, validation fails instead of relabeling or rewriting the output.

## Official Editor and runner assessment

Unity's official release API currently lists **5.6.6f2**, dated 2018-05-08,
with these installers:

| Host | Architecture | Official installer | API advertised size | Availability check |
|---|---|---|---:|---|
| Windows | x86_64 | `UnitySetup64-5.6.6f2.exe` | 568,230,912 bytes | Direct HEAD returned HTTP 200 |
| macOS | x86_64 | `Unity-5.6.6f2.pkg` | 756,324,393 bytes | Direct HEAD returned HTTP 200 |
| Linux | — | None listed for this release | — | Not an option for this exact release |

The x86_64 Windows installer makes a Windows x64 runner a plausible candidate;
it does not establish that a 2018 Editor and its licensing service work on the
current Windows Server image. The macOS archive is also x86_64, but this
review did not test Catalina or a hosted macOS image. No installer was
downloaded or executed. Current runner OS compatibility remains unverified.

Unity 5.6's own command-line manual documents `-batchmode`, `-nographics`,
`-projectPath`, `-executeMethod`, `-logFile`, and `-quit`; thus the existing
driver uses a supported headless Editor invocation. Those flags do not bypass
licensing.

Unity 5.6's manual activation instructions say the offline request is tied to
the machine that generated it. A hosted runner is ephemeral, so an activation
file from the owner's computer cannot be assumed to work there. The old
manual also describes serial/account activation. No license, activation
file, credentials, GitHub secret, or owner authorization was supplied, and
none was requested or used. A hosted Unity Editor job is **blocked** until
the license owner supplies an authorized activation method that is valid on
that runner. Do not place `.ulf`/`.alf` files, serials, account credentials,
or activation tokens in the repository or logs.

The usable route is therefore a locally licensed Windows/macOS Editor stage,
then an Ubuntu Actions validation stage. The local stage uses Python only.
This avoids requiring .NET 10 on macOS Catalina: Microsoft's current .NET
support table starts at macOS 14, while this repository pins .NET SDK 10.0.100.
Ubuntu Actions installs .NET 10 for AssetsTools.NET after output transfer.

Sources checked:

- [Unity release API for 5.6.6f2](https://services.api.unity.com/unity/editor/release/v1/releases?version=5.6.6f2&limit=10)
- [Unity Download Archive](https://unity.com/releases/editor/archive)
- [Unity 5.6 command-line arguments](https://docs.unity3d.com/560/Documentation/Manual/CommandLineArguments.html)
- [Unity 5.6 manual activation](https://docs.unity3d.com/560/Documentation/Manual/ManualActivationGuide.html)
- [Microsoft .NET macOS support](https://learn.microsoft.com/dotnet/core/install/macos)

## Run the locally licensed Editor stage

Obtain Unity 5.6.6f2 from the official Unity archive under a license that
permits its use. This probe needs only the desktop Editor, not Unity's PS4
module. Use Python 3.9 or later. The runner copies the synthetic project to
the external output directory, keeping Unity's `Library`, generated assets,
and logs out of the repository.

On macOS, `--editor` points inside the installed app bundle, for example
`/Applications/Unity/Unity.app/Contents/MacOS/Unity`. On Windows, use the
installed `Unity.exe`. Run twice into fresh directories:

```sh
python3 scripts/run_unity56_editor_stage.py \
  --editor "/path/to/Unity-5.6.6f2/Editor/Unity" \
  --output "/tmp/theforest-ucm-unity56-run-a"
python3 scripts/run_unity56_editor_stage.py \
  --editor "/path/to/Unity-5.6.6f2/Editor/Unity" \
  --output "/tmp/theforest-ucm-unity56-run-b"
python3 scripts/compare_unity56_probe_runs.py \
  "/tmp/theforest-ucm-unity56-run-a/generated" \
  "/tmp/theforest-ucm-unity56-run-b/generated" \
  --report "/tmp/theforest-ucm-unity56-comparison.json"
```

The Editor stage verifies the exact version, saves/imports/reopens the ten
synthetic scenes and prefabs, checks each field snapshot, builds bundles, and
validates its output report/YAML/hashes with Python. Its final message states
that the overall probe is still incomplete until AssetsTools.NET runs.

To transfer only sanitized output for Actions, package the two runs:

```sh
python3 scripts/package_unity56_editor_probe.py package \
  "/tmp/theforest-ucm-unity56-run-a/generated" \
  "validation/unity56-editor-probe.zip" \
  --repeat-run "/tmp/theforest-ucm-unity56-run-b/generated"
git add validation/unity56-editor-probe.zip \
  validation/unity56-editor-probe.zip.sha256
git commit -m "Add synthetic Unity 5.6.6f2 probe output"
git push origin feature/visual-menu-foundation
```

The packager validates the report first and includes only its scenes, prefabs,
their `.meta` files, AssetBundles, and a manifest. It excludes the Unity log,
temporary project, install files, license data, credentials, and UABEA
classdata. It rejects unlisted files, path traversal, symlinks, oversized
files, and archives over 50 MiB. The checksum sidecar protects transfer
integrity; it is not a cryptographic attestation that Unity produced the
archive.

The new `unity56-editor-output.yml` workflow runs when the ZIP is committed to
the PR. It verifies the checksum, safely extracts the allowlisted files, and
runs AssetsTools.NET plus Python on Ubuntu. It does not install Unity or use a
license secret. With two runs it compares report snapshots, bundle
dependencies, exact report/scene/prefab/AssetBundle hashes, and AssetsTools.NET
PathID/class/PPtr summaries. It records but does not compare `.meta` GUIDs,
which Unity allocates as asset identities in each scratch project. With one
run it marks repeatability **NOT_CHECKED**. Its uploaded
Actions artifact contains JSON validation summaries only.

On a host that already supports the pinned .NET SDK, the existing
`scripts/run_unity56_editor_probe.sh` can run both stages locally using
`UNITY_566F2_EDITOR`, `CLASSDATA_TPK`, and `UCM_UNITY_PROBE_OUTPUT`. Do not use
that full runner on Catalina; use the Python stage and hosted Ubuntu path.

## Later PlayMaker compatibility test

The general Unity probe does not require PlayMaker. A later private test may
use a historical PlayMaker 1 release only if it is legitimately obtained
from the operator's Unity Asset Store account or the vendor's authorized
archive, and its vendor documentation supports Unity 5.6.6f2. Import it only
into a private copy of this synthetic project. Keep the package, DLLs,
source, license files, and credentials out of the repository. Record its
version and local hash privately.

A historical version compatible with Unity 5.6 demonstrates general
serialization only. It is not evidence of the version bundled with The
Forest, nor does it validate the title's schema. That requires comparing the
exact `PlayMakerFSM`, `Fsm`, state/event/transition graph, variables, actions,
ActionData, PPtrs/dependencies, defaults, opaque tail, and version-specific
values against the title's derived evidence. The missing full writer and
independent Editor reload check are the next PlayMaker-specific requirements.
Keep `CutSceneController`, Rewired, original game files, and all game packages
untouched.

## Current verification status

The Unity Editor and license are unavailable in this Codex environment. No
real Editor save/reimport, AssetBundle build, or AssetsTools.NET parse of
Editor output has run. C# 4 stub compilation creates no serialized output;
Python archive tests use parser-contract fixtures only. Existing format-17
Actions validate their independent synthetic fixture, not Editor output. The
new transfer workflow is prepared but will remain unexecuted until a licensed
local Editor run produces and submits the allowlisted archive.
