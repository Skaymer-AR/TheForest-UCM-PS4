# DebugConsole, Unity IMGUI y Rewired — decisión de integración

**Juego:** The Forest PS4 CUSA12398 v1.15. **Alcance:** análisis estático
offline y herramientas locales. No se ejecuta código del juego, no se accede a
memoria de consola, no se activan hooks ni flags, y no se genera un PRX.

## Decisión

**NO-GO: el PRX GoldHEN actual no tiene una vía legítima demostrada para
registrar o ejecutar un panel Unity IMGUI.** `DebugConsole.OnGUI` es una ruta
IMGUI real compilada en el juego, pero no es una API de extensión. `Awake`
puede destruir el componente antes de registrar la instancia, y
`GetInstance` solo devuelve el campo estático. No se ha demostrado un objeto
vivo de `DebugConsole`, un callback de Unity que el PRX pueda registrar, ni un
cargador IL2CPP PS4 capaz de aportar un nuevo callback AOT.

Por lo tanto, el menú UCM y su navegación se mantienen desconectados del juego.
No llamar a `OnGUI`, `GetInstance`, `ShowConsole`, Rewired ni métodos de
gameplay desde el PRX; no usar `DebugConsole` NULL; no modificar flags; no
reactivar los hooks v0.5/v0.6.

## Evidencia y confianza

Los resultados nativos de `Awake` y `GetInstance` provienen del análisis
offline que el usuario hizo sobre el PRX original y registró en el comentario
del PR #2 del 2026-10-30. El PRX y `global-metadata.dat` no están montados en
este checkout. El reporte previo registra SHA-256 del módulo
`0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`, metadata
v23 con SHA-256
`238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`, y 42/42
prefijos comparados offline. Solo `OnGUI` y `ToggleConsole` se comprobaron
además físicamente con PS4Debug.

| Hallazgo | Estado | Alcance de la conclusión |
| --- | --- | --- |
| `DebugConsole.Awake`, `0x005C1C30` | RVA resuelto contra el PRX/metadata privados; flujo parcial resumido abajo | Se conocen guardas, un registro y rutas a `Object.Destroy`; el dump nativo completo no está en este repositorio para volver a dibujar todas las aristas. |
| `Cheats.DebugConsole` | Campo estático identificado en metadata PS4 v23; el guard nativo lee `Cheats.static_fields+0x10` en `0x005C1E13` | Cuando el byte es cero, la rama conduce a una ruta `Destroy`. El valor durante la sesión real no está verificado. |
| `DebugConsole.Instance` | Campo estático identificado en metadata PS4 v23; `Awake` almacena `this` en `static_fields+0x10` en `0x005C1EA2` | Registro condicionado, no una API pública de registro. |
| `DebugConsole.GetInstance`, `0x005CB690` | Cuerpo inspeccionado en el PRX original, `0x005CB6B0..0x005CB6C2` | Lee y retorna el mismo `Instance`; no crea ni activa un objeto. |
| Clase referida desde `0x33EC070` | `Cheats` corroborada por el campo y el uso de `CheatsBridge.SetGodMode` | Confirmación del tipo de esa referencia según el análisis del PR; no convierte su RVA en dirección RAM reutilizable. |
| Referencia `0x33EB300`, byte `static_fields+0x01` | Candidata `CoopPeerStarter.DedicatedHost` por comparación con PC | **No identificada de forma independiente en el registro de tipos PS4**. La rama `je 0x005C1D2B` evita la ruta de destrucción cuando el byte es cero; su significado de juego sigue siendo candidato. |
| Singleton `Instance` NULL | Observación anterior de PS4Debug, en menú y partida | Hecho de esas lecturas; no mide el valor de los flags en entrada a `Awake` ni demuestra que `Awake` se ejecutó en esas escenas. |
| `DebugConsole.OnDestroy` | No hay RVA/cuerpo nativo en la evidencia acotada disponible aquí | No se puede afirmar si limpia, conserva o compara `Instance`. No se infiere el comportamiento estándar de Unity como comportamiento de esta clase. |

El manifiesto [`PS4_STATIC_FIELD_EXPECTATIONS.json`](PS4_STATIC_FIELD_EXPECTATIONS.json)
fija versión y hash de metadata reportados, junto con los dos nombres de campo
estático. [`verify_il2cpp_static_fields.py`](../scripts/verify_il2cpp_static_fields.py)
contrasta esos nombres y su declaración `static` con un `dump.cs` generado
localmente. La nota `static_fields+0x10` procede del desensamblado nativo: no
es un offset que el formato de metadata por sí solo verifique. El validador
tampoco puede probar que `0x33EB300` sea la clase `CoopPeerStarter`.

## Flujo de control conocido de `Awake`

El siguiente es un **mapa parcial basado en las instrucciones RVA reportadas
en la investigación privada**, no una reconstrucción byte a byte en este
checkout. Los guardas no se usan como autorización para cambiar el estado del
juego.

1. En `0x005C1C92`, `Awake` consulta el byte en `static_fields+0x01` de la clase
   referida desde `0x33EB300`. `je 0x005C1D2B` salta la ruta que termina en
   `Object.Destroy` (`0x02176930`) cuando el byte vale cero. `DedicatedHost` es
   solo la identificación candidata de esa clase/campo; debe resolverse en el
   registro de tipos PS4.
2. Más adelante, `Awake` comprueba el `DebugConsole.Instance` previo y usa
   `UnityEngine.Object.op_Implicit`/`CompareBaseObjects` para distinguir una
   instancia Unity válida/competidora. El análisis compartido indica que una
   instancia preexistente distinta se destruye antes de registrar la nueva.
   El volcado completo para fijar cada branch target no está disponible en el
   checkout actual.
3. En `0x005C1E13`, comprueba el byte que corresponde a
   `Cheats.DebugConsole`. Cuando está deshabilitado (byte cero), el flujo va a
   una ruta de `Object.Destroy`; el cuerpo asigna el singleton solo en la ruta
   que supera los guardas.
4. En `0x005C1EA2`, `Awake` escribe `this` en
   `DebugConsole.static_fields+0x10`.
5. `GetInstance` (`0x005CB690`) lee ese campo y lo retorna. No hay
   instanciación, reactivación ni creación de callback en el getter.

Esto explica una causa **posible y respaldada por código** del singleton NULL:
el guard `Cheats.DebugConsole == false` conduce a destrucción antes del
registro. No prueba que ese flag tuviera ese valor en la consola, ni que sea la
causa de las observaciones NULL. La identidad exacta de `DedicatedHost` sigue
pendiente de metadata PS4.

El analizador [`analyze_il2cpp_lifecycle.py`](../scripts/analyze_il2cpp_lifecycle.py)
construye un CFG conservador a partir de una ventana nativa privada. Puede
seguir ramas directas dentro de la ventana, marcar calls a
`UnityEngine.Object.Destroy` y comprobar stores a memoria anotados por el
analista. No infiere semántica de un campo desde un registro. Las pruebas usan
ventanas sintéticas y validan el algoritmo, no sustituyen la ventana privada
completa de `Awake`.

## `OnDestroy`: RVA y limpieza pendientes de los originales

El desensamblado adjunto contiene ventanas selectivas de doce métodos, pero no
incluye `DebugConsole.OnDestroy`. Los archivos originales
`Il2CppUserAssemblies.prx` y `global-metadata.dat` tampoco están montados en
este workspace. Por eso aquí no hay evidencia para publicar el índice
`MethodDefinition`, el `methodIndex`, el RVA exacto, el cuerpo o una escritura a
`Instance` de `OnDestroy`. La respuesta verificable sigue siendo **no resuelto**;
no se infiere que Unity limpie el singleton por comportamiento usual.

El nuevo comando único
[`analyze_ps4_il2cpp_pipeline.py`](../scripts/analyze_ps4_il2cpp_pipeline.py)
lee el método directamente de metadata v23, selecciona el puntero nativo con
`methodIndex`, valida que el RVA caiga en un `PT_LOAD` file-backed y puede
desensamblar una ventana local acotada. El análisis solo reporta una limpieza
directa si una anotación basada en la instrucción exacta identifica el campo y
el `MOV` tiene fuente inmediata cero. Registros, alias, helpers o ventanas con
saltos externos quedan sin resolver. Una ventana CFG cerrada tampoco prueba por
sí sola el tamaño exacto del método ni que Unity invoque `OnDestroy`.

No se ha vuelto a buscar el cuerpo de `Awake` o `GetInstance`; sus hechos
siguen separados en el manifiesto estático: `Cheats.DebugConsole` se lee en la
guarda cerca de `0x005C1E13`, mientras `this` se escribe a
`DebugConsole.Instance` en `0x005C1EA2`.

## DualShock 4: ruta Rewired

| Sitio | Operación observada en PS4 | Qué acredita |
| ---: | --- | --- |
| `PS4Controller.Update`, `0x00476080` | Llama a `ProcessGamePads` en `0x00476179`; otra ruta hace tail-jump a `0x004761A0` en `0x0047618B`; también llama `UpdateConnectionMap` (`0x00476DD0`) | El callback `Update` del juego conduce al procesado de pad. No es callback de render ni punto de extensión demostrado. |
| `ProcessGamePads`, `0x004761A0` | Llama `Rewired.ReInput.get_players` (`0x00934F40`) en `0x00476207` | El juego usa la abstracción Rewired. No revela por sí solo la API física que recibe el estado. |
| `0x00476279` | Carga el slot de referencia de tipo en `0x033EF3E8`; busca el tipo entre las interfaces de la clase de un objeto | Patrón de resolución de interfaz IL2CPP. El nombre de tipo no está ligado a metadata en la evidencia actual. |
| `0x004762C1..0x004762D6` | Calcula una entrada de tabla de métodos de interfaz, carga un puntero en `RSI`, invoca el slot en `[RCX]` | Dispatch de interfaz/vtable fuertemente respaldado por la secuencia. Método destino y prototipo siguen sin resolver. |
| `0x00476300..0x00476315` | Repite el lookup/dispatch para otro receptor/resultante | Segunda llamada indirecta compatible con dispatch IL2CPP; no se identifica como `GetButton`, lectura ScePad ni otro método concreto. |

En ambas llamadas, el receptor llega en `RDI` y el slot de `MethodInfo` se
carga en `RSI` antes de `call qword ptr [RCX]`. Es evidencia de flujo de
registros coherente con el ABI nativo IL2CPP de esta ruta, no una firma
administrada ni un target demostrado. El slot de referencia `0x033EF3E8` necesita
resolverse desde el inicializador/clase asociada del **mismo PRX** y ligarse al
tipo de metadata v23 antes de nombrar la interfaz.

El pipeline unificado inspecciona metadata v23 y reporta candidatos `Rewired`
en una tabla sin asociarlos al slot. Metadata de tipos y un RVA de variable
global no bastan para probar la relación: falta la tabla/registro nativo exacto
del build y el inicializador que puebla ese slot. En la ventana adjunta, el
resolutor confirma ambas instrucciones `call qword ptr [RCX]` como dispatch
indirecto con referencia al slot `0x033EF3E8`; no identifica la interfaz,
método, implementación ni API ScePad.

La ruta demostrada es `PS4Controller.Update → ProcessGamePads → Rewired`; no
hay evidencia aquí de un lector de DualShock accesible sin interceptar el
juego. Un handle ScePad propio podría ser independiente de esos hooks, pero el
SDK disponible no acredita que coexista con el handle de The Forest ni que no
consuma su entrada. Por tanto, no hay provider DS4 habilitado.

## Arquitectura propuesta y requisitos

La única vía Unity IMGUI técnicamente válida sería que **Unity invoque un
callback de un componente/plug-in del título** en un contexto IMGUI real, y
que dicho callback envíe el draw list UCM al sistema GUI. En esta build, el
candidato existente es `DebugConsole.OnGUI`, que llama `GUI`, `GUILayout`,
`GUI.TextField` y `GUIUtility.CheckOnGUI`. La existencia de ese cuerpo no
permite que el PRX registre un segundo `OnGUI`.

La alternativa concreta es una frontera title-scoped:

```text
callback Unity propiedad del título (IMGUI/Update)
       ├── obtiene snapshot de entrada en el contexto del juego
       ├── alimenta el menú y mapper ya existentes
       └── emite draw list dentro del contexto Unity válido
                    ↕ interfaz estable y versionada
              estado UCM nativo
```

Para considerarla implementable tienen que validarse todos estos puntos:

1. Un cargador existente de esta build que soporte código AOT/IL2CPP y que
   pueda introducir un componente/callback en el ciclo Unity. La llamada
   `AppDomain.Load` observada en `DllModLoader` no demuestra que IL2CPP pueda
   ejecutar el DLL ni que se instale un `MonoBehaviour`.
2. Una firma/callback del título con `OnGUI` activo, contexto de GUI correcto,
   hilo y duración de vida definidos. `UnityEngine.Rendering`/`IssuePluginEvent`
   solo sería una alternativa para render nativo si un caller Unity del título
   realmente encola el evento y existe un plugin Unity compatible cargado.
3. Una fuente de entrada de solo lectura con ownership/coexistencia probada:
   snapshot Rewired desde callback propio del título, o un handle DS4 que no
   interfiera con el handle existente. Ninguna está resuelta todavía.
4. Un contrato de desactivación que retire el callback y espere prueba de
   quiescencia antes de liberar estado; no usar esperas bloqueantes en hilo de
   render/input ni liberar recursos mientras un callback pueda estar activo.

**Decisión práctica:** no se ha demostrado hoy que el juego tenga un loader
compatible para la primera pieza. Si no existe un componente AOT ya disponible
en el título o un loader documentado y funcional que pueda añadirlo sin
modificar PKG, un PRX GoldHEN independiente no puede insertar legítimamente un
panel Unity IMGUI bajo las restricciones actuales. Un compositor HDMI externo
sería una alternativa visual fuera del proceso, pero no cumpliría el objetivo
de overlay Unity ni el control de cheats del juego.

## Decisión de integración

La evaluación GO/NO-GO por alternativa, requisitos del callback y siguiente
componente se mantiene en [`INTEGRATION_DECISION.md`](INTEGRATION_DECISION.md).
La ejecución local reproducible y los límites de parser están en
[`IL2CPP_ANALYSIS_PIPELINE.md`](IL2CPP_ANALYSIS_PIPELINE.md). Ambos documentos
mantienen el safety hold: no hooks, no flags y no prueba nueva en consola.
