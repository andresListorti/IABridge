# Setup de IA local — resumen para Claude Code

## Hardware
- CPU: Ryzen 9 5900X
- Placa madre: ROG Crosshair VIII Dark Hero
- GPU: RTX 3060 (12 GB VRAM)
- RAM: 32 GB
- Disco F: SSD principal (Windows, programas)
- Disco G: "IAPassport" — disco externo WD My Passport 4TB (HDD mecánico), dedicado exclusivamente a modelos de IA y ComfyUI

## Ollama
- Instalado en C:\ (ruta fija del instalador, no configurable)
- Variable de entorno `OLLAMA_MODELS` seteada a `G:\modelosIA`
- Nota: si Ollama ya estaba corriendo como servicio cuando se setea la variable, no la toma — hace falta reiniciar la PC completa para que el servicio la relea
- Modelos descargados (todos en G:\modelosIA):
  - `mistral` (~4.4 GB)
  - `llama3.1` (~4.9 GB)
  - `deepseek-r1:14b` (~9 GB)
  - `qwen2.5:14b` (~9 GB)
  - `qwen2.5-coder:14b` (~9 GB) — modelo elegido para programación
  - `qwen3:14b` (~9.3 GB) — modelo elegido como agente por defecto en OpenCode
- No se descargó `qwen3-coder` porque solo existe en versión 30B MoE (no entra completo en 12GB VRAM, sería lento)

## OpenCode
- Instalado vía `ollama launch opencode` (comando disponible en la app de escritorio de Ollama, sección Apps)
- Corre en terminal (PowerShell)
- Configurado usando `qwen3:14b` como modelo, vía Ollama local (sin cuenta, sin cloud)
- Se puede cambiar de modelo dentro de la sesión (ej. a qwen2.5-coder:14b para tareas de código específicas)
- Cierre correcto: `/exit` dentro de la sesión antes de cerrar la terminal

## ComfyUI (generación de imágenes)
- Versión: `ComfyUI_windows_portable_nvidia` (release oficial GitHub, paquete portable con Python embebido)
- Instalado en: `G:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable`
- Se ejecuta con `run_nvidia_gpu.bat` dentro de esa carpeta → abre servidor local en `http://127.0.0.1:8188`
- Modelo descargado: `sd_xl_base_1.0.safetensors` (SDXL Base, ~6.5 GB) en la carpeta `ComfyUI\models\checkpoints`
- No se descargó el modelo Refiner de SDXL; en la plantilla "SDXL Simple" se reemplazó el checkpoint del Refiner por el mismo Base para evitar el error de archivo faltante
- Imágenes generadas se guardan en: `ComfyUI\output`
- Primera generación de prueba exitosa (prompt de ejemplo, ~35 segundos)

## Filosofía de uso / división de trabajo
- Ollama + OpenCode: tareas de código rápidas, privadas, o que no requieren conexión a internet — corren en background en la PC de Andres
- Claude (chat/Claude Code): razonamiento complejo, contexto amplio, revisión externa, búsqueda de información actualizada
- No hay automatización real entre Claude (chat) y el sistema local: es una decisión manual de Andres en cada tarea, sobre qué "cerebro" usar
- Pendiente/opcional: sumar una herramienta de texto a voz local para que el sistema dé respuestas habladas resumidas al terminar tareas (no imprescindible)

## Actualización 2026-08-27 — migración de G: (HDD externo) a F: (SSD)

Todo lo de arriba describe la instalación original en el disco externo G: ("IAPassport").
**Ese disco ya no se usa y fue desconectado.** Motivo: cargar un modelo de 9GB desde el
HDD mecánico tardaba 60-235 segundos; desde el SSD NVMe tarda unos segundos.

Ubicaciones nuevas (reemplazan todo lo que este documento dice que vivía en G:\):
- Modelos de Ollama: `F:\Modelos Locales` (antes `G:\ModelosIA`)
- ComfyUI: `F:\ComfyUI_windows_portable_nvidia` (antes en G:)
- Proyectos delegados a OpenCode: `F:\ProyectosIA` (antes `G:\ProyectosIA`)

Se verificó integridad byte a byte (hash SHA256 de cada blob de modelo contra su propio
nombre de archivo) antes de borrar los originales en G:. Ademas se agregaron dos
variables de entorno de rendimiento: `OLLAMA_FLASH_ATTENTION=1` y
`OLLAMA_KV_CACHE_TYPE=q8_0`.

Para el estado actual y las notas técnicas vivas del proyecto, `CLAUDE.md` es la
referencia autoritativa — este archivo queda como historia de cómo se armó todo
originalmente, no como estado actual.
