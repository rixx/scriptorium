import re

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
