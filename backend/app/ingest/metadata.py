from dataclasses import dataclass
from pathlib import Path

MAKE_ALIASES = {"vw": "volkswagen"}

DOC_TYPES = {
    "owners": "owners_manual",
    "radio": "radio",
    "repair": "repair",
    "workshop": "workshop",
    "ssp": "ssp",
    "tech-tip": "tech_tip",
    "wiring": "wiring",
}

LANGS = {"pl", "en", "fr", "de"}


@dataclass(frozen=True)
class PdfMetadata:
    car_makes: list[str]
    car_models: list[str]
    doc_type: str | None
    lang: str | None


def detect_metadata(filename: str) -> PdfMetadata:
    parts = Path(filename).stem.split("_")
    if len(parts) < 4:
        return PdfMetadata(car_makes=[], car_models=[], doc_type=None, lang=None)

    makes = [MAKE_ALIASES.get(make, make) for make in parts[0].split("+") if make]
    models = [_strip_digits(model) for model in parts[1].split("+") if model]
    doc_type = DOC_TYPES.get(parts[2])
    lang_token = parts[-1].lower()
    lang = lang_token if lang_token in LANGS else None
    return PdfMetadata(car_makes=makes, car_models=models, doc_type=doc_type, lang=lang)


def _strip_digits(model: str) -> str:
    return model.rstrip("0123456789") or model
