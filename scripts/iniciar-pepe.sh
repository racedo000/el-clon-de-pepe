#!/bin/sh
# Ejecutar dentro de Ubuntu 24.04; se usa el traductor neuronal LIVIANO.
set -eu
export ARGOS_CHUNK_TYPE=MINISBD
export ARGOS_DEVICE_TYPE=cpu
export PEPE_ARGOS_PYTHON=/root/pepe-argos-liviano/bin/python
export PEPE_ARGOS_READY=/root/pepe-argos-liviano/pepe_modelos_ok
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Repo por defecto en /root/el-clon-de-pepe, pero funciona en otra ubicación.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec /usr/bin/python3 "$DIR/el_clon_de_pepe.py"
