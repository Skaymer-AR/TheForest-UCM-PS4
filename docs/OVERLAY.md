# Visual menu foundation

This is a host-tested UI implementation, not a verified in-game overlay.
The first diagnostic CI build succeeded in [run 40957399526](https://github.com/Skaymer-AR/TheForest-UCM-PS4/actions/runs/40957399526)
at `68150e5cdb033f62faeeb3fb2b5b1957be1ca06e`. That result predates this UI.

## Implemented boundary

`source/plugin_main.c` owns one `Overlay`. It refuses duplicate loads and
unexpected title/update, checks that SDK title/version strings are terminated,
initializes UI state on successful load and clears it on unload. No worker,
frame hook, pad handle, Unity object, or game pointer is created. The overlay
remains **detached**: installing this PRX still only displays the load notification.

`src/overlay.c` owns UI-only items and delegates category/navigation behavior to
the portable menu core. Rectangles and text are emitted through synchronous
renderer callbacks in a logical 1280x720 canvas. It uses no gameplay dispatcher.
Current rows change only hint visibility and panel opacity, or close the menu.
Other categories explicitly have no verified actions. Rendering uses bounded
stack text; no per-frame allocation or game memory reads occur.

The platform adapter must call `overlay_attach` only after its prerequisites
are verified, then call `overlay_frame` on the single owning frame thread.
Invalid render callbacks and duplicate attachment are rejected. Input is
normalized, not interpreted as native ScePad button bits. L1+R1 toggles visibility;
D-pad navigates; L1/R1 change tabs; Cross selects; Circle closes. Buttons are
edge-triggered without repeat. Disconnect hides the menu. A neutral input sample
is mandatory on attach/reconnect to avoid activating held buttons. A standalone
shoulder press changes tabs immediately, so assembling the open/close chord
across samples can change the current tab before toggling; it never executes an
action. Input is not suppressed in the game in this stage.

## Console adapter: verification required before implementation/activation

1. Confirm actual plugin load/unload on CUSA12398 v1.15, SDK/GoldHEN versions,
   and the behavior of the current notification probe. CI success is not proof.
2. Discover `Il2CppUserAssemblies.prx` using verified module enumeration, and
   establish its relocated segment ranges, permissions and executable identity
   against the exact locally owned update. The process `base_address` printed
   by the probe is **not** a verified IL2CPP module base. Never reuse the observed
   `0x8029C000` as a fixed base. No game binaries belong in the repository.
3. Identify a render callback that runs even with no DebugConsole instance.
   An independent Unity IMGUI callback is a candidate, not an implemented route.
   Confirm method signatures, return types, calling convention, hidden
   `MethodInfo` arguments, object lifetime, and the render/main thread against
   the exact IL2CPP build before invoking any engine API. Do not assume desktop
   Unity exports or create managed objects from an arbitrary plugin thread.
   `DebugConsole.OnGUI` may never run while its instance is NULL; it is not an
   acceptable assumed frame source. No call to DebugConsole is made here.
4. Implement renderer callbacks using validated engine drawing/text primitives
   and managed-string/font lifetime handling. Save/restore GUI color, matrix,
   clipping and other touched rendering state; draw only in the correct IMGUI
   event phase to avoid duplicate draws. Map the logical canvas to the actual
   viewport and safe area. A native framebuffer backend would need separate
   verification of formats, buffers, fences and render-state preservation;
   guessed framebuffer writes are not a fallback.
5. Verify ScePad ABI and controller/user ownership. Prefer a verified copy of
   existing frame input: do not steal/close a game-owned pad handle or drain its
   event queue. Map actual DS4 bits to `PAD_*`, check connection/read failures,
   and feed one coherent sample per frame. Input capture while visible needs a
   separately verified policy; the prototype does not prevent gameplay input.
6. Only after these checks, install the minimum reversible callback interception.
   A code hook changes executable RAM even if observing game state only; this
   stage installs none. Validate original bytes and relocation/trampoline safety,
   forward original calls exactly once with unchanged arguments and return,
   and fail closed on any mismatch. Do not modify unknown flags, PKG or saves.
7. Before unload, detach the adapter, prevent new callbacks and wait for active
   callbacks on a thread that cannot deadlock the render thread. Restore only
   hook bytes still owned by this plugin, release only plugin-owned resources,
   then call `overlay_stop`. The current detached build has no callbacks to
   drain. `overlay_stop` alone is not synchronization for a future adapter.

Read-only `Awake` instrumentation remains an independent prerequisite for
understanding the inactive console: verify its RVA/signature/ABI and pointer
chains before bounded observations at entry/exit. Post-Awake guard values do
not establish entry values. No guessed signatures or absolute guard addresses
are wired into this implementation. None of the overlay depends on activating
DebugConsole or calling a method through NULL.

## Validation and rollback

Run `sh scripts/test.sh` on Linux or Catalina with a C99 compiler. Tests cover
menu behavior plus renderer validation, draw bounds/content, empty categories,
chord debouncing, UI settings, disconnect/reconnect and stop/reinitialize.
`output/overlay-preview.svg` renders actual draw commands on a host backend;
it is a design preview, not a PS4 screenshot.

For a PRX build, activate LLVM/OpenOrbis, set `OO_PS4_TOOLCHAIN`, `GOLDHEN_SDK`
and `GOLDHEN_TEMPLATE` (official plugin repository), then run
`sh scripts/build-prx.sh`. The shared CI/local script uses a disposable template
copy, leaving upstream tracked files unchanged. The artifact name stays
`theforest_ucm_probe.prx` to preserve the existing installation path. Automated
PR builds test and cross-compile changes; they do not test hardware.

Console validation is offline/single-player only. Keep the existing INI backup;
remove the probe line and restart to roll back, as described in the README.
Do not enable experimental plugins simultaneously. Next milestone is a verified
platform adapter drawing this UI and receiving DS4 input with safe detach.
Gameplay commands remain disabled until each action is independently verified.
