"""Shared lexical normalization; stored source text and offsets stay untouched."""
import unicodedata


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().translate(
        str.maketrans({"ё": "е", "’": "'", "ʼ": "'", "‘": "'", "`": "'"})
    ).split())
