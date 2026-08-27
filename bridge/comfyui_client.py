"""Cliente minimo para la API de ComfyUI (SDXL text-to-image, checkpoint Base
usado tambien como refiner, tal como quedo configurado en la instalacion).

Encolar y consultar estan separados a proposito (no hay una funcion que
"genere y espere"): una llamada MCP remota (Claude mobile via el connector)
tiene un tiempo de espera limitado, y ComfyUI puede tardar mas de eso con
VRAM compartida con Ollama. El patron es el mismo que opencode_run_task /
opencode_job_status - encolar devuelve al toque, se consulta el resultado
despues.
"""

import uuid
from pathlib import Path

import httpx

COMFYUI_URL = "http://127.0.0.1:8188"
CHECKPOINT = "sd_xl_base_1.0.safetensors"
OUTPUT_DIR = Path(
    "F:/ComfyUI_windows_portable_nvidia/ComfyUI_windows_portable/ComfyUI/output"
)


def _build_workflow(prompt: str, negative_prompt: str, seed: int, steps: int) -> dict:
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": CHECKPOINT},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "claude",
                "images": ["8", 0],
            },
        },
    }


async def queue_image(
    prompt: str,
    negative_prompt: str = "",
    seed: int | None = None,
    steps: int = 25,
) -> dict:
    """Encola una generacion SDXL en ComfyUI y devuelve al toque (no espera
    a que termine). Devuelve {"prompt_id": "..."} o {"error": "..."}."""
    if seed is None:
        seed = int.from_bytes(uuid.uuid4().bytes[:4], "big")
    client_id = str(uuid.uuid4())
    workflow = _build_workflow(prompt, negative_prompt, seed, steps)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=15,
            )
            resp.raise_for_status()
        except httpx.ConnectError:
            return {
                "error": "No se pudo conectar a ComfyUI en 127.0.0.1:8188. "
                "Verifica que este corriendo (start_comfyui.ps1)."
            }
        except httpx.HTTPStatusError as e:
            return {"error": f"ComfyUI rechazo el workflow: {e.response.text[:500]}"}

    return {"prompt_id": resp.json()["prompt_id"]}


async def check_image(
    prompt_id: str, save_to: str | None = None, filename: str | None = None
) -> dict:
    """Consulta una sola vez si una generacion encolada con queue_image ya
    termino. Devuelve {"status": "processing"}, {"status": "done", "images":
    [...], "saved_to": "..." si aplica}, o {"error": "..."}."""
    async with httpx.AsyncClient() as client:
        try:
            hist_resp = await client.get(
                f"{COMFYUI_URL}/history/{prompt_id}", timeout=10
            )
            hist_resp.raise_for_status()
        except httpx.ConnectError:
            return {"error": "No se pudo conectar a ComfyUI en 127.0.0.1:8188."}
        hist = hist_resp.json()

    if prompt_id not in hist:
        return {"status": "processing"}

    outputs = hist[prompt_id].get("outputs", {})
    images = []
    for node_output in outputs.values():
        for img in node_output.get("images", []):
            images.append(
                f"{img['subfolder']}/{img['filename']}"
                if img.get("subfolder")
                else img["filename"]
            )

    result = {"status": "done", "images": images}
    if save_to and images:
        import shutil

        src = OUTPUT_DIR / images[0]
        dest_dir = Path(save_to)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (filename or Path(images[0]).name)
        shutil.copyfile(src, dest)
        result["saved_to"] = str(dest)
    return result
