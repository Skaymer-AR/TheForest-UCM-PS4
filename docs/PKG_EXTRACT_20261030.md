# Private CUSA12398 1.15 update PKG extraction and read-only verification — 2026-10-30

Status: the PKG/PFS extraction produced the three requested targets, and the read-only extract checker has now been run against the files currently in Google Drive. Native Unity integration remains **NO-GO under the current constraints**. Private game binaries and generated decompilation output are never committed.

**Follow-up: the header-only limitation below is resolved offline.** Segment
inspection found unencrypted, uncompressed payloads. The new plaintext SELF
reader reconstructs both ELF analysis copies, including version trailers and
normalizing stale fields of an absent section table. Their complete hashes
match the retained earlier ELFs; all 42 method prefixes also match. See
[the AOT proposal](AOT_INTEGRATION_PROPOSAL.md) for hashes, registration results,
tool limits and the remaining build-pipeline blocker. No console dump was needed.

## Provenance reported from Google Colab

- Source filename: `The.Forest_CUSA12398_v1.15_BACKPORT_[5.05-6.72]_OPOISSO893.pkg`
- SHA-256 of the complete package: **not measured**; size `1609170944` bytes reconstructed as 8 fragments, each present. Equal size alone is **not** an end-to-end integrity check.
- PKG magic `0x7f434e54`; Content ID `EP0238-CUSA12398_00-THEFOREST0000000`; `APP_VER=01.15`, `CATEGORY=gp`; `SYSTEM_VER=0x05508000`; `sdk_ver=05050000`.
- PFS flags `0xa0000000000003cc`, including `0x2000000000000000` (new crypt flag). Initial unpacker `qequ/ps4-pkg-unpacker` exited 4 with `inode 0 is corrupt`. The reported read-only tool workaround forced old key derivation in `PfsReader.cs` and `ReaderChain.cs`; the rebuilt tool's `--list` exited 0.
- Outer PFS: `block=0x10000`, reported Signed/Encrypted. Inner PFSC v2: 1,599,909,642 stored bytes -> 2,105,344,000 logical bytes, 32,125 blocks of which 18,030 compressed. Inner PFS: 201 inodes, 170 files; 21 PKG entry files. These figures establish directory readability, not full PFSC or PKG-signature verification.

## Extracted-file fingerprints

| Extracted private file | Bytes | SHA-256 |
| --- | ---: | --- |
| `eboot.bin` | 21830618 | `fac03b6402a7659f0efd0c133aea2252e4218a6be7f23cf84b6af82099adcd2a` |
| `Media/Modules/Il2CppUserAssemblies.prx` | 63934584 | `f7e590358efbfb68dc5a61bf51b070b2b85eb223070b82a31e3fd5e5118777b6` |
| `Media/Metadata/global-metadata.dat` | 15400780 | `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3` |
| `Media/Native/Data/Metadata/global-metadata.dat` | 15400780 | `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3` |

Both current metadata copies are byte-for-byte identical by SHA-256, and match the prior private metadata hash. The current PRX SHA-256 differs from the earlier private PRX SHA-256 `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`. The current eboot hash is now recorded as a baseline; no earlier eboot hash was available for comparison. A PRX hash difference alone does not establish that IL2CPP method bodies changed: signing/container bytes, backport changes, or executable code could account for it.

## Read-only checker run

The branch's `scripts/check_private_pkg_extract.py` was run on a temporary copy of the current Drive files. The copies remained outside GitHub. Full stdout:

```text
The Forest PS4 CUSA12398 1.15 | private read-only evidence
eboot: eboot.bin
  size=21830618 sha256=fac03b6402a7659f0efd0c133aea2252e4218a6be7f23cf84b6af82099adcd2a
  type=SCE/SELF container (RVA mapping not possible without a decrypted ELF)
IL2CPP PRX: Media/Modules/Il2CppUserAssemblies.prx
  size=63934584 sha256=f7e590358efbfb68dc5a61bf51b070b2b85eb223070b82a31e3fd5e5118777b6
  type=SCE/SELF container (RVA mapping not possible without a decrypted ELF)
  historical PRX SHA: DIFFERENT
metadata: Media/Metadata/global-metadata.dat
  size=15400780 sha256=238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3
  historical metadata SHA: SAME
metadata: Media/Native/Data/Metadata/global-metadata.dat
  size=15400780 sha256=238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3
  historical metadata SHA: SAME
anchor checks: SKIPPED (input is not a decrypted ELF64)
VERDICT: evidence only; does not validate a live callback, ABI, or hook.
```

Checker exit code: `0` (the report is informational; it does not mean the anchors were verified).

A separate read-only header inspection returned:

| File | First 16 bytes |
| --- | --- |
| `eboot.bin` | `4f 15 3d 1d 00 01 01 12 01 01 00 00 80 04 70 04` |
| `Il2CppUserAssemblies.prx` | `4f 15 3d 1d 00 01 01 12 01 01 00 00 40 04 70 04` |

The first four bytes identify the SELF format; this is not cryptographic
signature verification. The original checker correctly skipped RVA comparisons
because it did not parse SELF entries. The follow-up reader now maps the actual
plaintext payloads with bounds checks, so the current reconstruction has been
compared in full with the previous ELF and the 42 candidate prefixes. A SELF
marker alone is not evidence that the payloads are encrypted. The original
stdout above is retained as the result of that limited checker, not as the
final state of the binary comparison.

## Integration feasibility gate

The extraction result does not supply a new Unity/IL2CPP integration route:

- No title-owned AOT component, IL2CPP method-registration pipeline, or scene bootstrap that a GoldHEN PRX can use has been demonstrated.
- `DebugConsole.OnGUI` remains a static GUI candidate, not a proven live gameplay callback; its singleton was previously observed as NULL.
- `DllModLoader.AppDomain.Load` does not prove that new native AOT methods are registered or that a `MonoBehaviour` is created.
- A Unity native rendering callback still needs a Unity-loaded plug-in and a title-owned caller to enqueue it; GoldHEN's `plugin_load` alone does not provide either.
- The global GNM/VideoOut/ScePad detour prototypes remain prohibited after the prior black-screen and console-lock incidents. No PRX is generated or installed.

The existing `docs/INTEGRATION_DECISION.md` remains the architecture decision. The viable no-hook Unity direction would require a documented PS4 AOT loader/registration/bootstrap or a build pipeline that integrates and registers a title-owned component. The latter changes the PKG/build architecture and is not authorized by this task, so it was not attempted. The alternative title-local detour would require separate authorization and a safe relocation, synchronized patching, rollback, and quiescence design; it is not a current implementation path.

This is not a pivot to GoldHEN cheat JSON. The target remains a native in-game graphical mod menu controlled by DualShock 4. No PKG, save, or architecture was changed.
