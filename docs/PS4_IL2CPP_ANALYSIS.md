# Análisis estático offline — The Forest PS4 CUSA12398 v1.15

## Procedencia y fuerza de la evidencia

Los 42 RVA originales se recuperaron de la tabla de punteros IL2CPP en el offset de archivo `0x31738C0`. Se mantienen como RVA; no se reutiliza la base RAM `0x8029C000` de una sesión anterior.

El reporte adjunto declara que los 42 prefijos coinciden con el PRX original `Il2CppUserAssemblies.prx`, SHA-256 `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`. Ese PRX no se adjuntó al workspace, así que esta sesión no volvió a calcular las 42 comparaciones. El desensamblado adjunto sí se procesó como texto y sus prefijos de `DebugConsole.OnGUI` y `DebugConsole.ToggleConsole` coinciden con las dos firmas que el usuario confirmó físicamente con PS4Debug. Las otras 40 funciones tienen coincidencia offline reportada, pero no lectura física en RAM.

El desensamblado contiene 12 ventanas acotadas; una ventana no representa necesariamente el límite de una función. Se procesó con [analyze_disassembly_report.py](../scripts/analyze_disassembly_report.py), sin guardar el dump adjunto en Git. El analizador ELF [analyze_ps4_il2cpp_candidates.py](../scripts/analyze_ps4_il2cpp_candidates.py) sigue disponible para una comparación byte a byte privada.

## Candidatos, llamadas y contexto

| Método / destino | RVA | Evidencia del desensamblado | Evaluación para UCM |
| --- | ---: | --- | --- |
| `PS4Controller.Update` | `0x00476080` | Guarda `RDI` en `R14`; llama por puntero (`RBX`) y, si se cumple la condición, hace `call 0x004761A0` desde `0x00476179`. Otra rama restaura registros y hace tail-jump a `0x004761A0` desde `0x0047618B`. | **Llama directamente a `ProcessGamePads`.** Es un punto de ciclo de juego/input, no un callback de render ni una API de suscripción. Reemplazarlo aún sería un hook de código del juego. |
| `PS4Controller.ProcessGamePads` | `0x004761A0` | La ventana parcial llama a `0x00934F40`; también hace llamadas indirectas `call qword ptr [rcx]` en `0x004762D6` y `0x00476315`. | Puede ayudar a localizar el flujo de mando, pero la ventana no identifica `scePadReadState` ni permite descartar que se consulte dentro de esos helpers. No hay una lectura DS4 propia demostrada aquí. |
| `TheForest.UI.VirtualCursor.LateUpdate` | `0x01F65960` | Comienza copiando `RDI` a `R12`, llama a `0x01F66C60` y después llama varios punteros obtenidos indirectamente. La ventana no muestra una API de render identificable. | Callback de ciclo de juego por nombre/metadatos; no se acredita como callback de render nativo ni como interfaz para agregar otro panel. |
| `TheForest.DebugConsole.OnGUI` | `0x005C37B0` | Prólogo guarda registros, alinea `RSP` a 32 bytes y reserva `0x100`; guarda `RDI` en `R12`, llama a `0x005C8E00`, prueba `AL` y lee `byte ptr [R12+0x5A]`. | Es el candidato más cercano al flujo IMGUI. El singleton observado anteriormente era NULL; el desensamblado no demuestra que Unity invoque actualmente una instancia válida. Las llamadas son direcciones sin símbolos, no se identifica `GUI.*` o un renderer externo. |
| `TheForest.DebugConsole.ToggleConsole` | `0x005CB6D0` | Compara `[RDI+0x5A]`, escribe el valor invertido en `SIL` y salta a `0x005CA800`. | La arista directa está confirmada tanto por los bytes PS4Debug como por el desensamblado privado. |
| Destino de `ToggleConsole` | `0x005CA800` | Copia `RDI` a `R14`, `ESI` a `R13D`, y escribe `R13B` en `[R14+0x5A]`. Luego llama helpers y una función indirecta; cuando el estado nuevo es verdadero también escribe `1` en `[R14+0xED]`. | Código real relacionado con el estado de la consola; el mismo byte `this+0x5A` que consulta `OnGUI`. El nombre del método, sus efectos completos y su seguridad de invocación siguen sin validarse. No llamar con un `this` desconocido o nulo. |
| `TheForest.Tools.DllModLoader.Awake` | `0x022CEF10` | Recorre una colección usando su longitud en `[R15+0x18]` y elementos desde `[R15+RBX*8+0x20]`; llama un slot virtual en `0x022CF014` y después a `LoadDllMod` en `0x022CF01D`. | La relación directa `Awake → LoadDllMod` está comprobada en el archivo. No demuestra que exista una API de plugins GoldHEN ni que el mod loader de PC funcione como cargador de extensiones en IL2CPP PS4. |
| `TheForest.Tools.DllModLoader.LoadDllMod` | `0x022CF050` | La ventana muestra varios helpers y llamadas indirectas por vtable; no cubre toda la función. | No se identifica registro de callbacks, renderer o ABI completo para invocarlo. |
| `TheForest.Modding.UI.ModList.OnEnable` | `0x017D5390` | Primer opcode `ret`, seguido de padding. | Método vacío en esta build; no sirve como extensión. |
| `TheForest.Modding.UI.ModList.Refresh` | `0x017D53A0` | Primer opcode `ret`, seguido de padding. | También vacío. `ClearUI` (`0x017D53B0`) sí tiene cuerpo, pero su ventana muestra limpieza/recorrido de UI, no registro para extenderla. |
| `CheatsBridge.SetGodMode` | `0x0147D620` | Conserva `ESI` en `EBX`, obtiene un bloque de campos estáticos y escribe `BL` en el byte `+0x0B`. La ventana siguiente muestra setters vecinos escribiendo en `+0x0C` y `+0x0D`. | Evidencia de setters nativos de estado. No demuestra el prototipo completo, el estado de inicialización del bloque ni que sea seguro invocarlos desde el PRX. No se escriben esos offsets directamente. |

El análisis de llamadas directas entre los inicios conocidos encontró:

- `PS4Controller.Update → PS4Controller.ProcessGamePads`: `call` en `0x00476179` y tail-jump en `0x0047618B`.
- `DllModLoader.Awake → DllModLoader.LoadDllMod`: `call` en `0x022CF01D` dentro del recorrido de colección.
- `DebugConsole.ToggleConsole → 0x005CA800`: tail-jump en `0x005CB6DA`.

Esto no es un grafo global de xrefs. Las ventanas no resuelven llamadas indirectas, imports, vtables ni límites completos de cada función.

## ABI y opción de integración con Unity

Los bytes de `ToggleConsole` corresponden a `xor esi,esi; cmp byte ptr [rdi+0x5A],0; sete sil; jmp rel32`. En la convención AMD64 observada, `RDI` se comporta como puntero a objeto y `SIL` como booleano del segundo argumento. El destino confirma el flujo: guarda esos argumentos y escribe el booleano a `[this+0x5A]`. Es una firma compatible con un wrapper de toggle, no un prototipo IL2CPP completo.

`OnGUI` recibe un valor en `RDI` que preserva como `R12`, consistente con un método de instancia. Unity ejecuta `OnGUI` dentro de IMGUI y puede invocarlo varias veces por frame. La ventana aporta referencias a lógica propia, pero no muestra cómo registrar una segunda función `OnGUI` desde el PRX. Interceptar `OnGUI` sería un hook de código del juego y el ciclo de vida/trampolín aún no está aprobado.

`LateUpdate` y `Update` son callbacks del ciclo de Unity, no callbacks de la cola gráfica nativa. `GL.IssuePluginEvent` todavía requeriría que el juego encole el evento desde un caller propio. `DllModLoader.Awake` es el próximo candidato de investigación offline por su recorrido y llamada real a `LoadDllMod`, pero no se debe tomar como una vía de carga probada.

Para el DualShock 4, las ventanas del juego no localizan una importación ScePad identificable. La ruta menos invasiva sigue siendo investigar un handle ScePad propio y validar su coexistencia/ownership, entregar snapshots desde un worker y no interceptar `PS4Controller.Update` ni `scePadReadState`. Aún no existe proveedor PS4.

## Próximos componentes seguros

1. Usar el mapa IL2CPP privado para resolver los helpers observados `0x00934F40`, `0x01FB2160`, `0x02166EB0` y `0x01DADDD0`, y obtener cuerpos completos de `ProcessGamePads`, `VirtualCursor.LateUpdate` y `LoadDllMod`.
2. Resolver por nombre los métodos indirectos/vtables y los imports usados por `ProcessGamePads`; solo entonces clasificar su acceso a ScePad.
3. Extraer firmas administradas y prototipos nativos completos de los métodos candidatos, sin ejecutarlos ni escribir estado del juego.
4. Mantener `src/unity_host_adapter.*` y el mapper DS4 en host; no añadir provider Unity/PS4 hasta demostrar una fuente de callback y ownership de input.

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
