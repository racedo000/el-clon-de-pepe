#!/usr/bin/env python3
"""Instala Argos 1.11.0 sin PyTorch/Stanza/spaCy, usando MiniSBD.
Los modelos se guardan en la carpeta estándar de Argos, fuera del venv.
Instalación opcional: solo para traducción Natural (offline después).
"""
from pathlib import Path
import os
import subprocess
import sys
import urllib.request
import venv

BASE = Path('/root/pepe-argos-liviano')
PYTHON = BASE / 'bin/python'
READY = BASE / 'pepe_modelos_ok'
CACHE = Path('/root/pepe-argos-modelos')
MODELS = {
    ('es', 'en'): ('translate-es_en-1_9.argosmodel', 'https://data.argosopentech.com/argospm/v1/translate-es_en-1_9.argosmodel'),
    ('en', 'es'): ('translate-en_es-1_0.argosmodel', 'https://data.argosopentech.com/argospm/v1/translate-en_es-1_0.argosmodel'),
}
DEPS = ['ctranslate2>=4,<5', 'sentencepiece>=0.2,<0.3', 'minisbd', 'packaging', 'sacremoses>=0.0.53,<0.2']

def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run([str(x) for x in args], check=True, **kwargs)

def main():
    if READY.is_file():
        print('El entorno liviano ya fue validado:', READY)
        return
    if not PYTHON.is_file():
        venv.EnvBuilder(with_pip=True).create(str(BASE))
    run([PYTHON, '-m', 'pip', 'install', '--no-cache-dir', *DEPS])
    run([PYTHON, '-m', 'pip', 'install', '--no-cache-dir', '--no-deps', 'argostranslate==1.11.0'])
    sbd = BASE / 'lib/python3.12/site-packages/argostranslate/sbd.py'
    if not sbd.is_file():
        raise RuntimeError('No se encontró sbd.py; el instalador espera Python 3.12 de Ubuntu 24.04.')
    code = sbd.read_text(encoding='utf-8')
    old = 'import stanza\nfrom minisbd import'
    new = 'try:\n    import stanza\nexcept ImportError:\n    stanza = None\n\nfrom minisbd import'
    if old in code:
        sbd.with_suffix('.py.original').write_text(code, encoding='utf-8')
        sbd.write_text(code.replace(old, new, 1), encoding='utf-8')
    elif new not in code:
        raise RuntimeError('El código de Argos es distinto; no se aplicó ningún parche inseguro.')
    print('Argos configurado para usar MiniSBD sin instalar Stanza.', flush=True)
    # Los modelos ya instalados en ~/.local/share/argos-translate son reutilizables.
    CACHE.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(ARGOS_CHUNK_TYPE='MINISBD', ARGOS_DEVICE_TYPE='cpu',
               ARGOS_INTRA_THREADS='2', ARGOS_INTER_THREADS='1')
    available_script = ('from argostranslate import package;'
                        'print(";".join(p.from_code+"-"+p.to_code for p in package.get_installed_packages()))')
    r = subprocess.run([str(PYTHON), '-c', available_script], env=env, check=True, capture_output=True, text=True)
    installed = set(r.stdout.strip().split(';'))
    for (src, dst), (filename, url) in MODELS.items():
        if f'{src}-{dst}' in installed:
            print('Modelo instalado:', src, dst, flush=True)
            continue
        archive = CACHE / filename
        if not archive.exists() or archive.stat().st_size < 10_000_000:
            if archive.exists():
                raise RuntimeError('Descarga previa incompleta (no sobrescrita): ' + str(archive))
            part = CACHE / (filename + '.parcial')
            if part.exists():
                raise RuntimeError('Descarga parcial existente: ' + str(part))
            print('Descargando modelo oficial:', filename, flush=True)
            request = urllib.request.Request(url, headers={'User-Agent': 'El-Clon-de-Pepe/1.0'})
            with urllib.request.urlopen(request, timeout=180) as response, part.open('wb') as f:
                import shutil
                shutil.copyfileobj(response, f, length=1024 * 1024)
            if part.stat().st_size < 10_000_000:
                raise RuntimeError('Descarga incompleta: ' + filename)
            part.rename(archive)
        run([PYTHON, '-c', 'from argostranslate import package; import sys; package.install_from_path(sys.argv[1])', archive], env=env)
    test_code = ('from argostranslate import translate; import sys; '
                 'print(translate.translate(sys.stdin.read().strip(), sys.argv[1], sys.argv[2]))')
    for src, dst, original in [('es','en','Hola, soy Pepe.'),('en','es','Hello, I am Pepe.')]:
        out = subprocess.run([str(PYTHON), '-c', test_code, src, dst],
                             input=original, env=env, check=True, capture_output=True, text=True, timeout=300)
        if not out.stdout.strip():
            raise RuntimeError('Traducción vacía para ' + src + '-' + dst)
        print(src, '→', dst, ':', out.stdout.strip(), flush=True)
    READY.write_text('Argos Translate 1.11.0, MiniSBD. Verificado en ambos sentidos.\n', encoding='utf-8')
    print('ARGOS LIVIANO INSTALADO:', READY, flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ERROR:', exc, file=sys.stderr)
        sys.exit(1)
