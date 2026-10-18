#!/data/data/com.termux/files/usr/bin/bash
# Instalar en Termux (~/.shortcuts/Pepe.sh), no dentro de Ubuntu.
export PATH="/data/data/com.termux/files/usr/bin:/system/bin"
URL="http://127.0.0.1:8765/"
if curl -fsS --max-time 2 "$URL" >/dev/null 2>&1; then
  termux-open-url "$URL"
  exit 0
fi
(for i in {1..40}; do
  if curl -fsS --max-time 2 "$URL" >/dev/null 2>&1; then
    termux-open-url "$URL"
    exit 0
  fi
  sleep 1
done) &
exec proot-distro login ubuntu2404 -- /root/el-clon-de-pepe/scripts/iniciar-pepe.sh
