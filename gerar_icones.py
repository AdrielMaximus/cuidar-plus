from PIL import Image, ImageDraw

def bez(p0, p1, p2, p3, n=40):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0]
        y = u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
        pts.append((x, y))
    return pts

CURVAS = [
    ((50, 82), (20, 60), (12, 42), (12, 30)),
    ((12, 30), (12, 19), (21, 12), (31, 12)),
    ((31, 12), (39, 12), (46, 16), (50, 23)),
    ((50, 23), (54, 16), (61, 12), (69, 12)),
    ((69, 12), (79, 12), (88, 19), (88, 30)),
    ((88, 30), (88, 42), (80, 60), (50, 82)),
]
CORACAO = [p for c in CURVAS for p in bez(*c)]

def icone(tam, arquivo):
    T = tam * 4
    img = Image.new("RGB", (T, T), "#2f7d6d")
    d = ImageDraw.Draw(img)
    k = T * 0.62 / 76
    f = lambda x, y: (T / 2 + (x - 50) * k, T / 2 + (y - 47) * k)
    d.polygon([f(x, y) for x, y in CORACAO], fill="white")
    for x0, y0, x1, y1 in [(45, 28, 55, 58), (35, 38, 65, 48)]:
        d.rectangle([f(x0, y0), f(x1, y1)], fill="#2f7d6d")
    img.resize((tam, tam), Image.LANCZOS).save(arquivo)

icone(192, "docs/icon-192.png")
icone(512, "docs/icon-512.png")
icone(180, "docs/apple-touch-icon.png")
print("Icones criados em docs/")