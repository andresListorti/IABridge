"""Registro simple de jobs delegados a OpenCode, en un JSON en disco."""

import json
import threading
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "jobs" / "registry.json"
REGISTRY_PATH.parent.mkdir(exist_ok=True)
_lock = threading.Lock()


def _load() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_job(job_id: str, prompt: str, model: str, workdir: str) -> None:
    with _lock:
        data = _load()
        data[job_id] = {
            "prompt": prompt,
            "model": model,
            "workdir": workdir,
            "status": "running",
        }
        _save(data)


def update_status(job_id: str, status: str, summary: str | None = None) -> None:
    with _lock:
        data = _load()
        if job_id in data:
            data[job_id]["status"] = status
            if summary is not None:
                data[job_id]["summary"] = summary
            _save(data)


def all_jobs() -> dict:
    with _lock:
        return _load()
