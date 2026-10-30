# Sony DualShock 4 hardware elements: CUSA12398 v1.15 / Unity 5.6.6f2

**Result:** twenty-four hardware-element identifiers recovered from the private
Unity serialized `Rewired.Data.Mapping.HardwareJoystickMap` object
`sharedassets0.assets:133`. The parser validates the profile by
`MonoScript` class/namespace, target GameObject references, and an exact
element table for this specific build; it does not patch or upload any game file.

**Source provenance:** `Media/sharedassets0.assets`
SHA-256 `f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321`.
The profile includes hardware UUIDs
`83b427e4-086f-47f3-bb06-be266abd1ca5` and
`cd9718bf-a87a-44bc-8716-60a0def28a9f`. These UUIDs also occur in both
previously inspected Rewired InputManager prefabs.

## Identifiers in the serialized hardware profile

| Element name | Rewired hardware element ID |
| --- | ---: |
| Left Stick X / Y | 0 / 1 |
| Right Stick X / Y | 2 / 3 |
| L2 / R2 | 4 / 5 |
| Cross / Circle / Square / Triangle | 6 / 7 / 8 / 9 |
| L1 / R1 | 10 / 11 |
| Share / Options / PS / Touchpad button | 12 / 13 / 14 / 15 |
| Left / Right stick button | 16 / 17 |
| D-Pad Up / Right / Down / Left | 18 / 19 / 20 / 21 |
| Left / Right stick composites | 22 / 23 |

These indices describe the **SonyDualShock4 hardware profile** and must not
be confused with game **action IDs** (`MenuToggle=2`, `Select=57/58`),
OrbisPad button masks, or live readings from a controller. Their presence
does not demonstrate Rewired has assigned this profile to a real player.

`scripts/inspect_ds4_hardware_elements.py` reproduces this inventory
locally without modifying the assets. Synthetic negative tests enforce
missing/mutated profile rejection. A private derived JSON output can be
generated with:

```sh
python3 scripts/inspect_ds4_hardware_elements.py \
  --assets-root /private/UnityAssets \
  --output /private/ds4-hardware-derived.json
```

## AOT prototype adapter

`prototype/Unity56/Assets/UCM/UcmDs4HardwareInput.cs` defines an
`IUcmInputSource` wrapper around an **as-yet-unimplemented** title-owned
`IUcmRewiredHardwareSnapshotSource`. The intended future provider must:

1. Sample the actual connected Rewired controller assigned to the **local
   Player**, from Unity's main thread.
2. Verify that the active controller/profile and map are compatible with the
   serialized hardware IDs above and produce a consistent snapshot.
3. Supply an **element-indexed** 32-bit mask, distinct from platform/OrbisPad
   button masks and action IDs, without consuming gameplay input.
4. Return a clear failure or disconnection if ownership, mapping or
   connection is unknown. The C# adapter then returns neutral input and the
   menu cannot be opened accidentally.

The adapter normalizes L1/R1, D-pad and Cross/Circle only after all checks
pass; the existing `UltimateMenuHost` can consume the normalized snapshot
through its `IUcmInputSource` API. This is not an implementation of the
Rewired runtime provider; we still cannot verify the active Player,
selected controller map, or focus while playing The Forest.

C# 4/Mono unit tests cover both supported UUIDs, element normalization,
disconnection, unknown profile, unassigned Player, unverified map and provider
failure. The CI compiles both Unity stub variants and executes those tests;
the stubs are **not** Unity 5.6/PS4 binaries.

## Decision gate

The Unity Player version, scenes, both input-manager prefab graphs, hardware
element IDs and action catalogs are now identified offline. This still does
not create any AOT code registration or scene bootstrap in the retail title.
Making the graphical UCM appear in the game needs either:

- The original Unity/PS4 project and authorized matching IL2CPP build
  pipeline, to produce a coherent build with our own MonoBehaviour; **not
  available** from a retail PKG or dummy assemblies.
- A **separately authorized** new integration architecture, with its own
  offline safety proof before any new hardware experiment; earlier unsafe
  global hooks froze the PS4 and will not be revived.

There is no verified, low-risk, installable PS4 menu artifact in this stage.
No PKG/PRX modifications, runtime memory patches, or console tests were
performed.
