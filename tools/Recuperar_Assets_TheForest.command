#!/bin/bash
# macOS Catalina+/Intel — The Forest CUSA12398 v1.15, read-only FTP collector.
# NO PS4 writes, hooks, plugins, cheats, or PKG modification.
set -u
finish() {
  printf '\nPresiona Enter para cerrar esta ventana... '
  read -r _unused || true
}
trap finish EXIT

printf '\n== THE FOREST PS4: RECUPERAR ASSETS UNITY ==\n\n'
printf 'Necesitas GoldHEN FTP activo, The Forest abierto en su menu,\n'
printf 'y la Mac y la PS4 conectadas a la misma red local.\n\n'
if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: no se encontro Python 3 en esta Mac.\n'
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  printf 'ERROR: curl no esta disponible.\n'
  exit 1
fi

printf 'IP local de tu PS4 (ej. 192.168.1.50): '
read -r IP
case "$IP" in
  ''|*[!0-9.]*)
    printf 'IP no valida: usa solamente numeros y puntos.\n'
    exit 1 ;;
esac

SCRIPT="$(mktemp /tmp/forest_ucm_assets.XXXXXX.py)" || exit 1
trap 'rm -f "$SCRIPT"; finish' EXIT
# Pinned reviewed source; no mutable branch/code is executed.
SOURCE='https://raw.githubusercontent.com/Skaymer-AR/TheForest-UCM-PS4/d0478d330e0e38343e6e41e100b46240d727bb85/scripts/collect_ps4_unity_assets_ftp.py'
printf '\nDescargando el verificador original desde un commit fijo...\n'
if ! curl --fail --location --silent --show-error --max-time 45 "$SOURCE" -o "$SCRIPT"; then
  printf 'ERROR: no se pudo bajar el verificador. Revisa Internet.\n'
  exit 1
fi

printf '\n[1/2] Solo INVENTARIO FTP; nada se copia todavia:\n\n'
if ! python3 "$SCRIPT" --host "$IP" --port 2121; then
  printf '\nNo se accedio al juego montado. Comprueba FTP y deja\n'
  printf 'The Forest abierto en el menu principal.\n'
  exit 1
fi
printf '\nCopiar los seis archivos a tu Mac? [s/N]: '
read -r ANSWER
case "$ANSWER" in
  s|S|si|SI|Si) ;;
  *) printf '\nListo: inventario unicamente; sin descargas.\n'; exit 0 ;;
esac

DEST="$HOME/Desktop/TheForest_CUSA12398_Assets"
printf '\n[2/2] Copiando SOLO seis archivos y comprobando SHA-256:\n%s\n' "$DEST"
if python3 "$SCRIPT" --host "$IP" --port 2121 --download --output "$DEST"; then
  printf '\nEXITO: seis hashes del juego v1.15 verificados.\n'
  printf 'Los archivos estan en %s\n' "$DEST"
  printf 'Compartilos PRIVADAMENTE con Work para seguir el analisis.\n'
else
  printf '\nNo se pudieron verificar los seis archivos.\n'
  printf 'Manda una captura de esta ventana para investigar el error.\n'
  exit 2
fi
