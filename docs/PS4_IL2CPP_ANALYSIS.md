# Análisis estático offline — The Forest PS4 CUSA12398 v1.15

## Evidencia y límites

Los RVA se recuperaron del análisis anterior de los binarios reales de PS4, correlacionando la tabla de punteros IL2CPP en el offset de archivo `0x31738C0` con una base observada en una sesión. La lista completa de 42 direcciones está en [PS4_IL2CPP_PRIOR_EVIDENCE.md](PS4_IL2CPP_PRIOR_EVIDENCE.md). Los RVA se conservan; no se reutiliza la base RAM `0x8029C000` de aquella sesión.

El usuario confirmó físicamente por PS4Debug los primeros 16 bytes de `DebugConsole.OnGUI` y `DebugConsole.ToggleConsole`. Las otras 40 entradas son candidatos de RVA procedentes de aquel análisis, sin coincidencia de bytes confirmada en el material disponible ahora. No está el ELF privado en este checkout, por lo que no es posible afirmar aquí un cuerpo de función, una lista completa de xrefs o un ABI nativo para los cinco candidatos solicitados.

El analizador [analyze_ps4_il2cpp_candidates.py](../scripts/analyze_ps4_il2cpp_candidates.py) procesa una copia local privada. Antes de desensamblar exige que los dos prefijos confirmados coincidan en sus RVA. Esto sirve de anclaje contra una base equivocada o un ELF de otra build, pero aún no acredita por sí solo la identidad/versionado completo del archivo.

## Candidatos prioritarios

| Método PS4 | RVA del análisis original | Estado de bytes | Qué permiten concluir los datos actuales |
| --- | ---: | --- | --- |
| `PS4Controller.Update` | `0x00476080` | Candidato; no confirmado | El nombre apunta a lógica de ciclo `Update` del controlador. Sin bytes ni xrefs no se confirma que sea un `MonoBehaviour.Update`, qué objeto lo ejecuta, ni si lee el mando o delega en `ProcessGamePads`. |
| `PS4Controller.ProcessGamePads` | `0x004761A0` | Candidato; no confirmado | Está a `+0x120` del RVA candidato `Update`. La proximidad sugiere revisar ambos en una misma región; no demuestra una llamada entre ellos. |
| `TheForest.UI.VirtualCursor.LateUpdate` | `0x01F65960` | Candidato; no confirmado | Si el nombre coincide con el callback generado por IL2CPP, `LateUpdate` pertenece al ciclo de actualización de Unity, después de `Update`; no es un callback nativo de render. La fuente de PC indica lógica de cursor/HUD, pero su cuerpo no se traslada a PS4. |
| `TheForest.DebugConsole.OnGUI` | `0x005C37B0` | **Prefijo de 16 bytes confirmado en PS4Debug** | Los bytes empiezan `55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 E4`: prólogo que guarda registros y alinea stack; el último opcode queda truncado. Esto no revela el prototipo ni el hilo/contexto. La instancia estática de `DebugConsole` se observó `NULL`, así que no se ha confirmado componente activo al que conectar el menú. |
| `TheForest.Tools.DllModLoader.Awake` | `0x022CEF10` | Candidato; no confirmado | El código de referencia de PC describe carga de DLL/reflection. El candidato PS4 y su cuerpo no demuestran que exista un loader de assemblies modulares en IL2CPP PS4. |
| `TheForest.Tools.DllModLoader.LoadDllMod` | `0x022CF050` | Candidato; no confirmado | Está a `+0x140` de `Awake`. La distancia no demuestra que `Awake` lo llame. Su ABI y el soporte de DLL en PS4 permanecen desconocidos. |
| `TheForest.Modding.UI.ModList.OnEnable` | `0x017D5390` | Candidato; no confirmado | `Refresh` y `ClearUI` aparecen en `0x017D53A0` y `0x017D53B0` (+`0x10` cada uno). Este patrón compacto puede corresponder a stubs/thunks o métodos pequeños; solo bytes y límites de función lo resuelven. La nota anterior de bytes tipo `C3 90...` no está guardada como una firma confirmada, así que no se trata como hecho. |
| `CheatsBridge.SetCreative` / `SetGodMode` / `SetInfiniteEnergy` / `SetNoSurvival` | `0x0147D5C0` / `0x0147D620` / `0x0147D680` / `0x0147D740` | Candidatos; no confirmados | Son nombres de setters de estado de gameplay. No se dispone de bytes/xrefs que acrediten un enlace desde el menú, y ninguno es un punto de renderizado. |
| `TheForest.DebugConsole.ToggleConsole` | `0x005CB6D0` | **Prefijo de 16 bytes confirmado en PS4Debug** | El salto relativo confirmado tiene destino calculado `0x005CA800`; el nombre y ABI del destino no se conocen. Detalle a continuación. |

Las separaciones entre RVA son solo observaciones de layout. Para afirmar una arista se requiere un `call`/`jmp` directo desensamblado o resolver por separado una referencia indirecta/virtual. Ninguna distancia es una referencia cruzada.

## Decodificación de las dos firmas confirmadas

### `DebugConsole.OnGUI`

Firma exacta registrada por PS4Debug:

```text
55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 E4
```

La secuencia parcial corresponde a `push rbp; mov rbp,rsp; push r15; push r14; push r13; push r12; push rbx; and rsp,...`. El byte final `E4` no tiene su byte ModRM en la muestra, de modo que el prólogo no se decodifica completo. No se deduce una firma C/C++, `this`, parámetros IL2CPP ocultos ni seguridad de invocación a partir de este prefijo.

Unity documenta `OnGUI` como parte de IMGUI: procesa eventos GUI y puede ejecutarse varias veces por frame. Eso lo hace el candidato de juego más cercano a presentación 2D, pero no lo convierte en una extensión pública para un PRX. El singleton de `DebugConsole` observado por el usuario era `NULL`; no se probó que hubiera una instancia activa que Unity llamara. Interceptar su entrada sería otro hook y no está habilitado.

### `DebugConsole.ToggleConsole`

Firma exacta registrada por PS4Debug:

```text
31 F6 80 7F 5A 00 40 0F 94 C6 E9 21 F1 FF FF 90
```

Descomposición del prefijo:

```text
31 F6                  xor esi, esi
80 7F 5A 00            cmp byte ptr [rdi + 0x5A], 0
40 0F 94 C6            sete sil
E9 21 F1 FF FF          jmp rel32
```

El `rel32` es `-0xEDF`; el destino se calcula desde el final del salto: `0x005CB6D0 + 0x0F - 0x0EDF = 0x005CA800`. Esta es una referencia estática directa derivada de una firma PS4 confirmada. El destino no se ha identificado por nombre.

Las instrucciones son compatibles con un puntero de objeto en `RDI` (se lee `[RDI+0x5A]`) y un valor booleano en `SIL`, registro bajo del segundo argumento entero en la convención AMD64 común. El tailcall conserva `RDI` y pasa el booleano calculado. Esto no establece el prototipo completo del wrapper IL2CPP ni demuestra que sea seguro invocarlo. Nunca se llama con `RDI == NULL`.

## Interpretación del ciclo de vida / render

- `OnGUI` sería el candidato lógico si una instancia de `DebugConsole` viva recibiera eventos GUI, pero el singleton observado es nulo y no hay API para registrar nuestro propio `OnGUI` desde el PRX.
- `VirtualCursor.LateUpdate` sería una fase de juego de Unity, normalmente en el hilo principal. Su nombre y su implementación de PC no lo convierten en el hilo de render ni en una ruta de dibujo nativa.
- `PS4Controller.Update` y `ProcessGamePads` pueden ser relevantes para observar dónde toma input el juego. Sin desensamblado y referencias cruzadas no se sabe si consultan ScePad, consumen estado ya normalizado o son stubs.
- `DllModLoader.Awake` y `ModList.OnEnable` son eventos de ciclo de vida Unity candidatos. No exponen, según la evidencia disponible, una interfaz de suscripción para añadir nuestro panel. La carga de DLL de PC no acredita mod loading en PS4 IL2CPP.
- La ruta de Unity `GL.IssuePluginEvent` requiere un caller del propio juego que encole el evento. No se encontró tal caller entre estas pruebas; un PRX no obtiene esa ruta solo por existir en el proceso.

No hay, por tanto, un punto de integración de render seguro confirmado. El renderer del menú y su draw-list siguen desacoplados; no se añade un detour de VideoOut, GNM, ScePad ni de los métodos candidatos.

## Entrada DualShock 4

Las funciones públicas OpenOrbis `scePadInit`, `scePadOpen`, `scePadReadState` y `scePadClose` permiten estudiar un handle propio sin interceptar funciones compartidas. No se ha verificado que el título permita abrir un segundo handle, ni quién es dueño de un handle reportado como ya abierto. No se toma prestado ni se cierra un handle del juego. `src/pad_input_map.*` solo convierte bitmasks de un snapshot en controles normalizados y permanece host-only; no implementa lectura real en PS4.

Una futura ruta sin detour tendría que validar primero propiedad/coexistencia del handle, mover lecturas a un worker acotado y entregar snapshots atómicos al callback visual. Esa ruta aún no está integrada ni probada en consola.

## Reanálisis con ELF privado

El archivo original no se incluye en Git. Ejecutar localmente con un ELF descifrado que corresponda a CUSA12398 v1.15:

```sh
python3 scripts/analyze_ps4_il2cpp_candidates.py \
  --binary /ruta/privada/Il2CppUserAssemblies.elf \
  --output /ruta/privada/ps4-il2cpp-analysis.md
```

Para escanear `call` y `jmp` directos a los 42 destinos y mostrar sus sitios:

```sh
python3 scripts/analyze_ps4_il2cpp_candidates.py \
  --binary /ruta/privada/Il2CppUserAssemblies.elf \
  --scan-xrefs \
  --output /ruta/privada/ps4-il2cpp-analysis.md
```

El mapeo ELF usa el link/image base de `PT_LOAD`; si debe especificarse, `--image-base` espera ese valor estático, nunca la dirección RAM de PS4Debug. El script contrasta ambas firmas antes de desensamblar; para cambiar un mapeo se corrige el image base hasta que ambas anclas coincidan, sin sustituirlas por direcciones runtime. El resultado solo informa aristas directas; virtual dispatch e indirect calls requieren análisis separado. No sube el ELF ni lo copia al repositorio.

Comprobación host de parser y casos sintéticos:

```sh
python3 -m unittest discover -s tests -p 'test_ps4_il2cpp*.py' -v
```

La prueba host no valida un ELF del juego, GoldHEN, Unity ni el hardware PS4.
