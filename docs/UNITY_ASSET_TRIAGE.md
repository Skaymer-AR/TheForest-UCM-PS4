# The Forest CUSA12398 1.15: Unity asset triage

**Status:** path inventory tool developed; game asset data **not yet analyzed**.
The Drive folder `TheForest_Extraidos` previously held only `eboot.bin`,
`Il2CppUserAssemblies.prx` and two identical `global-metadata.dat` copies.
These are not the Player's serialized scenes or Rewired configuration.

The complete PkgUnpack `--list` output described **170** PFS files, but its
full text was not retained in this workspace. We have only the initial listing
snippet (GI/lightmap files under `Media/GI/level29`), so it would be misleading
to claim we have identified gameplay scenes, build version or DS4 action maps.

## Added read-only discovery tool

`scripts/inventory_unity_assets.py` classifies **names only** from either
the complete `PkgUnpack --list` output or a local folder of private extracts.
It does not read or decrypt scenes, change the package, parse scene objects,
or assume a Unity Player version.

```sh
python3 scripts/inventory_unity_assets.py --listing /private/theforest-pkg-list.txt
python3 scripts/inventory_unity_assets.py --root /private/selective-extracts
```

The report distinguishes candidate Player files (`globalgamemanagers`,
`boot.config`), scene candidates (`level0`, `levelN`), serialized assets,
bundles, StreamingAssets, and **files explicitly named Rewired**. Names are
triage hints only; the configuration could be embedded in any other assets.

### Next asset evidence to collect (private, read-only)

1. Save the complete `PkgUnpack --list` output (the fixed legacy-key-derivation
   build that already produced `170` PFS files). Run the inventory against
   that listing; preserve only the report in GitHub.
2. Selectively extract Player initialization and likely scene bundles and
   inspect them with a Unity 5.x-compatible serialized-file parser. Do not
   upload copyrighted binary assets to GitHub.
3. Verify the Player's exact Unity version against serialized headers or
   another *validated* source; do not promote the ELF's `5.6.6f2` candidate
   to a confirmed Editor/PS4 SDK pair without cross-checks.
4. Inspect types and serialized objects to locate actual Rewired InputManager,
   action-to-button mapping and scene bootstrap hierarchy. An asset name,
   text search, or scene label alone cannot prove runtime input behavior.
5. Compare the result against the existing `prototype/Unity56` contract
   and `docs/AOT_INTEGRATION_PROPOSAL.md`. Report the precise absent input;
   do not claim access to a retail IL2CPP build toolchain.

## Scope boundary

This does not authorize rebuilding the PKG, using global hooks, creating
a runtime PRX, editing the metadata tables directly, or installing anything
on the PS4. It is targeted evidence collection toward **our own graphical
DualShock 4 Ultimate Mod Menu**, not GoldHEN cheat JSON.
