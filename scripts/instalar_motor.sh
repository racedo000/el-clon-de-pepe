#!/bin/sh
# Ejecutar en Ubuntu 24.04, desde cualquier carpeta.
set -eu
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
SRC=/root/omnivoice.cpp
REV=886fc079838ca7400cb2b42b36e2a65aa1daabe8
if [ ! -e "$SRC" ]; then
  git clone https://github.com/ServeurpersoCom/omnivoice.cpp.git "$SRC"
fi
if [ ! -d "$SRC/.git" ]; then
  echo 'ERROR: carpeta ocupada sin repositorio Git; no se modificó.' >&2
  exit 1
fi
cd "$SRC"
# Mantiene el commit probado del motor, en lugar de una rama que cambia.
if [ ! -e build/omnivoice-tts ]; then
  git checkout "$REV"
  git submodule update --init --recursive
  cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=OFF -DGGML_VULKAN=OFF
  cmake --build build --target omnivoice-tts --parallel 2
else
  echo 'Motor original existente; no se recompila ni se sobrescribe.'
fi
