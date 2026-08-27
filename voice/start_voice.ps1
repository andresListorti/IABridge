# Arranca el asistente de voz local (independiente de Claude).
# Requiere que Ollama este corriendo (el servicio normal de Windows alcanza).
Set-Location $PSScriptRoot
& ".\venv\Scripts\python.exe" voice_loop.py
