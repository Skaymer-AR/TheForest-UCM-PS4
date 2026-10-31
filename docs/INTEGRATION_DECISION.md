# Decisión de integración del Ultimate Mod Menu

**Objetivo:** menú gráfico Unity IL2CPP para The Forest PS4, controlado con DualShock 4.  
**Decisión de arquitectura:** host propio `MonoBehaviour` AOT, incorporado al build del título antes de generar IL2CPP.  
**Estado actual:** propuesta viable como ruta de build, pero todavía no se puede compilar ni ejecutar con los insumos disponibles.

## Forma del host

1. Compilar `UltimateMenuHost` junto al código del título para la misma versión de Unity y el mismo backend IL2CPP de PS4.
2. Preservar su clase, métodos y bootstrap del stripping de IL2CPP. El bootstrap, en el hilo de Unity, crea un `GameObject`, agrega el componente AOT y mantiene una única instancia entre escenas.
3. Leer un snapshot de entrada desde el jugador Rewired que ya posee el título. Confirmar los mapas de acciones del DS4 y la política para bloquear o reenviar movimiento antes de definir controles.
4. Dibujar el menú desde el callback IMGUI del componente. Mantener la navegación y el renderizador existentes como núcleo desacoplado; enlazarlos al host con una interfaz simple y comprobable.

Un puente nativo del núcleo existente puede evaluarse como biblioteca estática con una ABI C plana dentro de ese mismo build. Antes hay que probar el enlace PS4 y el paso de datos en un fixture mínimo. No se presupone `DllImport`, carga dinámica de DLL ni un proveedor PRX.

## Evidencia que fija el límite

La imagen de código actual se reconstruyó desde los segmentos plaintext del SELF y coincide completa con la referencia histórica; la metadata y las 42 anclas también coinciden. El registro actual contiene 85.372 destinos de métodos nativos válidos, pero no registra `TheForest.UCM.UltimateMenuHost`. Su inicializador entrega tablas globales al registrador, que guarda esos punteros; llamar al registrador con tablas parciales no agrega tipos y puede reemplazar el registro del juego.

Por ello el host debe entrar por el generador/build IL2CPP del título, con tablas, métodos, layouts y bootstrap consistentes. Los binarios retail y metadata disponibles no bastan para generar ni vincular ese host. No se afirma que exista ya un menú que pueda cargarse en el juego.

## Insumos y cambios necesarios

| Área | Hace falta |
| --- | --- |
| Proyecto | Proyecto Unity original o fuente completa y reconstruible de la integración IL2CPP, incluidos código generado, scripts/entradas de enlace y dependencias usadas por el build. |
| Versiones | Confirmar la versión exacta de Unity desde los assets/Player; `5.6.6f2` aparece en el ELF y es solo candidata. |
| Toolchain | Unity Editor y soporte de build PS4 de esa versión; SDK PS4 autorizado con compilador, linker, headers y bibliotecas compatibles. |
| Registro AOT | Generador IL2CPP que incluya el host y produzca metadata, métodos, tablas, layouts y preservación de stripping coherentes con el título. |
| Entrada | Assets/configuración Rewired del juego para verificar jugador, mapas DS4, conexión, foco y reenvío de controles. |

Cambios del host: nuevo componente C# AOT, bootstrap preservado de escena, adaptador Rewired leído en el hilo principal, renderer IMGUI y binding pequeño con el menú existente. Si el núcleo C se integra estáticamente, añadir solo el puente C ABI probado. Cada punto se implementaría y revisaría como cambio del proyecto de build; el PKG no se toca dentro del trabajo autorizado actual.

## Herramientas y pruebas previas a cualquier despliegue

Herramientas offline ya añadidas: `scripts/unwrap_plain_self.py` para recuperar imágenes ELF de SELF plaintext con validación de límites, y `scripts/inspect_aot_registration.py` para validar registro, índices y rangos ejecutables. Las pruebas sintéticas comprueban rechazo ante secciones cifradas/comprimidas o malformadas, tablas incoherentes e índices inválidos.

Con el proyecto/toolchain disponibles, la primera demostración debe ser un build mínimo reproducible que incluya el host, valide el registro generado, cree el componente desde el bootstrap y demuestre la ABI del renderer con fixtures. Luego, las pruebas de integración del título deben comprobar ciclo de escena, preservación AOT y entrada Rewired sin alterar el mapping. La validación en consola y cualquier modificación/reconstrucción del PKG quedan fuera de la autorización vigente.

## Riesgos abiertos

- La cadena completa Unity PS4 + IL2CPP v23 debe confirmarse con el proyecto y SDK exactos; una versión de editor parecida no garantiza compatibilidad binaria.
- Añadir una clase sin regenerar juntas las tablas y layouts IL2CPP puede causar fallo de carga o corrupción; no es seguro editar el registro retail a mano.
- El nombre de acción Rewired no identifica por sí solo un botón DS4. El mapa, foco y convivencia con los controles del personaje deben salir de los assets/proyecto.
- La igualdad del ELF derivado valida la comparación de imágenes contra las referencias disponibles, pero no verifica firmas Sony del SELF/PKG ni el comportamiento en ejecución.

Hasta contar con los insumos, el trabajo autorizado y verificable es el analizador, las pruebas offline y esta propuesta. El próximo avance técnico depende del proyecto/build AOT compatible; después se puede presentar un cambio concreto de build para autorización, sin cambiar el objetivo del menú.
