from typing import Final, Literal

LanguageCode = Literal["ja", "en"]

SUPPORTED_LANGUAGES: Final[tuple[LanguageCode, ...]] = ("ja", "en")
DEFAULT_LANGUAGE: Final[LanguageCode] = "ja"

_LANGUAGE_ALIASES: Final[dict[str, LanguageCode]] = {
    "ja-jp": "ja",
    "ja_jp": "ja",
    "jp": "ja",
    "en-us": "en",
    "en_us": "en",
    "en-gb": "en",
    "en_gb": "en",
}


def normalize_language(language: str | None) -> LanguageCode:
    if not language:
        return DEFAULT_LANGUAGE

    normalized = language.strip().lower().replace("_", "-")
    if normalized in SUPPORTED_LANGUAGES:
        return normalized  # type: ignore[return-value]

    alias_value = _LANGUAGE_ALIASES.get(normalized)
    if alias_value is not None:
        return alias_value

    if normalized.startswith("ja"):
        return "ja"
    if normalized.startswith("en"):
        return "en"

    return DEFAULT_LANGUAGE


__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "LanguageCode",
    "normalize_language",
]
