"""NHS Number validation using the Modulus 11 algorithm."""

import re

_STRIP_RE = re.compile(r"[\s\-]")


def format_nhs_number(raw: str) -> str:
    """Return NHS Number stripped of spaces/hyphens, or the original string."""
    return _STRIP_RE.sub("", str(raw))


def validate_nhs_number(raw: str) -> bool:
    """
    Return True if raw is a valid NHS Number (Modulus 11 check digit).

    Accepts numbers with or without spaces/hyphens (e.g. "943 476 5919" or "9434765919").
    Returns False for anything that does not pass the check, including blanks.
    """
    digits = format_nhs_number(raw)

    if not digits.isdigit() or len(digits) != 10:
        return False

    # Weights for positions 1-9 (index 0-8)
    weights = [10, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits, weights))
    remainder = total % 11
    check_digit = 11 - remainder

    if check_digit == 11:
        check_digit = 0

    # check_digit == 10 is invalid — no valid NHS Number can produce it
    if check_digit == 10:
        return False

    return check_digit == int(digits[9])
