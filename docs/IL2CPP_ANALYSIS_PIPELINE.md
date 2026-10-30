# Pipeline offline para IL2CPP PS4 v23

Este flujo lee localmente `global-metadata.dat`, el ELF/PRX original y ventanas
acotadas de desensamblado. No ejecuta ni modifica el juego y no copia ni sube
los binarios privados. La versión de metadata, el hash del módulo y el hash de
metadata quedan validados antes de aceptar las correspondencias.

## Estado de los insumos en Codex Cloud

En el checkout de esta tarea están disponibles el informe Markdown y el texto
de ventanas selectivas que adjuntó el usuario. Se confirmó que el parser
acepta esas ventanas y que `ProcessGamePads` contiene llamadas indirectas en
`0x004762D6` y `0x00476315`, ambas precedidas por el lookup de interfaz IL2CPP
que referencia el slot `0x033EF3E8`.

No están disponibles aquí el PRX original ni `global-metadata.dat`. Por ello
no se publica un índice/RVA real para `DebugConsole.OnDestroy`, no se vinculan
`0x033EB300`/`0x033EF3E8` a tipos PS4 y no se identifica un destino virtual.
Los hashes esperados y el offset del método-pointer table sí están registrados
en la evidencia anterior, pero no reemplazan los archivos fuente necesarios
para volver a comprobarlos.

## Una sola ejecución reproducible

En una máquina que conserve localmente los dos originales privados:

```sh
python3 scripts/analyze_ps4_il2cpp_pipeline.py \
  --metadata /ruta/privada/global-metadata.dat \
  --module /ruta/privada/Il2CppUserAssemblies.prx \
  --disassembly /ruta/privada/Desensamblado_Metodos.txt \
  --output /tmp/theforest-il2cpp-report.md
```

El hash y la versión esperados se fijan por defecto al build PS4 reportado:

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
  --disassemble-targeted --window-bytes 0x180 \
  --output /tmp/theforest-il2cpp-targeted.md
```

El tamaño es una ventana de inspección, no una longitud de función IL2CPP. Si
el CFG termina abierto, contiene saltos externos o bytes omitidos, el reporte
retiene la incertidumbre. Para revisar limpieza de `Instance`, se requiere
además una anotación local, basada en el desensamblado exacto, como:

```sh
--store-site 0x<RVA_INSTRUCCION>=TheForest.DebugConsole.Instance
```

El analizador confirma que la instrucción anotada es un `MOV` con destino en
memoria. Solo clasifica como escritura cero una fuente inmediata `0`/`0x0`;
no hace análisis de flujo de datos para registros ni asume que el nombre de la
anotación sea verdadero. El reporte diferencia una limpieza visible de la
prueba de que todos los caminos o el callback de Unity estén activos.

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
3. Reporta `DebugConsole.OnDestroy` con índice/RVA si existe en esos insumos y
   evalúa exclusivamente las instrucciones de la ventana suministrada.
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
CFG con rutas completas e incompletas, las dos llamadas virtuales y el estado
no resuelto de los slots sin metadata registration. No simula resultados reales
de la PS4 ni confirma que Unity llame a los métodos.
