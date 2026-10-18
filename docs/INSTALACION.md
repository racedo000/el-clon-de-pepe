# Instalación en Termux + Ubuntu 24.04 (ARM64)

Esta guía reproduce la configuración que usamos para **El Clon de Pepe**.
No borres distribuciones ni entornos existentes para seguirla. Los comandos
se ejecutan en **dos entornos diferentes**: Termux Android y Ubuntu (PRoot).

## 1. Instalar Ubuntu 24.04 (Termux Android, símbolo `$`)

Instalá Termux desde una fuente confiable y ejecutá:

```sh
pkg update
pkg install -y proot-distro git
proot-distro install ubuntu:24.04 --name ubuntu2404
proot-distro login ubuntu2404
```

Si `ubuntu2404` ya existe, **no la reinstales**: simplemente entrá con
`proot-distro login ubuntu2404`. Consulta [proot-distro](https://github.com/termux/proot-distro).

## 2. Preparar Ubuntu (comandos dentro de Ubuntu)

```sh
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
apt update
apt install -y git ca-certificates cmake ninja-build build-essential \
  python3 python3-venv python3-pip ffmpeg curl
```

Verificá Python: `/usr/bin/python3 --version` (Ubuntu 24.04 usa Python 3.12).

## 3. Traer este repositorio

Para clonar el proyecto publicado en GitHub:

```sh
git clone https://github.com/racedo000/el-clon-de-pepe.git /root/el-clon-de-pepe
cd /root/el-clon-de-pepe
```

También podés copiar esta carpeta a `/root/el-clon-de-pepe/` sin usar Git.

## 4. Compilar OmniVoice original (CPU, sin root)

```sh
sh scripts/instalar_motor.sh
```

El script clona [omnivoice.cpp](https://github.com/ServeurpersoCom/omnivoice.cpp),
usa el commit **`886fc079838ca7400cb2b42b36e2a65aa1daabe8`** probado
en el proyecto, inicializa su submódulo GGML y compila el ejecutable de CPU.
Se guarda en `/root/omnivoice.cpp/build/omnivoice-tts`.

## 5. Descargar los GGUF (aceptá la licencia antes)

Primero revisá la ficha y las condiciones de uso **CC BY-NC 4.0** de
[Serveurperso/OmniVoice-GGUF](https://huggingface.co/Serveurperso/OmniVoice-GGUF).
El proyecto no incluye ni redistribuye pesos. Para obtenerlos vos mismo:

```sh
/usr/bin/python3 scripts/descargar_modelos.py
```

Se descargan unos **660 MB** entre el modelo de voz y su codec Q4_K_M.
Requiere internet solo en esta fase.

## 6. Calidad Media/Rápida (recomendado)

```sh
/usr/bin/python3 scripts/preparar_calidades.py
```

Crea `/root/omnivoice_tuned/`, **sin modificar el original**. Lee
`OV_STEPS=24` para Media y `OV_STEPS=16` para Rápida. Si omitís este paso,
la interfaz utilizará Alta (32 pasos) hasta instalar el motor experimental.

## 7. Traducción clásica (opcional)

```sh
apt install -y apertium apertium-eng-spa
```

## 8. Transcripción automática local (opcional)

```sh
/usr/bin/python3 scripts/instalar_transcripcion_pepe.py
```

Descarga y compila [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
y su modelo tiny multilingüe. Después, al grabar o subir una referencia,
se genera automáticamente una transcripción **editable**. Si no instalás
Whisper, escribí la transcripción a mano.

## 9. Traducción Natural liviana (opcional)

**No uses el instalador pesado que añade Stanza/PyTorch/CUDA.** La versión
liviana funciona con Argos 1.11.0 y MiniSBD en Python 3.12:

```sh
/usr/bin/python3 scripts/instalar_argos_liviano.py
```

El instalador usa `--no-deps` únicamente para Argos tras instalar sus
dependencias necesarias y hace un pequeño parche local para que `stanza`
sea opcional. Descarga los dos modelos español ↔ inglés desde el publicador
de Argos si todavía no están instalados, y comprueba ambas traducciones.
Tras instalarlo, no necesita internet.

## 10. Iniciar la app

```sh
sh /root/el-clon-de-pepe/scripts/iniciar-pepe.sh
```

Navegá en Chrome a **http://127.0.0.1:8765/**, en el mismo teléfono.
Mantené Termux vivo mientras uses la interfaz. Detener con `Ctrl + C`.

## 11. Acceso directo opcional en Android

Instalá [Termux:Widget](https://github.com/termux/termux-widget) desde la
misma fuente que Termux. **Desde Termux, fuera de Ubuntu**:

```sh
mkdir -p ~/.shortcuts
cp /RUTA/AL/REPOSITORIO/scripts/Pepe-Termux-Widget.sh ~/.shortcuts/Pepe.sh
chmod 700 ~/.shortcuts
chmod +x ~/.shortcuts/Pepe.sh
```

Si descargaste el repo **dentro de Ubuntu**, no podrás usar directamente
`/root/el-clon-de-pepe` desde el shell normal de Termux. Copiá el script
desde una ubicación Android accesible o pegá su contenido manualmente en
`~/.shortcuts/Pepe.sh`. Usá el widget para ejecutar el acceso directo.

## Diagnóstico

- **`Address already in use`**: hay otro servidor en el puerto 8765; detener
  el anterior con `Ctrl + C`.
- **`Faltan archivos del motor/modelo`**: revisá los pasos 4 y 5.
- **Media o Rápida deshabilitada**: revisá el paso 6 y `OV_FAST_BIN`.
- **Traducción Natural no disponible**: revisá el paso 9 y la existencia de
  `/root/pepe-argos-liviano/pepe_modelos_ok`.
- **Whisper no disponible**: revisá el paso 8.
- **Modelo y paquetes pesan mucho**: no subas caches/venvs a GitHub; la
  carpeta `.gitignore` excluye los formatos sensibles/pesados.
- **Tiempo largo de CPU**: esperable en Snapdragon; cerrar apps pesadas,
  sin forzar temperaturas ni prioridad sobre Android.

## Uso responsable

Trabajá solo con voces propias o autorizadas; no uses voces sintéticas para
engañar a otros sobre quién habló. El audio de referencia se procesa
temporalmente y las salidas se guardan en `web_outputs/` de la carpeta
del motor (borrado manual si se desea).
