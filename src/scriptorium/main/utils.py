import colorsys
import re

from PIL import Image
from sklearn.cluster import KMeans
from unidecode import unidecode


def slugify(text):
    """Convert Unicode string into blog slug.

    Can't use Django's for backwards compatibility – this one turns
    j.k. r into j-k-r, Django's turns it into jk-r."""
    text = re.sub("[–—/:;,.]", "-", text)  # replace separating punctuation
    ascii_text = unidecode(text).lower()  # best ASCII substitutions, lowercased
    ascii_text = re.sub(r"[^a-z0-9 -]", "", ascii_text)  # delete any other characters
    ascii_text = ascii_text.replace(" ", "-")  # spaces to hyphens
    ascii_text = re.sub(r"-+", "-", ascii_text)  # condense repeated hyphens
    return ascii_text


def get_dominant_colours(path, count):
    im = Image.open(path)

    # Resizing means less pixels to handle, so the *k*-means clustering converges
    # faster.  Small details are lost, but the main details will be preserved.
    im = im.resize((100, 100))

    # Ensure the image is RGB, and use RGB values in [0, 1] for consistency
    # with operations elsewhere.
    im = im.convert("RGB")
    colors = [(r / 255, g / 255, b / 255) for (r, g, b) in im.getdata()]

    return KMeans(n_clusters=count).fit(colors).cluster_centers_


def get_spine_color(cover, cluster_count=3):
    dominant_colors = get_dominant_colours(cover.path, count=cluster_count)
    hsv_candidates = {
        tuple(rgb_col): colorsys.rgb_to_hsv(*rgb_col) for rgb_col in dominant_colors
    }

    candidates_by_brightness_diff = {
        rgb_col: abs(hsv_col[2] * hsv_col[1])
        for rgb_col, hsv_col in hsv_candidates.items()
    }

    rgb_choice, _ = max(candidates_by_brightness_diff.items(), key=lambda t: t[1])
    hex_color = "#%02x%02x%02x" % tuple(int(v * 255) for v in rgb_choice)
    return hex_color
