"""Convierte un retrato en un SVG ASCII monocromo que se "escribe" como una
terminal y se congela.

Por qué positivo y no negativo: el SVG dibuja tinta clara sobre fondo oscuro, así
que el brillo percibido de una celda es su densidad de tinta. Mapear claro ->
denso (`RAMP` ascendente) reproduce la foto en positivo; el mapeo inverso
convierte la piel en un hueco negro y el pelo en un halo brillante. El fondo ya
viene a 0 desde prep_photo.py, así que cae por debajo de BLACK_FLOOR y se vuelve
espacio.

Monocromo a propósito: el color por carácter es lo que hace que los retratos
ASCII se vean sucios. Un solo color + un buen ramp de densidad se lee limpio.

GitHub renderiza SVG embebidos con <img> y ejecuta sus animaciones SMIL (no
ejecuta JS). Cada fila se revela con un barrido de recorte de izquierda a
derecha más un cursor de bloque montado en el borde del barrido, escalonado de
arriba a abajo: el retrato se imprime una vez y se queda fijo.

    python3 scripts/make_ascii_svg.py [entrada.png] [salida.svg]

    STATIC=1 python3 scripts/make_ascii_svg.py   # emite el estado final, sin animación
"""
import html
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "source-prepped.png")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "assets", "daniel-ascii.svg")

COLS, ROWS = 100, 53
CELL_W, CELL_H = 8, 15
RAMP = " .`:-=+*cs#%@"   # densidad de tinta ascendente: claro -> denso
GAMMA = 1.0
BLACK_FLOOR = 0.06       # por debajo de esto la celda queda en blanco (fondo)

PAD = 20
TITLEBAR_H = 30
STATUS_H = 30
ART_W, ART_H = COLS * CELL_W, ROWS * CELL_H
CANVAS_W = ART_W + PAD * 2
CANVAS_H = TITLEBAR_H + ART_H + STATUS_H + PAD

BG, BG2 = "#0d1117", "#111722"
FRAME = "#30363d"
TITLE_TEXT = "#7d8590"
ACCENT = "#38bdf8"       # el cian del perfil
INK = "#c9d1d9"          # el único color del ascii

ROW_DUR = 0.11
STAGGER = 0.11           # == ROW_DUR -> un solo cursor barriendo hacia abajo

USER = "daniel@github"
NAME = "Kevin Daniel Aguilar Junco"
STATIC = bool(os.environ.get("STATIC"))


def ascii_rows(path: str) -> list[str]:
    """Muestrea la imagen en una rejilla COLS x ROWS de caracteres."""
    img = np.array(Image.open(path).convert("L"))
    grid = cv2.resize(img, (COLS, ROWS), interpolation=cv2.INTER_AREA)
    rows = []
    for y in range(ROWS):
        line = []
        for x in range(COLS):
            lum = pow(grid[y, x] / 255.0, GAMMA)
            if lum <= BLACK_FLOOR:
                line.append(" ")
                continue
            idx = int(lum * (len(RAMP) - 1) + 0.5)
            line.append(RAMP[max(0, min(len(RAMP) - 1, idx))])
        rows.append("".join(line))
    return rows


def build_svg(rows: list[str]) -> str:
    art_top = TITLEBAR_H + PAD * 0.35
    font_size = CELL_H * 0.86
    p: list[str] = []

    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" font-family="ui-monospace, SFMono-Regular, '
        f'Menlo, Consolas, monospace">'
    )
    p.append(
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/>'
        "</linearGradient></defs>"
    )
    p.append(f'<rect width="{CANVAS_W}" height="{CANVAS_H}" rx="12" fill="url(#bg)"/>')
    p.append(
        f'<rect x="0.5" y="0.5" width="{CANVAS_W - 1}" height="{CANVAS_H - 1}" rx="12" '
        f'fill="none" stroke="{FRAME}" stroke-width="1"/>'
    )

    # barra de título estilo macOS
    p.append(f'<line x1="0" y1="{TITLEBAR_H}" x2="{CANVAS_W}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>')
    for i, dot in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        p.append(f'<circle cx="{PAD + i * 16}" cy="{TITLEBAR_H / 2}" r="5" fill="{dot}"/>')
    p.append(
        f'<text x="{CANVAS_W / 2}" y="{TITLEBAR_H / 2 + 4}" fill="{TITLE_TEXT}" font-size="12" '
        f'text-anchor="middle">{USER}: ~$ ./portrait.sh</text>'
    )

    # un <text> por fila: un solo color -> sin marcado por carácter, archivo pequeño
    for ry, line in enumerate(rows):
        row_y = art_top + ry * CELL_H
        baseline = row_y + CELL_H * 0.74
        delay = ry * STAGGER
        text = (
            f'<text xml:space="preserve" x="{PAD}" y="{baseline:.1f}" fill="{INK}" '
            f'font-size="{font_size:.1f}" textLength="{ART_W}" '
            f'lengthAdjust="spacing">{html.escape(line)}</text>'
        )
        if STATIC:
            p.append(text)
            continue
        p.append(
            f'<clipPath id="r{ry}"><rect x="{PAD}" y="{row_y:.1f}" height="{CELL_H}" width="0">'
            f'<animate attributeName="width" from="0" to="{ART_W}" begin="{delay:.3f}s" '
            f'dur="{ROW_DUR:.2f}s" fill="freeze"/></rect></clipPath>'
        )
        p.append(f'<g clip-path="url(#r{ry})">{text}</g>')
        p.append(
            f'<rect y="{row_y + 1:.1f}" width="{CELL_W}" height="{CELL_H - 2}" fill="{INK}" '
            f'opacity="0"><animate attributeName="x" from="{PAD}" to="{PAD + ART_W}" '
            f'begin="{delay:.3f}s" dur="{ROW_DUR:.2f}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0.85" begin="{delay:.3f}s"/>'
            f'<set attributeName="opacity" to="0" begin="{delay + ROW_DUR:.3f}s"/></rect>'
        )

    # barra de estado con cursor que parpadea siempre
    line_y = TITLEBAR_H + ART_H + PAD * 0.35
    text_y = line_y + 19
    prompt = f"{USER}:~$ whoami "
    cursor_x = PAD + (len(prompt) + len(NAME) + 1) * 13 * 0.6
    p.append(f'<line x1="0" y1="{line_y:.1f}" x2="{CANVAS_W}" y2="{line_y:.1f}" stroke="{FRAME}"/>')
    p.append(
        f'<text x="{PAD}" y="{text_y:.1f}" fill="{TITLE_TEXT}" font-size="13">'
        f'{html.escape(prompt)}<tspan fill="{ACCENT}">{html.escape(NAME)}</tspan></text>'
    )
    p.append(
        f'<rect x="{cursor_x:.0f}" y="{text_y - 12:.1f}" width="8" height="14" fill="{INK}">'
        f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" '
        f'dur="1s" repeatCount="indefinite"/></rect>'
    )
    p.append("</svg>")
    return "".join(p)


def main() -> None:
    rows = ascii_rows(SRC)
    svg = build_svg(rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(svg)
    ink = sum(1 for r in rows for c in r if c != " ") / (COLS * ROWS)
    print(f"wrote {OUT} {len(svg)} bytes; {CANVAS_W}x{CANVAS_H}; ink={ink:.3f}")


if __name__ == "__main__":
    main()
