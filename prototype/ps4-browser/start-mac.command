#!/bin/bash
# A local, non-privileged HTTP server for the PS4 browser demo.
cd "$(dirname "$0")" || exit 1
PORT=8765
IP=$(/usr/sbin/ipconfig getifaddr en0 2>/dev/null || /usr/sbin/ipconfig getifaddr en1 2>/dev/null)
echo "============================================"
echo "THE FOREST UCM - SOLO PRUEBA DE NAVEGADOR"
echo "No instala nada ni modifica la consola."
echo "============================================"
if [ -n "$IP" ]; then
 echo "En la PS4, abri: http://$IP:$PORT/index.html"
else
 echo "Consulta la IP local de la Mac en Preferencias del Sistema > Red"
 echo "Y abri en la PS4: http://TU-IP:$PORT/index.html"
fi
echo "Para detener el servidor: Control+C."
if command -v python3 >/dev/null 2>&1; then
 exec python3 -m http.server "$PORT" --bind 0.0.0.0
elif [ -x /usr/bin/python ]; then
 exec /usr/bin/python -m SimpleHTTPServer "$PORT"
else
 echo "Falta Python 3 o el Python incluido en macOS."; exit 2
fi
