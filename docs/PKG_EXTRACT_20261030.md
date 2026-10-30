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

La inspección estructural de SELF, ELF y tablas IL2CPP no valida la firma digital Sony del SELF ni la firma o integridad criptográfica del PKG. El hash íntegro del PKG tampoco está medido. Por tanto, no se declara verificación criptográfica de firmas.

La arquitectura y el bloqueo para crear el menú AOT se documentan en [`AOT_INTEGRATION_PROPOSAL.md`](AOT_INTEGRATION_PROPOSAL.md): hace falta el proyecto Unity original o todas las entradas reconstruibles del build IL2CPP, junto al toolchain PS4 compatible y autorizado. No se modificó ni reconstruyó el PKG, no se creó ni instaló un PRX y no hubo prueba en consola.
