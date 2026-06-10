from dataclasses import dataclass
from pathlib import Path

import fitz

from app.ingest.cleaning import dehyphenate, repeating_lines, strip_noise
from app.ingest.headings import body_font_size, extract_headings
from app.ingest.metadata import detect_metadata
from app.ingest.splitter import count_tokens, split_macros, split_micros

MIN_MICRO_TOKENS = 20


@dataclass
class Section:
    heading: str | None
    text: str
    page_start: int
    page_end: int


@dataclass
class Parent:
    id: str
    source: str
    section: str | None
    page_start: int
    page_end: int
    lang: str | None
    doc_type: str | None
    car_make: str | None
    car_models: list[str] | None
    text: str


@dataclass
class MicroPayload:
    parent_id: str
    text: str
    source: str
    page: int
    lang: str | None
    doc_type: str | None
    car_makes: list[str]
    car_models: list[str]


def chunk_pdf(path: Path) -> tuple[list[Parent], list[MicroPayload]]:
    meta = detect_metadata(path.name)
    with fitz.open(path) as doc:
        raw_pages = [page.get_text() for page in doc]
        body_size = body_font_size(doc)
        headings = extract_headings(doc, body_size)

    pages = [dehyphenate(page) for page in raw_pages]
    repeating = repeating_lines(pages)
    cleaned_pages = [strip_noise(page, repeating) for page in pages]
    sections = _group_into_sections(cleaned_pages, headings)

    parents: list[Parent] = []
    micros: list[MicroPayload] = []
    for section in sections:
        macros = split_macros(section.text)
        for macro in macros:
            parent_id = str(macro.id)
            parents.append(Parent(
                id=parent_id,
                source=path.name,
                section=section.heading,
                page_start=section.page_start,
                page_end=section.page_end,
                lang=meta.lang,
                doc_type=meta.doc_type,
                car_make=meta.car_makes[0] if meta.car_makes else None,
                car_models=meta.car_models or None,
                text=macro.text,
            ))
            for micro in split_micros(macro):
                if count_tokens(micro.text) < MIN_MICRO_TOKENS:
                    continue
                micros.append(MicroPayload(
                    parent_id=parent_id,
                    text=micro.text,
                    source=path.name,
                    page=section.page_start,
                    lang=meta.lang,
                    doc_type=meta.doc_type,
                    car_makes=meta.car_makes,
                    car_models=meta.car_models,
                ))
    return parents, micros


def _group_into_sections(pages: list[str], headings) -> list[Section]:
    first_heading_per_page: dict[int, str] = {}
    for heading in headings:
        first_heading_per_page.setdefault(heading.page, heading.text)

    sections: list[Section] = []
    current_heading: str | None = None
    current_text: list[str] = []
    current_start = 1

    for page_index, page_text in enumerate(pages, start=1):
        if page_index in first_heading_per_page:
            if current_text:
                sections.append(Section(
                    heading=current_heading,
                    text="\n\n".join(current_text),
                    page_start=current_start,
                    page_end=page_index - 1,
                ))
            current_heading = first_heading_per_page[page_index]
            current_text = [page_text] if page_text.strip() else []
            current_start = page_index
        elif page_text.strip():
            current_text.append(page_text)

    if current_text:
        sections.append(Section(
            heading=current_heading,
            text="\n\n".join(current_text),
            page_start=current_start,
            page_end=len(pages),
        ))
    return sections