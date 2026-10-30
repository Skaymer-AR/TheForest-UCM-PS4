# Estado del proyecto The Forest UCM PS4

## Estado actual (2026-10-30)

El usuario retiró el PRX experimental y confirmó que The Forest CUSA12398 v1.15 vuelve a iniciar normalmente. No se solicita otra prueba en PS4 durante esta revisión.

El PRX activo es una base sin hooks. Comprueba título/versión y muestra una notificación; no dibuja el menú, no lee el DualShock 4 y no modifica el juego. Ningún artifact con hooks v0.5/v0.6 debe instalarse o recomendarse.

## Historial de hardware confirmado

- v0.3, sin hooks: notificó que cargó y permitió entrar a una partida sin congelamientos.
- v0.5, con renderer GNM y hooks de VideoOut/Pad: la notificación apareció, pero el juego quedó negro después de la pantalla inicial. El shell de PS4 respondió y el juego pudo cerrarse.
- v0.6, perfil passive_all con hooks de VideoOut/Pad: se produjo un bloqueo completo de la consola.
- Tras retirar el PRX experimental, el juego volvió a iniciar normalmente.

Estos resultados relacionan el problema con el camino de integración experimental, pero no identifican el hilo ni la instrucción exacta que falló.

## DebugConsole

En una sesión anterior se observó la instancia de DebugConsole en NULL. Las guardas consultadas después de iniciar tampoco tienen semántica confirmada. No se modificaron guardas, datos del juego, PKG ni partidas; la integración actual no llama a DebugConsole.

No se guardan ni reutilizan direcciones absolutas de esa sesión para este diseño.

## Implementación conservada

El modelo de menú, sus categorías, navegación DualShock normalizada, interfaz de render y generador de draw-list siguen en src/ y sus pruebas host. El backend PS4 v0.5 está archivado en archive/unsafe-v0.5 solo para auditoría. Los detours v0.6 están en archive/unsafe-v0.6. Esos archivos no participan en el build.

El nuevo src/bridge_lifecycle.* es un modelo host-only de estados y leases. No es una integración runtime ni prueba que GoldHEN proporcione una barrera de descarga segura.

## Verificación y límites

- scripts/assert-safe-build.py verifica que el PRX compile sin hooks y que no incorpore el modelo host.
- scripts/test.sh prueba el menú, la capa visual y el modelo de ciclo de vida.
- SANITIZE=1 sh scripts/test.sh ejecuta los tests con ASan y UBSan.
- GitHub Actions produce únicamente theforest-ucm-safe-baseline-only.

La evaluación del trampoline, ABI, riesgos de concurrencia, alternativas de renderizado y los límites de las pruebas está en [SAFE_OVERLAY_DESIGN.md](SAFE_OVERLAY_DESIGN.md). Una compilación o test host no confirma que el overlay funcione en PS4.
