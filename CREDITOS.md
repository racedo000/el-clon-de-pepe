# Créditos, licencias y atribución

**El Clon de Pepe** es una interfaz local para Android/Termux, construida con
iteraciones de diseño y pruebas del usuario y asistencia de ChatGPT para el
prototipado y la documentación. No es un producto oficial de ninguno de los
proyectos que aparecen a continuación ni tiene afiliación con ellos.

## Dependencias y trabajos anteriores

| Proyecto | Utilización | Licencia / información |
| --- | --- | --- |
| [OmniVoice (k2-fsa / Xiaomi)](https://github.com/k2-fsa/OmniVoice) | Modelo TTS base, clonación, diseño de voz | Código Apache-2.0; revisar licencia del modelo por separado |
| [omnivoice.cpp](https://github.com/ServeurpersoCom/omnivoice.cpp) | Motor C++/GGML que ejecuta la síntesis | MIT; Copyright (c) 2023-2026 The omnivoice.cpp authors |
| [OmniVoice-GGUF, Serveurperso](https://huggingface.co/Serveurperso/OmniVoice-GGUF) | Pesos cuantizados opcionales, descargados por el usuario | **CC BY-NC 4.0; uso no comercial** |
| [GGML](https://github.com/ggml-org/ggml) | Cálculos de inferencia (submódulo de omnivoice.cpp) | Licencia del proyecto upstream |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | Transcripción de grabaciones locales | MIT; Copyright (c) 2023-2026 The ggml authors |
| [Argos Translate](https://github.com/argosopentech/argos-translate) | Traducción neuronal local opcional | MIT; Copyright (c) 2020 Argos Open Technologies, LLC |
| [MiniSBD](https://github.com/argosopentech/minisbd) | Segmentación de oraciones para Argos liviano | Revisar licencia upstream |
| [Apertium](https://github.com/apertium/apertium) | Traducción clásica opcional | GPL-2.0 según archivo COPYING upstream; consultar las licencias de los pares de idiomas |
| [VoiceStudio, debpalash](https://github.com/debpalash/VoiceStudio) | Inspiración en funciones de un estudio de voces; **su aplicación original no se incluye** | AGPL-3.0; la aplicación de este repositorio no incorpora sus archivos |

## Importante sobre los pesos

La licencia MIT de **los archivos de código propios de este repositorio** NO
cambia ni elimina las restricciones de terceros. Los pesos `OmniVoice-GGUF`
permanecen bajo CC BY-NC 4.0 y **no se adjuntan ni redistribuyen aquí**.
Antes de usar el modelo, leer la [ficha y licencia del publicador](https://huggingface.co/Serveurperso/OmniVoice-GGUF).
Los binarios y modelos de Whisper/Argos/Apertium se instalan desde sus fuentes
originales. Se deben respetar sus condiciones por separado.

## Privacidad

El repositorio no incluye las grabaciones de prueba, voces clonadas,
transcripciones, capturas privadas, nombres de usuario del teléfono ni datos
personales. Al usar la app, los audios de salida se guardan localmente en
`/root/omnivoice.cpp/web_outputs/`; las referencias se procesan en carpetas
temporales. Si publicás capturas o ejemplos, revisá que tengas permiso.

Solo cloná voces propias o para las que tengas autorización clara. Informá
cuando un audio es sintético y no lo uses para suplantar a otras personas.
