# Arranca el servidor ia-bridge (MCP local para Ollama/OpenCode/ComfyUI).
# Uso: doble clic o ".\start_bridge.ps1" desde PowerShell.
Set-Location $PSScriptRoot
& ".\venv\Scripts\python.exe" -u server.py
