from PIL import Image

img = Image.open("raton.png").convert("RGBA")

# Crear múltiples tamaños dentro del .ico
img.save(
    "raton.ico",
    format="ICO",
    sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]
)