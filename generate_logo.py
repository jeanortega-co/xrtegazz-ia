from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:
    raise SystemExit(f'Pillow no está disponible: {exc}')

p = Path('static')
p.mkdir(exist_ok=True)


img = Image.new('RGBA', (1024, 1024), (0, 0, 0, 255))
d = ImageDraw.Draw(img)

img = Image.new('RGBA', (1024, 1024), (0, 0, 0, 255))
d = ImageDraw.Draw(img)

x_color = (255, 255, 255, 255)
line_width = 140

d.line((300, 300, 724, 724), fill=x_color, width=line_width)
d.line((724, 300, 300, 724), fill=x_color, width=line_width)

img_final = img.resize((512, 512), Image.Resampling.LANCZOS)
img_final.save(p / 'logo.png')

print('Icono premium generado en', p / 'logo.png')