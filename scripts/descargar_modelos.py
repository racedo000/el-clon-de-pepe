#!/usr/bin/env python3
"""Descarga los dos GGUF desde su repositorio oficial. No se redistribuyen aquí.
Al ejecutar, el usuario debe cumplir la licencia CC BY-NC 4.0 de los pesos.
"""
from pathlib import Path
import os
import urllib.request

MODELS = Path('/root/omnivoice.cpp/models')
REV = '361609388ae572a820d085185bbbe2a2aac4b30e'
FILES = {
    'omnivoice-base-Q4_K_M.gguf': 200_000_000,
    'omnivoice-tokenizer-Q4_K_M.gguf': 150_000_000,
}

def main():
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, min_bytes in FILES.items():
        path = MODELS / name
        if path.exists() and path.stat().st_size >= min_bytes:
            print('Conservando modelo existente:', path, flush=True)
            continue
        if path.exists():
            raise SystemExit('Modelo incompleto presente (no sobrescrito): ' + str(path))
        url = f'https://huggingface.co/Serveurperso/OmniVoice-GGUF/resolve/{REV}/{name}'
        part = MODELS / (name + '.parcial')
        if part.exists():
            raise SystemExit('Descarga parcial existente (no sobrescrita): ' + str(part))
        print('Descargando (~cientos de MB):', name, flush=True)
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'El-Clon-de-Pepe/1.0'})
            with urllib.request.urlopen(request, timeout=180) as response, part.open('wb') as dest:
                while True:
                    data = response.read(1024 * 1024)
                    if not data:
                        break
                    dest.write(data)
            if part.stat().st_size < min_bytes:
                raise RuntimeError('Descarga demasiado pequeña: ' + name)
            part.rename(path)
            print('Listo:', path, flush=True)
        finally:
            # Se conserva un parcial solo si falló (no se sobrescribe automáticamente).
            pass
if __name__ == '__main__':
    main()
