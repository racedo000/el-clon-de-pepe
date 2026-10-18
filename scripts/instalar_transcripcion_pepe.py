#!/usr/bin/env python3
"""Instala Whisper.cpp y el modelo tiny multilingüe en Ubuntu/Termux.
Se descarga una vez; luego toda transcripción del Clon de Pepe es local.
No modifica OmniVoice ni los archivos del VoiceStudio existente.
"""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path('/root/whisper.cpp')
CLI = ROOT / 'build/bin/whisper-cli'
MODEL = ROOT / 'models/ggml-tiny.bin'
MODEL_URL = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin'
MODEL_SHA256 = 'be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21'


def require_tool(name):
    if not shutil.which(name):
        raise RuntimeError(f'No encontré {name}. Instalalo dentro de Ubuntu con: apt update && apt install -y git cmake ninja-build ffmpeg ca-certificates')


def run(args):
    print('\nEjecutando: ' + ' '.join(map(str, args)), flush=True)
    env = os.environ.copy()
    env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    subprocess.run([str(a) for a in args], check=True, env=env)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def download_model():
    if MODEL.is_file() and MODEL.stat().st_size > 70_000_000:
        print('\nVerificando integridad del modelo existente…', flush=True)
        if sha(MODEL) == MODEL_SHA256:
            print('Modelo correcto: no hace falta volver a descargarlo.')
            return
        raise RuntimeError('El modelo existe pero su hash no coincide. No lo voy a sobrescribir.')
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    part = MODEL.with_suffix('.bin.descargando')
    if part.is_file():
        part.unlink()
    print('\nDescargando Whisper tiny multilingüe (~78 MB). Esto requiere internet una sola vez.', flush=True)
    try:
        req = urllib.request.Request(MODEL_URL, headers={'User-Agent': 'ElClonDePepe/1.0'})
        with urllib.request.urlopen(req, timeout=120) as response, part.open('wb') as dest:
            downloaded = 0
            while True:
                data = response.read(1024 * 1024)
                if not data:
                    break
                dest.write(data)
                downloaded += len(data)
                if downloaded % (10 * 1024 * 1024) < (1024 * 1024):
                    print(f'  Descargados: {downloaded / (1024 * 1024):.0f} MiB', flush=True)
        if sha(part) != MODEL_SHA256:
            raise RuntimeError('El archivo descargado no pasó la verificación SHA-256.')
        part.replace(MODEL)
    finally:
        if part.exists():
            part.unlink()
    print('Modelo descargado y verificado correctamente.', flush=True)


def main():
    for tool in ('git', 'cmake', 'ninja', 'ffmpeg', 'ffprobe'):
        require_tool(tool)
    if not ROOT.exists():
        print('Clonando Whisper.cpp sin tocar OmniVoice…', flush=True)
        run(['git', 'clone', '--depth', '1', 'https://github.com/ggml-org/whisper.cpp.git', ROOT])
    elif not (ROOT / 'CMakeLists.txt').is_file():
        raise RuntimeError('La carpeta /root/whisper.cpp ya existe, pero no parece Whisper.cpp. No se modificó.')
    if not CLI.is_file():
        print('Compilando Whisper.cpp para ARM64 (2 trabajos en paralelo)…', flush=True)
        run(['cmake', '-S', ROOT, '-B', ROOT / 'build', '-G', 'Ninja',
             '-DCMAKE_BUILD_TYPE=Release', '-DWHISPER_BUILD_TESTS=OFF',
             '-DWHISPER_BUILD_EXAMPLES=ON', '-DGGML_BLAS=OFF', '-DGGML_VULKAN=OFF'])
        run(['cmake', '--build', ROOT / 'build', '--target', 'whisper-cli', '--parallel', '2'])
    if not CLI.is_file():
        raise RuntimeError('No apareció el ejecutable whisper-cli después de compilar.')
    download_model()
    print('\n✅ ¡Transcripción local instalada!', flush=True)
    print('Cerrá el servidor anterior con Ctrl+C e iniciá el_clon_de_pepe.py.', flush=True)
    print('El botón ✨ Transcribir audio automáticamente estará disponible.', flush=True)
    print('El texto es una sugerencia: corregilo antes de generar la clonación.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print('\n⚠️ Instalación incompleta: ' + str(exc), file=sys.stderr)
        print('OmniVoice y las versiones anteriores siguen sin cambios.', file=sys.stderr)
        sys.exit(1)
