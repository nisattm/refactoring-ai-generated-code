"""Case-insensitive normalization (LIB-COM-30 / LIB-SRCH-01)."""


def normalize(text: str) -> str:
    return text.replace("İ", "i").replace("I", "i").replace("ı", "i").casefold()
