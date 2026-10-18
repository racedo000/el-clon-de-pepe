# 🐸🎙️ El Clon de Pepe

**Estudio de voz totalmente local para Android (Termux + Ubuntu 24.04 / PRoot).**
Generá narraciones, cloná **tu propia voz o voces autorizadas**, transcribí
referencias y traducí textos de español a inglés y viceversa. La interfaz se
abre en Chrome desde `http://127.0.0.1:8765/`.

> Proyecto comunitario y experimental, no una app Android APK. Necesitás
> Termux abierto mientras usás la interfaz. Instalación inicial con internet;
> generación, clonación, transcripción y traducción funcionan sin internet
> después de descargar las herramientas y modelos.

## Funciones

- Voz masculina / femenina **experimentales**, mediante `--instruct male/female`.
- Clonación de voz a partir de una grabación propia o autorizada y su transcripción.
- Grabación desde el navegador o selección de archivo de audio.
- Reconocimiento automático de la transcripción con **whisper.cpp** (opcional).
- Calidad **Media 24 pasos** por defecto, con Alta 32 y Rápida 16.
- Prioridad de CPU normal / moderada / segundo plano (`nice`).
- Cronómetro, barra de pasos de síntesis, reproductor y descarga WAV.
- Traducción desactivada por defecto; español ↔ inglés con **Apertium** o
  **Argos Translate + MiniSBD** (opcionales).
- Servidor accesible únicamente desde el propio teléfono (`127.0.0.1`).

## Instalación

Consultá **[docs/INSTALACION.md](docs/INSTALACION.md)** para el procedimiento
completo en un teléfono ARM64 con Termux, PRoot y Ubuntu 24.04.

**Uso rápido después de instalar:**

```sh
# En Termux:
proot-distro login ubuntu2404
# Dentro de Ubuntu:
/root/el-clon-de-pepe/scripts/iniciar-pepe.sh
```

En Chrome: **http://127.0.0.1:8765/**. Detener con `Ctrl + C`.

## Requisitos

- Android ARM64, Termux, PRoot-Distro y Ubuntu 24.04 con Python 3.12.
- Compiladores C/C++, CMake, Ninja, Git y FFmpeg instalados en Ubuntu.
- Memoria suficiente y espacio para dos GGUF (unos 660 MB), ejecutables y
  modelos opcionales de transcripción/traducción. El modelo puede tardar
  varios minutos por frase en CPU; depende del teléfono y de la grabación.
- No hace falta PyTorch para el servidor web ni para Argos **liviano**.

## Estructura

```text
el_clon_de_pepe.py                # Interfaz HTML+JavaScript y servidor Python local
scripts/instalar_motor.sh         # Compila motor OmniVoice a partir de su repo
scripts/descargar_modelos.py      # Descarga los modelos GGUF en el teléfono
scripts/preparar_calidades.py     # Compila copia experimental de 16/24 pasos
scripts/instalar_transcripcion_pepe.py  # whisper.cpp + modelo tiny
scripts/instalar_argos_liviano.py # Traducción neuronal pequeña (sin PyTorch)
scripts/iniciar-pepe.sh           # Inicia el servidor con MiniSBD
scripts/Pepe-Termux-Widget.sh     # Acceso directo opcional para Termux:Widget
docs/INSTALACION.md              # Guía paso a paso
CREDITOS.md                      # Atribuciones, privacidad y licencias
LICENSE                          # Licencia del código propio (MIT)
.gitignore                       # Exclusión de modelos, audios y secretos
```

## Seguridad y licencias

- **No subas grabaciones reales, WAV de salida, `.gguf`, modelos `.argosmodel`,
  claves ni datos personales al repositorio.** Esos archivos NO se incluyen.
- No redistribuimos pesos: los GGUF usados llevan licencia
  **[CC BY-NC 4.0, uso no comercial](https://huggingface.co/Serveurperso/OmniVoice-GGUF)**.
- Código de esta interfaz bajo **MIT**; motores/modelos de terceros tienen
  sus propias licencias. [Ver créditos](CREDITOS.md).
- La clonación debe ser consensuada; no suplantar personas.

## Estado

Probado de forma experimental en un teléfono ARM64 con Snapdragon 6 Gen 3,
Ubuntu 24.04 en Termux. Los resultados y tiempos varían según el hardware.
No se garantiza precisión de traducción, transcripción o generación vocal.

## Créditos

Integración, experiencia de usuario y pruebas: contribuidores del proyecto,
con apoyo de ChatGPT para desarrollo y documentación. Gracias a los equipos
de **OmniVoice, omnivoice.cpp, whisper.cpp, Argos, Apertium y GGML**.
Ver [CREDITOS.md](CREDITOS.md) para enlaces y licencias.
