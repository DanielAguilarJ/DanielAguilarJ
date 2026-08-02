"""Prepara una foto de perfil para convertirla en ASCII limpio.

Pipeline:
  1. Aisla al sujeto. El fondo de un avatar de estudio es claro y *desaturado*
     (S <= ~15) mientras que piel, pelo y ropa pasan de S ~55; ese contraste de
     croma separa mejor que cualquier umbral de luminancia, y no necesita
     descargar modelos (rembg/u2net).
  2. Suaviza la piel con un filtro bilateral: conserva bordes (ojos, boca,
     mechones) y elimina el grano que en ASCII se ve como ruido.
  3. Estira el rango tonal del sujeto y *levanta las sombras* (`LIFT`).
     El SVG se dibuja claro sobre fondo oscuro, así que el brillo percibido de
     cada celda es su densidad de tinta: mapeamos claro -> denso para obtener un
     positivo fotográfico. Sin el lift, el pelo oscuro caería a 0 y la cabeza
     se quedaria sin silueta sobre el fondo negro.
  4. Compone al sujeto sobre NEGRO puro, de modo que el fondo cae a 0 y el ramp
     lo convierte en espacios.

Salida: assets/source-prepped.png (escala de grises), que consume
make_ascii_svg.py. Se ejecuta solo cuando cambia la foto.

    python3 scripts/prep_photo.py [entrada.jpeg] [salida.png]
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
INP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "source-photo.jpeg")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "assets", "source-prepped.png")

SCALE = 3          # sobremuestreo: la fuente es un avatar de 261px
SAT_MIN = 52       # S por debajo de esto (y claro) es fondo: los halos del
                   # fondo llegan a S~48, la piel/ropa arranca en S~64
DARK_MAX = 70      # lo muy oscuro es sujeto aunque esté desaturado
SMOOTH = 34        # sigmaColor del filtro bilateral (0 lo desactiva)
P_LO, P_HI = 2.0, 99.0   # percentiles del sujeto para el estirado tonal
LIFT = 44          # piso de gris del sujeto: mantiene visible el pelo oscuro
FEATHER = 1.0      # difuminado del borde de la máscara, en px


def subject_mask(rgb: np.ndarray) -> np.ndarray:
    """Máscara del sujeto por croma + oscuridad, limpiada morfológicamente."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    fg = ((sat >= SAT_MIN) | (gray <= DARK_MAX)).astype(np.uint8) * 255

    h, w = fg.shape
    # el avatar viene recortado en círculo: fuera del círculo nunca hay sujeto
    yy, xx = np.mgrid[0:h, 0:w]
    outside = np.sqrt((yy - h / 2) ** 2 + (xx - w / 2) ** 2) > 0.495 * h
    fg[outside] = 0

    k = max(3, (h // 100) | 1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((k * 3, k * 3), np.uint8))

    # conserva solo el componente mayor (la persona) y rellena huecos internos
    n, lab, stats, _ = cv2.connectedComponentsWithStats((fg > 127).astype(np.uint8), 8)
    if n > 1:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = np.where(lab == keep, 255, 0).astype(np.uint8)
    holes = cv2.bitwise_not(fg)
    n, lab, stats, _ = cv2.connectedComponentsWithStats((holes > 127).astype(np.uint8), 8)
    if n > 1:
        border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
        for i in range(1, n):
            if i not in border:
                fg[lab == i] = 255
    return fg


def main() -> None:
    im = Image.open(INP).convert("RGB")
    im = im.resize((im.width * SCALE, im.height * SCALE), Image.LANCZOS)
    rgb = np.array(im)

    fg = subject_mask(rgb)
    if not (fg > 127).any():
        raise SystemExit(f"no subject found in {INP}: revisa SAT_MIN/DARK_MAX")

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if SMOOTH:
        gray = cv2.bilateralFilter(gray, 0, float(SMOOTH), 9)

    g = gray.astype(np.float32)
    lo, hi = np.percentile(g[fg > 127], [P_LO, P_HI])
    g = np.clip((g - lo) / max(1.0, hi - lo), 0.0, 1.0)
    g = LIFT + g * (255.0 - LIFT)

    mask = cv2.GaussianBlur(fg.astype(np.float32) / 255.0, (0, 0), FEATHER)
    out = np.clip(g * mask, 0, 255).astype(np.uint8)   # sujeto sobre negro

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    Image.fromarray(out, mode="L").save(OUT)
    print(f"wrote {OUT} {out.shape} subject={mask.mean():.3f}")


if __name__ == "__main__":
    main()
