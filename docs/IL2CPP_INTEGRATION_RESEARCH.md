# Investigación de integración Unity IL2CPP

La evidencia PS4 original fue recuperada en [PS4_IL2CPP_PRIOR_EVIDENCE.md](PS4_IL2CPP_PRIOR_EVIDENCE.md): contiene 42 RVA candidatos de The Forest CUSA12398 v1.15 y dos prefijos de 16 bytes confirmados por el usuario con PS4Debug. La tabla no equivale a 42 firmas confirmadas ni aporta por sí sola un ABI invocable.

El análisis aplicado a los candidatos y sus límites está en [PS4_IL2CPP_ANALYSIS.md](PS4_IL2CPP_ANALYSIS.md). El script [analyze_ps4_il2cpp_candidates.py](../scripts/analyze_ps4_il2cpp_candidates.py) puede validar los dos anclajes contra un ELF privado, producir ventanas de desensamblado y encontrar llamadas/saltos directos. Rehúsa continuar si no coinciden ambos anclajes. Los binarios, metadatos y dumps originales permanecen fuera del repositorio.

## Conclusión de integración

`DebugConsole.OnGUI` es el candidato PS4 más próximo a un callback de GUI y su entrada tiene una firma confirmada. `DebugConsole` fue observado con su singleton en `NULL`; no hay una instancia confirmada que reutilizar. Además, `OnGUI` pertenece al ciclo IMGUI de Unity, no es por sí mismo un registro para plugins nativos ni evidencia de que un PRX pueda añadir un segundo callback.

`VirtualCursor.LateUpdate`, `PS4Controller.Update`, `DllModLoader.Awake` y `ModList.OnEnable` tienen RVA extraídos del análisis PS4 previo, pero no bytes, cuerpos, ABI ni referencias cruzadas verificadas en el material disponible en Cloud. Sus nombres/firmas administradas de PC sirven como hipótesis de ciclo de vida, no como prueba para PS4. Las distancias entre RVA tampoco prueban que un método llame a otro.

La única arista que se puede derivar ahora de bytes confirmados es el salto relativo de `DebugConsole.ToggleConsole` (RVA `0x005CB6D0`) a `0x005CA800`. El nombre del destino y su prototipo no se han establecido. El detalle está en el informe PS4.

## Entrada y renderizado

OpenOrbis publica `scePadInit`, `scePadOpen`, `scePadReadState` y `scePadClose` en [Pad.h](https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain/blob/master/PS4Toolchain/include/orbis/Pad.h). Un handle propio y un worker separado evitarían detours compartidos, pero la coexistencia con el handle del juego y la propiedad de un handle “ya abierto” siguen sin verificarse. `src/pad_input_map.*` solo mapea bitmasks en host; no abre ni consulta el mando.

Unity documenta `GL.IssuePluginEvent`/`CommandBuffer.IssuePluginEventAndData` como ruta para ejecutar código nativo desde un evento de render encolado por un caller del juego. No se ha encontrado en estos candidatos un caller administrado accesible desde el PRX. `OnGUI` y `LateUpdate` son callbacks de componente, no callbacks de la cola gráfica nativa.

`src/unity_host_adapter.*` sigue siendo host-only: consume snapshots de input y un proveedor de callback explícito, con registro/desregistro no bloqueantes y retención de recursos si no hay prueba de quiescencia. No implementa una fuente Unity ni se compila en el PRX.

## Reproducir el análisis en privado

```sh
python3 scripts/analyze_ps4_il2cpp_candidates.py \
  --binary /ruta/privada/Il2CppUserAssemblies.elf \
  --output /ruta/privada/ps4-il2cpp-analysis.md
```

Para incluir llamadas y saltos directos de todo el módulo:

```sh
python3 scripts/analyze_ps4_il2cpp_candidates.py \
  --binary /ruta/privada/Il2CppUserAssemblies.elf \
  --scan-xrefs \
  --output /ruta/privada/ps4-il2cpp-analysis.md
```

Si el ELF no expresa el mismo link/image base usado para obtener los RVA, se puede indicar `--image-base 0x...` con el **base virtual de enlace del ELF**, nunca con una dirección RAM de una sesión de PS4Debug. El script no hace llamadas al juego, no parchea, no sube archivos y no acepta una dirección runtime como base documentada. El análisis falla antes del desensamblado si las entradas `OnGUI` y `ToggleConsole` no coinciden con los dos prefijos confirmados.

Los xrefs del script cubren únicamente `call`/`jmp` directos visibles en el desensamblado. No resuelven llamadas indirectas, virtual dispatch, punteros de función, límites exactos de funciones ni el contexto del hilo. Las pruebas sintéticas cubren el parser, el mapeo ELF y el fallo cerrado; no verifican los binarios del juego ni la consola.

## Estado de seguridad

No se habilitan hooks, escritura de framebuffer ni lectura de ScePad en el PRX. La ruta de integración in-game permanece sin validar hasta identificar un callback de Unity alcanzable y un ciclo de vida seguro. Consulte [SAFE_OVERLAY_DESIGN.md](SAFE_OVERLAY_DESIGN.md) para el análisis de trampolines, carreras, descarga y rutas alternativas.
