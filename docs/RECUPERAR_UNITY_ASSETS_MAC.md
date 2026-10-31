# Launch the read-only collector on macOS

The standalone **`tools/Recuperar_Assets_TheForest.command`** prompts for a local PS4
IP, runs the no-transfer directory inventory, then asks whether to download
the six exact-build Unity files to the user's **Mac Desktop**.

- macOS Catalina compatible Bash script; `curl` and `python3` required.
- Helper source is pinned to reviewed commit `d0478d33` (not a moving branch).
- Downloaded game files are private; do not commit them to this repository.
- Unmodified installed The Forest CUSA12398 v1.15 needs to be running at its
  title menu, with GoldHEN FTP server enabled on local TCP port 2121.
- The PS4 FTP game mount **may** not be visible on all environments; no PS4
  connection test has been performed. Existing hash-checked script will report
  a precise failure rather than guessing paths or changing the console.
- On Mac: download the `.command` file, right-click it and choose Open on
  first use. If execution permission is lost during download, from its folder
  run `chmod +x Recuperar_Assets_TheForest.command`.
- The script never writes to the PS4, installs plugins or patches the PKG.

No menu-host runtime/DS4 controller-map callback is proven from these files.
