#!/usr/bin/env python3
"""El Clon de Pepe - voces, clonación, STT, Apertium y Argos Translate offline.
Solo se escucha en 127.0.0.1:8765. Servidor sin bibliotecas Python externas.
El motor compilado, el codec y los modelos Q4 se mantienen intactos.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from queue import Queue, Empty
from collections import deque
from urllib.parse import unquote, urlsplit
import base64
import binascii
import json
import os
import re
import shutil
import subprocess
import time

ROOT = Path('/root/omnivoice.cpp')
BIN = Path(os.environ.get('OV_BIN', ROOT / 'build/omnivoice-tts'))
MODEL = Path(os.environ.get('OV_MODEL', ROOT / 'models/omnivoice-base-Q4_K_M.gguf'))
CODEC = Path(os.environ.get('OV_CODEC', ROOT / 'models/omnivoice-tokenizer-Q4_K_M.gguf'))
OUTPUTS = ROOT / 'web_outputs'
PORT = 8765
MAX_CHARS = 180
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_POST_BYTES = 11 * 1024 * 1024
LANGUAGES = {'Spanish', 'English', 'Portuguese', 'French', 'Italian', 'Japanese', 'Auto'}
DURATIONS = {'auto', '2', '4', '6', '8'}
QUALITY_STEPS = {'high': 32, 'balanced': 24, 'fast': 16}
# Motor local de reglas español <-> inglés. Se instala opcionalmente con apt.
TRANSLATION_MODES = {
    'off': None,
    'es-en': ('spa-eng', 'English'), 'en-es': ('eng-spa', 'Spanish'),
    'es-en-natural': ('argos:es-en', 'English'),
    'en-es-natural': ('argos:en-es', 'Spanish'),
}
ARGOS_PYTHON = Path(os.environ.get('PEPE_ARGOS_PYTHON', '/root/pepe-argos-venv/bin/python'))
# El instalador crea este marcador ÚNICAMENTE después de traducir en ambos sentidos.
ARGOS_READY = Path(os.environ.get('PEPE_ARGOS_READY', '/root/pepe-argos-venv/pepe_modelos_ok'))
ARGOS_SCRIPT = r'''import os, sys
os.environ['ARGOS_DEVICE_TYPE'] = 'cpu'
os.environ['ARGOS_INTRA_THREADS'] = '2'
os.environ['ARGOS_INTER_THREADS'] = '1'
from argostranslate import translate
src, dst = sys.argv[1:3]
source = sys.stdin.read().strip()
if not source: raise SystemExit('texto vacío')
output = translate.translate(source, src, dst).strip()
if not output: raise SystemExit('sin traducción')
print(output)
'''
APERTIUM_BIN = Path(os.environ.get('APERTIUM_BIN', '/usr/bin/apertium'))

# Modo de diagnóstico: instrucciones de un solo atributo.
# El diseño de voces es inestable en algunos idiomas/combinaciones, por lo
# que evitamos combinar edad/tono hasta comprobar el audio real del teléfono.
# Conservamos sin cambios el motor original y el modo de clonación.
NARRATOR_INSTRUCT = {
    'normal': 'male',
    'female': 'female',
}
# Ajustes de prioridad solo para el proceso hijo. No se eleva por encima
# de la prioridad heredada: Android/PRoot sin root no suelen permitirlo.
CPU_NICE_ADJUST = {'max': 0, 'medium': 5, 'low': 10}
NICE_BINARY = '/usr/bin/nice' if Path('/usr/bin/nice').is_file() else shutil.which('nice')
FAST_BIN = Path(os.environ.get('OV_FAST_BIN', '/root/omnivoice_tuned/build/omnivoice-tts'))
WHISPER_ROOT = Path(os.environ.get('WHISPER_ROOT', '/root/whisper.cpp'))
WHISPER_BIN = Path(os.environ.get('WHISPER_BIN', WHISPER_ROOT / 'build/bin/whisper-cli'))
WHISPER_MODEL = Path(os.environ.get('WHISPER_MODEL', WHISPER_ROOT / 'models/ggml-tiny.bin'))
STT_LANGUAGES = {'Spanish': 'es', 'English': 'en', 'Portuguese': 'pt', 'French': 'fr',
                 'Italian': 'it', 'Japanese': 'ja', 'Auto': 'auto'}
lock = Lock()
job = {'state': 'idle', 'message': 'Listo para generar una voz.', 'url': '',
       'phase': '', 'step': 0, 'total_steps': 0, 'estimate_seconds': None,
       'elapsed_seconds': 0, 'quality': 'balanced', 'cpu_priority': 'max', 'spoken_text': '', 'spoken_lang': ''}
_started_at = None
stt_job = {'state': 'idle', 'message': 'Transcripción automática disponible si instalás Whisper.', 'text': '', 'elapsed_seconds': 0}
_stt_started_at = None


PAGE = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#111827"><title>El Clon de Pepe 🐸 · Traducción natural offline</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif}*{box-sizing:border-box}
body{margin:0;background:linear-gradient(155deg,#141b2c,#090d16);color:#e7edf8;min-height:100dvh;padding:22px 14px}
main{max-width:650px;margin:14px auto}header{display:flex;gap:11px;align-items:center;margin-bottom:25px}
.logo{display:grid;place-items:center;background:linear-gradient(135deg,#124a3f,#176c60);color:#75efbd;border-radius:16px;width:54px;height:54px;font-size:29px}
h1{margin:0;font-size:24px;letter-spacing:-.7px}small,p{color:#a7b4c7}header small{display:block;margin-top:2px}
.card{padding:22px;border:1px solid #303b4d;border-radius:21px;background:#172030;box-shadow:0 12px 40px #0003}
label{display:block;font-size:14px;font-weight:650;margin:0 0 9px}textarea,select,input[type=file]{width:100%;background:#0d1523;border:1px solid #3d4d62;border-radius:11px;color:#fff;font:inherit;outline:none}
textarea{min-height:120px;resize:vertical;padding:14px;line-height:1.5}textarea:focus,select:focus{border-color:#62dab0}
select,input[type=file]{padding:11px}input[type=file]{font-size:13px}
.options{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}
.under{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:#9aaac0;margin-top:6px}
button{width:100%;background:#62dbac;color:#0a2119;border:0;border-radius:12px;font-weight:800;font-size:17px;padding:15px;margin-top:22px;cursor:pointer}
button.secondary{background:#27384a;border:1px solid #577085;color:#dcf6eb;margin:8px 0 13px;font-size:15px}
button:disabled{opacity:.5;cursor:wait}.status{margin-top:20px;padding:14px;border-radius:12px;background:#101a2a;color:#b9c7d9;font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
.result{margin-top:20px;display:none}.result.show{display:block}audio{width:100%;margin:12px 0}
a.download{display:inline-block;text-decoration:none;color:#90f5c6;font-weight:700;padding:8px 0}
footer{text-align:center;margin:20px auto;font-size:12px;color:#8493a9;line-height:1.6}
.clone{display:none;margin-top:20px;padding:16px;border:1px solid #456a64;border-radius:15px;background:#11272c}
.clone.show{display:block}.clone p{font-size:13px;line-height:1.55;margin:0 0 13px}
.clone #refPreview{display:none}.clone .notice{font-size:12px;color:#b3c7c1}
.clone textarea{min-height:85px;font-size:15px}
.tuning-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:19px}
.tuning-grid > div{min-width:0}
.tuning-grid select{padding:11px 7px;font-size:13px;min-width:0}
.tuning-grid label{min-height:36px;margin-bottom:6px}
.quality{margin-top:0}
.priority-info{font-size:12px;line-height:1.5;color:#b1c3d5;margin:9px 0 0}
@media(max-width:325px){.tuning-grid{grid-template-columns:1fr}.tuning-grid label{min-height:0}}
.notice-quality{padding:12px;border-radius:11px;background:#2d2530;color:#f6d6aa;border:1px solid #73573a;font-size:13px;line-height:1.5;margin:9px 0 0}
.progress-area{display:none;margin-top:18px;padding:14px;background:#0e1928;border:1px solid #304258;border-radius:13px}
.progress-area.show{display:block}.progress-title{display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:14px;font-weight:650}
progress{display:block;width:100%;height:17px;accent-color:#62dbac;margin:13px 0 6px}
.progress-detail{font-size:12px;color:#b1c3d5;line-height:1.5}
.timer{font-variant-numeric:tabular-nums;color:#98f0ce;font-weight:750;white-space:nowrap}
.subheading{font-size:18px;font-weight:750;margin:0 0 10px}
#refHint{margin:3px 0 13px;min-height:20px;color:#c3ddcf;font-size:13px}
#sttInfo{margin:4px 0 12px;font-size:12px;line-height:1.5;color:#b9cfe0}
button.stt{margin:4px 0 8px;background:#254e5a;border:1px solid #5d9c9d;color:#e2fff7;font-size:14px;padding:12px}
button.stt:disabled{opacity:.65}
.translation{margin-top:19px;border:1px solid #395b61;background:#11242b;border-radius:15px;padding:15px}
.translation h2{font-size:17px;margin:0 0 12px}
.translation .translation-panel{display:none;margin-top:14px}
.translation .translation-panel.show{display:block}
.translation textarea{min-height:85px}
.translation .translation-hint,.translation .translation-status{color:#c0d6dc;font-size:12px;line-height:1.6;margin:8px 0 0}
.translation .translation-status{color:#a1ebcd}
.translation button{margin:9px 0 0;padding:10px;font-size:13px}
.translation .translation-meta{display:flex;justify-content:space-between;gap:6px;font-size:12px;color:#b8c9d3}


@media(max-width:380px){.options{grid-template-columns:1fr}.card{padding:15px}}
</style></head><body><main>
<header><div class="logo" aria-hidden="true">🐸</div><div><h1>El Clon de Pepe</h1><small>🌍 Voces, clonación y traducción local · Android</small></div></header>
<div class="card">
<label for="text">Texto para convertir en voz</label>
<textarea id="text" maxlength="180" placeholder="Escribí lo que querés que diga la voz">Hola, repetiré todo lo que escribas aquí.</textarea>
<div class="under"><span>Empezá con frases cortas: la CPU puede tardar minutos.</span><span id="count">0/180</span></div>
<div class="options"><div><label for="lang">Idioma</label><select id="lang"><option value="Spanish">Español</option><option value="English">Inglés</option><option value="Portuguese">Portugués</option><option value="French">Francés</option><option value="Italian">Italiano</option><option value="Japanese">Japonés</option><option value="Auto">Auto</option></select></div>
<div><label for="duration">Duración</label><select id="duration"><option value="auto">Automática</option><option value="2">2 segundos</option><option value="4">4 segundos</option><option value="6">6 segundos</option><option value="8">8 segundos</option></select></div></div>
<div style="margin-top:19px"><label for="mode">Tipo de voz</label><select id="mode"><option value="normal">🎙 Narrador masculino</option><option value="female">🎵 Voz femenina (experimental)</option><option value="clone">🐸 Clonar</option></select></div>
<p id="narratorHint" class="priority-info">🎙️ Prueba con atributos simples para evitar distorsión. Para relatos, elegí duración Automática y calidad Media. El resultado dependerá de OmniVoice.</p>
<div class="tuning-grid">
  <div class="quality"><label for="quality">Calidad esperada</label>
    <select id="quality"><option value="high">✨ Alta · 32 pasos</option>
    <option value="balanced" selected>⚖️ Media · 24 pasos</option>
    <option value="fast">⚡ Rápida · 16 pasos</option></select>
  </div>
  <div><label for="cpuPriority">Prioridad de CPU</label>
    <select id="cpuPriority"><option value="max">🚀 Máxima disponible</option>
    <option value="medium">⚖️ Moderada</option>
    <option value="low">🌿 Segundo plano</option></select>
  </div>
</div>
<p class="notice-quality" id="qualityNotice">⚖️ Media (24 pasos): equilibrio entre velocidad y claridad. La semejanza de voz no está garantizada y puede variar entre generaciones.</p>
<p class="priority-info" id="cpuNotice">🚀 Sin reducción de prioridad: conserva el comportamiento de antes. No supera el límite normal de Android sin root.</p>
<section class="translation" aria-label="Traducción opcional">
<h2>🌐 Traducción sin internet</h2>
<label for="translationMode">Traducir antes de generar la voz</label>
<select id="translationMode">
<option value="off" selected>🚫 No traducir (predeterminado)</option>
<option value="es-en">🇪🇸 Español → 🇬🇧 Inglés · Clásica</option>
<option value="en-es">🇬🇧 Inglés → 🇪🇸 Español · Clásica</option>
<option value="es-en-natural">✨ Español → Inglés · Natural (experimental)</option>
<option value="en-es-natural">✨ Inglés → Español · Natural (experimental)</option>
</select>
<p id="translationHint" class="translation-hint">Desactivada. OmniVoice leerá exactamente el texto que escribas, sin traducirlo.</p>
<div id="translationPanel" class="translation-panel">
<label for="translatedText">Texto traducido que dirá la voz (editable)</label>
<textarea id="translatedText" maxlength="350" placeholder="La traducción aparecerá aquí y podrás corregirla."></textarea>
<div class="translation-meta"><span id="translationCount">0 caracteres</span><span>Máximo de voz: 180</span></div>
<p id="translationStatus" class="translation-status" role="status">Seleccioná una dirección para traducir automáticamente.</p>
<button class="secondary" type="button" id="retranslate">↻ Traducir otra vez</button>
</div>
</section>
<section class="clone" id="cloneSection">
<div class="subheading">🎤 Mi voz de referencia</div>
<p>Grabá entre 5 y 10 segundos hablando claramente en un lugar tranquilo. Usá solo tu voz o una grabación con permiso. La grabación se envía únicamente a este servidor en tu teléfono.</p>
<button type="button" class="secondary" id="record">● Empezar a grabar</button>
<p id="micInfo" class="notice">Chrome puede pedir permiso para usar el micrófono. La grabación se detiene automáticamente a los 12 segundos.</p>
<label for="refFile">O elegir una grabación del teléfono (WAV, M4A, MP3, WebM…)</label>
<input type="file" id="refFile" accept="audio/*,.wav,.m4a,.mp3,.webm,.ogg,.aac,.mp4">
<div id="refHint">Todavía no hay audio seleccionado.</div>
<audio id="refPreview" controls preload="metadata"></audio>
<button type="button" class="stt" id="transcribe" disabled>↻ Reintentar transcripción</button>
<p id="sttInfo">Al terminar de grabar o subir un audio, Whisper transcribirá automáticamente si está instalado. Después podés corregir el texto.</p>
<label for="refText">Texto de referencia (podés corregirlo)</label>
<textarea id="refText" maxlength="400" placeholder="Ejemplo: Hola, esta es una prueba de mi propia voz para el estudio."></textarea>
<p class="notice" style="margin-top:8px">Comprobá y corregí la transcripción: cuanto más fiel sea a la grabación, mejor referencia tendrá la clonación. Arriba escribís la frase nueva.</p>
</section>
<button id="generate">🎙 Generar voz</button>
<div id="status" class="status" role="status" aria-live="polite">Preparado para generar. No requiere internet.</div>
<div id="progressArea" class="progress-area" aria-live="off"><div class="progress-title"><span id="progressTitle">Preparando…</span><span id="timer" class="timer">00:00</span></div>
<progress id="progressBar" max="100" aria-label="Avance de los pasos de síntesis"></progress>
<div id="progressDetail" class="progress-detail">La barra mostrará los pasos reales de síntesis. No representa el tiempo total.</div></div>
<div id="result" class="result"><label>Tu voz generada</label><audio id="player" controls preload="none"></audio><a id="download" class="download" download>↓ Descargar WAV</a></div>
</div><footer>Los audios de referencia se procesan temporalmente y no se conservan.<br>Funciona solo mientras Termux esté ejecutando este servidor en 127.0.0.1.</footer>
</main><script>
'use strict';
const $=id=>document.getElementById(id),text=$('text'),count=$('count'),btn=$('generate'),status=$('status'),result=$('result'),player=$('player'),link=$('download');
const mode=$('mode'),section=$('cloneSection'),recBtn=$('record'),file=$('refFile'),hint=$('refHint'),refText=$('refText'),preview=$('refPreview');
const transcribeBtn=$('transcribe'),sttInfo=$('sttInfo'),narratorHint=$('narratorHint');
const quality=$('quality'),qualityNotice=$('qualityNotice'),cpuPriority=$('cpuPriority'),cpuNotice=$('cpuNotice'),progressArea=$('progressArea'),progressBar=$('progressBar'),progressTitle=$('progressTitle'),progressDetail=$('progressDetail'),timer=$('timer');
const translationMode=$('translationMode'),translationPanel=$('translationPanel'),translationHint=$('translationHint'),translatedText=$('translatedText'),translationStatus=$('translationStatus'),translationCount=$('translationCount'),retranslate=$('retranslate');
const translationDirections={
'es-en':'Clásica: español → inglés. Traducción offline.',
'en-es':'Clásica: inglés → español. Traducción offline.',
'es-en-natural':'✨ Natural (Argos): español → inglés. Consume más RAM y CPU; revisá el resultado.',
'en-es-natural':'✨ Natural (Argos): inglés → español. Consume más RAM y CPU; revisá el resultado.'};
let translationAvailable=false,naturalAvailable=false, translationRequestId=0, translationTimer=null, translationKey='', translationPending=false, translationEditRevision=0;
function translationReady(){return translationMode.value.endsWith('-natural')?naturalAvailable:translationAvailable}
function translationInstallHint(){return translationMode.value.endsWith('-natural')?'⚠️ Falta Argos offline. Ejecutá /usr/bin/python3 /root/instalar_traduccion_natural_pepe.py en Ubuntu.':'⚠️ Falta Apertium: apt install apertium apertium-eng-spa'}
function originalKey(){return translationMode.value+'|'+text.value.trim()}
function updateTranslationCount(){
 translationCount.textContent=translatedText.value.length+' caracteres';
 translationCount.style.color=translatedText.value.length>180?'#ffa7a7':'';
}
translatedText.addEventListener('input',()=>{translationEditRevision++;translationKey=originalKey();updateTranslationCount();translationStatus.textContent='✏️ Traducción editada. Se utilizará este texto al generar.'});
async function runTranslation(){
 if(translationMode.value==='off'||!text.value.trim())return;
 const id=++translationRequestId,key=originalKey(),direction=translationMode.value,editRevision=translationEditRevision;
 translationPending=true;
 translationStatus.textContent='⏳ Traduciendo localmente…';
 try{
  const r=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text.value.trim(),direction})});
  const v=await r.json();
  if(id!==translationRequestId||originalKey()!==key||editRevision!==translationEditRevision)return;
  if(!r.ok){translationStatus.textContent='⚠️ '+(v.message||'No se pudo traducir.');translationKey='';return}
  translatedText.value=v.translated_text;translationKey=key;
  updateTranslationCount();
  translationStatus.textContent=v.translated_text.length>180?'⚠️ El texto supera los 180 caracteres. Acortalo antes de generar.':'✅ Traducción lista y editable. Al generar se leerá este texto.';
 }catch(e){if(id===translationRequestId){translationKey='';translationStatus.textContent='⚠️ No se pudo conectar con el traductor local.'}}
 finally{if(id===translationRequestId)translationPending=false}
}
function scheduleTranslation(delay=550){
 if(translationTimer!==null)clearTimeout(translationTimer);
 ++translationRequestId;translationPending=false;translationKey='';
 if(translationMode.value==='off')return;
 translatedText.value='';updateTranslationCount();
 if(!translationReady()){translationStatus.textContent=translationInstallHint();return}
 if(!text.value.trim()){translationStatus.textContent='Escribí primero el texto original.';return}
 translationStatus.textContent='Preparando traducción automática…';
 translationTimer=setTimeout(()=>{translationTimer=null;runTranslation()},delay);
}
translationMode.addEventListener('change',()=>{
 const on=translationMode.value!=='off';translationPanel.classList.toggle('show',on);
 translationHint.textContent=on?translationDirections[translationMode.value]:'Desactivada. OmniVoice leerá exactamente el texto que escribas, sin traducirlo.';
 scheduleTranslation(70);
});
retranslate.addEventListener('click',()=>scheduleTranslation(0));
text.addEventListener('input',()=>scheduleTranslation(800));
const qualityNotes={high:'⚠ Alta (32 pasos): es la calidad que ya conocés. Más cálculo de CPU, tiempo de espera, batería y temperatura. No garantiza mayor parecido.',balanced:'⚖️ Media (24 pasos): ahora es la predeterminada. Equilibra velocidad y calidad; los resultados pueden variar.',fast:'⚠ Rápida (16 pasos): ahorra pasos, pero puede alterar la claridad, el parecido o recortar palabras.'};
quality.addEventListener('change',()=>qualityNotice.textContent=qualityNotes[quality.value]);
const cpuNotes={
  max:'🚀 Sin reducción de prioridad: conserva la configuración anterior. Sin root no podemos subirla por encima de la prioridad heredada. Puede consumir más CPU y batería.',
  medium:'⚖️ Moderada: OmniVoice cede un poco de CPU a otras aplicaciones (nice +5). Puede tardar más.',
  low:'🌿 Segundo plano: cede más CPU a otras aplicaciones (nice +10). Puede tardar bastante más.'
};
cpuPriority.addEventListener('change',()=>cpuNotice.textContent=cpuNotes[cpuPriority.value]);
fetch('/api/capabilities',{cache:'no-store'}).then(r=>r.json()).then(c=>{
  for(const option of quality.options)if(option.value!=='high'&&!c.fast_available)option.disabled=true;
  if(!c.fast_available){
   quality.value='high';
   qualityNotice.textContent='⚠️ No se encontró el motor alternativo. Por ahora queda disponible Alta (32 pasos) hasta compilar 24/16 pasos.';
  }
  translationAvailable=!!c.translation_available;
  naturalAvailable=!!c.natural_translation_available;
  if(!translationReady() && translationMode.value!=='off')scheduleTranslation(0);

  sttAvailable=!!c.stt_available;transcribeBtn.disabled=!sttAvailable;
  if(!c.stt_available){
   sttInfo.textContent='⚠️ Para transcripción automática sin internet primero instalá Whisper local. Hasta entonces podés escribir el texto manualmente.';
  }else if((recorded||file.files[0]) && !sttActive){
   queueAutomaticStt(); // También funciona si el audio se seleccionó antes de cargar capacidades.
  }else if(!(recorded||file.files[0])){
   sttInfo.textContent='✅ Whisper instalado: al terminar de grabar o subir audio, transcribiré solo. Podés corregir el resultado.';
  }
  if(!c.nice_available){for(const option of cpuPriority.options)if(option.value!=='max')option.disabled=true;
    cpuNotice.textContent='En este Ubuntu no se encontró el comando nice: solo se puede usar la prioridad original.';}
}).catch(()=>{});
let jobState='idle', anchorSeconds=0, anchorAt=performance.now();
function fmtTime(seconds){const v=Math.max(0,Math.floor(seconds));return String(Math.floor(v/60)).padStart(2,'0')+':'+String(v%60).padStart(2,'0')}
function tick(){const elapsed=anchorSeconds+(jobState==='running'?(performance.now()-anchorAt)/1000:0);timer.textContent=fmtTime(elapsed)}
setInterval(tick,250);

let rec=null,stream=null,recorded=null,previewUrl=null,autoStop=null,recordStart=0;
const textPresets={
  normal:'Hola, repetiré todo lo que escribas aquí.',
  female:'Hola, repetiré todo lo que escribas aquí.',
  clone:'¡Hola! Soy un clon. Repetiré lo que escribas aquí.'
};
let lastPreset=textPresets.normal;
// Versionar cada grabación impide que una transcripción vieja reemplace otra.
// Whisper procesa un solo audio a la vez; las nuevas grabaciones se reintentan
// sin obligar al usuario a tocar ningún botón.
let audioVersion=0,sttVersion=-1,sttActive=false,sttAvailable=false;
let sttSubmitting=false,sttRetryTimer=null,sttUserEdited=false;
refText.addEventListener('input',()=>{sttUserEdited=true});
function resetReference(){
 audioVersion++;sttActive=false;sttVersion=-1;sttUserEdited=false;refText.value='';
 if(sttRetryTimer!==null){clearTimeout(sttRetryTimer);sttRetryTimer=null;}
 transcribeBtn.disabled=!sttAvailable;
}
function queueAutomaticStt(delay=80){
 if(!sttAvailable){
  sttInfo.textContent='⚠️ Para transcribir automáticamente hace falta Whisper instalado. También podés escribir la transcripción manualmente.';
  return;
 }
 if(!recorded&&!file.files[0])return;
 if(sttRetryTimer!==null)clearTimeout(sttRetryTimer);
 sttInfo.textContent='⏳ Transcribiendo el audio automáticamente…';
 sttRetryTimer=setTimeout(()=>{sttRetryTimer=null;startTranscription(true)},delay);
}
function autoTranscribe(){queueAutomaticStt();}

function updateCount(){count.textContent=text.value.length+'/180'}text.addEventListener('input',updateCount);updateCount();
mode.addEventListener('change',()=>{
 section.classList.toggle('show',mode.value==='clone');
 narratorHint.style.display=mode.value==='clone'?'none':'block';
 narratorHint.textContent=mode.value==='female'?'⚠️ Voz femenina experimental: se usa solo el atributo female. Probá Calidad Media y duración Automática. Si genera ruido en español, la clonación con una referencia autorizada suele ser más estable.':'🎙️ Narrador: usamos solo male para reducir combinaciones de atributos. Probá Calidad Media y duración Automática.';
 const next=textPresets[mode.value];
 if(text.value.trim()===lastPreset.trim()||text.value.trim()===''){text.value=next;updateCount();scheduleTranslation(80);}
 lastPreset=next;
});
function previewAudio(blob,label){if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(blob);preview.src=previewUrl;preview.style.display='block';hint.textContent=label+' · '+Math.ceil(blob.size/1024)+' KB';}
file.addEventListener('change',()=>{if(rec&&rec.state==='recording')rec.stop();recorded=null;resetReference();if(file.files[0]){previewAudio(file.files[0],'Audio seleccionado');autoTranscribe();}else{hint.textContent='Todavía no hay audio seleccionado.';preview.style.display='none';}});
function stopTracks(){if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}if(autoStop){clearTimeout(autoStop);autoStop=null}}
recBtn.addEventListener('click',async()=>{
 if(rec&&rec.state==='recording'){rec.stop();return}
 if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia||!window.MediaRecorder){hint.textContent='Este navegador no admite grabación: usá la aplicación Grabadora y seleccioná el archivo.';return}
 try{
  stream=await navigator.mediaDevices.getUserMedia({audio:true});
  const chunks=[];rec=new MediaRecorder(stream);recordStart=Date.now();
  rec.ondataavailable=e=>{if(e.data&&e.data.size)chunks.push(e.data)};
  rec.onstop=()=>{stopTracks();recBtn.textContent='● Grabar otra vez';if(!chunks.length){hint.textContent='La grabación salió vacía. Volvé a intentar.';return}recorded=new Blob(chunks,{type:rec.mimeType||'audio/webm'});file.value='';resetReference();previewAudio(recorded,'Grabación propia de '+Math.round((Date.now()-recordStart)/1000)+' s');autoTranscribe()};
  rec.onerror=()=>{stopTracks();recBtn.textContent='● Empezar a grabar';hint.textContent='Error al grabar. Podés elegir un archivo.'};
  rec.start();recBtn.textContent='■ Detener grabación';hint.textContent='Grabando… Leé tu frase en voz alta.';
  autoStop=setTimeout(()=>{if(rec&&rec.state==='recording')rec.stop()},12000);
 }catch(e){stopTracks();hint.textContent='No se pudo usar el micrófono. Revisá los permisos de Chrome o elegí un audio.'}
});
function showSttState(s){
 if(!sttActive||sttVersion!==audioVersion)return;
 if(s.state==='running'){
  sttInfo.textContent='⏳ '+(s.message||'Escuchando la grabación…')+' ('+fmtTime(s.elapsed_seconds||0)+')';
 }else if(s.state==='ready'){
  sttActive=false;transcribeBtn.disabled=false;
  // Nunca pisar las correcciones que el usuario escribió mientras transcribía.
  if(!sttUserEdited){
   refText.value=s.text||'';
   sttInfo.textContent='✅ Transcripción completada en '+fmtTime(s.elapsed_seconds||0)+'. Revisá y corregí el texto si es necesario.';
  }else{
   sttInfo.textContent='✅ El reconocimiento terminó, pero conservé tus correcciones manuales. Podés reintentar con el botón.';
  }
 }else if(s.state==='error'){
  sttActive=false;transcribeBtn.disabled=false;
  sttInfo.textContent='⚠️ '+(s.message||'No se pudo transcribir. Escribí el texto manualmente.');
 }
}
async function pollStt(){
 if(!sttActive)return;
 try{const r=await fetch('/api/transcribe-status',{cache:'no-store'});if(r.ok)showSttState(await r.json())}
 catch(e){sttInfo.textContent='No se pudo consultar la transcripción. Revisá Termux.'}
}
async function startTranscription(automatic=false){
 const sample=recorded||file.files[0];
 if(!sample){if(!automatic)sttInfo.textContent='Primero grabá o elegí un audio.';return}
 if(!sttAvailable){sttInfo.textContent='⚠️ Falta instalar Whisper local para transcribir. Podés completar el texto a mano.';return}
 if(sample.size>8*1024*1024){sttInfo.textContent='La grabación supera los 8 MB.';return}
 if(rec&&rec.state==='recording'){sttInfo.textContent='Detené primero la grabación.';return}
 if(sttSubmitting){if(automatic)queueAutomaticStt(1200);return}
 if(sttActive && sttVersion===audioVersion)return;
 const version=audioVersion;
 sttSubmitting=true;transcribeBtn.disabled=true;
 sttInfo.textContent='⏳ Reconociendo automáticamente las palabras…';
 try{
  const audio=await toBase64(sample);
  if(version!==audioVersion)return;
  const r=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ref_audio:audio,lang:$('lang').value})});
  const s=await r.json();
  if(version!==audioVersion)return;
  if(r.status===409 && automatic){
   // Un audio anterior puede seguir en el motor; al terminar se reintentará.
   queueAutomaticStt(1800);return;
  }
  if(!r.ok){sttInfo.textContent='⚠️ '+(s.message||'No se pudo iniciar.');return}
  sttVersion=version;sttActive=true;showSttState(s);
 }catch(e){if(version===audioVersion)sttInfo.textContent='⚠️ No pude conectar con Whisper. Podés escribir el texto a mano.'}
 finally{
  sttSubmitting=false;
  if(!sttActive)transcribeBtn.disabled=!sttAvailable;
 }
}
transcribeBtn.addEventListener('click',()=>startTranscription(false));
function updateState(s){
 status.textContent=s.message||'Procesando…';const busy=s.state==='running';btn.disabled=busy;
 btn.textContent=busy?'⏳ Generando voz…':'🎙 Generar voz';
 const previous=jobState;jobState=s.state;
 if(previous!==s.state||!busy||Math.abs((Number(s.elapsed_seconds)||0)-(anchorSeconds+(performance.now()-anchorAt)/1000))>2){
  anchorSeconds=Number(s.elapsed_seconds)||0;anchorAt=performance.now();
 }
 const visible=busy||s.state==='ready'||s.state==='error';progressArea.classList.toggle('show',visible);
 if(s.state==='ready'){
  progressBar.value=100;progressTitle.textContent='¡Generación completada!';
  progressDetail.textContent='Tiempo total: '+fmtTime(s.elapsed_seconds||0)+(s.spoken_lang?' · Idioma hablado: '+s.spoken_lang:'')+(s.spoken_text?' · Texto leído: '+s.spoken_text:'');
 }
 else if(busy && Number(s.total_steps)>0 && Number(s.step)>0){
  const step=Math.min(Number(s.step),Number(s.total_steps)),total=Number(s.total_steps);
  progressBar.value=Math.round(100*step/total);
  progressTitle.textContent='Síntesis: '+step+' / '+total+' pasos';
  let detail='Quedan '+(total-step)+' pasos en esta etapa. Progreso de pasos, no del tiempo total.';
  if(s.estimate_seconds!=null && step<total)detail+=' Restante aproximado de esta etapa: '+fmtTime(s.estimate_seconds)+'.';
  progressDetail.textContent=detail;
 } else if(busy){
  progressBar.removeAttribute('value');progressTitle.textContent=s.phase||'Cargando / preparando…';
  progressDetail.textContent='Preparando el audio o el modelo. Aún no es posible calcular cuánto falta.';
 } else if(s.state==='error'){
  progressBar.removeAttribute('value');progressTitle.textContent='Generación interrumpida';progressDetail.textContent='Tiempo transcurrido: '+fmtTime(s.elapsed_seconds||0);
 }
 tick();
 if(s.state==='ready'&&s.url&&link.dataset.current!==s.url){link.dataset.current=s.url;player.src=s.url;link.href=s.url;result.classList.add('show')}
}
async function poll(){try{const r=await fetch('/api/status',{cache:'no-store'});if(r.ok)updateState(await r.json());else status.textContent='No se pudo consultar el estado.'}catch(e){status.textContent='Sin conexión. ¿Está abierto Termux?'}}
function toBase64(blob){return new Promise((resolve,reject)=>{const rd=new FileReader();rd.onload=()=>resolve(String(rd.result).split(',')[1]||'');rd.onerror=()=>reject(new Error('No se pudo leer el archivo'));rd.readAsDataURL(blob)})}
btn.addEventListener('click',async()=>{
 const t=text.value.trim();if(!t){status.textContent='Escribí primero la frase nueva.';return}
 if(rec&&rec.state==='recording'){status.textContent='Detené primero la grabación.';return}
 const payload={text:t,lang:$('lang').value,duration:$('duration').value,mode:mode.value,quality:quality.value,cpu_priority:cpuPriority.value,translation:translationMode.value};
 if(translationMode.value!=='off'){
  if(!translationReady()){status.textContent=translationInstallHint();return}
  if(translationKey===originalKey() && translatedText.value.trim()){
   if(translatedText.value.trim().length>180){status.textContent='⚠️ Acortá el texto traducido a 180 caracteres o menos.';return}
   payload.translated_text=translatedText.value.trim();
  }
  // Si la vista previa todavía está cargando, el servidor traducirá con el motor elegido.
 }
 if(mode.value==='clone'){
  const sample=recorded||file.files[0];if(!sample){status.textContent='Grabá tu voz o seleccioná un audio de referencia.';return}
  if(sample.size>8*1024*1024){status.textContent='El audio pesa más de 8 MB. Usá una grabación corta.';return}
  payload.ref_text=refText.value.trim();if(payload.ref_text.length<3){status.textContent='Escribí exactamente lo que dijiste en la grabación.';return}
  status.textContent='Preparando tu grabación…';try{payload.ref_audio=await toBase64(sample)}catch(e){status.textContent=e.message;return}
 }
 btn.disabled=true;result.classList.remove('show');link.dataset.current='';status.textContent='Iniciando el motor…';
 try{const r=await fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const s=await r.json();updateState(s);if(!r.ok)btn.disabled=false}
 catch(e){btn.disabled=false;status.textContent='Error al conectar con el servidor.'}
});
poll();setInterval(poll,3000);setInterval(pollStt,1500);
</script></body></html>'''


def set_job(**fields):
    with lock:
        job.update(fields)


def snapshot():
    with lock:
        result = dict(job)
        if result['state'] == 'running' and _started_at is not None:
            result['elapsed_seconds'] = round(time.monotonic() - _started_at, 1)
        return result


def prepare_reference(raw_audio, transcription, folder):
    """Convierte temporalmente una grabación autorizada a WAV mono de 24 kHz."""
    source = folder / 'referencia_entrada'
    wav = folder / 'referencia.wav'
    transcript = folder / 'referencia.txt'
    source.write_bytes(raw_audio)
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(source)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
    )
    if probe.returncode != 0:
        raise ValueError('No pude leer la grabación. Probá con WAV, M4A, MP3 o WebM.')
    try:
        seconds = float(probe.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        raise ValueError('No pude calcular la duración de la grabación.') from None
    if not 2 <= seconds <= 20:
        raise ValueError(f'La grabación dura {seconds:.1f} s. Usá entre 2 y 20 segundos (ideal: 5–10).')
    run = subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
         '-i', str(source), '-vn', '-ac', '1', '-ar', '24000',
         '-c:a', 'pcm_s16le', str(wav)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90,
    )
    if run.returncode != 0 or not wav.is_file() or wav.stat().st_size <= 44:
        raise ValueError('No pude convertir el audio a WAV. Probá grabándolo otra vez.')
    transcript.write_text(transcription.strip() + '\n', encoding='utf-8')
    return wav, transcript


def available_translations():
    """Devuelve True solo si el ejecutable y los modos ida/vuelta están instalados."""
    if not APERTIUM_BIN.is_file() or not os.access(APERTIUM_BIN, os.X_OK):
        return False
    try:
        res = subprocess.run([str(APERTIUM_BIN), '-l'], capture_output=True, text=True,
                             timeout=8, errors='replace')
        return res.returncode == 0 and all(x in res.stdout for x in ('spa-eng', 'eng-spa'))
    except (OSError, subprocess.TimeoutExpired):
        return False


def natural_available():
    """El marcador solo existe luego de que el instalador validó los dos modelos."""
    return ARGOS_PYTHON.is_file() and ARGOS_READY.is_file() and os.access(ARGOS_PYTHON, os.X_OK)


def translate_natural(text, direction):
    """Invoca Argos en su propio venv. No usa APIs, cloud ni red."""
    if direction not in ('es-en-natural', 'en-es-natural'):
        raise ValueError('Dirección natural inválida.')
    if not natural_available():
        raise ValueError('Falta instalar Argos offline. Ejecutá: /usr/bin/python3 /root/instalar_traduccion_natural_pepe.py')
    src, dst = ('es', 'en') if direction == 'es-en-natural' else ('en', 'es')
    env = os.environ.copy()
    env.update(ARGOS_DEVICE_TYPE='cpu', ARGOS_INTRA_THREADS='2', ARGOS_INTER_THREADS='1')
    try:
        result = subprocess.run(
            [str(ARGOS_PYTHON), '-c', ARGOS_SCRIPT, src, dst],
            input=text.strip() + '\n', text=True, capture_output=True, timeout=180,
            env=env, errors='replace',
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Argos no pudo traducir o tardó demasiado. Probá el modo Clásico.') from exc
    if result.returncode != 0:
        raise ValueError('Argos no pudo traducir. Comprobá la instalación o elegí Clásico. ' + result.stderr.strip()[-250:])
    translated = ' '.join(result.stdout.split()).strip()
    if not translated:
        raise ValueError('Argos no devolvió texto. Probá con otra frase.')
    return translated, TRANSLATION_MODES[direction][1]


def translate_offline(text, direction):
    """Traducción local con el motor elegido, sin shell ni APIs externas."""
    if direction not in TRANSLATION_MODES or direction == 'off':
        raise ValueError('Dirección de traducción inválida.')
    if direction.endswith('-natural'):
        return translate_natural(text, direction)
    if not available_translations():
        raise ValueError('No está instalado Apertium con español e inglés. Dentro de Ubuntu ejecutá: apt update && apt install -y apertium apertium-eng-spa')
    pair, target_lang = TRANSLATION_MODES[direction]
    try:
        result = subprocess.run([str(APERTIUM_BIN), '-u', pair],
                                input=text.strip() + '\n', capture_output=True,
                                text=True, errors='replace', timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Falló el traductor offline o se agotó el tiempo.') from exc
    if result.returncode != 0:
        raise ValueError('Apertium no pudo traducir. Comprobá la instalación y probá de nuevo.')
    translated = ' '.join(result.stdout.split()).strip()
    if not translated:
        raise ValueError('Apertium no devolvió palabras. Probá con otra frase.')
    return translated, target_lang


def synthesize(text, lang, duration, mode, audio, transcription, quality, cpu_priority,
               translation, translated_text):
    global _started_at
    filename = f'voz_{int(time.time() * 1000)}.wav'
    output = OUTPUTS / filename
    # Traducción explícitamente elegida: no se ejecuta al estar desactivada.
    # Si falla la traducción, no debemos generar accidentalmente en el idioma original.
    try:
        if translation != 'off':
            set_job(phase='Traduciendo texto offline…', message='Traduciendo en el teléfono con ' + ('Argos Natural' if translation.endswith('-natural') else 'Apertium Clásico') + '…')
            target_lang = TRANSLATION_MODES[translation][1]
            if translated_text:
                spoken_text = translated_text
            else:
                spoken_text, target_lang = translate_offline(text, translation)
            if not (1 <= len(spoken_text) <= MAX_CHARS):
                raise ValueError('La traducción supera los 180 caracteres. Acortala en la vista previa y volvé a generar.')
        else:
            spoken_text, target_lang = text, lang
        set_job(spoken_text=spoken_text, spoken_lang=target_lang)
    except Exception as exc:
        set_job(state='error', message='Error de traducción: ' + str(exc), url='')
        with lock:
            if _started_at is not None:
                job['elapsed_seconds'] = round(time.monotonic() - _started_at, 1)
            _started_at = None
        return
    chosen_binary = BIN if quality == 'high' else FAST_BIN
    steps = QUALITY_STEPS[quality]
    nice_adjust = CPU_NICE_ADJUST[cpu_priority]
    cmd = [str(chosen_binary), '--model', str(MODEL), '--codec', str(CODEC), '-o', str(output)]
    if mode in ('normal', 'female'):
        cmd += ['--instruct', NARRATOR_INSTRUCT[mode]]
    if target_lang != 'Auto':
        cmd += ['--lang', target_lang]
    if duration != 'auto':
        cmd += ['--duration', duration]
    # GNU nice modifica solo el hijo; no modifica la prioridad del servidor ni
    # la de otras aplicaciones. Incrementos positivos funcionan sin root.
    if nice_adjust:
        if not NICE_BINARY:
            raise ValueError('No se encontró el comando nice en Ubuntu. Elegí Máxima disponible.')
        cmd = [NICE_BINARY, '-n', str(nice_adjust)] + cmd
    env = os.environ.copy()
    env['OMP_NUM_THREADS'] = '2'
    if quality != 'high':
        env['OV_STEPS'] = str(steps)
        env['OV_THREADS'] = env.get('OV_THREADS', '4')
    else:
        env.pop('OV_STEPS', None)
    try:
        with TemporaryDirectory(prefix='referencia_', dir=ROOT) as tmp:
            if mode == 'clone':
                set_job(state='running', phase='Preparando grabación…', message='Convirtiendo la referencia a WAV…')
                wav, txt = prepare_reference(audio, transcription, Path(tmp))
                cmd += ['--ref-wav', str(wav), '--ref-text', str(txt)]
            set_job(state='running', phase='Cargando modelos…',
                    message=('Clonando tu voz' if mode == 'clone' else 'Generando voz') +
                    f' · {steps} pasos · CPU ({cpu_priority}). No cierres Termux.')
            print('[voz] Iniciando motor: calidad', quality, '| prioridad', cpu_priority, '| nice +', nice_adjust, flush=True)
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, cwd=ROOT, env=env, text=True,
                                    bufsize=1, errors='replace')
            # Leer la salida en otro hilo: permite aplicar timeout incluso si el motor deja de responder.
            lines = Queue()
            def drain():
                try:
                    for line in proc.stdout:
                        lines.put(line)
                finally:
                    lines.put(None)
            Thread(target=drain, daemon=True).start()
            try:
                proc.stdin.write(spoken_text + '\n')
                proc.stdin.close()
            except BrokenPipeError:
                pass
            recent = deque(maxlen=40)
            last_step = 0
            first_step_at = None
            finished_output = False
            while not finished_output:
                if time.monotonic() - _started_at > 1800:
                    proc.kill()
                    proc.wait()
                    raise TimeoutError('Se superó el límite de 30 minutos.')
                try:
                    line = lines.get(timeout=0.6)
                except Empty:
                    continue
                if line is None:
                    finished_output = True
                    break
                recent.append(line)
                # Paso real informado por OmniVoice. No extrapolamos el porcentaje a la carga o el codec.
                match = re.search(r'\[MaskGIT-Step\]\s*(\d+)\s*/\s*(\d+)', line)
                if match:
                    current, total = map(int, match.groups())
                    now = time.monotonic()
                    if current <= last_step:
                        first_step_at = None  # comenzó otro fragmento
                    if first_step_at is None:
                        first_step_at = now
                    last_step = current
                    approx = None
                    if current >= 3 and total > current:
                        avg = (now - first_step_at) / (current - 1)
                        approx = round(avg * (total - current), 1)
                    set_job(phase='Sintetizando voz…', step=current, total_steps=total,
                            estimate_seconds=approx, message=f'Sintetizando: {current}/{total} pasos…')
                elif '[MaskGIT] Start:' in line:
                    last_step = 0
                    first_step_at = None
                    set_job(step=0, total_steps=0, estimate_seconds=None,
                            phase='Comenzando síntesis…', message='Modelo cargado. Comenzando los pasos de generación…')
                elif '[TTS] Decode:' in line or '[WAV] Wrote' in line:
                    set_job(step=0, total_steps=0, estimate_seconds=None,
                            phase='Decodificando y guardando WAV…', message='Los pasos terminaron; guardando el audio…')
            rc = proc.wait(timeout=10)
            if rc != 0 or not output.is_file() or output.stat().st_size <= 44:
                tail = ''.join(recent)[-1800:]
                set_job(state='error', phase='', message='No se pudo generar el audio.\n' + tail, url='')
                return
        set_job(state='ready', phase='Terminado', message='¡Voz generada! Tocá reproducir o descargá el WAV.',
                url=f'/audio/{filename}')
        print('[voz] Audio listo:', filename, flush=True)
        # Mantiene todos los WAV anteriores y borra la referencia temporal.
    except (subprocess.TimeoutExpired, TimeoutError):
        set_job(state='error', message='La generación excedió el tiempo límite de 30 minutos.', url='')
    except ValueError as exc:
        set_job(state='error', message=str(exc), url='')
    except Exception as exc:
        set_job(state='error', message=f'Error al ejecutar OmniVoice: {exc}', url='')
    finally:
        with lock:
            if _started_at is not None:
                job['elapsed_seconds'] = round(time.monotonic() - _started_at, 1)
            _started_at = None


def stt_snapshot():
    with lock:
        result = dict(stt_job)
        if result['state'] == 'running' and _stt_started_at is not None:
            result['elapsed_seconds'] = round(time.monotonic() - _stt_started_at, 1)
        return result


def stt_worker(audio, lang):
    global _stt_started_at
    try:
        with TemporaryDirectory(prefix='transcripcion_', dir=ROOT) as tmp:
            folder = Path(tmp)
            source = folder / 'entrada_audio'
            wav = folder / 'audio_16k.wav'
            out = folder / 'texto'
            source.write_bytes(audio)
            check = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                    '-of', 'default=noprint_wrappers=1:nokey=1', str(source)],
                                   capture_output=True, text=True, timeout=30)
            if check.returncode != 0:
                raise ValueError('No pude interpretar el archivo de audio.')
            try:
                seconds = float(check.stdout.strip().splitlines()[0])
            except (ValueError, IndexError):
                raise ValueError('No pude detectar la duración del audio.') from None
            if not 2 <= seconds <= 20:
                raise ValueError('Para clonar, usá una grabación de 2 a 20 segundos.')
            conv = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                                   '-y', '-i', str(source), '-vn', '-ac', '1', '-ar', '16000',
                                   '-c:a', 'pcm_s16le', str(wav)],
                                  capture_output=True, text=True, timeout=90)
            if conv.returncode != 0 or not wav.is_file():
                raise ValueError('No pude convertir el audio para la transcripción.')
            with lock:
                stt_job.update(message='Whisper está reconociendo las palabras…')
            args = [str(WHISPER_BIN), '-m', str(WHISPER_MODEL), '-f', str(wav),
                    '-l', STT_LANGUAGES[lang], '-t', '2', '-nt',
                    '-otxt', '-of', str(out)]
            result = subprocess.run(args, capture_output=True, text=True, timeout=300,
                                    cwd=WHISPER_ROOT, errors='replace')
            transcript_file = folder / 'texto.txt'
            if result.returncode != 0 or not transcript_file.is_file():
                tail = (result.stderr or result.stdout or '')[-500:]
                raise ValueError('Whisper no pudo transcribir la grabación. ' + tail)
            transcript = ' '.join(transcript_file.read_text(encoding='utf-8').split()).strip()
            if not transcript:
                raise ValueError('No se detectaron palabras claras. Probá grabar otra vez.')
            transcript = transcript[:400]
            with lock:
                stt_job.update(state='ready', message='Transcripción lista. Revisá las palabras.', text=transcript)
    except (ValueError, subprocess.TimeoutExpired) as exc:
        with lock:
            stt_job.update(state='error', message=str(exc), text='')
    except Exception as exc:
        with lock:
            stt_job.update(state='error', message='Error del transcriptor: '+str(exc), text='')
    finally:
        with lock:
            if _stt_started_at is not None:
                stt_job['elapsed_seconds'] = round(time.monotonic() - _stt_started_at, 1)
            _stt_started_at = None


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data, mime, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def json(self, code, obj):
        self.respond(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'),
                     'application/json; charset=utf-8')

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            self.respond(200, PAGE.encode('utf-8'), 'text/html; charset=utf-8')
        elif path == '/api/status':
            self.json(200, snapshot())
        elif path == '/api/transcribe-status':
            self.json(200, stt_snapshot())
        elif path == '/api/capabilities':
            self.json(200, {'fast_available': FAST_BIN.is_file() and os.access(FAST_BIN, os.X_OK),
                            'nice_available': bool(NICE_BINARY),
                            'stt_available': WHISPER_BIN.is_file() and os.access(WHISPER_BIN, os.X_OK)
                            and WHISPER_MODEL.is_file() and WHISPER_MODEL.stat().st_size > 70_000_000,
                            'translation_available': available_translations(),
                            'natural_translation_available': natural_available()})
        elif path.startswith('/audio/'):
            name = unquote(path.removeprefix('/audio/'))
            if not re.fullmatch(r'voz_[0-9]+\.wav', name):
                return self.json(404, {'error': 'Archivo no encontrado.'})
            target = OUTPUTS / name
            if not target.is_file():
                return self.json(404, {'error': 'Archivo no encontrado.'})
            self.respond(200, target.read_bytes(), 'audio/wav',
                         {'Content-Disposition': f'inline; filename="{name}"'})
        else:
            self.json(404, {'error': 'Ruta no encontrada.'})

    def do_POST(self):
        post_path = urlsplit(self.path).path
        if post_path not in ('/api/generate', '/api/transcribe', '/api/translate'):
            return self.json(404, {'error': 'Ruta no encontrada.'})
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            return self.json(403, {'message': 'Origen no autorizado.', 'state': 'error'})
        if self.headers.get_content_type() != 'application/json':
            return self.json(415, {'message': 'Formato inválido.', 'state': 'error'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 2 or size > MAX_POST_BYTES:
                return self.json(413, {'message': 'El texto o la grabación es demasiado grande.', 'state': 'error'})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Datos inválidos.')
            if post_path == '/api/translate':
                original = data.get('text', '')
                direction = data.get('direction')
                if not isinstance(original, str) or not (1 <= len(original.strip()) <= MAX_CHARS):
                    raise ValueError('Escribí entre 1 y 180 caracteres para traducir.')
                if direction not in TRANSLATION_MODES or direction == 'off':
                    raise ValueError('Seleccioná una dirección de traducción válida.')
                translated, target_lang = translate_offline(original, direction)
                return self.json(200, {'translated_text': translated, 'lang': target_lang})
            if post_path == '/api/transcribe':
                if not (WHISPER_BIN.is_file() and WHISPER_MODEL.is_file()):
                    raise ValueError('Falta instalar Whisper local. Usá instalar_transcripcion_pepe.py.')
                lang = data.get('lang', 'Spanish')
                b64 = data.get('ref_audio')
                if lang not in STT_LANGUAGES:
                    raise ValueError('Idioma inválido.')
                if not isinstance(b64, str) or len(b64) > (MAX_AUDIO_BYTES * 4 // 3 + 8):
                    raise ValueError('El audio supera 8 MB.')
                try:
                    audio = base64.b64decode(b64, validate=True)
                except (binascii.Error, ValueError):
                    raise ValueError('No se pudo leer el archivo de audio.') from None
                if not 100 <= len(audio) <= MAX_AUDIO_BYTES:
                    raise ValueError('Seleccioná un audio de hasta 8 MB.')
                global _stt_started_at
                with lock:
                    if job['state'] == 'running' or stt_job['state'] == 'running':
                        return self.json(409, {'state': 'error', 'message': 'Esperá a que termine la generación o la transcripción actual.'})
                    _stt_started_at = time.monotonic()
                    stt_job.update(state='running', message='Preparando grabación…', text='', elapsed_seconds=0)
                Thread(target=stt_worker, args=(audio, lang), daemon=True).start()
                return self.json(202, stt_snapshot())
            raw_text = data.get('text')
            if not isinstance(raw_text, str):
                raise ValueError('Escribí una frase.')
            text = raw_text.strip()
            lang = data.get('lang', 'Spanish')
            duration = data.get('duration', 'auto')
            mode = data.get('mode', 'normal')
            quality = data.get('quality', 'balanced')
            cpu_priority = data.get('cpu_priority', 'max')
            translation = data.get('translation', 'off')
            translated_text = data.get('translated_text', '')
            if not (1 <= len(text) <= MAX_CHARS):
                raise ValueError('Escribí entre 1 y 180 caracteres.')
            if lang not in LANGUAGES or duration not in DURATIONS or mode not in {'normal', 'female', 'clone'} or quality not in QUALITY_STEPS or cpu_priority not in CPU_NICE_ADJUST:
                raise ValueError('Idioma, duración, calidad o modo inválidos.')
            if translation not in TRANSLATION_MODES:
                raise ValueError('Modo de traducción inválido.')
            if translation != 'off':
                if translation.endswith('-natural'):
                    if not natural_available():
                        raise ValueError('Instalá Argos: /usr/bin/python3 /root/instalar_traduccion_natural_pepe.py')
                elif not available_translations():
                    raise ValueError('Instalá Apertium: apt install apertium apertium-eng-spa')
                if not isinstance(translated_text, str) or len(translated_text) > MAX_CHARS:
                    raise ValueError('La traducción editada debe tener un máximo de 180 caracteres.')
                translated_text = translated_text.strip()
            else:
                translated_text = ''  # No usar traducciones antiguas con el selector desactivado.
            if cpu_priority != 'max' and not NICE_BINARY:
                raise ValueError('No está instalado el comando nice en Ubuntu.')
            if quality != 'high' and not (FAST_BIN.is_file() and os.access(FAST_BIN, os.X_OK)):
                raise ValueError('El motor de 16/24 pasos aún no está instalado. Ejecutá primero el optimizador.')
            audio, transcription = b'', ''
            if mode == 'clone':
                transcription = data.get('ref_text')
                b64 = data.get('ref_audio')
                if not isinstance(transcription, str) or not (3 <= len(transcription.strip()) <= 400):
                    raise ValueError('Escribí lo que se escucha en tu grabación.')
                if not isinstance(b64, str) or len(b64) > (MAX_AUDIO_BYTES * 4 // 3 + 8):
                    raise ValueError('Seleccioná una grabación de hasta 8 MB.')
                try:
                    audio = base64.b64decode(b64, validate=True)
                except (binascii.Error, ValueError):
                    raise ValueError('El archivo de audio no se pudo leer.') from None
                if not 100 <= len(audio) <= MAX_AUDIO_BYTES:
                    raise ValueError('La grabación está vacía o supera 8 MB.')
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            return self.json(400, {'state': 'error', 'message': f'Datos inválidos: {exc}', 'url': ''})
        global _started_at
        with lock:
            if job['state'] == 'running' or stt_job['state'] == 'running':
                return self.json(409, {'state': 'error', 'message': 'Terminá primero el trabajo que ya está en curso.'})
            _started_at = time.monotonic()
            job.update(state='running', message='Preparando generación… No cierres Termux.', url='',
                       phase='Preparando…', step=0, total_steps=0, estimate_seconds=None,
                       elapsed_seconds=0, quality=quality, cpu_priority=cpu_priority,
                       spoken_text='', spoken_lang='')
        Thread(target=synthesize, args=(text, lang, duration, mode, audio, transcription,
                                        quality, cpu_priority, translation, translated_text), daemon=True).start()
        self.json(202, snapshot())

    def log_message(self, fmt, *args):
        print('[web] ' + (fmt % args), flush=True)


def main():
    missing = [str(p) for p in (BIN, MODEL, CODEC) if not p.is_file()]
    if missing:
        raise SystemExit('Faltan archivos del motor/modelo:\n' + '\n'.join(missing))
    OUTPUTS.mkdir(exist_ok=True)
    print(f'El Clon de Pepe · Traducción Clásica y Natural offline: http://127.0.0.1:{PORT}/', flush=True)
    print('Termux debe permanecer activo. Para detenerlo: Ctrl+C.', flush=True)
    try:
        ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever(poll_interval=0.2)
    except OSError as exc:
        raise SystemExit(f'No pude abrir el puerto {PORT}: {exc}. Cerrá antes el servidor anterior con Ctrl+C.')


if __name__ == '__main__':
    main()
