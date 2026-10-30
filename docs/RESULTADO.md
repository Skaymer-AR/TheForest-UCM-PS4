# Estado del proyecto The Forest UCM PS4

Actualizado: 2026-10-30. Rama de trabajo: `feature/visual-menu-foundation`.

## Estado de seguridad

The Forest CUSA12398 v1.15 vuelve a iniciar normalmente cuando el PRX
experimental está retirado. No se solicita otra prueba en PS4 durante esta
etapa.

- v0.3 sin hooks cargó y permitió jugar.
- v0.5 con renderer GNM y hooks de VideoOut/Pad dejó la imagen del juego negra;
  el menú de PS4 siguió respondiendo.
- v0.6 `passive_all` produjo un bloqueo completo de PS4.
- No se capturó la instrucción o el hilo exacto. El análisis de trampolines,
  ABI, concurrencia y descarga distingue riesgos comprobados de hipótesis en
  [SAFE_OVERLAY_DESIGN.md](SAFE_OVERLAY_DESIGN.md).

## Avance de integración Unity

- La referencia pública de PC muestra `DllModLoader.Awake` como cargador de
  assemblies por reflection, `ModList.OnEnable/Refresh` como ciclo de vida de
  UI, `CheatsBridge` como puente de gameplay y `VirtualCursor.LateUpdate` como
  lógica de cursor.
- `DebugConsole.OnGUI` es el candidato más cercano a dibujado en esa referencia
  PC, pero la instancia observada en PS4 estaba en `NULL`. No se encontró una
  forma demostrada de registrar un callback propio desde el PRX.
- No hay binario ELF ni `global-metadata.dat` PS4 en el repo; por eso aún no hay
  RVAs ni ABI nativo comprobables para CUSA12398. La tabla de evidencia y el
  analizador offline están en
  [IL2CPP_INTEGRATION_RESEARCH.md](IL2CPP_INTEGRATION_RESEARCH.md).
- `src/unity_host_adapter.*` es un contrato host-only. Recibe un proveedor
  explícito de frame/render e input, se cierra sin espera y retiene estado si
  no hay prueba de quiescencia. No existe todavía un proveedor para Unity PS4.
- `src/pad_input_map.*` solo transforma los bits públicos de OpenOrbis a
  controles normalizados. Las llamadas `scePadOpen`/`scePadReadState` no se
  integran porque la propiedad/coexistencia de handles con el juego no está
  validada.
- Las opciones de God Mode, stamina, hambre/sed, inventario, construcción,
  teletransporte, spawn, tiempo y clima permanecen sin implementación real.

## Verificación

- `python3 scripts/assert-safe-build.py`: bloquea hooks en el backend y
  confirma que Actions no invoque el build del PRX.
- `SANITIZE=1 sh scripts/test.sh`: pruebas de menú, UI, draw-list, modelo de
  lifecycle, adaptador, mapper DS4 y analizador con entradas sintéticas.
- GitHub Actions corre pruebas offline y no crea un artifact PRX de
  notificación.

Ninguna prueba host confirma que el menú se muestre dentro del juego ni que un
callback o handle sea seguro en hardware. No se modifican PKG, partidas,
framebuffer, flags desconocidos ni binarios originales del juego.
