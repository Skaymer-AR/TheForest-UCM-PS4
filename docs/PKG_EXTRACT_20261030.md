# Extracción CUSA12398 1.15: evidencia offline — 2026-10-30

El verificador de procedencia se ejecutó sobre copias temporales de los archivos actuales de Drive. Su salida describe los contenedores SELF y no inspecciona sus segmentos. Después, `scripts/unwrap_plain_self.py` reconstruyó los ELF de análisis a partir de los segmentos declarados plaintext. Los insumos originales y las copias derivadas permanecen fuera del repositorio.

## Salida completa de `check_private_pkg_extract.py`

Comando: `python3 scripts/check_private_pkg_extract.py --root <directorio privado con los tres archivos>`  
Código de salida: `0`.

```text
The Forest PS4 CUSA12398 1.15 | private read-only evidence
eboot: eboot.bin
  size=21830618 sha256=fac03b6402a7659f0efd0c133aea2252e4218a6be7f23cf84b6af82099adcd2a
  type=SCE/SELF container (RVA mapping not possible without a decrypted ELF)
IL2CPP PRX: Il2CppUserAssemblies.prx
  size=63934584 sha256=f7e590358efbfb68dc5a61bf51b070b2b85eb223070b82a31e3fd5e5118777b6
  type=SCE/SELF container (RVA mapping not possible without a decrypted ELF)
  historical ELF SHA comparison: NOT COMPARABLE (current input is not a decrypted ELF64)
metadata: global-metadata.dat
  size=15400780 sha256=238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3
  historical metadata SHA: SAME
anchor checks: SKIPPED (input is not a decrypted ELF64)
VERDICT: evidence only; does not validate a live callback, ABI, or hook.
```

El verificador recibe el SELF, por eso omite las anclas RVA. Su comparación de hash ahora falla cerrada y no compara un hash SELF con el hash de un ELF histórico.

## Comparación de los ELF reconstruidos

| Insumo actual | Tamaño SELF | SHA-256 SELF | ELF reconstruido | SHA-256 ELF |
| --- | ---: | --- | ---: | --- |
| `eboot.bin` | 21,830,618 | `fac03b6402a7659f0efd0c133aea2252e4218a6be7f23cf84b6af82099adcd2a` | 21,813,434 | `66b31b4f252b1a70a893685d8b24c8c430c01ada919fa50c34cf66aec8eee185` |
| `Il2CppUserAssemblies.prx` | 63,934,584 | `f7e590358efbfb68dc5a61bf51b070b2b85eb223070b82a31e3fd5e5118777b6` | 63,849,064 | `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969` |

Ambos ELF reconstruidos coinciden byte por byte con los ELF históricos retenidos. Las 42 de 42 anclas de prefijo del módulo coinciden. `global-metadata.dat` mide 15,400,780 bytes, tiene SHA-256 `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3` y coincide con la metadata histórica.

La reconstrucción encontró cinco segmentos de carga plaintext y sin compresión por archivo. Conserva los segmentos de versión al final y normaliza campos descriptivos de una tabla de secciones ausente; la igualdad completa con los ELF retenidos valida la reconstrucción frente a las referencias disponibles. Esto no es verificación criptográfica.

## Resultado de la inspección IL2CPP

El ELF del PRX contiene una inicialización generada que pasa las estructuras de `CodeRegistration` y `MetadataRegistration` al registrador nativo. El inspector valida los conteos y los 85.372 índices de métodos nativos; todos apuntan a rangos ejecutables. El tipo propuesto `TheForest.UCM.UltimateMenuHost` no está registrado. El registrador observado asigna los punteros recibidos a slots globales; no se debe invocar con tablas parciales como si las fusionara.

La inspección estructural de SELF, ELF y tablas IL2CPP no valida la firma digital Sony del SELF ni la firma o integridad criptográfica del PKG. En esa ejecución histórica, el hash íntegro del PKG aún no estaba medido; la reconstrucción y revalidación de la copia actual se registran abajo. Por tanto, no se declara verificación criptográfica de firmas.

La arquitectura y el bloqueo para crear el menú AOT se documentan en [`AOT_INTEGRATION_PROPOSAL.md`](AOT_INTEGRATION_PROPOSAL.md): hace falta el proyecto Unity original o todas las entradas reconstruibles del build IL2CPP, junto al toolchain PS4 compatible y autorizado. No se modificó ni reconstruyó el PKG, no se creó ni instaló un PRX y no hubo prueba en consola.

## Revalidación de Drive y límite de extracción PFS — 2026-10-30

Se volvieron a listar las dos carpetas de Drive indicadas por el propietario. `TheForest_Extraidos` contiene `eboot.bin` y el árbol `Media`; dentro de ese árbol solo aparecen:

| Ruta de Drive | Contenido actual |
| --- | --- |
| `Media/Native/Data/Metadata/` | `global-metadata.dat` |
| `Media/Metadata/` | `global-metadata.dat` |
| `Media/Modules/` | `Il2CppUserAssemblies.prx` |

No aparecen `globalgamemanagers.assets`, `sharedassets0.assets`, `sharedassets1.assets` ni `level0`, `level1` o `level2`. Esos seis archivos se nombran porque son los insumos privados que el análisis histórico de [`REWIRED_SCENE_GRAPH_20261030.md`](REWIRED_SCENE_GRAPH_20261030.md) declara haber inspeccionado; **no se reobtuvieron ni se recalcularon sus hashes en esta ejecución**. La carpeta `TheForest_PKG_Partes` sí contiene las ocho partes listadas abajo.

| Parte | Bytes |
| --- | ---: |
| `parte_01.bin` a `parte_07.bin` | 209,715,200 cada una |
| `parte_08.bin` | 141,164,544 |

La concatenación de las partes en un archivo temporal privado produce 1,609,170,944 bytes, SHA-256 `7214800a8276fdf5fceb91a4e18064114aded1265508d78085b41a1f317dbff3`. El encabezado indica Content ID `EP0238-CUSA12398_00-THEFOREST0000000`, DRM PS4 (`0x0F`), tipo de contenido `0x1A`, un PFS y un `package_size` coincidente. El flag `PKG_FLAGS_FINALIZED` está apagado. El PFS comienza en `0x780000` y ocupa 1,601,306,624 bytes. El hash y la lectura del encabezado confirman la reconstrucción de las partes, **no** la firma ni la integridad criptográfica del contenido.

### Prueba con extractor local

Se compiló en `/tmp`, sin instalar paquetes del juego ni guardar binarios en el repositorio, `flatz/pkg_pfs_tool` en el commit `4e74afa98b0f57b2b50a2182c1ef89905dc040a7`. La compilación local usó sus cabeceras y bibliotecas estáticas Linux incluidas más zlib del sistema; `readelf`/`ldd` muestran como dependencias dinámicas solo `libz.so.1` y `libc.so.6`. El compilador emitió advertencias de truncamiento de cadenas/formato del código de la herramienta.

`--info --dump-sfo --dump-playgo` terminó con código `0` y corroboró `TITLE=The Forest`, `TITLE_ID=CUSA12398`, `APP_VER=01.15` y el Content ID indicado. Esto lee metadatos del contenedor y no demuestra que el PFS esté descifrado.

`--list` y `--unpack-inner-pfs --no-signature-check --no-icv-check --unpack` terminaron con código `1`. En ambos casos la herramienta informó que faltaba el exponente privado del keyset `pkg_entry_key_3`, no pudo cargarlo ni descifrar el bloque de claves de entradas y no obtuvo la clave de imagen para generar las claves de cifrado/firma PFS. Omitir las comprobaciones de firma e ICV no resolvió esa falta. **No se extrajo el PFS ni el árbol `Image0` y no se modificó el PKG.**

### Actualización posterior: assets aportados en ZIP

El propietario aportó después `Archivo.zip`, `Archivo(1).zip`, `Archivo 2.zip`,
`Archivo 2(1).zip` y `Archivo 3.zip`. Una ejecución privada del
`scripts/verify_unity_assets_in_archives.py` verificó con los seis SHA-256
fijados las copias de `globalgamemanagers.assets`, `sharedassets0.assets`,
`sharedassets1.assets`, `level0`, `level1` y `level2`; `sharedassets0/1` también
aparecen en `Archivo 3.zip`. Las coincidencias se extrajeron a `/tmp` para
análisis, sin modificar el PKG ni añadir assets al repositorio.

Esto permitió decodificar parte de los mapas serializados
`ControllerMap_Editor` / `ActionElementMap` para los dos InputManager. El
resultado derivado está en
[`REWIRED_CONTROLLER_MAPS_20261030.md`](REWIRED_CONTROLLER_MAPS_20261030.md).
Sigue sin conocerse el Player activo, el controlador conectado/asignado, qué
gestor o mapa se carga y habilita, el foco de entrada ni la política de
consumo durante una sesión. La extracción PFS de la copia privada continúa
bloqueada por la falta de la clave privada `pkg_entry_key_3`; estos ZIPs no
requirieron esa extracción. No se alteró el PKG, no se instaló ningún PRX y
no se hizo una prueba en consola.
