"""Term normalization (vendored): shape a label for use as a concept id."""
import re


def _normalize_term(term: str) -> str:
    """Lowercase, collapse spaces/hyphens to underscores, drop non-word chars."""
    term = term.lower().strip()
    term = re.sub(r"[\s\-]+", "_", term)
    term = re.sub(r"[^\w]", "", term)
    return term
