# Corre esto vos manualmente despues de cada reinicio de la PC, para que
# el bridge vuelva a ser alcanzable desde Claude mobile. No se automatiza
# a proposito: que algo quede expuesto a internet lo tenes que activar vos.
tailscale funnel --bg 8765
