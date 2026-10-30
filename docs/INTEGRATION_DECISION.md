# Decisión de integración del UCM

**Build objetivo:** The Forest PS4 CUSA12398 v1.15, GoldHEN 2.4B18.9 en
firmware 12.02. **Resultado:** **NO-GO** para un overlay Unity ejecutable con
las restricciones actuales. No se encontró ni se demostró un host AOT
propiedad del título que el PRX GoldHEN pueda cargar o registrar. No se añade
un proveedor ficticio al adaptador existente.

El último dump reportado contiene un módulo SCE/SELF con hash distinto de la
imagen ELF64 histórica que respalda los RVA del análisis. La metadata coincide,
pero no hay ELF descifrado para mapear esos RVA contra el dump actual; esto no
demuestra que el código descifrado haya cambiado. La procedencia está en
[`PS4_DUMP_PROVENANCE.json`](PS4_DUMP_PROVENANCE.json).

La decisión no significa que el objetivo sea imposible en cualquier
arquitectura. Identifica la pieza concreta que falta: un componente ejecutable
compilado/registrado por el backend IL2CPP del juego y un bootstrap que lo
inserte en el ciclo Unity. El PRX actual no ofrece ese bootstrap.

## Evaluación de las rutas

| Ruta | Decisión | Motivo verificable |
| --- | --- | --- |
| `DebugConsole.OnGUI` existente | **BLOQUEADA: callback de gameplay no verificado** | La firma y las llamadas IMGUI se comprobaron en el código PS4; no hay captura de una invocación durante gameplay y la instancia se observó NULL allí. El método compilado no demuestra que Unity lo ejecute en esta sesión ni ofrece registro para UCM. No se integra por detour. |
| Crear un AOT `MonoBehaviour` y añadirlo a un objeto | **NO-GO bajo el estado actual** | Es el host Unity adecuado para `OnGUI` y lectura Rewired, pero no hay proyecto Unity del juego ni loader PS4 demostrado que acepte código nativo AOT nuevo, registre sus métodos en IL2CPP y agregue la instancia a un objeto activo. No se ha demostrado que `DllModLoader.AppDomain.Load` haga ninguna de esas tres cosas. |
| `DllModLoader` / `AppDomain.Load` | **Candidato no validado** | El PS4 nativo confirma la ruta `DllModLoader.Awake → LoadDllMod` y llamadas a `File.ReadAllBytes`/`AppDomain.Load`. Eso demuestra una carga solicitada por el código compilado, no que IL2CPP ejecute IL arbitrario, que los métodos nuevos estén AOT compilados, ni que se registre un `MonoBehaviour`. No contamos el ModAPI de PC como evidencia. |
| Unity native plug-in / `UnityRenderingEvent` | **NO-GO** | Unity debe cargar el módulo como plugin Unity y llamar su inicializador `UnityPluginLoad` con `IUnityInterfaces`; el título debe encolar el evento de render. El loader GoldHEN observado carga un PRX y llama `plugin_load` (resuelve `plugin_unload`, pero eso no forma un ciclo Unity); no proporciona la inicialización Unity ni se encontró un caller del título para encolar un evento. Un evento de render nativo tampoco habilita por sí solo IMGUI. |
| Llamar `GUI`/`GUILayout` desde hilo o notificación del PRX | **NO-GO** | No es un evento IMGUI de Unity. `GUIUtility.CheckOnGUI` dentro del callback existente refuerza que las funciones GUI dependen de ese contexto. |
| Detour title-scoped de `DebugConsole.OnGUI` | **CERRADA / NO-GO** | No existe prueba de ejecución del callback en gameplay. Aunque conservaría el PKG, faltan además ABI del renderer, quiescencia de hilos y teardown seguro. No se habilita el detour ni se genera PRX. |
| Hook global GNM/VideoOut/ScePad | **PROHIBIDO** | Las versiones v0.5/v0.6 causaron pantalla negra y bloqueo de consola. Se mantienen deshabilitadas. |

### Qué aporta cada callback

Unity IMGUI requiere que Unity invoque `OnGUI` en sus eventos GUI —por ejemplo
Layout/Repaint— para un componente asociado a un objeto válido. Un `Update` o
`LateUpdate` del juego demuestra contexto de ciclo de vida Unity, pero no
contexto IMGUI. `GL.IssuePluginEvent` ofrece otro contexto nativo de render,
pero requiere un plugin Unity reconocido y un caller Unity que encole el evento;
no es un registro que el PRX GoldHEN pueda llamar por sí solo.

El código de GoldHEN disponible en el plugin loader llama
`sceKernelLoadStartModule`, resuelve `plugin_load`/`plugin_unload` con
`sceKernelDlsym` y ejecuta `plugin_load`. El loader usa `plugin_unload` en su
ruta de error de carga; no documenta con eso un ciclo de callback Unity ni una
prueba de quiescencia para el cierre normal del PRX. No se pasa un objeto
`UnityEngine`, una interfaz `IUnityInterfaces`, ni un callback de ciclo Unity.
Referencias del loader: [GoldHEN plugin loader](https://github.com/GoldHEN/GoldHEN_Plugins_Repository/blob/main/plugin_src/plugin_loader/source/main.c)
y [plugin template](https://github.com/GoldHEN/GoldHEN_Plugins_Repository/blob/main/plugin_src/plugin_template/source/main.c).

Por tanto, un PRX independiente puede poseer código nativo y su propio
`plugin_load`, pero eso no lo convierte en un componente del PlayerLoop ni le
da contexto GUI. `src/unity_host_adapter.*` expresa el contrato que haría falta
(callback, render context, renderer y snapshot de mando), y sigue host-only:
no existe un proveedor PS4 que satisfaga ese contrato.

## Entrada del DualShock 4

La ruta nativa confirmada del juego es
`PS4Controller.Update → ProcessGamePads → Rewired.ReInput.get_players`.
Las llamadas indirectas en `0x004762D6` y `0x00476315` siguen el patrón de
dispatch de interfaz IL2CPP, pero la interfaz Rewired, los métodos y las
implementaciones concretas no están ligados todavía al registro nativo de
este build. No se atribuyen a `GetButton`, ScePad ni a otra API concreta.

Con un host AOT real, la opción menos intrusiva sería leer un snapshot Rewired
desde un callback propio del título y no consumirlo. Aún habría que verificar
la interfaz/API exacta, dispositivo asignado, jugador, estado de conexión y
cómo pausar o dejar pasar los controles de personaje al abrir/cerrar el menú.
Un handle abierto con `scePadOpen` sería otra posibilidad, pero los headers
públicos solo prueban las firmas; no prueban coexistencia con el handle de
Rewired de este juego. No hay un provider de mando implementado.

## Inicialización y cierre necesarios

Una implementación viable debe cumplir esta secuencia:

1. Un bootstrap del título crea/obtiene una instancia Unity válida en el hilo
   del juego y registra el callback en un estado definido (`Awake`/`OnEnable`).
2. El callback de render llama al menú solo durante el contexto IMGUI válido;
   el callback de entrada lee un snapshot no bloqueante y no comparte ownership
   del dispositivo sin autorización del juego.
3. `OnDisable`/`OnDestroy` deja de publicar el callback. Antes de descargar el
   PRX, el host demuestra que ningún callback está activo, encolado o puede
   comenzar. `plugin_unload` por sí solo no prueba esa quiescencia.
4. Si falla el retiro o no hay prueba de quiescencia, se retiene el estado y no
   se liberan callback, trampolín ni código que pudiera seguir en uso.

El adaptador host existente modela el último contrato de retiro y tiene pruebas
de concurrencia/fallos, pero el juego no provee sus operaciones de registro ni
quiescencia. No se llama `GetInstance` ni ningún método con `this` NULL.

## Restricción que debe cambiar

Para obtener un primer panel **sin hooks**, la vía defendible es añadir un host
AOT propio del título. Eso requiere cambiar la restricción **“no modificar
PKG”** y además disponer de un proyecto/build IL2CPP compatible (o un loader
PS4 documentado que registre código AOT nuevo). El host debe compilar sus
métodos para esta versión, incluirlos en el registro IL2CPP, actualizar en
conjunto `Il2CppUserAssemblies.prx` y `global-metadata.dat`, y crear una
instancia desde una escena/bootstrap del título. Permitir modificar el PKG sin
poder producir ese build/registro no alcanza.

Como alternativa distinta, se podría cambiar la prohibición de hooks globales
por autorización explícita de un **hook limitado a un callback IMGUI activo del
título**, usando un relocator x86-64 que preserve instrucciones RIP-relativas,
publicación sincronizada y quiescencia de todos los hilos. Todavía falta
identificar ese callback activo; `DebugConsole.OnGUI` no califica mientras la
instancia esté ausente. Esta alternativa conserva el PKG, pero deja de cumplir
“sin hooks” y requiere una infraestructura de desvío/rollback nueva, revisada
antes de cualquier PRX.

Con ambas restricciones intactas, no hay un componente ejecutable que pueda
conectar el menú a Unity. El siguiente componente necesario no es otro renderer
ni una notificación: es el **bootstrap AOT del título** (o evidencia verificable
de que `DllModLoader` ya carga y registra uno). Hasta tenerlo, solo avanzan de
forma segura los analizadores, el núcleo host y sus pruebas.

## Estado

| Área | Estado |
| --- | --- |
| Núcleo de menú/navegación | Implementado para host; sigue desconectado de Unity. |
| `DebugConsole.OnDestroy` | RVA `0x005C3340`, índice de definición `82470`, `methodIndex=75393`, token `0x0600777D`; `Counters=0` en `0x005C3384`, `Instance=this` en `0x005C356C`. Evidencia estática offline, no ejecución en consola. |
| Contexto IMGUI accesible desde GoldHEN | **No demostrado / NO-GO**. |
| AOT assembly loader y registro de componente | **No demostrado / NO-GO**. |
| Lectura segura de botones | Rewired es la ruta del juego, pero slots/métodos concretos sin resolver; handle ScePad propio sin prueba de coexistencia. |
| Funciones de cheat | Ninguna disponible en esta integración. |
| Hooks y prueba en hardware | Deshabilitados; no se solicita una prueba nueva en PS4. |

La evidencia del ciclo de vida está en
[`DEBUGCONSOLE_LIFECYCLE.md`](DEBUGCONSOLE_LIFECYCLE.md), los datos nativos en
[`PS4_ONDESTROY_NATIVE_RESOLVED.md`](PS4_ONDESTROY_NATIVE_RESOLVED.md), y la
decisión de seguridad de detours/unload en
[`SAFE_OVERLAY_DESIGN.md`](SAFE_OVERLAY_DESIGN.md).
