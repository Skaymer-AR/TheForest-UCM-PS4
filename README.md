# The Forest UCM PS4

## Estado

Objetivo: The Forest CUSA12398 v1.15, PS4 con firmware 12.02 y GoldHEN 2.4B18.9.
La consola vuelve a iniciar el juego normalmente después de retirar el PRX
experimental. No se solicita instalar ni probar otro PRX en esta etapa.

Los hooks de v0.5/v0.6 causaron una pantalla negra y un bloqueo completo,
respectivamente. El disparador exacto no quedó identificado. No instales ni
recomiendes esos artifacts históricos.

El código de menú, categorías, navegación y draw-list continúa en `src/`.
`src/unity_host_adapter.*` y `src/pad_input_map.*` son prototipos host-only: no
llaman a Unity ni a ScePad y no están incluidos en el PRX. Aún no hay un
callback de Unity verificado y accesible desde GoldHEN, ni un handle DS4 cuya
coexistencia con el juego esté validada. Las acciones de gameplay siguen sin
implementación comprobada.

## Investigación IL2CPP offline

Los SELF de la extracción actual se pudieron recuperar offline: sus payloads
no están cifrados/comprimidos. Ambos ELF reconstruidos coinciden íntegramente
con los anteriores y los 42 prefijos se comprobaron independientemente contra
el módulo actual. Las dos confirmaciones históricas de RAM siguen separadas
de esta comparación offline. El análisis de las llamadas, ABI y contexto está en
[`docs/PS4_IL2CPP_ANALYSIS.md`](docs/PS4_IL2CPP_ANALYSIS.md). Los analizadores
[`scripts/analyze_ps4_il2cpp_candidates.py`](scripts/analyze_ps4_il2cpp_candidates.py)
y [`scripts/analyze_disassembly_report.py`](scripts/analyze_disassembly_report.py)
procesan copias locales sin subirlas.

La [propuesta AOT](docs/AOT_INTEGRATION_PROPOSAL.md) identifica el registro
nativo real y el pipeline necesario para crear un componente propio en Unity.
`scripts/unwrap_plain_self.py` recupera únicamente layouts plaintext soportados;
`scripts/inspect_aot_registration.py` comprueba tablas v23 y presencia del host.
El build original todavía no incluye nuestro componente. Falta un pipeline
reproducible del título antes de poder proponer una integración de paquete.

El ELF original, metadatos y dumps generados deben permanecer fuera del
repositorio. Las herramientas no escriben en el juego ni habilitan hooks. Nunca
usan direcciones RAM de una sesión previa.

## Unity AOT prototype and asset inventory (offline)

The repository now includes a **separate Unity 5.6-oriented C# prototype** under
[`prototype/Unity56/`](prototype/Unity56/README.md). It implements a
`MonoBehaviour` bootstrap, `Update` input snapshot boundary and Unity IMGUI
`OnGUI` panel with the same 13 menu entries as the original C core. The
C# model is tested with Mono and synthetic Unity API stubs in GitHub Actions.
**It has not been compiled inside The Forest or against the PS4 runtime.**
Gameplay-changing entries remain disabled until their game API integration is
proved, and no Rewired/DS4 action IDs have been guessed.

The read-only [Unity asset inventory](docs/UNITY_ASSET_TRIAGE.md) and
[`scripts/inventory_unity_assets.py`](scripts/inventory_unity_assets.py)
select likely Player/scene/bundle paths from a saved private PKG file listing.
The full private PKG was recovered and its Unity assets inspected offline.
The serialized Player version is **5.6.6f2** and all **30 build-scene paths**
are verified in [the asset evidence report](docs/UNITY_PLAYER_ASSETS_20261030.md).
Real Rewired action-to-DS4 bindings and a callable retail bootstrap **remain unverified**.
Neither workflow modifies the PKG or publishes proprietary game assets.

## Rewired scene graph and native prefab selection (verified offline)

The current [Rewired scene/prefab investigation](docs/REWIRED_SCENE_GRAPH_20261030.md)
parses Unity object and script references, not just strings: the start,
title, and gameplay `RewiredSpawner` components all point to two input
prefabs in `sharedassets0.assets`. Verified native metadata names both
prefab fields; `InstanceManager` accesses the XInput field and
`InstanceVRManager` accesses the VR field. The built-in Rewired action
catalogs differ (`Select` is 57 in VR and 58 in XInput). These are action
IDs, **not** known DualShock 4 button bindings.

[`scripts/inspect_unity_rewired_assets.py`](scripts/inspect_unity_rewired_assets.py)
regenerates the evidence read-only from **private** Unity 5.6.6f2 assets.
The 5 input files and original game binaries are never committed; the CI
uses synthetic serialized fixtures. No gameplay controls, hook or PKG
build has been enabled.

## Pruebas host

```sh
python3 scripts/assert-safe-build.py
SANITIZE=1 sh scripts/test.sh
```

Las pruebas cubren el menú, el mapper DS4, el contrato del adaptador host,
fallos de registro/desregistro, concurrencia, y el parser con datos sintéticos.
No prueban el juego ni el runtime PS4.

GitHub Actions ejecuta únicamente verificaciones y pruebas offline. Esta rama
no compila ni publica un PRX de notificación. El source v0.8 y su script de
build se conservan para revisión, pero no son el objetivo del flujo actual.

No se modifican PKG, partidas, framebuffer, flags desconocidos ni direcciones
absolutas de sesiones anteriores.
