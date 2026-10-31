# Read-only Unity asset acquisition gate (CUSA12398 v1.15)

Work identified a missing input, **not** a PS4 graphical-menu test:
the six Unity files from the original installed title. Existing private
PKG parts do not expose PFS through the available offline extractor; no
PKG signing keys are needed or sought here.

The six known files have already been inspected in older private research;
their SHA-256 values and partial derived scene evidence live in
`docs/REWIRED_SCENE_GRAPH_20261030.md`. Their current raw bytes are **not**
present in the connected Drive folders and cannot be reconstructed from
the derived reports.

`scripts/collect_ps4_unity_assets_ftp.py` is a **read-only collector**
that can be used later when the user explicitly chooses a file transfer.
It has no PRX, hook or patch logic. The script itself was only tested with
a synthetic FTP stand-in; no PS4 hardware test was performed.

GoldHEN's opt-in FTP server normally uses TCP port **2121** on the local LAN.
The title's mounted files may appear below either
`/mnt/sandbox/pfsmnt/` or `/mnt/sandbox/pfsmount/`, in
`CUSA12398-app0`, `CUSA12398-patch0`, or
`CUSA12398-app0-patch0-union` mounts.
The collector checks these explicitly named alternatives, prioritizes the
effective union mount, and only reads whitelisted files with pinned SHA-256.
If none is mounted, it fails closed instead of exploring arbitrary paths. Merely owning a PKG does not
guarantee those paths are currently mounted.

On an authorized local machine, after the title is mounted and GoldHEN FTP
is enabled, **inventory without transfer**:

```sh
python3 scripts/collect_ps4_unity_assets_ftp.py --host <PS4_LAN_IP>
```

After the user authorizes the *separate read-only file collection*:

```sh
python3 scripts/collect_ps4_unity_assets_ftp.py --host <PS4_LAN_IP> --download \
  --output /private/PS4_CUSA12398_UnityAssets
```

The collector accepts only the following verified original SHA-256 values:
`globalgamemanagers.assets`, `sharedassets0.assets`,
`sharedassets1.assets`, `level0`, `level1`, and `level2`.
Only files with matching hashes are published locally. Other variants or
changed patches are rejected, never silently treated as this exact build.

If the six files already exist in a private desktop extraction, using that
copy avoids console access entirely. Never commit commercial assets into
GitHub or put FTP on the public internet. Anonymous FTP traffic is not
encrypted; use only a trusted local LAN.

## Uploaded ZIP audit — 2026-10-30

The read-only archive verifier was run against the uploaded `Archivo 2.zip`
(50,600,772 bytes; SHA-256
`aa1ae3c04d4d402452410b121e5f621bf3c20b0ab94f91d25497c138159fd86b`).
It scanned 41 ZIP entries without `--extract-dir` and verified four expected
files against the pinned hashes:

| Asset | SHA-256 | Result |
| --- | --- | --- |
| `globalgamemanagers.assets` | `2518dad0f38f6357276d1e33b4653a907df82dc8b0eb56450b49cb3eb86af2a8` | verified |
| `level0` | `d2d1b170cb1494ecaba4616b1d46e9467fac007c60fe0ba18fa8924a0e0ee8aa` | verified |
| `level1` | `cbfff68d57c3cadd304cead6c5486f9eb427c368b443bf4bfedff9d16172e790` | verified |
| `level2` | `99fce056f65647f62ba52d9957317b4ed876e600f854f12e65a20897d37c396d` | verified |

The archive does not contain `sharedassets0.assets` or
`sharedassets1.assets`; the verifier returned exit code `2` and
`all_six_verified: false`. **No files were extracted.** `sharedassets0.assets`
is needed to resolve the Rewired managers and DS4 hardware profile, while
`sharedassets1.assets` contains additional UI action data. A further private
ZIP with those two files—or a ZIP containing all six—will unblock the
complete offline asset analysis. No PKG, console, or PRX operation was used.

**Safety and evidence boundaries:** Transfer has not been performed,
runtime Rewired Player/ControllerMap and OnGUI registration remain unproven,
and this tooling is not a prerequisite to installing a PRX. No hardware
hook or gameplay test is authorized.
