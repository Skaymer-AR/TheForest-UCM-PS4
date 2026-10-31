# Synthetic Unity 5.6.6f2 serialization project

This project contains only project-authored C# probe scripts. It has no
PlayMaker package, The Forest content, Rewired data, PS4 modules, or game
assets. `ProjectSettings/ProjectVersion.txt` pins the required Editor version.

Open it with a legitimately installed Unity **5.6.6f2** Editor, or run the
repository driver documented in
[`docs/UNITY_EDITOR_566F2_SERIALIZATION_PROBE.md`](../../docs/UNITY_EDITOR_566F2_SERIALIZATION_PROBE.md).
The Editor creates scenes and prefabs through supported Editor APIs, saves
them as ForceText YAML, imports/reopens them, builds host-target AssetBundles,
and writes an external hash/structure report.

The state/action classes here are synthetic serializable data. They do not
implement or emulate the private PlayMaker `Fsm`, `ActionData`, or
`PlayMakerFSM` schemas. No test result should be described as a PlayMaker or
The Forest validation.
