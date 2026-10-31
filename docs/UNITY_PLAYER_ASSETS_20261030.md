# Unity 5.6.6f2 and scene manifest verified from The Forest PS4 CUSA12398 v1.15

**Analysis date:** 2026-10-30. **Scope:** read-only offline investigation against the complete private update PKG split across 8 Drive parts. No PS4 modifications, no external PRX, and no copyrighted game asset was uploaded to this repository.

## Package and extraction provenance

- Full reconstructed PKG: **1,609,170,944 bytes**, SHA-256 `7214800a8276fdf5fceb91a4e18064114aded1265508d78085b41a1f317dbff3`.
- Package PFS: outer encrypted signed filesystem, inner PFSC v2 container; **170 title files** plus one auxiliary `flat_path_table` in the inner directory tree. This matches the previous PkgUnpack count of 170.
- Independent private read-only Python PFS extraction reproduced `eboot.bin` SHA-256 `fac03b6402a7659f0efd0c133aea2252e4218a6be7f23cf84b6af82099adcd2a` and `global-metadata.dat` SHA-256 `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`. These independently match the earlier Colab extraction.
- Unity `Media/globalgamemanagers` bytes: **6,602,156**, SHA-256 `ccbd87142fd68b7931c5e7511d06060da5998a75f375d3325a901613004a4d89`.
- The `globalgamemanagers` serialized-file header has format **17**, endian marker `0`, data offset `0x1000` and **Player version `5.6.6f2`**. `level0`, `level1`, `level2`, `level6`, `sharedassets0.assets` and `globalgamemanagers.assets` also carry the same Player version in their headers.
- Thus the exact **Unity Player version is now confirmed from serialized game assets**, not merely inferred from an `eboot` string. This does **not** establish availability of a matching Unity PS4 Editor/SDK or the original project.

## Scene build index from globalgamemanagers

A validated little-endian length-prefixed array was recovered at file offset **`0x1C018`**, with **30 unique scene paths**:

| Level file | Unity build-scene path |
| --- | --- |
| `level0` | `Assets/Scenes/logoLoad.unity` |
| `level1` | `Assets/Scenes/TitleScene.unity` |
| `level2` | `Assets/Scenes/ForestMain_v08.unity` |
| `level3` | `Assets/Scenes/Ps4StartSceneNGUI.unity` |
| `level4` | `Assets/Scenes/CaveProps_Streaming.unity` |
| `level5` | `Assets/Scenes/TitleSceneLoader.unity` |
| `level6` | `Assets/Scenes/endgame_streaming.unity` |
| `level7` | `Assets/Scenes/epilogue_v01.unity` |
| `level8` | `Assets/Scenes/EpilogueLoader.unity` |
| `level9` | `Assets/Scenes/MainSceneGreebles.unity` |
| `level10` | `Assets/Scenes/MainSceneWorldStorySpots.unity` |
| `level11` | `Assets/Scenes/endgame_animPrefabs.unity` |
| `level12` | `Assets/Scenes/Cave_01_Props_Streaming.unity` |
| `level13` | `Assets/Scenes/Cave_02_Props_Streaming.unity` |
| `level14` | `Assets/Scenes/Cave_03_Props_Streaming.unity` |
| `level15` | `Assets/Scenes/Cave_04_Props_Streaming.unity` |
| `level16` | `Assets/Scenes/Cave_05_Props_Streaming.unity` |
| `level17` | `Assets/Scenes/Cave_06_Props_Streaming.unity` |
| `level18` | `Assets/Scenes/Cave_07_Props_Streaming.unity` |
| `level19` | `Assets/Scenes/Cave_08_Props_Streaming.unity` |
| `level20` | `Assets/Scenes/Cave_09_Props_Streaming.unity` |
| `level21` | `Assets/Scenes/Cave_10_Props_Streaming.unity` |
| `level22` | `Assets/Scenes/Cave_HC_Props_Streaming.unity` |
| `level23` | `Assets/Scenes/Cave_Snow_Props_Streaming.unity` |
| `level24` | `Assets/Scenes/endscene_sting.unity` |
| `level25` | `Assets/Scenes/CreditsScene.unity` |
| `level26` | `Assets/Scenes/NewGameCycleTestBlankScene.unity` |
| `level27` | `Assets/Scenes/Cave_Junk_Props_Streaming.unity` |
| `level28` | `Assets/Scenes/Cave_IE_Props_Streaming.unity` |
| `level29` | `Assets/Scenes/Cave_IW_Props_Streaming.unity` |

**Immediate targets:**
- `level0` logo/startup, `level1` title, `level2` **ForestMain_v08** gameplay, `level3` PS4 start scene.
- `level2` provides the best source material for analyzing Unity scene bootstrap and input focus. It does **not** prove a currently executing callback from static file content.
- A parser for this evidence is now available at [`scripts/read_unity_scene_manifest.py`](../scripts/read_unity_scene_manifest.py), with synthetic fixtures in `tests/test_read_unity_scene_manifest.py`. Inputs stay private; JSON output is derived metadata only.

## Controller and component evidence (names only)

The following UTF-8/ASCII spans were observed in extracted serialized file data:

| Private file | Observation |
| --- | --- |
| `Media/level0` | `Rewired Spawner` name appears once |
| `Media/level1` | `Rewired Spawner` and `DebugConsole` names each appear once |
| `Media/level2` | `Rewired Spawner`, `DebugConsole`, `PS4ControllerFeatures` names each appear once |
| `Media/sharedassets0.assets` | `RewiredConsts` and action-like strings `MenuToggle`, `Back`, `Horizontal`, `Vertical`, `Jump`, `Select`, plus category names `Menu`, `Movement`, `World`, `Inventory`, `Multiplayer` |

These are **name/string observations**, not parsed Unity GameObjects, activated components, Rewired action IDs, or physical DS4 bindings. In particular do **not** assert that `MenuToggle` is mapped to L1+R1, or that `DebugConsole.OnGUI` is active. A Unity 5.6 serialized object parser and Rewired controller-map decoding are the next step.

## Integration decision remains unchanged

- The verified Unity Player version and scene mapping remove **two research uncertainties** from the standalone AOT prototype.
- They do **not** provide the original Unity project, generated IL2CPP C++ sources, platform linker inputs, PS4 SDK, a registration/creation bootstrap in the retail game, or a validated DS4 input provider.
- The prototype at [`prototype/Unity56/`](../prototype/Unity56/README.md) still builds using synthetic Unity API stubs only; **no PS4 playable mod menu yet**.
- No permissions were expanded: no PKG rebuild/patch, no running hooks, no PRX installation, no gameplay patch actions.

## Next proof required

Read the serialized `level2` and `sharedassets0.assets` object tables using a Unity **5.6**-compatible reader to identify the real GameObject components, Rewired InputManager data and controller-to-action maps. Then evaluate a minimal AOT Unity host build with **matching** Unity Player version and a legitimate PS4 pipeline. Do not edit retail IL2CPP registration tables by hand.
