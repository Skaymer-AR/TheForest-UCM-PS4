# Private CUSA12398 1.15 update PKG extraction — 2026-10-30

Status: **PKG read / decrypted PFS / three targets extracted successfully**, but native Unity integration remains **NO-GO**. Private game binaries are never committed.

## Provenance reported from Google Colab

- Source filename: `The.Forest_CUSA12398_v1.15_BACKPORT_[5.05-6.72]_OPOISSO893.pkg`
- SHA256 of complete package: **not measured yet**; size `1609170944` bytes reconstructed as 8 fragments, each present. Equal size alone is **not** an end-to-end integrity check.
- PKG magic `0x7f434e54`; Content ID `EP0238-CUSA12398_00-THEFOREST0000000`; `APP_VER=01.15`, `CATEGORY=gp`; `SYSTEM_VER=0x05508000`; `sdk_ver=05050000`.
- PFS flags `0xa0000000000003cc`, includes `0x2000000000000000` (new crypt flag). Initial unpacker `qequ/ps4-pkg-unpacker` exit code 4: `inode 0 is corrupt`. **Read-only tool-only workaround:** force old key derivation in both `PfsReader.cs` and `ReaderChain.cs`. Rebuild passed; resulting `--list` exit 0.
- Outer PFS: `block=0x10000`, Signed/Encrypted. Inner PFSC v2: 1,599,909,642 stored bytes -> 2,105,344,000 logical bytes, 32,125 blocks of which 18,030 compressed. Inner PFS: 201 inodes, 170 files; 21 PKG entry files. This confirms directory readability; no full PFSC verification reported.

| Extracted private file | Bytes | SHA-256 |
| --- | ---: | --- |
| `eboot.bin` | 21830618 | `fac03b6402a7659f0efd0c133aea2252e4218a6be7f23cf84b6af82099adcd2a` |
| `Media/Modules/Il2CppUserAssemblies.prx` | 63934584 | `f7e590358efbfb68dc5a61bf51b070b2b85eb223070b82a31e3fd5e5118777b6` |
| `Media/Metadata/global-metadata.dat` | 15400780 | `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3` |
| `Media/Native/Data/Metadata/global-metadata.dat` | 15400780 | `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3` |

The metadata SHA-256 **matches the prior private metadata** exactly: identical bytes, not just compatible schema. The newly extracted PRX SHA **differs** from the earlier private PRX SHA `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`. **A hash difference does not prove changed IL2CPP methods:** container format, signing, backport patches, or executable code may differ. No new `eboot.bin` baseline has been established.

## Next discriminating check (read-only)

The repo now provides `scripts/check_private_pkg_extract.py`: classify ELF vs SELF/OELF, compare private sizes + SHA256, and **only if** it is a decrypted ELF64, check two known PS4Debug entry-byte anchors using the repo's `PT_LOAD` RVA mapper. It neither patches nor exports binaries. Run locally or in Colab against the user's private Drive folder.

```bash
python3 scripts/check_private_pkg_extract.py --root /content/drive/MyDrive/TheForest_Extraidos
```

- If the PRX is SELF/OELF: obtain a legally accessible decrypted ELF or game memory dump for a byte-for-byte RVA comparison **before** adopting earlier offsets. Do not infer offsets from a wrapped file.
- If decrypted ELF: compare the two anchors; a match only supports limited code-location stability, not a call ABI, live callback, overlay or safe hook.
- The existing IL2CPP AOT registration/bootstrap and live Unity render context are **still missing**. Do not generate an installable PRX or revive the global hooks that previously froze the console.

This is **not** a pivot to GoldHEN cheat JSON. Goal remains a native in-game graphical mod menu controlled by DualShock 4.
