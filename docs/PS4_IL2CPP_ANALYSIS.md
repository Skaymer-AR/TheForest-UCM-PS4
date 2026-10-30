# Análisis estático offline — The Forest PS4 CUSA12398 v1.15

## Procedencia y fuerza de la evidencia

Los 42 RVA originales se recuperaron de la tabla de punteros IL2CPP en el offset de archivo `0x31738C0`. Se mantienen como RVA; no se reutiliza la base RAM `0x8029C000` de una sesión anterior.

El reporte adjunto declara que los 42 prefijos coinciden con el PRX original `Il2CppUserAssemblies.prx`, SHA-256 `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`. Ese PRX no se adjuntó al workspace, así que esta sesión no volvió a calcular las 42 comparaciones. El desensamblado adjunto sí se procesó como texto y sus prefijos de `DebugConsole.OnGUI` y `DebugConsole.ToggleConsole` coinciden con las dos firmas que el usuario confirmó físicamente con PS4Debug. Las otras 40 funciones tienen coincidencia offline reportada, pero no lectura física en RAM.

El reporte privado más reciente identifica el módulo del dump actual como contenedor SCE/SELF (`f7e59035…8777b6`), no como ELF64 mapeable, y registra que su hash difiere del módulo histórico. La metadata conserva el hash histórico, pero eso no valida RVA nativos. El hash diferente tampoco demuestra por sí solo que el código descifrado haya cambiado. Hasta obtener una imagen ELF64 local correspondiente a este dump, los RVA de abajo siguen ligados únicamente a la evidencia histórica; las comprobaciones de anclas del dump actual fueron omitidas. Detalle reproducible sin binarios en [PS4_DUMP_PROVENANCE.json](PS4_DUMP_PROVENANCE.json).

El desensamblado contiene 12 ventanas acotadas; una ventana no representa necesariamente el límite de una función. Se procesó con [analyze_disassembly_report.py](../scripts/analyze_disassembly_report.py), sin guardar el dump adjunto en Git. El analizador ELF [analyze_ps4_il2cpp_candidates.py](../scripts/analyze_ps4_il2cpp_candidates.py) sigue disponible para una comparación byte a byte privada.

## Candidatos, llamadas y contexto

| Método / destino | RVA | Evidencia del desensamblado | Evaluación para UCM |
| --- | ---: | --- | --- |
| `PS4Controller.Update` | `0x00476080` | Guarda `RDI` en `R14`; llama por puntero (`RBX`) y, si se cumple la condición, hace `call 0x004761A0` desde `0x00476179`. Otra rama restaura registros y hace tail-jump a `0x004761A0` desde `0x0047618B`. | **Llama directamente a `ProcessGamePads`.** Es un punto de ciclo de juego/input, no un callback de render ni una API de suscripción. Reemplazarlo aún sería un hook de código del juego. |
| `PS4Controller.ProcessGamePads` | `0x004761A0` | Llama a `Rewired.ReInput.get_players` en `0x00476207`. Las llamadas `call qword ptr [rcx]` en `0x004762D6` y `0x00476315` siguen una secuencia de lookup de interfaz IL2CPP usando el slot de referencia de tipo en `0x033EF3E8`. | Se confirma el camino de abstracción Rewired y el patrón de interfaz/vtable. El tipo Rewired, los métodos y el acceso físico a ScePad siguen sin resolverse. |
| `TheForest.UI.VirtualCursor.LateUpdate` | `0x01F65960` | Comienza copiando `RDI` a `R12`, llama a `0x01F66C60` y después llama varios punteros obtenidos indirectamente. La ventana no muestra una API de render identificable. | Callback de ciclo de juego por nombre/metadatos; no se acredita como callback de render nativo ni como interfaz para agregar otro panel. |
| `TheForest.DebugConsole.OnGUI` | `0x005C37B0` | `RDI` se conserva como receptor; llama `HandleInput` (`0x005C8E00`) y la ventana completa contiene llamadas resueltas a `GUI`, `GUILayout`, `GUI.TextField` y `GUIUtility.CheckOnGUI`. | Es un callback IMGUI compilado, pero no prueba una instancia viva ni una API para registrar un callback externo. La instancia singleton se observó NULL. |
| `TheForest.DebugConsole.ToggleConsole` | `0x005CB6D0` | Compara `[RDI+0x5A]`, escribe el valor invertido en `SIL` y salta a `0x005CA800`. | La arista directa está confirmada tanto por los bytes PS4Debug como por el desensamblado privado. |
| `DebugConsole.ShowConsole` | `0x005CA800` | Copia `RDI` a `R14`, `ESI` a `R13D`, escribe `R13B` en `[R14+0x5A]`, y llama helpers de UI/input. | El nombre se resuelve desde metadata; el flujo no crea un objeto. Requiere un `this` válido y no es un punto de extensión. |
| `DebugConsole.Awake` | `0x005C1C30` | Campo `Cheats.DebugConsole` consultado en `0x005C1E13`; ruta false hacia `Object.Destroy`; store de `this` en `DebugConsole.static_fields+0x10` en `0x005C1EA2`. Otra guarda lee un campo candidato en `0x33EB300`. | Evidencia nueva del PR #2. El valor real del flag no está medido y la identidad PS4 del candidato `CoopPeerStarter.DedicatedHost` sigue sin verificar. CFG completo reproducible requiere el dump privado. |
| `DebugConsole.GetInstance` | `0x005CB690` | Lee y retorna `DebugConsole.static_fields+0x10` (`0x005CB6B0..0x005CB6C2`). | Getter, no instancia ni activa un componente. |
| `DebugConsole.OnDestroy` | **`0x005C3340`** | Original PRX + metadata v23 recuperados: `methodIndex=75393`. Primero puede limpiar `Counters` en `static_fields+0x08` y después, si `Instance` coincide con el objeto destruido, escribe **`this` y no NULL** en `Instance` (`static_fields+0x10`) en `0x005C356C`. | Evidencia offline detallada en [PS4_ONDESTROY_NATIVE_RESOLVED.md](PS4_ONDESTROY_NATIVE_RESOLVED.md). No demuestra ejecución del callback en PS4 ni permite usarlo como punto de extensión. |
| `TheForest.Tools.DllModLoader.Awake` | `0x022CEF10` | Recorre una colección usando su longitud en `[R15+0x18]` y elementos desde `[R15+RBX*8+0x20]`; llama un slot virtual en `0x022CF014` y después a `LoadDllMod` en `0x022CF01D`. | La relación directa `Awake → LoadDllMod` está comprobada en el archivo. No demuestra que exista una API de plugins GoldHEN ni que el mod loader de PC funcione como cargador de extensiones en IL2CPP PS4. |
| `TheForest.Tools.DllModLoader.LoadDllMod` | `0x022CF050` | La ventana muestra varios helpers y llamadas indirectas por vtable; no cubre toda la función. | No se identifica registro de callbacks, renderer o ABI completo para invocarlo. |
| `TheForest.Modding.UI.ModList.OnEnable` | `0x017D5390` | Primer opcode `ret`, seguido de padding. | Método vacío en esta build; no sirve como extensión. |
| `TheForest.Modding.UI.ModList.Refresh` | `0x017D53A0` | Primer opcode `ret`, seguido de padding. | También vacío. `ClearUI` (`0x017D53B0`) sí tiene cuerpo, pero su ventana muestra limpieza/recorrido de UI, no registro para extenderla. |
| `CheatsBridge.SetGodMode` | `0x0147D620` | Conserva `ESI` en `EBX`, obtiene un bloque de campos estáticos y escribe `BL` en el byte `+0x0B`. La ventana siguiente muestra setters vecinos escribiendo en `+0x0C` y `+0x0D`. | Evidencia de setters nativos de estado. No demuestra el prototipo completo, el estado de inicialización del bloque ni que sea seguro invocarlos desde el PRX. No se escriben esos offsets directamente. |

El análisis de llamadas directas entre los inicios conocidos encontró:

- `PS4Controller.Update → PS4Controller.ProcessGamePads`: `call` en `0x00476179` y tail-jump en `0x0047618B`.
- `DllModLoader.Awake → DllModLoader.LoadDllMod`: `call` en `0x022CF01D` dentro del recorrido de colección.
- `DebugConsole.ToggleConsole → 0x005CA800`: tail-jump en `0x005CB6DA`.

Esto no es un grafo global de xrefs. Las ventanas no resuelven automáticamente los destinos indirectos ni la identidad del type-ref de Rewired. El patrón de lookup/vtable sí se reconoce; para nombrar su tipo o métodos hace falta una asociación verificada con metadata y el módulo de esta versión.

## ABI y opción de integración con Unity

Los bytes de `ToggleConsole` corresponden a `xor esi,esi; cmp byte ptr [rdi+0x5A],0; sete sil; jmp rel32`. En la convención AMD64 observada, `RDI` se comporta como puntero a objeto y `SIL` como booleano del segundo argumento. El destino confirma el flujo: guarda esos argumentos y escribe el booleano a `[this+0x5A]`. Es una firma compatible con un wrapper de toggle, no un prototipo IL2CPP completo.

`OnGUI` recibe un valor en `RDI` que preserva como `R12`, consistente con un método de instancia. El cuerpo compilado llama APIs Unity IMGUI, pero no muestra cómo registrar una segunda función `OnGUI` desde el PRX. Interceptar `OnGUI` sería un hook a código del juego y no se habilita.

`LateUpdate` y `Update` son callbacks del ciclo de Unity, no callbacks de la cola gráfica nativa. `GL.IssuePluginEvent` todavía requeriría que el juego encole el evento desde un caller propio. `DllModLoader.Awake` y su llamada a `LoadDllMod` no prueban que `AppDomain.Load` ejecute componentes administrados bajo IL2CPP/AOT ni que exista registro Unity.

Para el DualShock 4, las ventanas del juego no localizan una importación ScePad identificable. La ruta menos invasiva sigue siendo investigar un handle ScePad propio y validar su coexistencia/ownership, entregar snapshots desde un worker y no interceptar `PS4Controller.Update` ni `scePadReadState`. Aún no existe proveedor PS4.

## Componentes seguros que siguen pendientes

1. **OnDestroy y sus dos stores ya están incorporados** al manifiesto y al pipeline: definición `82470`, `methodIndex=75393`, RVA `0x005C3340`; `Counters=0` en `0x005C3384`; `Instance=R14/this` en `0x005C356C`. Los tests host rechazan confundir el segundo store con un cero.
2. Resolver los inicializadores/registro nativo que ligan `0x33EB300` y `0x33EF3E8` a TypeDefs del metadata PS4 v23. La metadata sola y las coincidencias de nombre no bastan.
3. Interpretar los destinos de `ProcessGamePads` solo cuando el receiver, el slot y la tabla de interfaz estén ligados al mismo registro nativo.
4. Mantener `src/unity_host_adapter.*` y el mapper DS4 en host. La decisión formal es **no-go**: no se ha probado callback title-scoped ni loader AOT accesible desde el PRX. Para una integración sin hooks debe permitirse un host AOT del título registrado por su build IL2CPP; el detalle de esa restricción está en [`INTEGRATION_DECISION.md`](INTEGRATION_DECISION.md).

La ejecución local reproducible y sus límites están en
[`IL2CPP_ANALYSIS_PIPELINE.md`](IL2CPP_ANALYSIS_PIPELINE.md). La decisión por
alternativa de render/input y el siguiente componente necesario para un primer
panel están en [`INTEGRATION_DECISION.md`](INTEGRATION_DECISION.md).

No se habilitan hooks, lectura de mando, escrituras de framebuffer ni funciones de gameplay en esta etapa.

## Analizadores offline

Para resumir un desensamblado acotado ya generado en privado:

```sh
python3 scripts/analyze_disassembly_report.py \
  /ruta/privada/Desensamblado_Metodos.txt \
  --output /ruta/privada/summary.md
```

Para mapear RVA y validar bytes directamente contra un ELF privado:

```sh
python3 scripts/analyze_ps4_il2cpp_candidates.py \
  --binary /ruta/privada/Il2CppUserAssemblies.elf \
  --scan-xrefs \
  --output /ruta/privada/ps4-il2cpp-analysis.md
```

Los comandos no suben ni copian archivos del juego. El primer importador no necesita el ELF; contrasta los dos prefijos físicos si aparecen en el texto. El segundo exige que ambos prefijos coincidan antes de desensamblar. Sus pruebas usan texto y ELF sintéticos; no verifican runtime, GoldHEN, Unity ni PS4.

Para el mapa de ciclo de vida de `DebugConsole`, los call-sites IMGUI, los
dispatch indirectos de Rewired y las limitaciones para obtener xrefs completos,
ver [`DEBUGCONSOLE_LIFECYCLE.md`](DEBUGCONSOLE_LIFECYCLE.md). El resolutor
[`resolve_il2cpp_references.py`](../scripts/resolve_il2cpp_references.py)
acepta ventanas privadas acotadas o un `llvm-objdump` completo con
`--full-image`; solo resuelve referencias directas a RVA de método conocidos y
deja los callers sin nombre cuando no hay límites de función fiables.
