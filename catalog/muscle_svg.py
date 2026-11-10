import json
import re
from functools import lru_cache
from xml.etree import ElementTree as ET

from django.conf import settings

_STYLE_RE = re.compile(r'<style[^>]*>(.*?)</style>', re.S)
_CLASS_COLOR_RE = re.compile(r'\.(st\d+)\{[^}]*fill:(#[0-9A-Fa-f]{6})[^}]*\}')

MUSCLE_DIR = settings.BASE_DIR / 'static' / 'img' / 'muscles'


def _local(tag):
    return tag.split('}')[-1]


def _is_reddish(hex_color):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return r > 140 and r - g > 30 and r - b > 30


def _to_gray(hex_color):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    lum = round(0.299 * r + 0.587 * g + 0.114 * b)
    return f'#{lum:02x}{lum:02x}{lum:02x}'


@lru_cache(maxsize=4)
def _view_data(view):
    svg_path = MUSCLE_DIR / view / '_base.svg'
    content = svg_path.read_text(encoding='utf-8')
    style_match = _STYLE_RE.search(content)
    colors = dict(_CLASS_COLOR_RE.findall(style_match.group(1)))

    root = ET.parse(svg_path).getroot()
    outline_paths = []
    classed_paths = []
    for el in root.iter():
        if _local(el.tag) != 'path':
            continue
        d = el.get('d')
        if not d:
            continue
        cls = el.get('class')
        if cls and cls in colors:
            classed_paths.append((cls, d))
        else:
            outline_paths.append(d)

    gray_rules = ''.join(
        f'.{view}-g-{cls}{{fill:{_to_gray(color) if _is_reddish(color) else color};}}'
        for cls, color in colors.items()
    )
    native_rules = ''.join(f'.{view}-n-{cls}{{fill:{color};}}' for cls, color in colors.items())
    return tuple(outline_paths), tuple(classed_paths), gray_rules + native_rules


@lru_cache(maxsize=4)
def _muscle_paths(view):
    return json.loads((MUSCLE_DIR / view / 'paths.json').read_text(encoding='utf-8'))


def render_body_map(view, muscle_names):
    outline_paths, base_paths, style_rules = _view_data(view)
    outline_tags = ''.join(f'<path d="{d}"/>' for d in outline_paths)
    base_tags = ''.join(f'<path class="{view}-g-{cls}" d="{d}"/>' for cls, d in base_paths)

    muscle_paths = _muscle_paths(view)
    highlight_tags = []
    for name in muscle_names:
        for cls, d in muscle_paths.get(name, []):
            highlight_tags.append(f'<path class="{view}-n-{cls}" d="{d}"/>')

    layers = [
        f'<style>{style_rules}</style>',
        f'<g class="body-map-outline">{outline_tags}</g>',
        f'<g>{base_tags}</g>',
    ]
    if highlight_tags:
        layers.append(f'<g>{"".join(highlight_tags)}</g>')

    return (
        '<svg viewBox="0 0 432 648" class="body-map-svg" xmlns="http://www.w3.org/2000/svg">'
        + ''.join(layers)
        + '</svg>'
    )
