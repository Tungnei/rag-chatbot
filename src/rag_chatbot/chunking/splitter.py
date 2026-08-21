"""Split documents into overlapping chunks on natural boundaries."""

from __future__ import annotations

import re

from rag_chatbot.configs import ChunkingSettings

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class TextSplitter:
    def __init__(self, settings: ChunkingSettings) -> None:
        self._chunk_size = settings.chunk_size
        self._overlap = min(settings.chunk_overlap, settings.chunk_size - 1)
        self._min_size = settings.min_chunk_size

    def split(self, text: str) -> list[str]:
        """Split plain text, preferring paragraph then sentence boundaries."""
        units = self._split_units(text)
        chunks: list[str] = []
        current = ""

        for unit in units:
            if not current:
                current = unit
            elif len(current) + 1 + len(unit) <= self._chunk_size:
                current = f"{current}\n{unit}" if "\n" in current else f"{current} {unit}"
            else:
                chunks.append(current)
                current = self._carry_overlap(current, unit)

        if current:
            chunks.append(current)
        return self._merge_tiny(chunks)

    def split_markdown(self, text: str) -> list[tuple[str, str | None]]:
        """Split by heading, returning (chunk_text, nearest_heading) pairs."""
        sections = self._split_by_heading(text)
        result: list[tuple[str, str | None]] = []
        for heading, body in sections:
            body = body.strip()
            if not body:
                continue
            for chunk in self.split(body):
                result.append((chunk, heading))
        return result

    def _split_by_heading(self, text: str) -> list[tuple[str | None, str]]:
        matches = list(_MD_HEADING.finditer(text))
        if not matches:
            return [(None, text)]

        sections: list[tuple[str | None, str]] = []
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append((None, preamble))

        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            heading = match.group(2).strip()
            body = text[match.end() : end].strip()
            # A heading immediately followed by a sub-heading carries no content of its own.
            if not body:
                continue
            sections.append((heading, f"{heading}\n{body}"))
        return sections

    def _split_units(self, text: str) -> list[str]:
        units: list[str] = []
        for paragraph in _PARAGRAPH_BREAK.split(text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(paragraph) <= self._chunk_size:
                units.append(paragraph)
            else:
                units.extend(self._split_long_paragraph(paragraph))
        return units

    def _split_long_paragraph(self, paragraph: str) -> list[str]:
        parts: list[str] = []
        for sentence in _SENTENCE_END.split(paragraph):
            if len(sentence) <= self._chunk_size:
                parts.append(sentence)
            else:
                parts.extend(self._split_on_words(sentence))
        return parts

    def _split_on_words(self, text: str) -> list[str]:
        parts: list[str] = []
        current = ""
        for word in text.split():
            if not current:
                current = word
            elif len(current) + 1 + len(word) <= self._chunk_size:
                current = f"{current} {word}"
            else:
                parts.append(current)
                current = word
        if current:
            parts.append(current)
        return parts

    def _carry_overlap(self, previous: str, next_unit: str) -> str:
        if self._overlap <= 0:
            return next_unit
        tail = previous[-self._overlap :]
        # Start the overlap at a word boundary so no chunk begins mid-word.
        space = tail.find(" ")
        if space != -1:
            tail = tail[space + 1 :]
        candidate = f"{tail} {next_unit}".strip()
        return candidate if len(candidate) <= self._chunk_size else next_unit

    def _merge_tiny(self, chunks: list[str]) -> list[str]:
        merged: list[str] = []
        for chunk in chunks:
            if merged and len(chunk) < self._min_size:
                merged[-1] = f"{merged[-1]} {chunk}"
            else:
                merged.append(chunk)
        return [c for c in merged if c.strip()]
