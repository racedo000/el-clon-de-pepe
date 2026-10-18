#!/usr/bin/env python3
"""Compila un motor experimental OmniVoice con calidad variable SIN tocar el original.

Instalación prevista: Ubuntu 24.04 ARM64 en Termux, código existente en
/root/omnivoice.cpp. El nuevo binario queda en /root/omnivoice_tuned/build/omnivoice-tts.
Códigos de calidad: OV_STEPS=16 / 24 / 32; OV_THREADS=2/4/etc.
No descarga modelos y nunca modifica los WAV ni la instalación original.
"""
from pathlib import Path
import os
import shutil
import subprocess

ORIGINAL = Path('/root/omnivoice.cpp')
EXPERIMENTAL = Path('/root/omnivoice_tuned')
SOURCE_BIN = ORIGINAL / 'build/omnivoice-tts'
TARGET_BIN = EXPERIMENTAL / 'build/omnivoice-tts'
MARKER = EXPERIMENTAL / '.voicestudio_calidad_2026'


def abort(reason):
    raise SystemExit('ERROR: ' + reason)


def ignore_folder(folder, names):
    excluded = {'.git', '__pycache__', '.pytest_cache'}
    if Path(folder).resolve() == ORIGINAL.resolve():
        excluded |= {'build', 'build-fast', 'models', 'web_outputs', '.venv', 'venv'}
        excluded |= {name for name in names if name.lower().endswith(('.wav', '.gguf', '.mp3', '.m4a'))}
    return excluded.intersection(names)


def patch_once(path, old, new, what):
    src = path.read_text(encoding='utf-8')
    if src.count(old) != 1:
        abort(f'No pude reconocer el punto de cambio para {what}. No modifiqué el proyecto original.')
    path.write_text(src.replace(old, new, 1), encoding='utf-8')


def compile_command(command):
    print('\n+ ' + ' '.join(map(str, command)), flush=True)
    env = dict(os.environ)
    env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    subprocess.run([str(x) for x in command], check=True, env=env)


def main():
    if not SOURCE_BIN.is_file():
        abort('No está el ejecutable original. Verificá /root/omnivoice.cpp/build/omnivoice-tts.')
    if TARGET_BIN.is_file():
        print('El motor con calidades ya está compilado:', TARGET_BIN)
        return
    if EXPERIMENTAL.exists() and not MARKER.is_file():
        abort('La carpeta /root/omnivoice_tuned ya existe pero no es de este instalador. '
              'No la modificaré ni borraré sin tu permiso.')
    if not EXPERIMENTAL.exists():
        if not (ORIGINAL / 'src/backend.h').is_file() or not (ORIGINAL / 'src/omnivoice.cpp').is_file() \
                or not (ORIGINAL / 'ggml/CMakeLists.txt').is_file():
            abort('No encontré el código fuente completo de OmniVoice y su submódulo ggml.')
        print('Creando copia independiente del código (sin modelos, audios ni motor original)…', flush=True)
        shutil.copytree(ORIGINAL, EXPERIMENTAL, ignore=ignore_folder)
        patch_once(EXPERIMENTAL / 'src/backend.h',
                   'static int backend_cpu_n_threads(void) {\n',
                   '''static int backend_cpu_n_threads(void) {
    if (const char * configured = std::getenv("OV_THREADS")) {
        char * end = nullptr;
        long n = std::strtol(configured, &end, 10);
        if (end != configured && *end == '\\0' && n >= 1 && n <= 16) {
            return static_cast<int>(n);
        }
    }
''', 'los hilos de CPU')
        patch_once(EXPERIMENTAL / 'src/omnivoice.cpp',
                   '    p->mg_num_step             = 32;\n',
                   '''    p->mg_num_step             = 32;
    if (const char * configured = std::getenv("OV_STEPS")) {
        char * end = nullptr;
        long n = std::strtol(configured, &end, 10);
        if (end != configured && *end == '\\0' && n >= 16 && n <= 32) {
            p->mg_num_step = static_cast<int>(n);
        }
    }
''', 'la cantidad de pasos')
        MARKER.write_text('Motor experimental VoiceStudio: OV_STEPS y OV_THREADS.\n', encoding='utf-8')
    print('Compilando con dos trabajos en paralelo; el motor original no se modifica.', flush=True)
    compile_command(['cmake', '-S', EXPERIMENTAL, '-B', EXPERIMENTAL / 'build', '-G', 'Ninja',
                     '-DCMAKE_BUILD_TYPE=Release', '-DGGML_BLAS=OFF', '-DGGML_VULKAN=OFF'])
    compile_command(['cmake', '--build', EXPERIMENTAL / 'build', '--target',
                     'omnivoice-tts', '--parallel', '2'])
    if not TARGET_BIN.is_file():
        abort('CMake finalizó, pero no aparece el ejecutable nuevo.')
    print('\n¡LISTO! Motor alternativo:', TARGET_BIN)
    print('Original intacto:', SOURCE_BIN)
    print('Ya podés iniciar la nueva interfaz y elegir 16 / 24 / 32 pasos.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        abort('La compilación se detuvo con código ' + str(exc.returncode) +
              '. La versión original sigue funcionando; podés repetir el comando para reanudar.')
    except (OSError, shutil.Error) as exc:
        abort('Problema con archivos o permisos: ' + str(exc))
