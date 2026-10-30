# DebugConsole, Unity IMGUI y Rewired — análisis offline

**Objetivo:** determinar si la `DebugConsole` del juego ofrece un ciclo de vida
legítimo donde integrar el UCM, y mapear la ruta de entrada de PS4. El análisis
es estático y de solo lectura para The Forest CUSA12398 v1.15. No se ejecuta
código del juego ni se accede a memoria de consola.

## Resultado

`DebugConsole.OnGUI` es una implementación Unity IMGUI real y su firma de
entrada fue confirmada físicamente por PS4Debug. Eso acredita que el código
está compilado en el PRX, no que Unity esté invocando actualmente el callback.
La instancia singleton se observó como NULL en el menú principal y durante una
partida. La primera tanda de ventanas enviada a Codex no contenía `DebugConsole.Awake`
ni `GetInstance`. **Esas ventanas fueron recuperadas y desensambladas del PRX
original después del commit 37a059c**. La sección de actualización de abajo
explica las condiciones verificadas y lo que sigue siendo incierto. No hay una ruta comprobada para activar una instancia
legítima, ni un proveedor de callback al que conectar el UCM sin interceptar
código del juego.

Por ese motivo, el render IMGUI y la integración Rewired quedan sin conexión a
PS4. El menú, el draw list, el mapper de botones y `src/unity_host_adapter.*`
se conservan como componentes host; no se añadió un hook, una llamada Unity,
lectura de mando o una escritura de estado del juego.

## Evidencia y fuerza

| Dato | Estado | Qué demuestra |
| --- | --- | --- |
| `DebugConsole.OnGUI`, RVA `0x005C37B0` | Primeros 16 bytes confirmados en PS4Debug; prefijo también comparado offline | Entrada de una función de instancia candidata. No prueba que el componente esté activo ni que Unity llame al método. |
| `DebugConsole.ToggleConsole`, RVA `0x005CB6D0` | Primeros 16 bytes confirmados en PS4Debug | Lee `[this+0x5A]` y transfiere a `ShowConsole`; requiere un `this` válido. |
| `DebugConsole.ShowConsole`, RVA `0x005CA800` | Nombre resuelto con metadata y destino directo en PRX | Cambia el byte `[this+0x5A]` y actualiza otros subsistemas de la consola. No se ha probado que cree un objeto. |
| `DebugConsole.Awake`, RVA `0x005C1C30` | RVA e instrucción de registro cerca de `0x005C1EA2` proceden del análisis privado anterior; no está su ventana de instrucciones en los archivos recibidos | Hay una ubicación candidata de registro, pero la instrucción, el campo estático y sus condiciones no se pueden volver a verificar con el material acotado disponible. |
| `DebugConsole.GetInstance`, RVA `0x005CB690` | Candidato offline; cuerpo no incluido | El nombre/RVA no confirma que devuelva el campo observado, su firma ni quién lo consulta. |
| Referencia de instancia estática | Lectura PS4Debug anterior encontró el puntero NULL en menú y partida | Estado de esa sesión; no identifica por qué está NULL ni permite reutilizar una dirección RAM antigua. |
| `Object.op_Implicit` y `Object.Destroy` en `Awake` | Reportados por el análisis offline anterior, sin instrucciones ni CFG en el desensamblado recibido | Existe una ruta candidata de comprobación/destrucción; no se sabe qué condición la toma ni si destruye un duplicado, el objeto actual u otro. |

El desensamblado original `Desensamblado_Metodos.txt` tiene doce ventanas,
incluida una de `OnGUI` de `0x180` bytes y una de `ShowConsole` de `0x140`
bytes. No contiene las ventanas de `Awake` o `GetInstance`; por eso la ausencia
de sus referencias en ese archivo no significa que no existan. Los binarios,
metadata y desensamblados completos originales no se guardan en Git.

## ABI observado, no prototipos completos

| Método | Flujo de registros observado | Lo que sigue sin verificar |
| --- | --- | --- |
| `DebugConsole.OnGUI` | Conserva `RDI` en un registro no volátil y luego lo usa como `this`; llega a `GUIUtility.CheckOnGUI` | Prototipo administrado/nativo completo, posibles parámetros ocultos y si Unity entrega una instancia viva. |
| `DebugConsole.ToggleConsole` | Compara `[RDI+0x5A]`, produce un booleano en `ESI` y salta a `ShowConsole` | Firma de metadata completa y convenciones de llamada fuera de esa ruta. |
| `DebugConsole.ShowConsole` | Conserva `RDI` como `this`, guarda `ESI` y escribe el estado en `[this+0x5A]` | Firma completa, estado de inicialización y validez de cualquier `this` futuro. |
| `DebugConsole.Awake` / `GetInstance` | Las instrucciones de esos cuerpos no están en la ventana privada recibida | Convención de llamada, tipo de retorno, campos, parámetros ocultos y flujo de vida. |
| `Rewired.ReInput.get_players` | En la llamada desde `ProcessGamePads`, `RDI` y `ESI` se limpian antes del `call`; el resultado en `RAX` se prueba | Prototipo administrado/nativo, semántica del retorno, parámetros ocultos y qué jugador se obtiene. |
| Despacho en `ProcessGamePads` | Se observan `call qword ptr [RCX]` en `0x004762D6` y `0x00476315` | Tipo receptor, target/vtable, firma, parámetros y si el target lee botones o ejes. |

Estos son indicios del flujo AMD64, no declaraciones de prototipos ABI.

## Mapa de métodos y referencias

Las aristas de abajo son llamadas directas visibles o referencias descritas en
la resolución offline. Una llamada compilada no es una confirmación de que el
método se ejecutó en una sesión concreta.

| Origen | Sitio | Destino | Hallazgo |
| --- | ---: | --- | --- |
| `DebugConsole.OnGUI` `0x005C37B0` | `0x005C383C` | `DebugConsole.HandleInput` `0x005C8E00` | Lógica de entrada se ejecuta desde el cuerpo IMGUI. |
| `DebugConsole.OnGUI` | `0x005C3828`, `0x005C38B1` | `UnityEngine.GUI.get_color` `0x019BD860`; `GUIUtility.CheckOnGUI` `0x019BC470` | Confirma uso del contexto IMGUI en este cuerpo. La ventana también contiene operaciones Unity UI; la tabla de resolución offline identifica `GUILayout`, `GUI` y `GUI.TextField` en la implementación completa. |
| `DebugConsole.ToggleConsole` `0x005CB6D0` | `0x005CB6DA` | `DebugConsole.ShowConsole` `0x005CA800` | Tail jump confirmado por PS4Debug y el PRX. El cuerpo espera `this` en `RDI` y el booleano en `ESI`; esto no es una firma IL2CPP completa. |
| `DebugConsole.ShowConsole` | `0x005CA843` | `ChatBox.SetEnabled` `0x01FB2160` | Cambia el estado de UI relacionado con la consola. |
| `DebugConsole.ShowConsole` | `0x005CA87F` | `UnityEngine.Object.op_Implicit` `0x02166EB0` | Comprueba un objeto Unity en el flujo de visibilidad. No identifica por sí sola el campo comprobado. |
| `DebugConsole.ShowConsole` | `0x005CA911` | `TheForest.Utils.Input.SetState` `0x01DADDD0` | Actualiza el estado de input del juego al cambiar la consola. |
| `DebugConsole.ShowConsole` | `0x005CA96A` | `DebugConsole.CheckDisplayState` `0x005C2FE0` | Tail target registrado en la resolución del PRX; queda fuera de la ventana `ShowConsole` adjunta. |
| `DebugConsole.HandleInput` | `0x005C9202`, `0x005C9274` | `DebugConsole.ShowConsole` | El manejador existente puede volver a abrir/cerrar la consola; no aporta un punto de extensión nuevo. |
| `DebugConsole.HandleInput` | `0x005C92A7` | `PS4Controller.SetMouseEnabled` `0x00477330` | Ajusta el modo de cursor/input. |
| `DebugConsole.Awake` | cerca de `0x005C1EA2` | campo de instancia singleton, destino no resuelto | La ubicación de registro es evidencia previa; falta recuperar su instrucción y referencias entrantes/salientes completas. |
| `DebugConsole.GetInstance` `0x005CB690` | no disponible | — | Sin ventana ni xrefs entrantes en la evidencia acotada; no se afirma que nadie lo llame. |

La resolución de la ventana completa de `OnGUI` registra también estos
call-sites directos (la tabla disponible no conserva las RVA de destino para
estos cinco helpers): `0x005C3B11 → GUILayout.BeginHorizontal`,
`0x005C3BFE → GUILayout.DoLabel`, `0x005C3C17 → GUI.set_color`,
`0x005C3D32 → GUILayout.Label` y `0x005C3E61 → GUI.TextField`. Son evidencia
de llamadas dentro del cuerpo compilado, no evidencia de que el callback esté
activo ahora.

### Lo que `Awake` permite concluir hoy

El análisis anterior reportó que el cuerpo de `Awake` contiene llamadas a
`UnityEngine.Object.op_Implicit` y `UnityEngine.Object.Destroy`, y ubicó una
instrucción que interpretó como registro de la instancia alrededor de
`0x005C1EA2`. Sin el cuerpo exacto no es posible conectar esas llamadas a un
campo o rama determinados. Por tanto, **no se conoce**:

- si `Awake` asigna siempre el singleton o solo después de validar otra
  instancia;
- qué condición entra en `Destroy`, cuál objeto se pasa y si se usa la variante
  diferida de Unity;
- si se destruye un duplicado, se desactiva el objeto, falta un componente o
  una escena reemplaza la instancia;
- quién construye el objeto, qué escenas incluyen el componente y si se ejecuta
  `OnGUI` durante una partida actual.

La inspección estática previa de bundles informó objetos de escena con nombre
`DebugConsole`, pero un objeto serializado en un bundle no prueba que se cargue,
esté habilitado, complete `Awake` ni reciba eventos IMGUI. La lectura de
singleton NULL durante juego y menú impide tratar el getter o los métodos de
instancia como un camino de activación. No se invoca ningún método con `this`
nulo o supuesto.

## Ruta de entrada DualShock 4 observada

| Origen | Sitio | Destino o tipo de llamada | Interpretación |
| --- | ---: | --- | --- |
| `PS4Controller.Update` `0x00476080` | `0x00476179` | `ProcessGamePads` `0x004761A0` (`call`) | El ciclo Unity de input llega al procesamiento de pads. |
| `PS4Controller.Update` | `0x0047618B` | `ProcessGamePads` `0x004761A0` (`jmp`) | Rama de salida que termina en el mismo método. |
| `PS4Controller.Update` | `0x0047617E` | `UpdateConnectionMap` `0x00476DD0` | Actualiza el mapa de conexión; no es un callback de render. |
| `ProcessGamePads` | `0x00476207` | `Rewired.ReInput.get_players` `0x00934F40` | Relación directa resuelta contra metadata; el código consulta la abstracción de jugadores de Rewired. |
| `ProcessGamePads` | `0x004762D6`, `0x00476315` | `call qword ptr [rcx]` | Despacho indirecto. La ventana no resuelve el tipo concreto, método, firma, parámetros ni origen final del estado físico. |

`ProcessGamePads` obtiene `players` de Rewired y luego utiliza llamadas
indirectas. Sin el método destino/vtable completo no es correcto afirmar que
esas llamadas correspondan a `Player.GetButton`, a una API ScePad particular o
a una suscripción observable por un PRX. No se encontró un evento público de
Rewired ni una interfaz de lectura compartida para plugins.

La alternativa de menor intrusión a explorar es resolver offline los destinos
de interfaz/vtable y determinar si el juego expone un snapshot de jugador que
pueda leerse mediante una API documentada. Aún requeriría un contexto seguro y
una forma de obtener el jugador; llamar RVA nativos desde el PRX no constituye
por sí solo una API segura. Abrir un handle ScePad propio evitaría el detour
global, pero la coexistencia, ownership y posible consumo duplicado no están
validados. No se intercepta `scePadRead*`, `PS4Controller.Update` ni otra API
compartida.

## Integración concreta con el menú UCM

1. Mantener el menú y su draw list como estado/renderizador independiente. El
   adaptador host existente consume una entrada normalizada; no se cambia ese
   contrato.
2. El único candidato de Unity GUI con evidencia directa es agregar el draw
   list al contexto de un `OnGUI` real, donde Unity garantiza IMGUI. En esta
   build, eso implicaría reutilizar una instancia activa de `DebugConsole` o
   hallar un callback propio ya registrado por el juego.
3. No se ha comprobado una API de registro para un segundo callback, un
   cargador de extensiones IL2CPP utilizable, ni un objeto UCM ya existente.
   Interceptar `DebugConsole.OnGUI` seguiría siendo un hook a código del juego
   y no está habilitado bajo el safety hold.
4. No llamar `OnGUI`, `GetInstance`, `ToggleConsole` ni `ShowConsole` desde el
   PRX: faltan ABI completa, `MethodInfo`/contexto IL2CPP y una instancia válida.
   Fuera de un evento IMGUI, `GUIUtility.CheckOnGUI` también puede rechazar las
   llamadas de GUI.
5. Para el mando, preservar la frontera `snapshot → mapper → menú`. Solo se
   conectará a Rewired si un proveedor verificable ofrece el snapshot sin
   alterar el input del personaje; hasta entonces el proveedor PS4 está
   deshabilitado.

### Validaciones pendientes antes de diseñar un adaptador de juego

- Cuerpo completo de `DebugConsole.Awake` y `GetInstance`, límites de función,
  ramas, llamada exacta a `Destroy`, argumento y referencia estática asignada.
- Xrefs globales a esa referencia estática y a `OnGUI`, más la creación del
  objeto/componente y los callbacks de destrucción/desactivación.
- Firma administrada y ABI nativa completa (incluidos los parámetros ocultos
  que realmente use esta build, como un posible `MethodInfo*`),
  estado de inicialización IL2CPP y contexto/hilo del callback.
- Destinos de las llamadas indirectas de `ProcessGamePads`, resueltos con el
  tipo receptor/vtable de la metadata de esta misma build, y métodos Rewired
  reales que leen botones/ejes.
- Fuente no invasiva de callback Unity, snapshot DualShock y ciclo de vida que
  mantenga residentes los datos; no existe hoy una de esas tres piezas.

## Herramienta offline y pruebas

[`scripts/resolve_il2cpp_references.py`](../scripts/resolve_il2cpp_references.py)
combina los RVA registrados y los símbolos resueltos, y procesa ventanas
locales. Informa llamadas y saltos directos, llamadas indirectas sin resolver,
destinos de ramas condicionales y direcciones RIP relativas con una etiqueta
heurística de lectura/escritura. No identifica por sí sola el nombre de un
campo estático ni determina la condición de `Destroy`.

```sh
python3 scripts/resolve_il2cpp_references.py \
  /ruta/privada/Desensamblado_Metodos.txt \
  --output /ruta/privada/referencias.md
```

Con un `llvm-objdump` completo local, `--full-image` busca call/jump directos
entrantes a los métodos con RVA conocido. Deja el nombre del caller sin
resolver si no se proporcionó una tabla fiable de límites de función:

```sh
python3 scripts/resolve_il2cpp_references.py \
  /ruta/privada/Il2CppUserAssemblies.disasm.txt \
  --full-image \
  --output /ruta/privada/xrefs-entrantes.md
```

Para agregar símbolos obtenidos de metadata privada, se puede pasar un archivo
local con una entrada por línea, `0xRVA Nombre.Total.Del.Metodo`:

```sh
python3 scripts/resolve_il2cpp_references.py \
  /ruta/privada/Desensamblado_Metodos.txt \
  --symbols /ruta/privada/metodos.tsv \
  --output /ruta/privada/referencias.md
```

El analizador lee la entrada y escribe solo el informe solicitado. No sube ni
copia el ELF, `global-metadata.dat` o el desensamblado al repositorio. Sus
pruebas sintéticas validan resolución de símbolos, xrefs, ramas, operandos
RIP-relativos y clasificación conservadora de llamadas indirectas; no prueban
Unity ni ejecución en PS4.


## ACTUALIZACIÓN: Awake/GetInstance reanalizados directamente desde el PRX original (2026-10-29)

La nota previa sobre la falta de ventanas de `Awake`/`GetInstance` describía **solo los adjuntos disponibles en Codex Cloud**. La conversación original recuperó de su archivo privado `Il2CppUserAssemblies.prx` (SHA-256 `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`) y `global-metadata.dat` (v23, SHA-256 `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`) los cuerpos nativos faltantes. Se verificó que los RVA corresponden a `TheForest.DebugConsole.Awake` y `GetInstance` mediante la tabla de punteros IL2CPP y el mapa de métodos. El desensamblado se hizo **offline** con `llvm-objdump`; el binario y los metadatos no se agregan a GitHub.

### Instrucciones directas y su interpretación

| Instrucción RVA | Operación desensamblada | Evidencia |
| --- | --- | --- |
| `0x005C1C92` | Lee el byte de un campo estático en `class + 0xA0 + 0x01`; `je 0x005C1D2B` si es cero | Es la primera condición de exclusión. Por el código de referencia PC de esa misma clase, corresponde plausiblemente a `CoopPeerStarter.DedicatedHost`. **El nombre de la clase referida aún debe confirmarse independientemente en la tabla de tipos PS4**. |
| `0x005C1D47` | Lee un puntero de `DebugConsole` en `static_fields + 0x10` | Se compara la instancia ya registrada con el nuevo objeto; `UnityEngine.Object.op_Implicit` y `CompareBaseObjects` determinan si hay una instancia distinta. |
| `0x005C1E13` | Compara `byte ptr [Cheats.static_fields + 0x10], 0`; si es cero salta a una ruta que termina en `UnityEngine.Object.Destroy` | La clase `Cheats` está corroborada porque el setter nativo `CheatsBridge.SetGodMode` usa la misma referencia a clase (RIP `0x33EC070`) y escribe su byte estático `+0x0B`; el orden de los campos del metadata incluye `Cheats.DebugConsole` en `+0x10`. Corresponde al guard `!Cheats.DebugConsole` visto en la referencia PC. |
| `0x005C1E94`–`0x005C1EA2` | Obtiene `DebugConsole.static_fields` y escribe `this` (`R14`) en `+0x10` | **Confirmación estática de registro de la instancia**: `mov qword ptr [rax+0x10],r14` en `0x005C1EA2`. |
| `0x005CB6B0`–`0x005CB6C2` | `GetInstance` carga la clase, luego `static_fields` (`+0xA0`) y finalmente `+0x10`; retorna | **Confirma el getter del mismo campo estático**. No crea el objeto ni habilita el componente. |
| `0x005C1D26` | Tail-`jmp` a `0x02176930` (`UnityEngine.Object.Destroy`) tras preparar `this` | Ruta de destrucción de `Awake`, observable en varias condiciones de exclusión. |

**Interpretación de control de flujo:** el cuerpo PS4 concuerda con la lógica de `Awake` publicada para el port PC: rechazar un host dedicado, una instancia competidora o una consola de depuración deshabilitada; si no hay una instancia válida y pasa los guards, registrar `this`. Este paralelismo es **corroboración**, no una asunción de identidad completa entre las dos compilaciones. Las ramas y los campos nativos indicados arriba sí se examinaron directamente en el PRX PS4.

### Qué explica el singleton NULL y qué falta comprobar

La ruta `Cheats.DebugConsole == false` puede destruir el componente antes de asignar `DebugConsole.Instance`. Por tanto, **es una explicación plausible y respaldada por código** del `NULL` leído en menú y partida, pero aún no se midió el valor de ese flag en una sesión PS4. Tampoco se comprobó si el componente llega a recibir `Awake` o si el objeto fue desactivado previamente por escenas. **No afirmar un diagnóstico causal definitivo ni cambiar ese flag a ciegas.**

Aunque `OnGUI` está compilado con llamadas Unity IMGUI, activar el DebugConsole integrado no sería todavía instalar nuestro UCM, y **no ofrece una interfaz probada para registrar otro callback Unity desde GoldHEN**. `GetInstance` solo devuelve el puntero, no instancia el objeto; `ShowConsole` requiere un `this` válido.

### Próxima entrega de Codex, ahora acotada y accionable

1. Incorporar este CFG a la herramienta de resolución offline: deducir *por instrucciones* qué salto desemboca en `Destroy` y cuál alcanza el store de `Instance`, mostrando fuente, destino y guard de manera verificable.
2. Comprobar la identidad de la primera referencia de clase (`0x33EB300`) contra el registro de tipos para distinguir `CoopPeerStarter.DedicatedHost` de cualquier otra opción; verificar formalmente el layout de static fields de `Cheats` y `DebugConsole` con sus metadatos de la versión PS4.
3. Analizar `DebugConsole.OnDestroy` para determinar cuándo se anula o conserva `Instance` y si puede quedar un singleton obsoleto. La relación de escritura en `Awake` por sí sola no explica todas las causas de NULL.
4. Resolver el despacho indirecto Rewired sin suponer targets o APIs ScePad.
5. **Decisión de arquitectura**: documentar si existe realmente una ruta segura y existente para registrar un `OnGUI` externo sin detours ni modificar PKG. Si la respuesta es no, marcar la vía DebugConsole como **no habilitada** y evaluar otras arquitecturas, no producir más PRX de diagnóstico sin menú.
6. Si más adelante se plantea comprobar un guard en hardware, hacerlo solo mediante **lectura** de memoria debidamente validada y con consentimiento explícito; sin ejecutar métodos, escribir flags o instalar hooks.

No se requiere ninguna prueba en la consola en esta etapa. La conclusión central es que **ya no faltan los cuerpos de Awake/GetInstance para la investigación offline**: se recuperaron y se puede dejar de repetir esa solicitud.

## Siguiente experimento mínimo

**Actualización:** las ventanas de `Awake` (`0x005C1C30`) y `GetInstance`
(`0x005CB690`) **ya se recuperaron del PRX privado** y se resolvió el guard
de `Cheats.DebugConsole` como causa plausible de la ausencia de instancia.
El siguiente paso es formalizar el CFG/identidad de tipos de esas rutas,
analizar la destrucción en `OnDestroy` y resolver las llamadas indirectas de
Rewired desde `0x004761A0` con su metadata y vtables. Eso
permitirá contestar si `Awake` registra el singleton, qué condición llega a
`Destroy`, quién consulta `GetInstance` y qué métodos Rewired reciben los
botones. Si el resultado aún no muestra una ruta de registro/no invasiva, no
habrá base para habilitar una integración de render o input.
