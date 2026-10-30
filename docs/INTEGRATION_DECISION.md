# Decisión de integración del UCM

**Build:** The Forest PS4 CUSA12398 v1.15. **Estado de implementación:** NO-GO
para mostrar el UCM mediante la arquitectura GoldHEN actualmente comprobada.
La notificación del PRX y el núcleo visual host no equivalen a un panel dentro
de Unity. Se conserva la seguridad de no hooks; no se genera ni se solicita
instalar un PRX experimental.

## Alternativas evaluadas

| Alternativa | Decisión | Evidencia y condición para reconsiderar |
| --- | --- | --- |
| Reutilizar `DebugConsole.OnGUI` como registro externo | **NO-GO** | Es un callback IMGUI compilado del componente del juego, no una API de suscripción. `GetInstance` solo devuelve `Instance`; el flujo de `Awake` puede destruir el objeto antes de registrarlo. Falta demostrar que exista una instancia activa o un mecanismo de registro externo. |
| Llamar `GUI`/`GUILayout` desde el hilo del PRX | **NO-GO** | Las llamadas observadas en `OnGUI` no autorizan ejecutarlas desde otro hilo o fuera del evento IMGUI de Unity. No se ha demostrado contexto GUI, hilo ni duración de vida válidos para el PRX. |
| `UnityRenderingEvent` / `IssuePluginEvent` para render nativo | **NO-GO en este build; condicional para render nativo** | Requiere que un caller del título cargue un plug-in Unity compatible e invoque el evento en el hilo gráfico. No se ha encontrado ese caller. Esta ruta no suministra por sí misma `OnGUI` ni resuelve la entrada. |
| Callback AOT/component del título mediante un mod loader PS4/IL2CPP | **ÚNICA ruta candidata; hoy NO-GO** | Un componente ya compilado para IL2CPP podría recibir callbacks Unity propios (`OnGUI`/`Update`) y usar servicios Unity/Rewired desde su contexto. `DllModLoader.Awake` y `AppDomain.Load` no prueban que exista un loader ejecutable AOT en PS4. Para pasar a GO debe verificarse la carga de código AOT, cómo se agrega/activa el componente, firma ABI, hilo, contexto IMGUI y retiro seguro. |
| Detour localizado de un método del título (`OnGUI`/`Update`) | **NO-GO bajo el safety hold** | Aunque sería más acotado que interceptar GNM/VideoOut/ScePad, sigue requiriendo parcheo, relocación RIP, publicación atómica del original y quiescencia de todos los hilos. El SDK GoldHEN usado no acredita esas garantías; `DebugConsole.OnGUI` además podría no ejecutarse por ausencia de instancia. |
| Leer Rewired desde un callback propio del título | **Condicional; no implementado** | Evitaría interceptar ScePad y leería un snapshot dentro del ciclo del juego. Los callsites `0x004762D6`/`0x00476315` son vtable indirectos, pero faltan interfaz TypeDef exacta, slot de método y target concreto. Hace falta cerrar esa resolución y validar API/estado Rewired del jugador. |
| Abrir un handle ScePad propio para el DS4 | **NO-GO sin prueba de coexistencia** | No se encontró contrato PS4 de esta configuración que pruebe que un segundo handle sea no exclusivo, no consuma eventos y coexista con Rewired/handle del juego. Tampoco se debe asumir equivalencia con una lectura global. |

## Render e input son dos fronteras distintas

El render necesita un callback llamado por Unity en un contexto que acepte
IMGUI. Un PRX externo puede conservar el draw list del menú, pero todavía
necesita un puente que lo invoque desde un callback del título. La presencia
del código `DebugConsole.OnGUI` y de funciones GUI no proporciona ese puente.

La entrada necesita un snapshot de botones con ownership claro. La mejor
frontera conceptual es el mismo callback AOT del título leyendo Rewired sin
consumir sus eventos; la navegación quedaría desacoplada del input físico. Para
evitar que el mando también controle al personaje mientras el menú esté abierto
se necesita validar además un mecanismo de foco/consumo del juego. No se
interceptará ScePad globalmente ni se supondrá que abrir otro handle sea
transparente.

## Próximo componente necesario

El siguiente componente para que el UCM **pueda llegar a pantalla** es un
**host de callback Unity title-scoped**, no otro backend de framebuffer: un
componente AOT cargable por un mecanismo PS4 ya presente, con callback IMGUI
real y contrato de alta/baja probado. Su primera versión solo debe dibujar el
panel estático del menú existente y leer una entrada de prueba por Rewired;
no debe ejecutar cheats. Antes de conectarlo al PRX hay que demostrar en los
artefactos PS4 originales:

1. Un mod loader o cargador de plug-in compatible con IL2CPP AOT en esta build,
   incluyendo la ruta real de carga; `AppDomain.Load` no basta.
2. El método/callback propio que Unity invoca, su ABI, objeto dueño, thread,
   contexto IMGUI y momento de teardown.
3. La cadena de inicialización/registro que asocia los slots `0x033EB300` y
   `0x033EF3E8` con TypeDefs del metadata v23, y el target real de las dos
   llamadas virtuales Rewired.
4. Una fuente de input no consumidora y el comportamiento de foco al abrir el
   panel.
5. Un ciclo de vida que primero retire el callback y pruebe quiescencia antes
   de liberar recursos; sin spin/wait en render o input.

Si no existe loader AOT compatible ya disponible y no se permite modificar el
PKG, todavía no se ha demostrado una forma de añadir ese callback a esta build.
En ese caso se debe decidir entre encontrar un host title-scoped ya incluido en
el juego o cambiar el requisito de no modificar el paquete; llamar funciones
Unity desde el PRX fuera de su contexto no cierra la brecha.

## Capacidades actuales

| Área | Estado comprobado |
| --- | --- |
| Carga del PRX sin hooks | El usuario confirmó previamente que un probe no-hook permite iniciar y jugar. |
| Menú visual/navegación host | Existe y se conserva en `src/menu.*`, `src/overlay.*` y `src/drawlist.*`; no está conectado a Unity. |
| `DebugConsole.OnGUI` | El desensamblado selectivo muestra llamadas GUI; no prueba un callback externo. |
| Singleton `DebugConsole.Instance` | `Awake` lo escribe tras guardas; `GetInstance` lo lee. No prueba un valor activo en partida ni el comportamiento de `OnDestroy`. |
| Rewired | `PS4Controller.Update` conduce a `ProcessGamePads`; se observan dos dispatches virtuales, aún sin interfaz/método final. |
| Cheats | No hay funciones del UCM conectadas o marcadas como disponibles por este trabajo. |
| Hardware/Unity overlay | No validado en este trabajo. No se solicitó una prueba de PS4. |
