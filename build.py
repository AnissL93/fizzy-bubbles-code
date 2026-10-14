"""Build Fizzy Bubbles Code from Fuzzy Bubbles: fixed advance, glyphs centered, wide ones squeezed, coding tweaks.

usage: uv run --with fonttools build.py      (reads source/, writes FizzyBubblesCode-*.ttf)
"""
import math
import os
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.recordingPen import DecomposingRecordingPen

W, PAD = 600, 40  # advance width; minimum side bearing total for squeezed glyphs

def stroke(pen, pts, w, caps=True):
    """Polyline of width w as overlapping clockwise quads, with round joins (and round caps unless caps=False)."""
    r, c = w / 2, math.cos(math.pi / 8)
    for x, y in pts if caps else pts[1:-1]:
        pen.moveTo((x + r, y))
        for i in range(8):   # 8-segment quadratic circle, clockwise
            a, m = -math.pi / 4 * (i + 1), -math.pi / 4 * (i + 0.5)
            pen.qCurveTo((x + r / c * math.cos(m), y + r / c * math.sin(m)), (x + r * math.cos(a), y + r * math.sin(a)))
        pen.closePath()
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0); nx, ny = -(y1 - y0) / L * r, (x1 - x0) / L * r
        quad = [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(quad, quad[1:] + quad[:1]))
        if area > 0: quad.reverse()               # TrueType outer contours run clockwise
        pen.moveTo(quad[0]); [pen.lineTo(p) for p in quad[1:]]; pen.closePath()

def bezier(p0, p1, p2, p3, n=16):
    """n+1 points along a cubic curve, for stroke()."""
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d
                  for a, b, c, d in zip(p0, p1, p2, p3)) for t in (i / n for i in range(n + 1))]

def rect(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y0)); pen.lineTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.closePath()

def put(f, name, pen):
    glyf = f['glyf']
    glyf[name] = pen.glyph(); glyf[name].recalcBounds(glyf)
    f['hmtx'][name] = (W, getattr(glyf[name], 'xMin', 0))

def redraw(f, name, matrix=(1, 0, 0, 1, 0, 0), extra=None, keep=True):
    pen = TTGlyphPen(None)
    if keep: f.getGlyphSet()[name].draw(TransformPen(pen, matrix))
    if extra: extra(pen)
    put(f, name, pen)

def bounds(f, name):
    g = f['glyf'][name]; g.recalcBounds(f['glyf']); return g.xMin, g.yMin, g.xMax, g.yMax

def fit_y(f, name, y0, y1, sx=1.0):
    """Stretch a glyph vertically onto y0..y1 (and by sx around the cell centre)."""
    _, b0, _, b1 = bounds(f, name); sy = (y1 - y0) / (b1 - b0)
    redraw(f, name, (sx, 0, 0, sy, W / 2 * (1 - sx), y0 - b0 * sy))

def grow(f, name, s, sx=None, cy=None):
    """Scale by s (x by sx) around the glyph centre, then move its centre to height cy."""
    sx = s if sx is None else sx
    _, b0, _, b1 = bounds(f, name); mid = (b0 + b1) / 2; cy = mid if cy is None else cy
    redraw(f, name, (sx, 0, 0, s, W / 2 * (1 - sx), cy - mid * s))

def grow_dots(f, name, s):
    """Scale each contour by s around its own bottom centre, so dots grow without moving off the baseline."""
    rec = DecomposingRecordingPen(f.getGlyphSet()); f.getGlyphSet()[name].draw(rec)
    pen, part = TTGlyphPen(None), []
    for op in rec.value:
        part.append(op)
        if op[0] in ('closePath', 'endPath'):
            bp = BoundsPen(None); [getattr(bp, o)(*args) for o, args in part]
            x0, y0, x1, _ = bp.bounds; cx = (x0 + x1) / 2
            for o, args in part: getattr(TransformPen(pen, (s, 0, 0, s, cx * (1 - s), y0 * (1 - s))), o)(*args)
            part = []
    put(f, name, pen)

def box_glyphs(f, w):
    """Box drawing and blocks, edge to edge in the cell, so tmux/nvim/tree lines join up."""
    top, bot = f['hhea'].ascent, f['hhea'].descent
    cx, cy = W / 2, (top + bot) / 2
    edge = {'L': (0, cy), 'R': (W, cy), 'U': (cx, top), 'D': (cx, bot)}
    def arms(spec, t):
        def draw(pen):
            for a in spec:
                ex, ey = edge[a]
                if a in 'LR': rect(pen, min(ex, cx - t / 2), cy - t / 2, max(ex, cx + t / 2), cy + t / 2)
                else: rect(pen, cx - t / 2, min(ey, cy - t / 2), cx + t / 2, max(ey, cy + t / 2))
        return draw
    def round_corner(spec):
        def draw(pen):
            sx = 1 if 'R' in spec else -1; sy = 1 if 'U' in spec else -1; r = W / 4
            ox, oy = cx + sx * r, cy + sy * r
            arc = [(ox - sx * r * math.cos(t), oy - sy * r * math.sin(t)) for t in (math.pi / 2 * i / 8 for i in range(9))]
            stroke(pen, [edge['U' if sy > 0 else 'D']] + arc + [edge['R' if sx > 0 else 'L']], w, caps=False)
        return draw
    light = {0x2500: 'LR', 0x2502: 'UD', 0x250C: 'RD', 0x2510: 'LD', 0x2514: 'RU', 0x2518: 'LU', 0x251C: 'UDR',
             0x2524: 'UDL', 0x252C: 'LRD', 0x2534: 'LRU', 0x253C: 'LRUD', 0x2574: 'L', 0x2575: 'U', 0x2576: 'R', 0x2577: 'D'}
    heavy = {0x2501: 'LR', 0x2503: 'UD', 0x250F: 'RD', 0x2513: 'LD', 0x2517: 'RU', 0x251B: 'LU', 0x2523: 'UDR',
             0x252B: 'UDL', 0x2533: 'LRD', 0x253B: 'LRU', 0x254B: 'LRUD'}
    shapes = {cp: arms(s, w) for cp, s in light.items()}
    shapes |= {cp: arms(s, 2 * w) for cp, s in heavy.items()}
    shapes |= {cp: round_corner(s) for cp, s in {0x256D: 'RD', 0x256E: 'LD', 0x256F: 'LU', 0x2570: 'RU'}.items()}
    shapes |= {cp: (lambda b: lambda pen: rect(pen, *b))(b) for cp, b in {
        0x2588: (0, bot, W, top), 0x2580: (0, cy, W, top), 0x2584: (0, bot, W, cy),
        0x258C: (0, bot, cx, top), 0x2590: (cx, bot, W, top)}.items()}
    order = f.getGlyphOrder()
    for cp, draw in shapes.items():
        name = f'uni{cp:04X}'
        if name not in order: order.append(name)
        pen = TTGlyphPen(None); draw(pen); put(f, name, pen)
        for t in f['cmap'].tables:
            if t.isUnicode(): t.cmap[cp] = name
    f.setGlyphOrder(order)

def code_glyphs(f):
    """Programming tweaks so look-alike characters differ and punctuation is easy to spot."""
    cm = f.getBestCmap(); g = lambda c: cm[ord(c)]
    x0, _, x1, _ = bounds(f, g('|')); w = x1 - x0   # pen width that matches this weight
    # 0 vs O: slashed and 20 % narrower
    s = 0.8
    redraw(f, g('0'), (s, 0, 0, 1, W / 2 * (1 - s), 0), lambda p: stroke(p, [(205, 150), (395, 540)], w * 0.85))
    # l vs | vs 1 vs I: tailed l, bar from descender to ascender
    # one smooth stroke: slightly leaning stem that bends into the tail (tangents match at the join)
    l_path = bezier((285, 745), (272, 560), (250, 300), (248, 170)) + bezier((248, 170), (246, 60), (320, 5), (445, 40))[1:]
    redraw(f, g('l'), extra=lambda p: stroke(p, l_path, w), keep=False)
    fit_y(f, g('|'), -180, 800)
    # punctuation big enough to see
    for c in '.,;:': grow_dots(f, g(c), 1.5)
    # [ ] { } as tall as ( )
    _, p0, _, p1 = bounds(f, g('('))
    for c in '[]{}': fit_y(f, g(c), p0, p1)
    # operators bigger and on the + centre line, so -> <= == line up
    _, m0, _, m1 = bounds(f, g('+')); mid = (m0 + m1) / 2
    for c in '<>': grow(f, g(c), 1.25, cy=mid)
    for c in '=-': grow(f, g(c), 1.0, sx=1.35, cy=mid)
    grow(f, g('~'), 1.0, sx=1.2, cy=mid)
    # straight, upright quotes (curly ' looked like `)
    q = lambda *xs: lambda p: [stroke(p, [(x, 650), (x, 810)], w) for x in xs]
    redraw(f, g("'"), extra=q(300), keep=False)
    redraw(f, g('"'), extra=q(215, 385), keep=False)
    box_glyphs(f, w)

SLANT = 10   # italic angle in degrees; Fuzzy Bubbles has no italic, so italics are slanted uprights

def slant(f):
    """Oblique every glyph around mid x-height, so it stays in its cell; box drawing stays upright to keep tiling."""
    t, cy = math.tan(math.radians(SLANT)), f['OS/2'].sxHeight / 2
    upright = {n for cp, n in f.getBestCmap().items() if 0x2500 <= cp <= 0x259F}
    for name in f.getGlyphOrder():
        if name not in upright and f['glyf'][name].numberOfContours:
            redraw(f, name, (1, 0, t, 1, -t * cy, 0))
    f['post'].italicAngle = -SLANT
    f['hhea'].caretSlopeRise, f['hhea'].caretSlopeRun = 1000, round(1000 * t)
    f['head'].macStyle |= 2
    f['OS/2'].fsSelection = (f['OS/2'].fsSelection | 1) & ~(1 << 6)   # italic on, regular off

def build(src, dst, style):
    f = TTFont(src)
    gs, glyf, hmtx = f.getGlyphSet(), f['glyf'], f['hmtx']
    for name in f.getGlyphOrder():
        rec = DecomposingRecordingPen(gs); gs[name].draw(rec)
        g = glyf[name]
        if not rec.value:                       # empty glyph (space etc.)
            hmtx[name] = (W, 0); continue
        g.recalcBounds(glyf)
        bw = g.xMax - g.xMin
        s = min(1.0, (W - PAD) / bw) if bw else 1.0   # ponytail: plain x-squeeze, thins vertical strokes on m/w
        dx = (W - bw * s) / 2 - g.xMin * s
        pen = TTGlyphPen(None)
        rec.replay(TransformPen(pen, (s, 0, 0, 1, dx, 0)))
        glyf[name] = pen.glyph()
        glyf[name].recalcBounds(glyf)
        hmtx[name] = (W, glyf[name].xMin)
    code_glyphs(f)
    if 'Italic' in style: slant(f)
    for t in ('GPOS', 'kern', 'hdmx', 'LTSH'):   # kerning would break the grid
        if t in f: del f[t]
    for fr in f['GSUB'].table.FeatureList.FeatureRecord:   # fi/fl/ff ligatures squash two letters into one cell
        if fr.FeatureTag == 'liga': fr.Feature.LookupListIndex, fr.Feature.LookupCount = [], 0
    f['hhea'].advanceWidthMax = W
    f['post'].isFixedPitch = 1
    f['OS/2'].xAvgCharWidth = W
    f['OS/2'].panose.bProportion = 9           # monospaced
    fam, full = 'Fizzy Bubbles Code', f'Fizzy Bubbles Code {style}'
    ps = f"FizzyBubblesCode-{style.replace(' ', '')}"
    n = f['name']
    cr = n.getDebugName(0) + '; modifications Copyright 2026 AnissL93 (https://github.com/AnissL93/fizzy-bubbles-code)'
    for rec_ in list(n.names):
        if rec_.nameID in (3, 16, 17, 21, 22): n.removeNames(nameID=rec_.nameID)
    for nid, val in ((0, cr), (1, fam), (2, style), (3, ps), (4, full), (6, ps)):
        n.setName(val, nid, 3, 1, 0x409); n.setName(val, nid, 1, 0, 0)
    f.save(dst)

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    for style in ('Regular', 'Bold', 'Italic', 'Bold Italic'):
        src = 'Bold' if 'Bold' in style else 'Regular'
        build(os.path.join(here, 'source', f'FuzzyBubbles-{src}.ttf'),
              os.path.join(here, f"FizzyBubblesCode-{style.replace(' ', '')}.ttf"), style)
