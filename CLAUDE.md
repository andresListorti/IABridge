# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Not an app — it's the infrastructure that lets Claude Code and Claude mobile command a
set of local AI services (Ollama, OpenCode, ComfyUI) running on this machine, plus a
standalone voice assistant. Hardware: Ryzen 9 5900X, RTX 3060 (12GB VRAM), 32GB RAM.

Models and image-gen live on `F:\` (NVMe SSD — `F:\Modelos Locales` for Ollama,
`F:\ComfyUI_windows_portable_nvidia` for ComfyUI, `F:\ProyectosIA` for delegated
OpenCode work). **They used to live on an external HDD (`G:\`, "IAPassport") — migrated
to the SSD on 2026-08-27 because loading a 9GB model from the mechanical HDD took
60-235s, against ~2-5s from NVMe.** The `G:` disk is no longer used by anything in this
stack and was disconnected after the migration; if you see a stray reference to `G:\`
anywhere, it's stale — fix it, don't follow it. Background on the original setup (now
historical, paths in it point at the old `G:` layout): `resumen_setup_ia_local.md`.

## Layout

- `bridge/` — the MCP server (`server.py`) that exposes the local stack as tools to
  Claude Code (local, stdio-less HTTP) and Claude mobile (remote, via Tailscale Funnel).
  Own venv at `bridge/venv`.
  - `opencode_client.py` — talks to `opencode serve`'s HTTP API (session create /
    prompt_async / status / messages).
  - `comfyui_client.py` — talks to ComfyUI's `/prompt` + `/history` API, builds the
    SDXL text2img workflow graph inline (no saved workflow file exists).
  - `jobs.py` — flat-file job registry at `bridge/jobs/registry.json` (no DB).
- `voice/` — standalone push-to-talk voice loop (`voice_loop.py`), independent of
  Claude entirely: mic → faster-whisper (STT, CPU) → Ollama chat → Piper (TTS,
  `es_AR-daniela-high` voice). Own venv at `voice/venv`.

## Running it

Nothing in this stack auto-starts except Ollama and (since the last session) ComfyUI,
`opencode serve`, and the bridge — those launch from the Windows Startup folder via
`bridge/startup_all.ps1`. **Tailscale Funnel is deliberately excluded from autostart**
(exposing a port to the internet should be a human action each time, not silent on
boot) — run `bridge/reactivar_funnel.ps1` manually after each reboot.

Manual start (e.g. after code changes, since nothing hot-reloads):
```
cd F:\Ollama\bridge
.\start_all.ps1          # opens opencode serve, ComfyUI, and the bridge in 3 windows
```
Individually: `start_opencode_serve.ps1` (:4096), `start_comfyui.ps1` (:8188),
`start_bridge.ps1` (:8765). Voice: `cd F:\Ollama\voice; .\start_voice.ps1`.

Restart the bridge after editing `server.py`/`opencode_client.py`/`comfyui_client.py`/
`jobs.py` — kill whatever holds :8765 and relaunch:
```
PID=$(netstat -ano | grep ":8765" | grep LISTENING | awk '{print $5}' | head -1)
powershell -Command "Stop-Process -Id $PID -Force"
cd /f/Ollama/bridge && ./venv/Scripts/python.exe -u server.py > server.log 2>&1 &
```
Always run with `-u` (unbuffered) — buffered stdout redirected to a file makes the log
lag far behind reality, which cost real debugging time once already.

Smoke-testing a tool change without a real MCP client: POST to `/mcp` with
`Content-Type: application/json` + `Accept: application/json, text/event-stream`,
`initialize` → `notifications/initialized` → `tools/call`, reusing the
`mcp-session-id` response header across calls. Add `Authorization: Bearer $IA_BRIDGE_TOKEN`
if the bridge is running in exposed mode.

## Architecture facts that aren't obvious from one file

**Local vs. exposed mode is one code path, picked by an env var.** No
`IA_BRIDGE_TOKEN` in the environment → `server.py` binds streamable-http on
`127.0.0.1:8765`, no auth (this is the normal mode for Claude Code on this machine).
`IA_BRIDGE_TOKEN` set → same port, same bind address (127.0.0.1 — Tailscale Funnel
proxies to it locally, so it never needs 0.0.0.0), but wrapped in a Starlette
`BearerAuthMiddleware` requiring `Authorization: Bearer <token>` on every request, plus
`TransportSecuritySettings.allowed_hosts` extended with the Funnel's `.ts.net` hostname
(hardcoded as `FUNNEL_HOST` in `server.py` — MCP's DNS-rebinding protection otherwise
rejects any Host header that isn't localhost). The token is persisted as a user env var
(`setx IA_BRIDGE_TOKEN ...`), so `start_bridge.ps1` picks exposed mode automatically in
any new shell.

**qwen3:14b is the only model verified to execute real tool calls through
OpenCode+Ollama.** qwen2.5-coder:14b — despite being "the coding model" — returns the
tool call as a JSON *text* blob instead of invoking it, so files never get written.
This is a known unresolved upstream issue (Ollama's OpenAI-compat tool-calling layer),
not a config bug here. `opencode_client.DEFAULT_MODEL` is pinned to `qwen3:14b-32k`
accordingly — don't switch it back to a coder model without re-verifying tool calls
actually fire (create a throwaway file and check it exists, don't trust the response
text alone).

**Ollama's default 4K context silently breaks OpenCode's tool schema.** `qwen3:14b-32k`
and `qwen2.5-coder:14b-32k` are `ollama create` variants (Modelfiles in `bridge/`) with
`num_ctx 32768` layered on the same weights (no extra disk, just a new manifest) —
`opencode.jsonc`'s `ollama` provider entry points at the `-32k` tags, not the bare ones.

**OpenCode fails a `prompt_async` silently (fire-and-forget 204, error only in
opencode's own log) if the working directory doesn't exist yet.**
`opencode_client.create_session` now does `Path(workdir).mkdir(parents=True,
exist_ok=True)` before creating the session — this is load-bearing, not decorative;
removing it reintroduces jobs that vanish with no error surfaced to the caller.

**The RTX 3060's 12GB VRAM is the real bottleneck**, not compute. ComfyUI (SDXL, ~9GB)
and a loaded 14B Ollama model (~9-10GB) don't both fit — whichever loads second is
starved and everything gets very slow rather than erroring cleanly. The `check_status`
tool reports free VRAM and warns under 3GB; use it before delegating combined
code+image work. `OLLAMA_KEEP_ALIVE` is set to `30m` (persisted user env var, default
is 5m) to reduce how often a 9GB model has to reload — even from the SSD that's a
couple seconds, but it adds up across an agentic loop's many turns — but a longer
keep-alive also means it holds VRAM longer between uses, worsening the ComfyUI
conflict. There's no auto-arbitration between the two; it's manual.

Also persisted as user env vars (set 2026-08-27, alongside the SSD migration):
`OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` — both reduce VRAM pressure
from the KV cache, freeing up headroom for the Ollama/ComfyUI conflict above. Neither
had a measured downside when applied; if a future model behaves oddly, these are the
first thing to suspect and temporarily unset.

**`comfyui_generate_image` is fire-and-forget, same pattern as `opencode_run_task`** —
it queues the SDXL generation and returns a `prompt_id` immediately, it does not wait
for the image. Call `comfyui_job_status(prompt_id)` afterwards to check. This was a
deliberate fix on 2026-08-27: the previous version blocked for up to 6 minutes inside
one tool call, and a real request from Claude mobile through the Funnel connector got
cut off mid-task ("dejo cosas sin hacer") because ComfyUI was contending for VRAM with
Ollama and took longer than the remote caller was willing to wait. Never make it
synchronous again — any tool a remote MCP client calls needs to return fast, full stop.
`comfyui_job_status` takes `save_to` + `filename` to copy the finished image straight
into a project folder (e.g. `header.jpg` for a landing page OpenCode is building) once
it's ready, instead of a separate manual copy step.

**`opencode_run_task`/`opencode_job_status` default `workdir` to `F:/ProyectosIA`** —
a dedicated folder, not the root of `F:` or any system folder — specifically so a vague
mobile request ("build me an app") can't land somewhere it shouldn't. Claude is still
free to pass an explicit `workdir` elsewhere; the default is a safety net, not a hard
boundary. (Before the 2026-08-27 migration this pointed at `G:/ProyectosIA` on the
external HDD — the safety motivation was also "don't touch the SSD" back then; that
half of the reasoning no longer applies since everything lives on the SSD now, but the
"give it a dedicated folder, not a root" part still does.)

**`opencode session/status` is keyed by the exact `directory` string passed in the
query param** — querying with a different slash style or a different (but
equivalent-looking) path than the one the session was created with returns an empty
map, which looks identical to "job finished." When debugging a job that seems to
vanish, re-check the `workdir` recorded for that job in `bridge/jobs/registry.json`
before concluding it's done.

**Live-watching a running job**: `opencode attach http://localhost:4096 --session
<id> --dir <workdir>` attaches to the same `opencode serve` instance the bridge talks
to, showing reasoning/tool-call activity in real time — it needs both the session id
(only exists once the job is launched) and the exact `workdir` used to launch it.

**Restarting the bridge sometimes leaves a stale duplicate `server.py` process** — two
PIDs both showing as listening candidates, but only one actually holds port 8765.
Twice in one session, killing what looked like the orphan (the one *not* shown by
`netstat -ano | grep 8765` at that instant) took the real one down with it — the
listener seems to hand off between the two briefly on restart, so a netstat snapshot
right before the kill isn't reliable. Safer sequence: kill by the PID netstat shows
*right before* you kill it, then immediately re-check `netstat` — if nothing's
listening, just relaunch `start_bridge.ps1` again rather than trying to diagnose which
of the two survived.
