# Pipeline offline para IL2CPP PS4 v23

Este flujo lee localmente `global-metadata.dat`, el ELF/PRX original y ventanas
acotadas de desensamblado. No ejecuta ni modifica el juego y no copia ni sube
los binarios privados. La versión de metadata, el hash del módulo y el hash de
metadata quedan validados antes de aceptar las correspondencias.

## Estado de los insumos en Codex Cloud

Los binarios originales no están montados en este checkout. Sin embargo, el
usuario ya resolvió `DebugConsole.OnDestroy` directamente contra esos
originales. El resultado queda fijado en
[`PS4_ONDESTROY_NATIVE_RESOLVED.md`](PS4_ONDESTROY_NATIVE_RESOLVED.md) y en el
manifiesto de expectativas
[`PS4_ONDESTROY_EXPECTATIONS.json`](PS4_ONDESTROY_EXPECTATIONS.json): definición
82470, `methodIndex=75393`, token `0x0600777D`, RVA `0x005C3340`. El manifiesto
separa la escritura cero a `Counters` (`static_fields+0x08`, `0x005C3384`) de
la escritura de R14/`this` a `Instance` (`static_fields+0x10`, `0x005C356C`).
Los tests host validan esa clasificación con ventanas sintéticas; no vuelven
a analizar ni pretenden reemplazar los binarios originales.

Los slots `0x033EB300`/`0x033EF3E8` y los destinos de Rewired siguen sin tener
una asociación exacta con registro de tipos PS4. Las llamadas
`0x004762D6`/`0x00476315` permanecen indirectas y sin nombre de interfaz o
método destino.

Los contenedores actuales siguen siendo SCE/SELF y no se pasan directamente al
mapper de RVA. La inspección de sus entradas permitió recuperar sus payloads
plaintext offline con `scripts/unwrap_plain_self.py`. Ambos ELF reconstruidos
coinciden íntegramente con los anteriores; el módulo recuperado sí satisface
el hash fijado por este pipeline y los 42 prefijos fueron comprobados. La
metadata también coincide. La procedencia distingue contenedor y copia ELF en
[`PS4_DUMP_PROVENANCE.json`](PS4_DUMP_PROVENANCE.json); la investigación nueva
se concentra en [registro e integración AOT](AOT_INTEGRATION_PROPOSAL.md).

## Una sola ejecución reproducible

En una máquina que conserve localmente los dos originales privados:

```sh
python3 scripts/analyze_ps4_il2cpp_pipeline.py \
  --metadata /ruta/privada/global-metadata.dat \
  --module /ruta/privada/Il2CppUserAssemblies.prx \
  --disassembly /ruta/privada/Desensamblado_Metodos.txt \
  --output /tmp/theforest-il2cpp-report.md
```

El hash y la versión esperados se fijan por defecto a la imagen ELF64 histórica
que se pudo analizar, no al contenedor SCE/SELF del último dump:

- metadata v23, SHA-256 `238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3`;
- módulo SHA-256 `0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969`;
- tabla de punteros de métodos en el offset de archivo `0x31738C0`;
- PT_LOAD de imagen con base virtual `0`, requerido antes de tratar esos
  punteros como RVA; los métodos deben caer además en un segmento `PF_X`
  file-backed.

Un archivo que no coincida falla cerrado. Para regenerar ventanas selectivas
del PRX local se puede pedir al mismo comando que ejecute `llvm-objdump` o
`objdump` **solo** sobre los métodos de interés, sin desensamblar el ELF
completo:

```sh
python3 scripts/analyze_ps4_il2cpp_pipeline.py \
  --metadata /ruta/privada/global-metadata.dat \
  --module /ruta/privada/Il2CppUserAssemblies.prx \
  --disassemble-targeted --window-bytes 0x240 \
  --output /tmp/theforest-il2cpp-targeted.md
```

El tamaño es una ventana de inspección, no una longitud de función IL2CPP. El
valor `0x240` llega desde RVA `0x005C3340` hasta el inicio conocido de
`DebugConsole.Update` en `0x005C3580`, y cubre los stores observados de
`OnDestroy`. El pipeline comprueba los bytes de toda instrucción suministrada
contra el ELF original. En ese método reconoce de forma separada las dos
expectativas fijadas en el manifiesto: `Counters=0` en `0x005C3384` y
`Instance=R14` en `0x005C356C`; también verifica el `mov r14,rdi` en
`0x005C3351` antes de describir R14 como `this`. No interpreta el write-back
como limpieza del singleton ni como evidencia de objeto Unity vivo.

Para otros stores no cubiertos por ese manifiesto, se puede aportar una
anotación local basada en el desensamblado exacto, como:

```sh
--store-site 0x<RVA_INSTRUCCION>=TheForest.DebugConsole.Instance
```

Las anotaciones genéricas no se usan para sobrescribir ni renombrar las dos
expectativas PS4 ya registradas.

Para contrastar los campos `static` se puede añadir un `dump.cs` local
producido desde los mismos originales:

```sh
python3 scripts/analyze_ps4_il2cpp_pipeline.py \
  --metadata /ruta/privada/global-metadata.dat \
  --module /ruta/privada/Il2CppUserAssemblies.prx \
  --dump-cs /ruta/privada/dump.cs \
  --disassembly /ruta/privada/Desensamblado_Metodos.txt \
  --output /tmp/theforest-il2cpp-report.md
```

No usar `--expected-*-sha256` para aceptar otro build sin autenticar primero
ese build y actualizar la evidencia correspondiente. La salida del pipeline
omite rutas locales e instrucciones crudas.

## Qué resuelve el flujo

1. Lee índices y nombres de `Il2CppTypeDefinition`, `Il2CppMethodDefinition` y
   `Il2CppFieldDefinition` del formato v23.
2. Separa el índice de la fila `MethodDefinition` del campo `methodIndex`.
   Lee ese índice en la tabla del módulo y acepta el RVA solo si cae en un
   `PT_LOAD` ejecutable y respaldado por bytes del archivo. También compara cada secuencia
   de bytes de las ventanas contra el módulo y valida el destino comentado de
   accesos RIP-relative.
3. Para los hashes originales, exige que `DebugConsole.OnDestroy` resuelva a
   definición 82470, `methodIndex=75393`, token `0x0600777D` y RVA
   `0x005C3340`. Clasifica las instrucciones de `Counters` y `Instance`
   separadamente; no infiere la invocación en runtime.
4. Inspecciona los bytes estáticos de los slots nativos
   `0x033EB300`/`0x033EF3E8`, pero los etiqueta como bytes de archivo, nunca
   como valores de ejecución.
5. Busca candidatos metadata para `CoopPeerStarter.DedicatedHost` y para
   interfaces bajo `Rewired`; los mantiene en una tabla aparte y no los asocia
   a un slot nativo.
6. Clasifica las llamadas a `0x004762D6` y `0x00476315` como dispatch indirecto
   si la ventana contiene el patrón IL2CPP. No inventa el nombre del miembro,
   la implementación concreta ni una atribución a ScePad.

La metadata v23 nombra tipos y registra sus rangos, pero no es por sí sola un
mapa desde un RVA de variable global del ELF a un TypeDef. Para establecer esa
relación hace falta seguir el registro nativo/codegen del mismo build y el
inicializador de cada slot. Esos archivos y registros no están en el workspace
actual. Un nombre de PC o un TSV de nombres aportado sin esa procedencia no es
una resolución.

## Verificación

`tests/test_analyze_ps4_il2cpp_pipeline.py` crea metadata v23 y ELF sintéticos
pequeños. Verifica mapping `methodIndex`→RVA, hash/versión, ownership de campos,
CFG con rutas completas e incompletas, la identidad fija de `OnDestroy`, la
separación `Counters=0` frente a `Instance=this`, las dos llamadas virtuales y
el estado no resuelto de los slots sin metadata registration. Las pruebas no
simulan análisis de binarios originales, no verifican PS4 en vivo ni confirman
que Unity invoque los métodos.
