import logging
import shutil
import subprocess
from pathlib import Path

import fitz

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

TEXT_SAMPLE_PAGES = 5
TEXT_LAYER_THRESHOLD = 50

LANG_MAP = {"pl": "pol", "en": "eng", "fr": "fra", "de": "deu"}
DEFAULT_LANG = "eng"


def infer_language(filename: str) -> str:
    tag = Path(filename).stem.rsplit("_", 1)[-1].lower()
    return LANG_MAP.get(tag, DEFAULT_LANG)


def has_text_layer(pdf_path: Path) -> bool:
    with fitz.open(pdf_path) as doc:
        n = len(doc)
        if n == 0:
            return False
        if n <= TEXT_SAMPLE_PAGES:
            indexes = list(range(n))
        else:
            step = n // (TEXT_SAMPLE_PAGES + 1)
            indexes = [step * (i + 1) for i in range(TEXT_SAMPLE_PAGES)]
        total = sum(len(doc[i].get_text().strip()) for i in indexes)
        return total / len(indexes) >= TEXT_LAYER_THRESHOLD


def run_ocrmypdf(src: Path, dst: Path, language: str) -> None:
    cmd = [
        "ocrmypdf",
        "--language", language,
        "--optimize", "3",
        "--deskew",
        "--clean",
        "--skip-text",
        "--output-type", "pdfa",
        "--quiet",
        str(src),
        str(dst),
    ]
    log.info("OCR → %s (lang=%s)", dst.name, language)
    subprocess.run(cmd, check=True)


def process_file(src: Path) -> None:
    dst = PROCESSED_DIR / src.name
    if dst.exists():
        log.info("SKIP %s", src.name)
        return

    if has_text_layer(src):
        log.info("COPY %s", src.name)
        shutil.copy2(src, dst)
        return

    try:
        run_ocrmypdf(src, dst, infer_language(src.name))
    except subprocess.CalledProcessError as exc:
        dst.unlink(missing_ok=True)
        log.error("OCR failed for %s: %s", src.name, exc)
        raise


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        log.warning("No PDFs found in %s", RAW_DIR)
        return

    log.info("Found %d PDF(s) in %s", len(pdfs), RAW_DIR)
    for pdf in pdfs:
        process_file(pdf)
    log.info("Done. Output in %s", PROCESSED_DIR)


if __name__ == "__main__":
    main()
