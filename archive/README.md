# Quarantined PS4 backends

These source snapshots are retained for offline review and historical
reproducibility. They are not production sources and must not be compiled,
linked, loaded, or used for hardware trials.

- `unsafe-v0.5/` preserves the GNM renderer, VideoOut buffer observer, and
  passive DualShock 4 adapter from commit `cf4c764`.
- `unsafe-v0.6/` preserves the startup detour diagnostics from commit
  `2cccd52`.

The only PRX build input is `source/plugin_main.c` plus the no-op
`source/ps4_backend.c`. `scripts/assert-safe-build.py` guards that boundary.
