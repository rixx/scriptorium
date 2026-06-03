import colorsys
import re

from coloraide import Color
from PIL import Image

from scriptorium.main.utils import (
    UI_LIGHTNESS,
    get_dominant_colours,
    get_spine_color,
    get_ui_color,
)


def _make_striped_image(path, colors):
    """Paint horizontal stripes of the given RGB colors into a 100x100 image.

    100x100 means the resize inside `get_dominant_colours` is a no-op and
    boundary blending can't pollute the clusters."""
    im = Image.new("RGB", (100, 100))
    stripe_height = 100 // len(colors)
    pixels = []
    for i, color in enumerate(colors):
        is_last = i == len(colors) - 1
        height = 100 - stripe_height * i if is_last else stripe_height
        pixels.extend([color] * (100 * height))
    im.putdata(pixels)
    im.save(path)


class _FakeCover:
    """Duck-typed stand-in for an ImageField — get_spine_color only reads .path."""

    def __init__(self, path):
        self.path = str(path)


def test_get_dominant_colours_recovers_pure_primaries(tmp_path):
    path = tmp_path / "cover.png"
    _make_striped_image(path, [(255, 0, 0), (0, 255, 0), (0, 0, 255)])

    colors = get_dominant_colours(str(path), count=3)
    rounded = {tuple(round(v, 2) for v in c) for c in colors}

    assert rounded == {(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)}


def test_get_dominant_colours_crop_left_ignores_the_right_side(tmp_path):
    """With crop_left set, only the left strip feeds the clustering, so a colour
    confined to the right of the cover never shows up as dominant."""
    path = tmp_path / "cover.png"
    im = Image.new("RGB", (100, 100))
    # Left 30%: blue over green. Right 70%: solid red.
    im.paste((0, 0, 255), (0, 0, 30, 50))
    im.paste((0, 255, 0), (0, 50, 30, 100))
    im.paste((255, 0, 0), (30, 0, 100, 100))
    im.save(path)

    colors = get_dominant_colours(str(path), count=2, crop_left=0.3)
    rounded = {tuple(round(v, 2) for v in c) for c in colors}

    assert rounded == {(0.0, 0.0, 1.0), (0.0, 1.0, 0.0)}  # only the left strip


def test_get_dominant_colours_crop_top_drops_edge_bands(tmp_path):
    """crop_top trims top and bottom, so thin edge banners (e.g. a publisher
    note) are excluded and only the central body colour survives."""
    path = tmp_path / "cover.png"
    im = Image.new("RGB", (100, 100))
    im.paste((255, 0, 0), (0, 0, 100, 8))  # top banner
    im.paste((0, 0, 255), (0, 8, 100, 92))  # body
    im.paste((0, 255, 0), (0, 92, 100, 100))  # bottom banner
    im.save(path)

    colors = get_dominant_colours(str(path), count=1, crop_top=0.1)
    r, g, b = colors[0]

    # only the central blue body remains
    assert b > r
    assert b > g


def test_get_dominant_colours_returns_requested_count(tmp_path):
    path = tmp_path / "cover.png"
    _make_striped_image(
        path, [(10, 20, 30), (200, 100, 50), (40, 180, 90), (220, 220, 220)]
    )

    colors = get_dominant_colours(str(path), count=4)

    assert len(colors) == 4
    for r, g, b in colors:
        assert 0 <= r <= 1
        assert 0 <= g <= 1
        assert 0 <= b <= 1


def test_get_spine_color_returns_hex_string(tmp_path):
    path = tmp_path / "cover.png"
    _make_striped_image(path, [(200, 50, 50), (180, 180, 180), (30, 30, 120)])

    color = get_spine_color(_FakeCover(path))

    assert re.fullmatch(r"#[0-9a-f]{6}", color)


def test_get_spine_color_picks_most_saturated_candidate(tmp_path):
    """Among the dominant colours, the one with the highest v*s product wins.

    Near-white has saturation ~0, near-black has brightness ~0, so the vivid
    red is the only cluster with a non-trivial product and must be chosen."""
    path = tmp_path / "cover.png"
    _make_striped_image(path, [(250, 250, 250), (5, 5, 5), (220, 20, 20)])

    color = get_spine_color(_FakeCover(path), cluster_count=3)

    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    _, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    assert saturation > 0.8
    assert value > 0.7
    assert r > g
    assert r > b


def test_get_ui_color_equalises_to_target_lightness(tmp_path):
    """A vivid cover yields a hex accent pinned to the OKLCH target lightness,
    so accents from different covers read at equal perceived strength."""
    path = tmp_path / "cover.png"
    _make_striped_image(path, [(200, 50, 50), (180, 180, 180), (30, 30, 120)])

    color = get_ui_color(_FakeCover(path))

    assert re.fullmatch(r"#[0-9a-f]{6}", color)
    assert abs(Color(color).convert("oklch")["lightness"] - UI_LIGHTNESS) < 0.02


def test_get_ui_color_preserves_hue_of_chromatic_cluster(tmp_path):
    """The accent keeps the hue of the most colourful cluster (here, blue),
    even though that cluster is neither the lightest nor the darkest."""
    path = tmp_path / "cover.png"
    _make_striped_image(path, [(245, 245, 245), (120, 120, 120), (20, 40, 200)])

    color = get_ui_color(_FakeCover(path))

    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    assert b > r
    assert b > g


def test_get_ui_color_is_neutral_grey_for_greyscale(tmp_path):
    """A greyscale cover has no usable hue, so the accent is a near-neutral grey
    at the target lightness rather than a tinted (or jarring) colour."""
    path = tmp_path / "cover.png"
    _make_striped_image(path, [(20, 20, 20), (128, 128, 128), (230, 230, 230)])

    color = get_ui_color(_FakeCover(path))

    oklch = Color(color).convert("oklch")
    assert abs(oklch["lightness"] - UI_LIGHTNESS) < 0.02
    assert oklch["chroma"] < 0.02  # essentially no hue
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    assert max(r, g, b) - min(r, g, b) < 6  # visually grey
