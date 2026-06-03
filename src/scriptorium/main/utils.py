import colorsys
import re

import numpy as np
from coloraide import Color
from PIL import Image
from sklearn.cluster import KMeans
from unidecode import unidecode

# Equalised UI accent targets, in OKLCH. Every cover contributes only its hue;
# lightness and chroma are pinned so accents read consistently on the white
# background.
UI_LIGHTNESS = 0.55
UI_CHROMA = 0.15
# Covers whose most colourful cluster is below this OKLCH chroma are treated as
# greyscale: there is no meaningful hue to tint with, so fall back to a neutral
# grey at the same target lightness as the tinted accents (set in get_ui_color).
UI_MIN_CHROMA = 0.04
# The spine is rendered down the left edge of the cover, so sample the spine
# colour from just that strip rather than the whole cover.
SPINE_CROP = 0.20
# Trim this fraction off the top and bottom before sampling (spine and UI), so
# publisher banners and edition notes near the edges don't leak into the colour.
CROP_VERTICAL = 0.05

# sRGB (D65) <-> CIELAB, vectorised over an (N, 3) array of values in [0, 1].
_XYZ_FROM_RGB = np.array(
    [
        [0.41239080, 0.35758434, 0.18048079],
        [0.21263901, 0.71516868, 0.07219232],
        [0.01933082, 0.11919478, 0.95053215],
    ]
)
_RGB_FROM_XYZ = np.linalg.inv(_XYZ_FROM_RGB)
_D65 = np.array([0.95047, 1.0, 1.08883])
_LAB_EPS = 216 / 24389
_LAB_KAPPA = 24389 / 27


def slugify(text):
    """Convert Unicode string into blog slug.

    Can't use Django's for backwards compatibility – this one turns
    j.k. r into j-k-r, Django's turns it into jk-r."""
    text = re.sub("[–—/:;,.]", "-", text)  # replace separating punctuation
    ascii_text = unidecode(text).lower()  # best ASCII substitutions, lowercased
    ascii_text = re.sub(r"[^a-z0-9 -]", "", ascii_text)  # delete any other characters
    ascii_text = ascii_text.replace(" ", "-")  # spaces to hyphens
    return re.sub(r"-+", "-", ascii_text)  # condense repeated hyphens


def _srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def _rgb_to_lab(rgb):
    xyz = (_srgb_to_linear(rgb) @ _XYZ_FROM_RGB.T) / _D65
    f = np.where(xyz > _LAB_EPS, np.cbrt(xyz), (_LAB_KAPPA * xyz + 16) / 116)
    return np.stack(
        [116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])],
        axis=1,
    )


def _lab_to_rgb(lab):
    fy = (lab[:, 0] + 16) / 116
    fx = fy + lab[:, 1] / 500
    fz = fy - lab[:, 2] / 200
    f = np.stack([fx, fy, fz], axis=1)
    f3 = f**3
    xyz = np.where(f3 > _LAB_EPS, f3, (116 * f - 16) / _LAB_KAPPA) * _D65
    return _linear_to_srgb(xyz @ _RGB_FROM_XYZ.T)


def get_dominant_colours(path, count, crop_left=None, crop_top=None):
    im = Image.open(path)

    # Optionally restrict the sampled region: the left strip (where the spine is
    # drawn) and/or a margin off the top and bottom (to drop edge banners), so
    # the colour is sampled from the region it actually represents.
    if crop_left or crop_top:
        right = max(1, round(im.width * crop_left)) if crop_left else im.width
        top = round(im.height * crop_top) if crop_top else 0
        im = im.crop((0, top, right, im.height - top))

    # Resizing means less pixels to handle, so the *k*-means clustering converges
    # faster.  Small details are lost, but the main details will be preserved.
    im = im.resize((100, 100))

    # Ensure the image is RGB, and use RGB values in [0, 1] for consistency
    # with operations elsewhere.
    im = im.convert("RGB")
    rgb = np.asarray(im, dtype=float).reshape(-1, 3) / 255

    # Cluster in CIELAB so the grouping follows *perceived* colour difference
    # rather than raw RGB distance, then map the centres back to RGB.
    centres = KMeans(n_clusters=count, n_init="auto").fit(_rgb_to_lab(rgb))
    return _lab_to_rgb(centres.cluster_centers_)


def get_spine_color(cover, cluster_count=3):
    """The faithful cover colour, used for spines, edges and card borders.

    Sampled from the left strip of the cover (where the spine is shown), it
    picks the most colourful dominant cluster (highest HSV value*saturation)
    and renders it as-is, so the result stays close to the actual cover."""
    dominant_colors = get_dominant_colours(
        cover.path, count=cluster_count, crop_left=SPINE_CROP, crop_top=CROP_VERTICAL
    )
    hsv_candidates = {
        tuple(rgb_col): colorsys.rgb_to_hsv(*rgb_col) for rgb_col in dominant_colors
    }

    candidates_by_brightness_diff = {
        rgb_col: abs(hsv_col[2] * hsv_col[1])
        for rgb_col, hsv_col in hsv_candidates.items()
    }

    rgb_choice, _ = max(candidates_by_brightness_diff.items(), key=lambda t: t[1])
    r, g, b = (int(v * 255) for v in rgb_choice)
    return f"#{r:02x}{g:02x}{b:02x}"


def get_ui_color(cover, cluster_count=3):
    """An equalised accent colour for UI highlights (links, drop caps, graph).

    Takes the most chromatic dominant cluster, keeps only its hue, and pins
    lightness and chroma to fixed OKLCH targets before gamut-mapping back to
    sRGB. Every book therefore contributes an accent of equal perceived
    strength on the white background. Greyscale covers have no usable hue and
    fall back to a neutral."""
    dominant_colors = get_dominant_colours(
        cover.path, count=cluster_count, crop_top=CROP_VERTICAL
    )
    oklch = [
        Color("srgb", list(rgb_col)).convert("oklch") for rgb_col in dominant_colors
    ]
    chosen = max(oklch, key=lambda c: c["chroma"])
    # Greyscale covers have no usable hue: emit a neutral grey at the same
    # lightness so it reads as one of the family rather than a jarring tint.
    chroma = 0 if chosen["chroma"] < UI_MIN_CHROMA else UI_CHROMA
    accent = Color("oklch", [UI_LIGHTNESS, chroma, chosen["hue"]])
    return accent.fit("srgb").convert("srgb").to_string(hex=True)
