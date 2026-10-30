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
The title's mounted files may appear below
`/mnt/sandbox/pfsmnt/CUSA12398-app0/Media/` and/or a patch mount.
The script only enumerates matching title mounts and reads whitelisted files;
a different mount layout fails closed. Merely owning a PKG does not
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

**Safety and evidence boundaries:** Transfer has not been performed,
runtime Rewired Player/ControllerMap and OnGUI registration remain unproven,
and this tooling is not a prerequisite to installing a PRX. No hardware
hook or gameplay test is authorized.
