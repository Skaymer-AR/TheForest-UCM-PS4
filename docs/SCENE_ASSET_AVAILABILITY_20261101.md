# Scene asset inputs available in this session — 2026-11-01

## Recovery result

The working tree and the checked local private-data locations (`/workspace`,
`/tmp`, and `/mnt/data`) contain none of the requested archives or Unity
assets. Google Drive searches for the archive names and asset names returned no
matching files. The accessible `TheForest_Extraidos` folder contains
`eboot.bin` and `Media` subfolders for `Native`, `Metadata`, and `Modules`;
those contain metadata/module material, not the scene/shared-asset archives.
No requested ZIP or Unity asset bytes were downloaded or rehashed in this
session. The SHA-256 values below are prior pinned evidence only, not a claim
that the files are available now.

| Needed source | Prior pinned SHA-256 | Available now |
| --- | --- | --- |
| `Media/level2` | `99fce056f65647f62ba52d9957317b4ed876e600f854f12e65a20897d37c396d` | No |
| `Media/globalgamemanagers.assets` | `2518dad0f38f6357276d1e33b4653a907df82dc8b0eb56450b49cb3eb86af2a8` | No |
| `Media/sharedassets0.assets` | `f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321` | No |
| `Media/sharedassets1.assets` | `d227ee3ac409b21bb956c2457d19b248006c212f58ecd4fb396f34ffc2a6e815` | No |
| `Media/sharedassets2.assets` | `806d65aa19fd86cbd20ac8cb3f7e5a11cd6a4bd9c9438f0e243b38580303c105` | No |
| `Media/resources.assets` | `9b28d330969eaf9f6ae5dc0fa5e83b022174720744c272f80ee887a46e063536` | No |
| `Media/resources.assets.resS` | `521285d46383390607bbadd010c548b3a254909f0c47bda6adadaf3c1090ba4b` | No |

The prior archive reports mention `Archivo.zip`, `Archivo(1).zip`,
`Archivo 2.zip`, `Archivo 2(1).zip`, and `Archivo 3.zip`; none of those ZIP
files is present in the checked locations in this session. Since no matching
archive is available, `scripts/verify_unity_assets_in_archives.py` could not
be run against the original source archives and cannot reproduce the old
extraction report here.

## Smallest useful scene experiment

A full `Image0`/`Sc0` tree is **not** a prerequisite for the first offline
scene-object experiment. The minimum source set depends on the object graph:

- To edit `level2`, its exact bytes are mandatory.
- `globalgamemanagers.assets` is required to resolve the `MonoScript` pointer
  for a title-owned `PlayMakerFSM` and validate the script/type reference.
- `sharedassets0.assets` is needed to resolve the scene's existing Rewired
  prefab references and is the source for the controller maps if the input
  path is changed or validated.
- `sharedassets2.assets` is needed to resolve the scene's existing
  `FsmTemplate` references. A self-contained inline FSM can avoid adding a
  new template dependency, but it does not erase the scene's existing ones.
- `resources.assets` and `resources.assets.resS` are needed only if the new
  object graph or the scene's dependency table actually references objects or
  streamed payloads in those files; inspect the original `level2` table to
  decide.

Read the source scene's external table and all PPtrs before deciding the
candidate's exact allowlist. Preserve all existing components, keep the
`CutSceneController` FSMs byte-identical, and include every newly referenced
file in the dependency audit. This allows a bounded scene experiment without
requiring unrelated levels or the complete package tree.

## Integration choice while assets are unavailable

| Route | Assessment |
| --- | --- |
| New separate `PlayMakerFSM` in `level2`, using existing AOT `GUIBox`/`GUILabel` | Best current candidate: the scene contains a `PlayMakerGUI` object and the title has these AOT actions. A separate inline FSM avoids altering the cutscene controller and may avoid an external template. Static presence does not prove that `OnGUI` runs in gameplay. Still blocked by missing scene bytes, the opaque 40-byte FSM tail, and unvalidated serialized input actions. |
| Reuse an existing HUD/Unity UI prefab | Could provide visual primitives, but no available bytes identify a safe isolated prefab and there is no proven prefab callback that handles the L1+R1 chord. It does not remove the input-logic requirement. |
| Add a new native/AOT component | Least viable now: no title IL2CPP source/build pipeline or validated registration/bootstrap; the original PS4 module is a SELF/PRX container, not a linkable project. It would expand the patch and recovery surface. |

Do not generate a scene candidate from fixtures or inferred bytes. The single
current build blocker is that the hash-pinned scene source bundle is not
available: at minimum `level2`, `globalgamemanagers.assets`,
`sharedassets0.assets`, and `sharedassets2.assets` are needed for this scene's
object/script/map/template references. Any other files named by `level2`'s
external table can be added to that bounded set. This is not a requirement
for unrelated levels or the full `Image0`/`Sc0` tree.

## Input logic advanced offline

The existing host menu already implements a rising-edge chord. Its C and C#
tests now cover: isolated L1/R1 presses do not toggle; staggered presses toggle
only while both are held together; opening does not change category; releasing
one shoulder does not navigate; completing the chord closes; and holding the
chord does not toggle repeatedly. Existing navigation, reconnect-neutral,
Cross, and Circle checks remain in place. These tests validate the menu model,
not a PS4/Rewired provider or input consumption in the game.
