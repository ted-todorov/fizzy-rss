from PIL import Image, ImageDraw

def make_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * 0.22)
    draw.rounded_rectangle([0, 0, size-1, size-1], radius=radius, fill='#1a1a1a')
    s = size / 180
    bolt = [
        (95*s, 18*s),
        (52*s, 100*s),
        (80*s, 100*s),
        (68*s, 162*s),
        (128*s, 80*s),
        (100*s, 80*s),
    ]
    draw.polygon(bolt, fill='#FF9500')
    return img

make_icon(180).save('agents/rss/fizzy/apple-touch-icon.png')
icon_32 = make_icon(32)
icon_32.save('agents/rss/fizzy/favicon.ico', format='ICO', sizes=[(32, 32)])
print("Icons generated")
