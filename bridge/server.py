"""
ia-bridge: servidor MCP que le da a Claude Code (y mas adelante a Claude
mobile via connector remoto) acceso a los modelos locales de Ollama.

Fase 1 del plan: solo consultas rapidas a Ollama. Corre por Streamable HTTP
en 127.0.0.1:8765 para que el mismo proceso sirva despues, sin cambios, a un
connector remoto (Fase 3).
"""

import asyncio
import os

import httpx
from mcp.server.mcpserver import MCPServer

import comfyui_client
import jobs
import opencode_client

OLLAMA_URL = "http://localhost:11434"

server = MCPServer(
    name="ia-bridge",
    instructions=(
        "Da acceso a los modelos de IA que corren localmente en la PC de "
        "Andres via Ollama (RTX 3060, modelos en F:\\Modelos Locales, SSD "
        "NVMe). Usalo para "
        "consultas rapidas a un modelo local en vez de razonar todo vos, "
        "cuando Andres pida explicitamente usar la IA local."
    ),
)


@server.tool()
async def check_status() -> str:
    """Chequea que servicios locales estan corriendo y cuanta VRAM libre
    queda en la RTX 3060 (12GB total, compartida entre Ollama y ComfyUI:
    no entran los dos con modelos grandes cargados al mismo tiempo). Usa
    esto antes de pedir una tarea pesada si algo viene fallando o
    tardando de mas."""
    lines = []

    async with httpx.AsyncClient() as client:
        try:
            await client.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            lines.append("Ollama: OK (localhost:11434)")
        except httpx.ConnectError:
            lines.append("Ollama: NO responde")

        try:
            await client.get("http://127.0.0.1:4096/session/status", timeout=5)
            lines.append("opencode serve: OK (localhost:4096)")
        except httpx.ConnectError:
            lines.append("opencode serve: NO responde (correr start_opencode_serve.ps1)")

        try:
            await client.get("http://127.0.0.1:8188/system_stats", timeout=5)
            lines.append("ComfyUI: OK (localhost:8188)")
        except httpx.ConnectError:
            lines.append("ComfyUI: NO responde (correr start_comfyui.ps1)")

    proc = await asyncio.create_subprocess_exec(
        "nvidia-smi",
        "--query-gpu=memory.used,memory.total",
        "--format=csv,noheader,nounits",
        stdout=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    try:
        used, total = (int(x.strip()) for x in out.decode().split(","))
        libre = total - used
        lines.append(f"VRAM: {used}/{total} MB usados, {libre} MB libres")
        if libre < 3000:
            lines.append(
                "AVISO: poca VRAM libre. Si vas a pedir una tarea de "
                "codigo/voz con un modelo de 14B, cerra ComfyUI primero "
                "(y viceversa) o va a andar muy lento."
            )
    except Exception:
        lines.append("VRAM: no se pudo leer nvidia-smi")

    return "\n".join(lines)


@server.tool()
async def list_models() -> str:
    """Lista los modelos de Ollama instalados localmente, con su tamano."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    lines = [
        f"- {m['name']} ({m['size'] / 1e9:.1f} GB)" for m in data.get("models", [])
    ]
    return "\n".join(lines) if lines else "No hay modelos instalados."


@server.tool()
async def ollama_ask(prompt: str, model: str = "qwen3:14b") -> str:
    """Le hace una pregunta puntual a un modelo local de Ollama y devuelve
    la respuesta completa (sincronico, no para tareas largas).

    Args:
        prompt: la pregunta o instruccion para el modelo local.
        model: nombre del modelo Ollama a usar (default qwen3:14b).
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat", json=payload, timeout=300
            )
            resp.raise_for_status()
        except httpx.ConnectError:
            return (
                "No se pudo conectar a Ollama en localhost:11434. "
                "Verifica que el servicio este corriendo."
            )
        except httpx.ReadTimeout:
            return (
                f"El modelo {model} tardo mas de 5 minutos en responder. "
                "Proba de nuevo, deberia ir mas rapido una vez cargado en VRAM."
            )
        except httpx.HTTPStatusError as e:
            return f"Ollama devolvio un error: {e.response.status_code} {e.response.text}"
        data = resp.json()
    return data.get("message", {}).get("content", "").strip()


DEFAULT_WORKDIR = "F:/ProyectosIA"


@server.tool()
async def opencode_run_task(
    prompt: str,
    workdir: str = DEFAULT_WORKDIR,
    model: str = opencode_client.DEFAULT_MODEL,
) -> str:
    """Delega una tarea de codigo completa a OpenCode + un modelo local, en
    segundo plano (no bloquea, puede tardar varios minutos). Usa
    opencode_job_status despues para ver el resultado.

    Args:
        prompt: la tarea a realizar, en lenguaje natural (ej. "creá un
            script que...", "arreglá el bug de..."). Si es un proyecto nuevo
            (una app, un sitio, etc.), pedile en el prompt que cree su propia
            subcarpeta descriptiva dentro del workdir, no que tire los
            archivos sueltos.
        workdir: carpeta de trabajo absoluta donde OpenCode va a leer/escribir
            archivos. Default "F:/ProyectosIA" — dejalo asi salvo que Andres
            pida explicitamente otra ubicacion.
        model: modelo Ollama a usar. Por defecto qwen3:14b-32k, que es el
            unico verificado como confiable ejecutando tool calls reales
            (escribir/editar archivos) via OpenCode local. qwen2.5-coder no
            ejecuta tool calls de verdad en este setup, solo los describe
            como texto.
    """
    try:
        session_id = await opencode_client.create_session(workdir)
        await opencode_client.send_prompt_async(session_id, workdir, prompt, model)
    except httpx.ConnectError:
        return (
            "No se pudo conectar a opencode serve en localhost:4096. "
            "Verifica que este corriendo (start_opencode_serve.ps1)."
        )
    jobs.add_job(session_id, prompt, model, workdir)
    return f"Tarea lanzada en segundo plano. job_id={session_id}"


@server.tool()
async def opencode_job_status(job_id: str, workdir: str = DEFAULT_WORKDIR) -> str:
    """Consulta el estado de una tarea lanzada con opencode_run_task.

    Args:
        job_id: el id devuelto por opencode_run_task.
        workdir: la misma carpeta de trabajo usada al lanzar la tarea (si no
            se especifico una distinta, fue "F:/ProyectosIA").
    """
    try:
        running = await opencode_client.is_running(job_id, workdir)
    except httpx.ConnectError:
        return "No se pudo conectar a opencode serve en localhost:4096."

    summary = await opencode_client.get_summary(job_id, workdir)
    status = "running" if running else "done"
    jobs.update_status(job_id, status, summary)
    return f"status={status}\n\n{summary}"


@server.tool()
def list_jobs() -> str:
    """Lista todas las tareas delegadas a OpenCode en esta sesion del bridge,
    con su estado conocido (puede estar desactualizado hasta que se consulte
    opencode_job_status)."""
    data = jobs.all_jobs()
    if not data:
        return "No hay tareas registradas todavia."
    lines = []
    for job_id, info in data.items():
        lines.append(
            f"- {job_id} [{info['status']}] modelo={info['model']} "
            f"workdir={info['workdir']}\n  prompt: {info['prompt'][:100]}"
        )
    return "\n".join(lines)


@server.tool()
async def comfyui_generate_image(
    prompt: str, negative_prompt: str = "", steps: int = 25
) -> str:
    """Encola una generacion de imagen con ComfyUI (SDXL, RTX 3060) y
    devuelve al toque, sin esperar (no bloquea — la generacion tarda 30s a
    varios minutos si compite por VRAM con Ollama, y una llamada remota
    desde Claude mobile no puede quedarse esperando tanto). Usa
    comfyui_job_status con el prompt_id devuelto para ver el resultado.

    Args:
        prompt: descripcion de la imagen a generar, en ingles funciona mejor.
        negative_prompt: lo que se quiere evitar en la imagen (opcional).
        steps: pasos de sampling, mas alto = mas calidad pero mas lento.
    """
    result = await comfyui_client.queue_image(prompt, negative_prompt, steps=steps)
    if "error" in result:
        return result["error"]
    return (
        f"Generacion encolada. prompt_id={result['prompt_id']} — "
        "usa comfyui_job_status para ver cuando este lista."
    )


@server.tool()
async def comfyui_job_status(
    prompt_id: str, save_to: str | None = None, filename: str | None = None
) -> str:
    """Consulta si una imagen encolada con comfyui_generate_image ya
    termino. Si todavia esta procesando, devuelve eso — hay que volver a
    consultar mas tarde, no hay que esperar en la misma llamada.

    Args:
        prompt_id: el id devuelto por comfyui_generate_image.
        save_to: si la imagen es para un proyecto de codigo (ej. el header
            de una landing page que arma OpenCode), pasa la MISMA carpeta
            del proyecto (workdir) para que la copie ahi directamente en
            cuanto este lista, en vez de moverla a mano despues.
        filename: nombre de archivo a usar en save_to (ej. "header.jpg").
    """
    result = await comfyui_client.check_image(prompt_id, save_to, filename)
    if "error" in result:
        return result["error"]
    if result["status"] == "processing":
        return "Todavia procesando, volve a consultar en un rato."
    lines = ["Lista. Imagenes en ComfyUI\\output:"]
    lines += [str(comfyui_client.OUTPUT_DIR / f) for f in result["images"]]
    if "saved_to" in result:
        lines.append(f"Copiada tambien a: {result['saved_to']}")
    return "\n".join(lines)


def main() -> None:
    token = os.environ.get("IA_BRIDGE_TOKEN")
    if not token:
        # Modo local (Fase 1/2): solo Claude Code en esta PC le habla,
        # nadie mas puede llegar a 127.0.0.1.
        server.run(transport="streamable-http", host="127.0.0.1", port=8765)
        return

    # Modo expuesto (Fase 3, via Tailscale Funnel): exige un bearer token
    # fijo en cada request, porque el puerto queda alcanzable desde internet.
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import PlainTextResponse

    from mcp.server.transport_security import TransportSecuritySettings

    FUNNEL_HOST = "escritorio-andres.tailc98581.ts.net"

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.headers.get("authorization") != f"Bearer {token}":
                return PlainTextResponse("Unauthorized", status_code=401)
            return await call_next(request)

    app = server.streamable_http_app(
        transport_security=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1:*", "localhost:*", FUNNEL_HOST],
            allowed_origins=[
                "http://127.0.0.1:*",
                "http://localhost:*",
                f"https://{FUNNEL_HOST}",
            ],
        )
    )
    app.add_middleware(BearerAuthMiddleware)
    uvicorn.run(app, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
