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

La evidencia recuperada contiene 42 RVA candidatos de PS4 para CUSA12398
v1.15. PS4Debug confirmó las firmas de entrada de `DebugConsole.OnGUI` y
`DebugConsole.ToggleConsole`; las otras entradas no tienen bytes confirmados.
El análisis de candidatos y ABI, más instrucciones para generar xrefs directas
contra un ELF local, está en
[`docs/PS4_IL2CPP_ANALYSIS.md`](docs/PS4_IL2CPP_ANALYSIS.md). El analizador es
[`scripts/analyze_ps4_il2cpp_candidates.py`](scripts/analyze_ps4_il2cpp_candidates.py).

El ELF original, metadatos y dumps generados deben permanecer fuera del
repositorio. El script compara primero las dos firmas PS4 conocidas y se niega
a desensamblar si no coinciden. Nunca usa direcciones RAM de una sesión previa.

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
