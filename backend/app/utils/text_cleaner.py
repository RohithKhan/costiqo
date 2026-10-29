import re


STOPWORDS = {
    "a",
    "an",
    "and",
    "edition",
    "for",
    "latest",
    "new",
    "of",
    "sale",
    "the",
    "with",
}


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def tokenize(value: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    tokens = [token for token in normalized.split() if token and token not in STOPWORDS]
    return tokens
