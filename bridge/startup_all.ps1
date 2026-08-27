# Arranca automaticamente al iniciar sesion de Windows: ComfyUI, opencode
# serve, y el bridge MCP. Ollama arranca solo (su propio instalador ya lo
# deja en el inicio de Windows). Tailscale Funnel NO se arranca aca a
# proposito -- correlo vos con reactivar_funnel.ps1 despues de loguearte.

Start-Sleep -Seconds 15  # darle tiempo a Windows a terminar de iniciar sesion

$bridge = "F:\Ollama\bridge"
$voice = "F:\Ollama\voice"

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$bridge'; .\start_opencode_serve.ps1" -WindowStyle Minimized
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$bridge'; .\start_comfyui.ps1" -WindowStyle Minimized
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$bridge'; .\start_bridge.ps1" -WindowStyle Minimized
