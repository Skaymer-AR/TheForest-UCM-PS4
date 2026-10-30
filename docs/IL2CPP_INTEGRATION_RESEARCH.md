# Investigación de integración Unity IL2CPP

## Resultado actual

El mejor candidato de ciclo de vida encontrado en la evidencia pública es
`TheForest.DebugConsole.OnGUI`: en una referencia de PC es un callback de GUI
de un `MonoBehaviour`. No es un punto de extensión disponible para este PRX:
la instancia observada en la consola del usuario estaba en `NULL`, y todavía
no se ha demostrado cómo registrar código propio en ese callback desde un PRX
GoldHEN. `TheForest.UI.VirtualCursor.LateUpdate` también es un callback Unity,
pero actualiza el cursor del juego y no ofrece una ruta de dibujo extensible.

No se encontró un método del que podamos afirmar un RVA o una firma IL2CPP
nativa para **CUSA12398 v1.15**. El repositorio no contiene `eboot.bin`, un ELF
descifrado ni `global-metadata.dat`; los resultados de PC no se trasladan a
PS4. Por eso la columna PS4 de la tabla indica el dato faltante en vez de
inventar una dirección.

## Evidencia de métodos

La evidencia de firmas administradas es el código de referencia PC
[`Blightbuster/The-Forest`, commit `be0a628`](https://github.com/Blightbuster/The-Forest/tree/be0a628b4c0260f4d24e7b34e4fc509bd4dc3b5a).
Ese repositorio contiene un decompilado de `Assembly-CSharp` de PC. El mapa de
tipos de [forest-speedrun-tool, commit `c9cb3ed`](https://github.com/1deter/forest-speedrun-tool/blob/c9cb3edf8a145224cf6885402c19a66562571bbe/site/ForestSite/GameCode/steam-types.txt)
confirma algunos nombres en una compilación Steam; solo incluye nombre y hash
de tipo, no métodos ni direcciones.

| Candidato | Firma administrada comprobada en PC | RVA CUSA12398 v1.15 | Referencias y contexto | Evaluación |
| --- | --- | --- | --- | --- |
| `TheForest.Tools.DllModLoader.Awake` | `private void Awake()` | No verificable: faltan ELF y metadatos PS4 | [DllModLoader.cs](https://github.com/Blightbuster/The-Forest/blob/be0a628b4c0260f4d24e7b34e4fc509bd4dc3b5a/Assembly-CSharp/TheForest/Tools/DllModLoader.cs). En PC busca `./DllMods/*.dll`, llama a `LoadDllMod` y usa `Assembly.Load`/reflection para ejecutar entradas estáticas `__`. | Callback de arranque PC. No dibuja UI. No demuestra que ese loader exista o pueda cargar assemblies en IL2CPP PS4. |
| `TheForest.Tools.DllModLoader.LoadDllMod` | `private void LoadDllMod(string filename)` | No verificable | Misma fuente; usa reflection y carga de assemblies administrados. | No es callback de renderizado y depende de un mecanismo PC. |
| `TheForest.Modding.UI.ModList.OnEnable` | `private void OnEnable()` | No verificable | [ModList.cs](https://github.com/Blightbuster/The-Forest/blob/be0a628b4c0260f4d24e7b34e4fc509bd4dc3b5a/Assembly-CSharp/TheForest/Modding/UI/ModList.cs). Llama a `Refresh()`. | Ciclo de vida de UI existente; no es un callback para registrar un segundo panel. |
| `TheForest.Modding.UI.ModList.Refresh` | `public void Refresh()` | No verificable | Misma fuente. | El cuerpo de esa referencia PC está vacío. No es una API de dibujo. |
| `Cheats.CheatsBridge.SetCreative` | `public void SetCreative(bool onoff)` | No verificable | [Cheats.cs](https://github.com/Blightbuster/The-Forest/blob/be0a628b4c0260f4d24e7b34e4fc509bd4dc3b5a/Assembly-CSharp/Cheats.cs). | Bridge de acciones de juego PC; no registra renderizado. |
| `Cheats.CheatsBridge.SetGodMode` | `public void SetGodMode(bool onoff)` | No verificable | Misma fuente; asigna `Cheats.GodMode`. | Gameplay, no UI. No se implementa. |
| `Cheats.CheatsBridge.SetInfiniteEnergy` | `public void SetInfiniteEnergy(bool onoff)` | No verificable | Misma fuente; asigna `Cheats.InfiniteEnergy`. | Gameplay, no UI. No se implementa. |
| `Cheats.CheatsBridge.SetPermaDeath` | `public void SetPermaDeath(bool onoff)` | No verificable | Misma fuente. | Gameplay, no UI. No se implementa. |
| `Cheats.CheatsBridge.SetNoSurvival` | `public void SetNoSurvival(bool onoff)` | No verificable | Misma fuente. | Gameplay, no UI. No se implementa. |
| `Cheats.CheatsBridge.SetUnlimitedHairspray` | `public void SetUnlimitedHairspray(bool onoff)` | No verificable | Misma fuente. | Gameplay, no UI. No se implementa. |
| `TheForest.UI.VirtualCursor.Awake` | `private void Awake()` | No verificable | [VirtualCursor.cs](https://github.com/Blightbuster/The-Forest/blob/be0a628b4c0260f4d24e7b34e4fc509bd4dc3b5a/Assembly-CSharp/TheForest/UI/VirtualCursor.cs). Guarda `Instance` y configura el cursor. | Inicialización de un componente Unity. |
| `TheForest.UI.VirtualCursor.LateUpdate` | `private void LateUpdate()` | No verificable | Misma fuente; ajusta sensibilidad, lock del cursor, HUD y posición virtual. Unity documenta que `LateUpdate` ocurre después de `Update`. | Bucle de juego, no callback nativo de renderizado. Reusar o sustituirlo requeriría acceso al componente y ABI PS4 validados. |
| `TheForest.UI.VirtualCursor.OnDestroy` | `private void OnDestroy()` | No verificable | Misma fuente; limpia la referencia `Instance`. | Ciclo de vida de destrucción; no renderiza. |
| `TheForest.DebugConsole.Awake` | `private void Awake()` | No verificable | [DebugConsole.cs](https://github.com/Blightbuster/The-Forest/blob/be0a628b4c0260f4d24e7b34e4fc509bd4dc3b5a/Assembly-CSharp/TheForest/DebugConsole.cs). | Inicialización del objeto de consola; la instancia PS4 observada estaba ausente. |
| `TheForest.DebugConsole.Update` | `private void Update()` | No verificable | Misma fuente. | Lógica de consola/juego; no es el hilo nativo de render. |
| `TheForest.DebugConsole.OnGUI` | `private void OnGUI()` | No verificable | Misma fuente. | Candidato más cercano a dibujado: Unity llama `OnGUI` para procesar/renderizar GUI y puede hacerlo varias veces por frame. En la sesión del usuario `DebugConsole.Instance` estaba en `NULL`; no hay objeto activo al que conectarse. |
| `TheForest.DebugConsole.GetInstance` | `public static DebugConsole GetInstance()` | No verificable | Misma fuente. | Getter de instancia; una respuesta nula no registra un callback ni crea el objeto. |

Las firmas de la tabla son declaraciones C# de la referencia PC. No son
prototipos nativos de funciones PS4. En IL2CPP el ABI nativo puede incluir
`this`, parámetros ocultos de método/genéricos y detalles del compilador; debe
confirmarse con el binario exacto y desensamblado local.

## ¿Hay un callback real que se pueda reutilizar?

Hay callbacks Unity en el código del juego, pero no encontramos un punto de
registro externo que permita reutilizarlos sin modificar una entrada de
código:

1. `DebugConsole.OnGUI` sería el candidato de GUI si una instancia activa
   existiera. `GetInstance()` no resuelve el `NULL` observado. Crear un
   `GameObject`, invocar `AddComponent` o cambiar un flag de cheats requiere
   llamar Unity/IL2CPP con un ABI y un ciclo de vida que no se han validado.
2. `VirtualCursor.LateUpdate` pertenece a un objeto del juego y toca el cursor
   y HUD. Su nombre no lo convierte en un callback de renderizado. Unity lo
   llama luego de `Update`, no desde la cola nativa de render.
3. `ModList.OnEnable` solo se ejecuta cuando se habilita ese componente; la
   referencia no expone un evento de suscripción para código externo.
4. `DllModLoader.Awake` describe carga dinámica de DLL en la referencia PC.
   Eso no demuestra compatibilidad con IL2CPP, GoldHEN ni PS4.
5. `CheatsBridge` son métodos de juego invocados por el modding PC; no registra
   callbacks ni presenta UI.

La ruta oficial de Unity para ejecutar un callback nativo en el hilo de render
es `GL.IssuePluginEvent`/`CommandBuffer.IssuePluginEventAndData`. Unity exige
que un script del juego encole el evento y que exista un plugin nativo Unity.
Este PRX externo no tiene un caller administrado demostrado. Por tanto, el
adaptador añadido abajo acepta un proveedor de callback explícito para probar
la frontera, pero no implementa ni simula ese proveedor para el juego.

Referencias oficiales:

- [Unity: low-level native plug-in rendering extensions](https://docs.unity.com/en-us/engine/6000.0/manual/programming-environment/plug-ins/native-plugin-interface/low-level-native-plugin-rendering-extensions)
- [Unity: `GL.IssuePluginEvent`](https://docs.unity.com/en-us/engine/6000.6/script-reference/unityengine/gl/issuepluginevent)
- [Unity: `MonoBehaviour.OnGUI`](https://docs.unity3d.com/ja/6000.0/ScriptReference/MonoBehaviour.OnGUI.html)
- [Unity: `MonoBehaviour.LateUpdate`](https://docs.unity3d.com/es/current/ScriptReference/MonoBehaviour.LateUpdate.html)

## DualShock 4 sin interceptar funciones compartidas

OpenOrbis publica las firmas `scePadInit()`, `scePadOpen(userID, type,
index, param)`, `scePadReadState(handle, OrbisPadData *)` y
`scePadClose(handle)` en [Pad.h](https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain/blob/master/PS4Toolchain/include/orbis/Pad.h).
Su [documentación de Pad](https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain/blob/master/docs/MD/PS4%20Libraries/Pad.md)
describe la apertura y lectura por handle. Las constantes de botones usadas
por el mapper host corresponden a
[`_types/pad.h`](https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain/blob/master/PS4Toolchain/include/orbis/_types/pad.h).

La alternativa propuesta evita detours: abrir un handle propio para el usuario
activo, leerlo desde un worker de entrada y publicar solo un snapshot atómico
para el callback visual. El render no llama a ScePad. Si `scePadOpen` indica que
el handle ya está abierto, el prototipo falla cerrado; no toma prestado un
handle que no creó ni lo cierra. El ejemplo de GoldHEN
[`frame_logger`](https://github.com/GoldHEN/GoldHEN_Plugins_Repository/blob/998fe03fe0275b59310511187ba8550ed475a003/plugin_src/frame_logger/source/main.c)
consulta `scePadGetHandle` cuando `scePadOpen` falla por “already opened”, pero
la propiedad y el cierre de ese handle compartido no quedan establecidos por
esa muestra. La coexistencia con el handle que usa The Forest sigue sin
verificar y no se ha implementado en el PRX.

`src/pad_input_map.c` solo transforma el bitmask público en controles
normalizados. `src/unity_host_adapter.c` consume snapshots ya publicados; no
abre, lee ni intercepta ScePad. Ambos son host-only y no están en el build del
PRX.

## Adaptador host-only

`src/unity_host_adapter.*` conserva una frontera explícita:

- exige un proveedor versionado con registro y desregistro no bloqueantes;
- verifica que cada frame llegue en el contexto que el proveedor identifica
  como render;
- lee un snapshot no bloqueante y pasa los botones al overlay existente;
- requiere que `try_unregister` confirme que no quedan callbacks activos,
  pendientes ni futuros antes de permitir detener y liberar el estado;
- en caso `PENDING` o error conserva el estado; no espera ni libera recursos
  con un callback potencialmente en uso.

El host falso de las pruebas sí suministra ese contrato y permite probar menú,
selección, input, registro fallido, callback durante registro, cierre pendiente,
callback concurrente y fallo de desregistro. No existe todavía un proveedor de
Unity que cumpla ese ABI en CUSA12398; el adaptador no se compila en el PRX y no
se presenta como una integración in-game.

## Herramienta offline para la copia local

El repositorio no almacena ejecutables, `global-metadata.dat` ni dumps del
juego. `scripts/analyze_il2cpp.py` consume un `dump.cs` generado localmente por
Il2CppDumper o invoca una copia local del dumper. El dumper documenta soporte
para ELF/ELF64 y el formato de tres argumentos
([proyecto Il2CppDumper](https://github.com/Perfare/Il2CppDumper)). La
herramienta valida el prefijo magic/version de los metadatos, extrae las
declaraciones y RVA del dump, omite las rutas de entrada y escribe el informe
fuera del repo si así se indica. No descarga herramientas, no sube archivos y
no ejecuta el juego.

Si ya generaste `dump.cs` localmente:

```sh
python3 scripts/analyze_il2cpp.py \
  --metadata /ruta/privada/global-metadata.dat \
  --dump-cs /ruta/privada/dump.cs \
  --output /ruta/privada/theforest-candidates.md
```

Si tienes ELF descifrado y el ejecutable local de Il2CppDumper:

```sh
python3 scripts/analyze_il2cpp.py \
  --binary /ruta/privada/eboot.elf \
  --metadata /ruta/privada/global-metadata.dat \
  --dumper /ruta/privada/Il2CppDumper \
  --output /ruta/privada/theforest-candidates.md
```

El informe recuperado permitirá llenar RVA y firma administrada para esos
archivos locales. Después todavía habrá que validar que correspondan a
CUSA12398 v1.15 y confirmar el ABI nativo mediante desensamblado; no basta con
un nombre de método o un RVA.

## Verificación y límites

`SANITIZE=1 sh scripts/test.sh` ejecuta las pruebas C con ASan/UBSan, pruebas
de carreras/desregistro del adaptador y pruebas Python con datos sintéticos.
Los fixtures no incluyen bytes del juego. GitHub Actions ejecuta esos checks y
no compila ni publica un PRX de notificación. Ninguna prueba host confirma la
compatibilidad de un callback o handle en la consola.
