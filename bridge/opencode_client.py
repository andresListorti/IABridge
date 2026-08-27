"""Cliente minimo para la API HTTP de `opencode serve` (:4096)."""

from pathlib import Path

import httpx

OPENCODE_URL = "http://127.0.0.1:4096"

# qwen2.5-coder no ejecuta tool calls reales via Ollama dentro de OpenCode
# (el modelo devuelve el JSON del tool call como texto plano en vez de
# invocarlo). qwen3 si funciona de forma confiable como agente. Verificado
# a mano el 2026-08-26 antes de fijar este default.
DEFAULT_MODEL = "qwen3:14b-32k"


async def create_session(workdir: str) -> str:
    # Si la carpeta no existe, opencode falla el prompt en silencio (fire
    # and forget: 204 igual, el error solo queda en su log interno). La
    # creamos siempre antes de arrancar la sesion.
    Path(workdir).mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{OPENCODE_URL}/session",
            params={"directory": workdir},
            json={},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def send_prompt_async(session_id: str, workdir: str, prompt: str, model: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{OPENCODE_URL}/session/{session_id}/prompt_async",
            params={"directory": workdir},
            json={
                "model": {"providerID": "ollama", "modelID": model},
                "parts": [{"type": "text", "text": prompt}],
            },
            timeout=15,
        )
        resp.raise_for_status()


async def is_running(session_id: str, workdir: str) -> bool:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{OPENCODE_URL}/session/status", params={"directory": workdir}, timeout=10
        )
        resp.raise_for_status()
        return session_id in resp.json()


async def get_summary(session_id: str, workdir: str) -> str:
    """Ultimo texto del asistente + lista de archivos tocados por tool calls."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{OPENCODE_URL}/session/{session_id}/message",
            params={"directory": workdir},
            timeout=15,
        )
        resp.raise_for_status()
        messages = resp.json()

    last_text = ""
    files_touched = []
    for msg in messages:
        if msg["info"]["role"] != "assistant":
            continue
        for part in msg["parts"]:
            if part["type"] == "text":
                last_text = part["text"]
            elif part["type"] == "tool":
                tool_name = part.get("tool", "")
                if tool_name in ("write", "edit"):
                    fp = part.get("state", {}).get("input", {}).get("filePath")
                    if fp:
                        files_touched.append(fp)

    lines = [last_text.strip()] if last_text else []
    if files_touched:
        lines.append("Archivos modificados: " + ", ".join(sorted(set(files_touched))))
    return "\n".join(lines) if lines else "(sin respuesta de texto todavia)"
