# Propuesta de integración AOT — CUSA12398 1.15

Estado: **investigación y código offline autorizados; despliegue bloqueado**.
Objetivo: nuestro Ultimate Mod Menu gráfico, con DualShock 4. No se ha
modificado/reconstruido el PKG, instalado un módulo ni realizado un hook.

## 1. El ELF de la extracción actual ya se obtuvo offline

La revisión inicial de `check_private_pkg_extract.py` solo identificaba el
encabezado SELF. La inspección posterior de sus entradas demuestra que los
cinco payloads de cada archivo están sin cifrado y sin compresión. No hizo
falta una clave ni otra extracción desde la consola.

`scripts/unwrap_plain_self.py` recupera los rangos del ELF, comprueba que todos
los program headers con bytes tienen respaldo, reconoce el trailer de versión
y rechaza layouts cifrados, comprimidos, ambiguos o fuera de límites. El SELF
conserva `e_shentsize`/`e_shstrndx` de una tabla ausente (`e_shoff=e_shnum=0`);
la copia de análisis normaliza esos campos y lo declara en su salida. Los
huecos entre rangos se rellenan con cero. La comparación **del archivo completo**
con el ELF anterior comprueba también esos huecos y la normalización.

| Copia de análisis de la extracción actual | Bytes | SHA-256 | Comparación completa con el ELF anterior |
| --- | ---: | --- | --- |
| IL2CPP | 63849064 | `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969` | Idéntica |
| eboot | 21813434 | `66b31b4f252b1a70a893685d8b24c8c430c01ada919fa50c34cf66aec8eee185` | Idéntica |

Las 42 ventanas de 16 bytes del CSV anterior coinciden con el ELF actual
reconstruido. El metadata conserva SHA-256
`238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`.
La diferencia entre hashes SELF y ELF no representa una diferencia de código
en estos archivos. Esto no autentica criptográficamente el PKG/SELF ni prueba
qué módulos están cargados en una sesión de consola.

La versión **Unity Player `5.6.6f2`** ya está confirmada también en las cabeceras de
`Media/globalgamemanagers`, escenas `levelN` y archivos `sharedassets` extraídos
privadamente del mismo PKG; el BuildSettings serializado contiene **30 escenas**,
con `level2 = Assets/Scenes/ForestMain_v08.unity`. Véase
[`UNITY_PLAYER_ASSETS_20261030.md`](UNITY_PLAYER_ASSETS_20261030.md).
Esto **no** verifica que estén disponibles el Editor con soporte PS4, el SDK ni
el proyecto/build IL2CPP exactos del título.

## 2. Registro nativo localizado y comprobado

`scripts/inspect_aot_registration.py` procesa el ELF y metadata reales. Reconoce
un inicializador x64 acotado que prepara tres argumentos y salta al registrador.
Comprueba sus tablas usando el layout v23, incluidos los índices nativos de
tipos, los rangos SCE_RELRO y los punteros de métodos ejecutables.

Todas las direcciones siguientes son **VA de enlace del ELF**, con base cero
en este módulo; no son direcciones ASLR para usar en PS4.

| Elemento | Resultado estático |
| --- | --- |
| Inicializador generado | `0x0260F380` |
| Destino del registro | `0x00043A20` |
| CodeRegistration | `0x032C4C28` |
| MetadataRegistration | `0x032C4C98` |
| CodeGenerationOptions | `0x029413C4` |
| Tabla de punteros de métodos | VA `0x0316F8C0`, offset de archivo `0x031738C0` |
| Métodos nativos referenciados | **85372/85372** con puntero dentro de código ejecutable |
| Il2CppType registrados | **64163** |
| TypeDefinitions de metadata | **12963** |
| Entradas fieldOffsets / typeDefinitionSizes | **12963 / 12963**, coherentes con TypeDefinitions |
| Tipo propuesto `TheForest.UCM.UltimateMenuHost` | Ausente |

El desensamblado acotado del destino del registro muestra que guarda los
tres punteros recibidos en slots globales (`0x033DCEB8`, `0x033DCEC0`,
`0x033DCEC8`). Por ello **no se propone llamar otra vez al registrador con
tablas que contengan únicamente el menú**: reemplazaría las tablas globales
observadas. La existencia de la rutina no demuestra una API para añadir
componentes a un runtime ya iniciado.

El parser compartido tenía dos defectos que impedían procesar estos datos
reales: los rangos vacíos `start=-1,count=0` se rechazaban, y
`TypeDefinition.declaringTypeIndex` se trataba como índice de TypeDefinition.
Ese campo indexa la tabla nativa Il2CppType, cuyo tamaño es distinto. Ambos
casos están corregidos y probados; el nuevo inspector comprueba el límite
correcto contra `MetadataRegistration.typesCount`.

## 3. Arquitectura propuesta: componente propiedad del build

La vía sustentada por el pipeline de Unity es incorporar un `MonoBehaviour`
propio **antes** de la generación IL2CPP, de manera que el compilador produzca
un conjunto coherente de código, metadata, invokers, tamaños, offsets y datos
de inicialización. Es una arquitectura válida de Unity, pero **no hay todavía
un pipeline reproducible del título disponible con los archivos actuales**.

El host propuesto es `TheForest.UCM.UltimateMenuHost`:

1. Un método estático `Bootstrap`, incluido en el build y preservado frente a
   stripping, usa `RuntimeInitializeOnLoadMethod` después de cargar la escena.
   Su orden respecto de otros inicializadores no debe suponerse; espera a que
   los servicios del título estén listos sin bloquear el hilo principal.
2. El bootstrap crea un `GameObject` propio, añade `UltimateMenuHost` con
   `AddComponent` y conserva una sola instancia mediante `DontDestroyOnLoad`.
   El objeto existe entonces en una escena Unity. Un reinicio del dominio o
   regreso al título debe comprobarse antes de volver a crearlo.
3. `Update` toma un snapshot lógico del mando en el hilo Unity; el host mantiene
   el estado del menú. El callback GUI del **componente nuevo** dibuja la lista
   de comandos con las APIs GUI del motor y atiende sus eventos válidos.
4. El núcleo C existente puede incorporarse al build mediante una interfaz C
   de datos simples, estáticamente enlazada. Hay que demostrar primero ese
   enlace en un proyecto mínimo compatible; no se ha supuesto un nombre de
   `DllImport`, una convención de marshalling ni un plugin PS4 ya disponible.
5. `OnDisable`/`OnDestroy` desactiva la sesión y libera sus recursos bajo el
   ciclo del Player. Esta arquitectura no necesita descargar dinámicamente un
   PRX mientras Unity podría estar ejecutando sus callbacks.

La comprobación opcional `--require-host` exige que constructor, bootstrap y
callbacks propuestos estén en metadata y tengan cuerpos nativos ejecutables.
La presencia nativa es un requisito de build; **no** demuestra la ejecución
del bootstrap, la herencia MonoBehaviour, la creación de la instancia ni su
destrucción. Esas pruebas son una fase posterior en Unity.

## 4. Modificaciones concretas y prerrequisitos

| Pieza necesaria | Cambio futuro que habría que producir | Estado actual |
| --- | --- | --- |
| Fuente del host y preservación | Nuevo tipo C#, bootstrap y `link.xml`/preservación del tipo y callbacks | Diseño; no se añadió un proveedor ficticio al runtime |
| Código AOT del título | Compilar el host y regenerar CodeRegistration, métodos/invokers y dependencias que correspondan | Falta proyecto original o salida IL2CPP completa y recompilable |
| `global-metadata.dat` y registro nativo | Regenerar tipos, métodos, índices, tamaños, offsets, usos de metadata y atributos como un conjunto | Layout actual identificado; no se modificó ningún archivo propietario |
| Bootstrap del Player/escena | Incluir la información de inicialización que genere esa versión de Unity y verificar el objeto propio | Falta inspección del arranque/assets del título y proyecto mínimo |
| Puente del núcleo C | Compilar núcleo y puente en el enlace AOT, validar layout/ABI y límites de buffers | Enlace PS4 pendiente de demostrar; núcleo y adaptador actuales conservados |
| Entrada DS4 | Proveedor gestionado que lea el jugador y bindings Rewired reales del título | Métodos presentes; falta mapa de acciones/dispositivo y control de foco |
| PKG | Integrar salidas coherentes en una copia de prueba únicamente tras autorización posterior | No autorizado; no se produjo paquete |

Herramientas/insumos concretos:

- Python 3 y los dos analizadores de este PR: recuperación de SELF plaintext y
  validación del registro. LLVM/objdump permite revisar ventanas nativas.
- Il2CppDumper para contrastar estructuras v23 y exportar referencias. Sus
  assemblies dummy no contienen las implementaciones originales y no sustituyen
  el proyecto/fuentes del juego.
- Editor Unity compatible con el Player identificado, soporte PS4 y compilador,
  librerías y SDK de plataforma correspondientes, con acceso autorizado. Una
  toolchain homebrew o un generador FSELF no reemplaza el pipeline de Unity/PS4.
- Proyecto del título o C++ IL2CPP generado completo, scripts de enlace y
  dependencias reproducibles. Los tres binarios extraídos no proporcionan esto.
- Assets de arranque/escena y configuración Rewired para verificar creación,
  bindings y persistencia. Una reconstrucción automática de assets no prueba
  que el título completo pueda recompilarse sin perder código.

Se revisó también la inyección de clases de Il2CppInterop. Su
`InjectorHelpers.Setup` instala hooks de búsqueda de clases/tipos y otros
servicios; `ClassInjector` usa generación IL mediante Reflection.Emit. Es una
implementación real de inyección en su entorno, pero no satisface esta etapa
sin hooks ni aporta por sí misma un loader AOT PS4 compatible con v23. No se
portó ni instaló.

Una ampliación estática de tablas directamente sobre los binarios comerciales
sería otra investigación: necesitaría reubicar todas las referencias afectadas,
construir tipos/vtables/invokers/layouts válidos y enganchar la inicialización
del componente de forma coherente. No se ha demostrado ese generador/linker;
no se presenta como arquitectura lista para implementar.

## 5. DualShock 4 y núcleo gráfico

La metadata real contiene `Rewired.Player.GetButton`, `GetButtonDown`, `GetAxis`
y `Rewired.ReInput.get_players`, además de `GameObject.AddComponent` y
`Object.DontDestroyOnLoad`. Eso permite especificar un proveedor compilado
contra las referencias correctas, sin adivinar slots de interfaz nativos.
La documentación de Rewired define las lecturas del Player sobre **acciones**;
la correspondencia de una acción con L1, R1, cruceta, cruz o círculo necesita
el mapa real del juego. No se asignan IDs por suposición.

La propuesta conserva la navegación y dibujo de `src/`. Primero debe probarse
la lectura sin consumir ni cambiar asignaciones del mando. Después se necesita
un mecanismo explícito del título para que personaje y menú no respondan a
la misma pulsación mientras el panel tiene foco. Abrir otro handle ScePad no
forma parte de esta propuesta. El núcleo/adaptador host existente sigue sin
proveedor PS4 hasta demostrar el puente.

## 6. Pruebas y decisiones antes de autorizar otra fase

| Fase | Prueba necesaria | Criterio para continuar |
| --- | --- | --- |
| Offline realizada | Unwrap con límites, comparación completa de ambos ELF y 42 prefijos; coherencia de índices/tablas | PASS en los archivos privados actuales |
| Offline realizada | Fixtures corruptos/cifrados/comprimidos, no sobreescritura, tablas vacías e índices de distintos dominios | Rechazo sin producir un ELF parcial ante formato no soportado |
| Build mínimo aún pendiente | Unity/IL2CPP compatible genera el host, cuerpos nativos, metadata y bootstrap; gate `--require-host` | Fuente/toolchain disponibles y resultado reproducible; sin PKG del juego |
| Prueba Unity aún pendiente | Crear una instancia, dibujar panel, cambiar escena, desactivar/destruir, desconectar mando | Callback propio real, sin duplicación ni pérdidas de recursos; foco/input comprobados |
| Integración del título aún pendiente | Diff de archivos generados, ABI del puente y regresión de referencias originales | Cambios acotados, todos los métodos originales preservados/remapeados y plan de rollback |
| PKG/consola | Solo después de presentar el diff, riesgos y resultados anteriores | Autorización nueva y explícita; no habilitada por este PR |

Riesgos principales: elegir un Player/SDK incompatible; romper índices o layouts
de metadata; stripping del host/bootstrap; instancias duplicadas entre escenas;
marshalling o vida de buffers incorrectos; desincronización de foco/input; y
perder código original al intentar recompilar a partir de assemblies dummy.

**Decisión actual:** el ELF y el registro base están resueltos. El impedimento
para producir un componente nuevo es un pipeline de compilación/registro del
título, no la falta de otro análisis de su consola interna. Aún no corresponde
solicitar autorización para reconstruir el PKG: primero hay que demostrar el
build mínimo y el puente con los insumos indicados.

## Reproducción privada

```sh
python3 scripts/unwrap_plain_self.py --self /privado/actual/Il2CppUserAssemblies.prx \
  --reference-elf /privado/anterior/Il2CppUserAssemblies.prx \
  --output-elf /privado/analisis/Il2CppUserAssemblies.elf
python3 scripts/inspect_aot_registration.py --module /privado/analisis/Il2CppUserAssemblies.elf \
  --metadata /privado/global-metadata.dat --initializer-va 0x0260F380 \
  --method-table-file-offset 0x031738C0
```

El primer comando solo crea un archivo nuevo si todo el layout soportado pasa
sus comprobaciones. El segundo no escribe archivos. `--require-host` devuelve
3 con el build original porque nuestro tipo todavía no existe; el resultado
esperado no se convierte en prueba de creación de un componente.

## Fuentes primarias

- [Unity 5.6: pipeline IL2CPP](https://docs.unity3d.com/560/Documentation/Manual/IL2CPP-HowItWorks.html)
- [Unity 5.6: restricciones AOT](https://docs.unity3d.com/560/Documentation/Manual/ScriptingRestrictions.html)
- [Unity 5.6: inicialización de runtime](https://docs.unity3d.com/560/Documentation/ScriptReference/RuntimeInitializeOnLoadMethodAttribute.html)
- [Unity 5.6: stripping y link.xml](https://docs.unity3d.com/560/Documentation/Manual/IL2CPP-BytecodeStripping.html)
- [Rewired: Player.GetButtonDown(Int32)](https://guavaman.com/projects/rewired/docs/api-reference/html/M_Rewired_Player_GetButtonDown.htm)
- [OpenOrbis: estructuras SELF](https://github.com/OpenOrbis/create-fself/blob/master/pkg/fself/Structures.go), [escritura de entradas](https://github.com/OpenOrbis/create-fself/blob/master/pkg/fself/FSELF.go)
- [Formato de flags SELF](https://github.com/ps5-payload-dev/ftpsrv/blob/master/self.h), [layout de trailer plaintext](https://github.com/awake-devel/pkg-to-anyps5/blob/main/src/selfelf.rs)
- [Il2CppDumper: registro nativo](https://github.com/Perfare/Il2CppDumper/blob/4741d46ba9cd6159c5d853eb9d6fc48b4bfa2b1a/Il2CppDumper/Il2Cpp/Il2CppClass.cs), [resolución de TypeIndex](https://github.com/Perfare/Il2CppDumper/blob/4741d46ba9cd6159c5d853eb9d6fc48b4bfa2b1a/Il2CppDumper/Utils/Il2CppExecutor.cs)
- [Il2CppInterop: instalación de hooks](https://github.com/BepInEx/Il2CppInterop/blob/81a6f78c8b653e0da4a3420ac4cd00819e8b6292/Il2CppInterop.Runtime/Injection/InjectorHelpers.cs), [generación IL de ClassInjector](https://github.com/BepInEx/Il2CppInterop/blob/81a6f78c8b653e0da4a3420ac4cd00819e8b6292/Il2CppInterop.Runtime/Injection/ClassInjector.cs)
