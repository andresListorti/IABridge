"""
Loop de voz local e independiente de Claude (Objetivo 3 del plan).

microfono -> faster-whisper (STT) -> Ollama qwen3 local (chat) -> Piper (TTS)
-> parlante.

Push-to-talk simple por consola: ENTER arranca a grabar, ENTER de nuevo corta.
No pasa por Claude Code ni por el bridge MCP: es el "metodo propio" del
agente local para hablar con Andres.
"""

import numpy as np
import sounddevice as sd
import httpx
from faster_whisper import WhisperModel
from piper import PiperVoice

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen3:14b-32k"
SAMPLE_RATE = 16000
VOICE_MODEL = "models/es_AR-daniela-high.onnx"
SYSTEM_PROMPT = (
    "Sos un asistente de voz local que le habla a Andres en espanol "
    "rioplatense. Respondes corto y directo, como en una charla hablada, "
    "sin markdown, sin listas, sin asteriscos."
)


def record_until_enter() -> np.ndarray:
    frames = []

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback
    )
    stream.start()
    input()
    stream.stop()
    stream.close()
    if not frames:
        return np.zeros(0, dtype="float32")
    return np.concatenate(frames, axis=0).flatten()


def transcribe(whisper: WhisperModel, audio: np.ndarray) -> str:
    segments, _ = whisper.transcribe(audio, language="es")
    return " ".join(seg.text.strip() for seg in segments).strip()


def ask_ollama(history: list[dict]) -> str:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": MODEL, "messages": history, "stream": False},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def speak(voice: PiperVoice, text: str) -> None:
    for chunk in voice.synthesize(text):
        sd.play(chunk.audio_float_array, chunk.sample_rate)
        sd.wait()


def main() -> None:
    print("Cargando faster-whisper (STT, CPU)...")
    # CPU a proposito: faster-whisper necesita DLLs de cuBLAS/cuDNN que no
    # estan instaladas, y la VRAM de la 3060 ya la usan Ollama y ComfyUI.
    # "medium" en CPU (Ryzen 9 5900X) tarda unos segundos por frase, aceptable.
    whisper = WhisperModel("medium", device="cpu", compute_type="int8")

    print("Cargando voz Piper (TTS)...")
    voice = PiperVoice.load(VOICE_MODEL)

    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("\nListo. ENTER para grabar, ENTER de nuevo para cortar.")
    print("Escribi 'salir' + ENTER en vez de grabar para terminar.\n")

    while True:
        cmd = input("> ")
        if cmd.strip().lower() in ("salir", "exit", "quit"):
            break
        print("Grabando... (ENTER para cortar)")
        audio = record_until_enter()
        if audio.size == 0:
            print("No se grabo nada.")
            continue
        print("Transcribiendo...")
        text = transcribe(whisper, audio)
        if not text:
            print("No se entendio nada.")
            continue
        print(f"Vos: {text}")
        history.append({"role": "user", "content": text})
        print("Pensando...")
        reply = ask_ollama(history)
        history.append({"role": "assistant", "content": reply})
        print(f"Agente: {reply}")
        speak(voice, reply)


if __name__ == "__main__":
    main()
