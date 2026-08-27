# Arranca opencode como servidor headless en :4096, para que ia-bridge
# pueda delegarle tareas sin pagar el cold-boot en cada llamada.
opencode serve --port 4096 --hostname 127.0.0.1
