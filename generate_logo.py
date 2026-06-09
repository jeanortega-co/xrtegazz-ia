from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:
    raise SystemExit(f'Pillow no está disponible: {exc}')

p = Path('static')
p.mkdir(exist_ok=True)

img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

for i in range(0, 256, 18):
    alpha = 255 if i < 128 else 180
    d.rounded_rectangle([i, 0, 512 - i, 512], radius=40, fill=(255, 51, 51, alpha))

# Glow and center mark
# d.ellipse((70, 70, 442, 442), fill=(255, 255, 255, 20), outline=(255, 255, 255, 35), width=10)
# d.text((256, 256), 'X', fill=(255, 255, 255, 240), anchor='mm', font=font)

# Simple centered icon mark
for r in range(12, 0, -2):
    d.ellipse((256 - r * 16, 256 - r * 16, 256 + r * 16, 256 + r * 16), outline=(255, 255, 255, 35), width=2)

# center X-like shape
line_color = (255, 255, 255, 245)
d.line((160, 160, 352, 352), fill=line_color, width=18)
d.line((352, 160, 160, 352), fill=line_color, width=18)

img.save(p / 'logo.png')
print('Icono generado en', p / 'logo.png')
