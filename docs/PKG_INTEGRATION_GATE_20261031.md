# Private PKG and scene integration gate — 2026-10-31

## Authority and source handling

The owner authorized offline editing and rebuilding of private copies of the
CUSA12398 v1.15 package and Unity assets. This does not authorize PS4
installation, live hooks, memory writes, or publishing commercial files. Keep
source PKG parts, extracted assets, modified assets, and packages outside Git.

## Package evidence and reproducibility

The repository's historical package report records:

- Title `The Forest`, Title ID `CUSA12398`, APP_VER `01.15`.
- Content ID `EP0238-CUSA12398_00-THEFOREST0000000`.
- The freshly extracted SFO says `CATEGORY=gp`, `VERSION=01.00`, and
  `APP_VER=01.15`; OrbisPkgTool's classifier maps `gp` to a **patch/update**.
  The header says content type `0x1A`, which that tool uses as a game fallback
  only when SFO category is absent. Keep this header/category discrepancy
  visible instead of classifying from one field alone.
- DRM type `0x0F` and the SFO category indicate a retail-format update, not an
  FPKG. Header flags are `0x00000001`; the documented finalized bit 31 is
  clear. The package's signatures were not verified, so no installability
  claim follows from the readable header/SFO.
- Eight split parts totaling 1,609,170,944 bytes and a previously measured
  concatenated SHA-256 of
  `7214800a8276fdf5fceb91a4e18064114aded1265508d78085b41a1f317dbff3`.
- DRM/header fields and PFS offset/size documented in
  [`PKG_EXTRACT_20261030.md`](PKG_EXTRACT_20261030.md). These checks are not
  PKG signature or PFS integrity verification.

This run freshly re-hashed Drive copies of `eboot.bin` and
`global-metadata.dat`; both match the documented hashes. It also streamed the
eight PKG parts in their documented order without saving a package copy. Every
part size, the 1,609,170,944-byte concatenated size, and combined SHA-256
matched. A bounded header read reconfirmed the magic, Content ID, DRM/content
types, one-PFS count, declared package size, and PFS image bounds. This still
does not decrypt or validate the encrypted PFS, verify PKG signatures, or
reproduce an Image0 tree. OpenOrbis `PkgTool.Core` 0.2.231 successfully listed
27 entry records and extracted entry 10 (`PARAM_SFO`); the SFO output confirmed
the title, `TITLE_ID`, `APP_VER`, `VERSION`, `CATEGORY`, and `CONTENT_ID` above.
Its `pkg_validate` and `pkg_extractinnerpfs` commands both aborted before
package analysis because no usable `libssl` was available in this host. This
is an environment dependency failure, not a package-invalid verdict. The
current `TheForest_Extraidos` Drive folder
contains `eboot.bin` and the metadata/module portions of `Media`; it does not
contain a complete Image0 tree. Searches for the historical ZIPs and Unity
assets did not find them in the connected Drive.

There is a provenance gap in the repository: `UNITY_PLAYER_ASSETS_20261030.md`
reports a complete 170-file PFS extraction, while the later package/asset
acquisition notes say the available PFS tool could not decrypt the package and
that the six Unity files came from separately supplied ZIPs. Later PlayMaker
reports used 62 hash-pinned assets, but their source bytes are not currently
available in this workspace or connected Drive. Do not treat the historical
170-file extraction as a reproducible current dump until its source tree and
extraction command/log are revalidated.

### Tool assessment

- `flatz/pkg_pfs_tool` was previously compiled and run against this exact PKG.
  Header/SFO reads passed; PFS listing/extraction failed because its
  `pkg_entry_key_3` private exponent was unavailable. Disabling signature/ICV
  checks did not provide the missing decryption key.
- The MIT `pearlxcore/OrbisPkgTool` source was reviewed at commit
  `5cd42a515dc29a453c7abcb93318493bdb5b5e1f`. It advertises PKG/PFS extraction,
  eight-stage validation, GP4 FPKG building, and base/patch merge. Its reader
  source explicitly describes the retail-PKG fallback as using a **leaked
  Sony key-3 private key**, and the source contains private RSA key material.
  It was not run on this PKG and is not accepted here as a legitimate retail
  decryption path. Its README says FPKG installation/gameplay has not been
  tested on real PS4 hardware.
- The local OpenOrbis toolchain contains `create-gp4` and `PkgTool.Core`
  (`pkg_build` builds an FPKG from a GP4 project). This is a viable builder for
  an authorized extracted tree, not a retail-PFS decrypter. It was not run to
  build a title package because no validated scene candidate or complete tree
  is available. No PKG was built.
- Read-only commands used were `PkgTool.Core pkg_listentries`,
  `pkg_extractentry <pkg> 10 <param.sfo>`, and
  `sfo_listentries <param.sfo>` with
  `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`. The first two operations exited
  0 and exposed 27 outer entries plus the SFO above. Both
  `pkg_validate <pkg>` and `pkg_extractinnerpfs <pkg> <out>` aborted with exit
  134 and `No usable version of libssl was found`; no validation/extraction
  conclusion is drawn from those aborts.

## Packaging choice

| Route | Evidence-based decision |
| --- | --- |
| Update FPKG | Best packaging candidate because the input SFO classifies it as `gp` and contains APP_VER `01.15`. Build a patch FPKG from the matching update tree only after that tree is reproducibly available. There is no matching fake base package in Drive, and installing a fake patch over a retail base is unverified; do not claim compatibility. |
| Full FPKG base | Fallback only if a complete authorized base-game Image0/Sc0 tree is available. It needs substantially more files than the 1.15 update and is not justified by the current update-only source. |
| Unity scene/prefab edit | Preferred integration design. Add a separate `PlayMakerFSM` object to `level2`, reusing the title's AOT `GUIBox`/`GUILabel` and input actions. Do not touch either `CutSceneController` FSM. The current synthetic FSM container is not a valid retail FSM: its 40-byte tail is opaque and the component has not been imported by Unity 5.6.6f2 with a licensed PlayMaker 1 package. |
| New native/AOT code | Not currently justified. Adding a class requires a complete Unity/IL2CPP PS4 build and coherent registration/bootstrap; no such project/toolchain is available. The old global hooks remain prohibited. |

The graphics path with the strongest evidence is a **scene-owned FSM**:
`level2` serializes an enabled `PlayMakerGUI` object, its native `OnGUI` body
dispatches existing AOT `FsmStateAction.OnGUI` actions, and GUI drawing actions
exist in this title's IL2CPP. This does not prove the callback ran in a live
session, or that a new FSM serializes, imports, loads, or renders. Input is a
separate blocker: `MenuToggle` has no serialized DS4 binding, and the existing
L1/R1 bindings overlap gameplay actions. No safe chord consumption policy is
established, so L1+R1 must not be presented as implemented.

## Audits and status

`scripts/audit_private_pkg_tree.py` compares a private source tree and
candidate tree using SHA-256, rejects symlinks/case collisions, checks required
files, and fails if any changed/added/deleted path is outside an exact
allowlist. It reports metadata only. Its tests use synthetic files; it does
not parse Unity objects, validate PPtrs, validate PKG cryptography, or prove
installation.

| Milestone | Status |
| --- | --- |
| PKG metadata (`TITLE_ID`, `APP_VER`, Content ID, SFO category) | Freshly confirmed from the original streamed parts and extracted SFO; SFO `gp` indicates update, header `0x1A` disagrees with the tool fallback |
| Header, part sizes and concatenated PKG SHA-256 | **PASS**; current Drive parts match the historical values |
| PKG structurally validado | **PARCIAL**: header/entry table/SFO parse pass; full `pkg_validate` aborted on missing `libssl`; encrypted PFS and signatures remain unvalidated |
| Full original PFS/Image0 revalidated | **NOT VERIFIED**; exact PFS extraction remains blocked and no current full tree |
| Modified Unity asset produced | **NO** |
| PKG built | **NO** |
| Compatibility with installed base | **UNKNOWN** |
| Installed / game launched / menu visible / DS4 validated | **NOT TESTED** |

## Exact next input

Provide either (a) a complete private extracted `Image0` plus `Sc0` tree from
the owner's CUSA12398 v1.15 package with its extraction provenance, or (b) a
complete authorized installed-title dump. For the first isolated scene test,
the exact private sources must at minimum include `level2`,
`globalgamemanagers.assets`, the external assets referenced by that scene,
and the matching metadata/module already used by the analyzer. Also provide
access to Unity Editor 5.6.6f2 on a supported licensed host and a legitimately
owned PlayMaker 1 package compatible with that Editor. Only after the FSM
imports and its scene references pass Python and AssetsTools.NET round-trips
should a private package candidate be considered.

The nearest fallback is to first produce a **noncommercial Unity 5.6.6f2 +
licensed PlayMaker 1** FSM sample with the correct serialized tail and GUI/input
actions. Then port only that validated object graph into a private copy of
`level2`; this does not require compiling a new IL2CPP class.
