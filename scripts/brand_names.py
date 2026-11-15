"""Product-name shapes the rebrand rewrites and the branding check rejects.

Latin "Bitwarden" is handled separately. This module covers the spellings that
an exact Latin match misses: other scripts, and tokens within edit distance 2.
"""
from __future__ import annotations

import re

# Stems are specific enough that ordinary words in the same script do not match.
# A short inflection in the same script may follow the stem.
TRANSLITERATION_PATTERNS = (
    # Cyrillic: Bulgarian Битуорден and Буторден, Serbian Битварден, and nearby misspellings.
    r"(?i)(?:битуорден|битуордун|биуорден|битоурден|биуторден|битурден|битварден|бітварден|бітуорден|буторден|бутордън|бутварден|бутвардън|бутуорден)[а-яёіїєґ]{0,6}",
    # Bengali, including the two encodings of য.
    r"বিটও(?:\u09af\u09bc|\u09df)ার্ডেন[\u0980-\u09FF]{0,4}",
    # Hindi and Marathi.
    r"बिटव(?:ा|ॉ)?र्ड(?:े)?न[\u0900-\u097F]{0,4}",
    # Kannada, with or without ZWNJ, including a .ಕಾಮ್ host.
    r"ಬಿಟ್\u200c?ವ(?:ಾ)?ರ್ಡ[\u0c80-\u0cff\u200c]{0,10}(?:\.ಕಾಮ್|\.com)?",
    # Tamil. The stem stops before the pulli so உக்கு still matches.
    r"பிட்வார்டன[\u0b80-\u0bff]{0,6}",
    # Malayalam, including a space: ബിറ്റ് വാർഡൻ.
    r"ബിറ്റ്[\u200c\s]*വ[\u0d00-\u0d7f\u200c\s]{0,16}",
    # Sinhala, including a latin .com host.
    r"බිට්ව(?:ර්ඩන්|ාඩන්|ොන්)(?:\.com)?",
    # Arabic and Persian, including the spaced form بت وردين.
    r"بيتواردن؟?",
    r"بت[\s\u200c]*وردين",
    r"بیت\u200c?واردن",
)

# Bytes that mean a file is worth decoding. Shorter than the full pattern so
# UTF-16 resource tables are not skipped.
NAME_NEEDLES = (
    "Битуорден",
    "Буторден",
    "Битуордун",
    "Битварден",
    "বিটও",
    "बिटव",
    "ಬಿಟ್",
    "பிட்வார்டன்",
    "ബിറ്റ്",
    "ബിറ്റ് വാ",
    "බිට්ව",
    "بيتواردن",
    "بت وردين",
    "بیت",
    "Bitwaden",
    "Birwarden",
    "Biitiwarden",
    "Bidwarden",
    "Biwarden",
    "Bitwatden",
)

_COMPILED = tuple(re.compile(p) for p in TRANSLITERATION_PATTERNS)
# Whole Latin tokens. Length 8–12 keeps "twarden" (the tail of a punycode test
# fixture split on ü) out, and skips the exact "bitward…" forms the other
# matcher already owns.
_TOKEN = re.compile(r"(?<![A-Za-z0-9_@./])[A-Za-z]{8,12}(?![A-Za-z0-9_])")


def transliteration_spans(text: str):
    for cre in _COMPILED:
        for match in cre.finditer(text):
            yield match.start(), match.end()


def _distance(left: str, right: str) -> int:
    if abs(len(left) - len(right)) > 2:
        return 3
    prev = list(range(len(right) + 1))
    for char in left:
        cur = [prev[0] + 1]
        for index, other in enumerate(right, 1):
            cur.append(min(prev[index] + 1, cur[-1] + 1, prev[index - 1] + (char != other)))
        prev = cur
    return prev[-1]


def fuzzy_spans(text: str):
    """Latin tokens within edit distance 2 of bitwarden, excluding the exact stem."""
    for match in _TOKEN.finditer(text):
        word = match.group(0).lower()
        if word.startswith("bitward") or word.startswith("vaultwarden"):
            continue
        prev = text[match.start() - 1] if match.start() else ""
        # Punycode labels (xn--btwarden-65a) and percent-encoding.
        # An empty prev is a substring of every string, so it has to be excluded.
        if prev and prev in "-:%":
            continue
        if _distance(word, "bitwarden") <= 2:
            yield match.start(), match.end()


def needle_blobs() -> tuple[bytes, ...]:
    blobs = []
    for needle in NAME_NEEDLES:
        blobs.append(needle.encode("utf-8"))
        blobs.append(needle.encode("utf-16le"))
    return tuple(blobs)
