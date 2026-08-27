# Arranca los 3 servicios locales en ventanas separadas: Ollama (si no esta
# corriendo ya como servicio), opencode serve, ComfyUI, y el bridge MCP.
# Cerrar cualquiera de las ventanas apaga esa pieza.
$here = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$here'; .\start_opencode_serve.ps1" -WindowStyle Normal
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$here'; .\start_comfyui.ps1" -WindowStyle Normal
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$here'; .\start_bridge.ps1" -WindowStyle Normal

Write-Host "Arrancando opencode serve, ComfyUI y ia-bridge en ventanas separadas."
Write-Host "ComfyUI tarda 1-2 minutos en quedar listo la primera vez."
