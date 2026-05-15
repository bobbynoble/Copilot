"""Soundex implementation for surname fuzzy matching."""

_CODES = {
    "BFPV": "1",
    "CGJKQSXZ": "2",  # Y treated as vowel/separator per standard Soundex
    "DT": "3",
    "L": "4",
    "MN": "5",
    "R": "6",
}

_CHAR_MAP: dict[str, str] = {}
for chars, code in _CODES.items():
    for ch in chars:
        _CHAR_MAP[ch] = code


def soundex(name: str) -> str:
    """
    Return the American Soundex code for name.

    Returns an empty string for blank input.
    """
    upper = "".join(c for c in name.upper() if c.isalpha())
    if not upper:
        return ""

    first = upper[0]
    coded = first + "".join(
        _CHAR_MAP.get(ch, "0") for ch in upper[1:]
    )

    # Remove duplicate adjacent codes, then remove zeros
    deduped = coded[0]
    for ch in coded[1:]:
        if ch != deduped[-1]:
            deduped += ch
    filtered = deduped[0] + deduped[1:].replace("0", "")

    return (filtered + "000")[:4]
