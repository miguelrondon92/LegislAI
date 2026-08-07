import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class BillChunk:
    """Represents a chunk of bill text with metadata"""

    content: str
    chunk_type: str  # 'section', 'paragraph', 'macro', ...
    section_number: str = ""
    section_title: str = ""
    start_position: int = 0
    end_position: int = 0
    importance_score: float = 0.0
    chunk_key: str = ""

    def ensure_key(self) -> str:
        """Stable identity for resume: start:end + content hash."""
        if self.chunk_key:
            return self.chunk_key
        digest = hashlib.sha256(self.content.encode("utf-8", errors="replace")).hexdigest()[:16]
        self.chunk_key = f"{self.start_position}:{self.end_position}:{digest}"
        return self.chunk_key


class BillChunker:
    """Chunks bill text into non-overlapping sections / macro-chunks for AI analysis."""

    # Combined alternation — one ordered pass, no duplicate overlapping matches
    _HEADER_RE = re.compile(
        r"(?:"
        r"(?P<section_long>SECTION)\s+(?P<section_long_num>\d+[A-Z]*)\.?\s*(?P<section_long_title>.*?)"
        r"|(?P<section>SEC\.)\s+(?P<section_num>\d+[A-Z]*)\.?\s*(?P<section_title>.*?)"
        r"|(?P<title>TITLE)\s+(?P<title_num>\d+[A-Z]*)\.?\s*(?P<title_title>.*?)"
        r"|(?P<part>PART)\s+(?P<part_num>\d+[A-Z]*)\.?\s*(?P<part_title>.*?)"
        r"|(?P<chapter>CHAPTER)\s+(?P<chapter_num>\d+[A-Z]*)\.?\s*(?P<chapter_title>.*?)"
        r"|(?P<subtitle>SUBTITLE)\s+(?P<subtitle_num>\d+[A-Z]*)\.?\s*(?P<subtitle_title>.*?)"
        r")(?=\n|$)",
        re.IGNORECASE | re.MULTILINE,
    )

    def __init__(self, max_chunk_size: int = 8000, overlap_size: int = 500):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size

    def chunk_bill(
        self,
        bill_text: str,
        title: str = "",
        summary: str = "",
        include_title_summary: bool = False,
    ) -> List[BillChunk]:
        """
        Chunk a bill into non-overlapping sections (or paragraphs).

        Title/summary are not duplicated as separate chunks by default — the
        prepared bill text already embeds them when used by the analyzer.
        """
        chunks: List[BillChunk] = []

        if include_title_summary:
            if title:
                chunks.append(
                    BillChunk(
                        content=f"Title: {title}",
                        chunk_type="title",
                        importance_score=1.0,
                        start_position=0,
                        end_position=0,
                    )
                )
            if summary:
                chunks.append(
                    BillChunk(
                        content=f"Summary: {summary}",
                        chunk_type="summary",
                        importance_score=0.9,
                        start_position=0,
                        end_position=0,
                    )
                )

        section_chunks = self._extract_sections(bill_text)
        if section_chunks:
            chunks.extend(section_chunks)
        else:
            chunks.extend(self._chunk_by_paragraphs(bill_text))

        for chunk in chunks:
            chunk.ensure_key()

        logger.info(f"Created {len(chunks)} chunks from bill text")
        return chunks

    def build_macro_chunks(
        self,
        bill_text: str,
        max_chars: int,
        title: str = "",
        summary: str = "",
    ) -> List[BillChunk]:
        """
        Pack sections into document-order macro-chunks sized for Tier B map-reduce.
        Does not importance-rank or drop sections.
        """
        if max_chars < 1000:
            max_chars = 1000

        sections = self._extract_sections(bill_text)
        if not sections:
            sections = self._chunk_by_paragraphs(bill_text)

        macros: List[BillChunk] = []
        buf_parts: List[str] = []
        buf_start = 0
        buf_end = 0
        buf_len = 0

        def flush():
            nonlocal buf_parts, buf_start, buf_end, buf_len
            if not buf_parts:
                return
            content = "\n\n---\n\n".join(buf_parts)
            chunk = BillChunk(
                content=content,
                chunk_type="macro",
                start_position=buf_start,
                end_position=buf_end,
                importance_score=0.5,
            )
            chunk.ensure_key()
            macros.append(chunk)
            buf_parts = []
            buf_len = 0

        for section in sections:
            piece_len = len(section.content)
            if buf_parts and buf_len + piece_len + 8 > max_chars:
                flush()
            if not buf_parts:
                buf_start = section.start_position
            buf_parts.append(section.content)
            buf_end = section.end_position
            buf_len += piece_len + (8 if len(buf_parts) > 1 else 0)

            # Oversized single section: emit as its own macro (caller may still send it)
            if piece_len > max_chars and len(buf_parts) == 1:
                flush()

        flush()
        logger.info(
            f"Built {len(macros)} macro-chunks (max_chars={max_chars:,}) "
            f"from {len(sections)} sections"
        )
        return macros

    def _extract_sections(self, bill_text: str) -> List[BillChunk]:
        """Extract non-overlapping structured sections via one ordered regex pass."""
        if not bill_text:
            return []

        matches = list(self._HEADER_RE.finditer(bill_text))
        if not matches:
            return []

        # Deduplicate by start position (keep first match if overlapping starts)
        unique = []
        last_start = -1
        for match in matches:
            if match.start() == last_start:
                continue
            unique.append(match)
            last_start = match.start()

        sections: List[BillChunk] = []
        for i, match in enumerate(unique):
            chunk_type, section_num, section_title = self._match_meta(match)
            start_pos = match.start()
            end_pos = unique[i + 1].start() if i + 1 < len(unique) else len(bill_text)
            section_content = bill_text[start_pos:end_pos].strip()
            if len(section_content) <= 50:
                continue
            importance = self._calculate_section_importance(section_num, section_content)
            chunk = BillChunk(
                content=section_content,
                chunk_type=chunk_type,
                section_number=section_num,
                section_title=section_title,
                start_position=start_pos,
                end_position=end_pos,
                importance_score=importance,
            )
            chunk.ensure_key()
            sections.append(chunk)

        return sections

    def _match_meta(self, match: re.Match) -> tuple:
        gd = match.groupdict()
        if gd.get("section_long"):
            return "section", gd.get("section_long_num") or "", (gd.get("section_long_title") or "").strip()
        if gd.get("section"):
            return "section", gd.get("section_num") or "", (gd.get("section_title") or "").strip()
        if gd.get("title"):
            return "title", gd.get("title_num") or "", (gd.get("title_title") or "").strip()
        if gd.get("part"):
            return "part", gd.get("part_num") or "", (gd.get("part_title") or "").strip()
        if gd.get("chapter"):
            return "chapter", gd.get("chapter_num") or "", (gd.get("chapter_title") or "").strip()
        if gd.get("subtitle"):
            return "subtitle", gd.get("subtitle_num") or "", (gd.get("subtitle_title") or "").strip()
        return "section", "", ""

    def _chunk_by_paragraphs(self, bill_text: str) -> List[BillChunk]:
        """Chunk bill text by paragraphs when no clear sections exist."""
        chunks: List[BillChunk] = []
        paragraphs = re.split(r"\n\s*\n", bill_text)
        current_chunk = ""
        chunk_start = 0
        cursor = 0

        for paragraph in paragraphs:
            raw = paragraph
            paragraph = paragraph.strip()
            pos = bill_text.find(raw, cursor) if raw else -1
            if pos < 0:
                pos = cursor
            cursor = pos + len(raw)

            if not paragraph:
                continue

            if len(current_chunk) + len(paragraph) > self.max_chunk_size and current_chunk:
                chunk = BillChunk(
                    content=current_chunk,
                    chunk_type="paragraph",
                    start_position=chunk_start,
                    end_position=chunk_start + len(current_chunk),
                    importance_score=0.5,
                )
                chunk.ensure_key()
                chunks.append(chunk)
                overlap_text = (
                    current_chunk[-self.overlap_size :] if self.overlap_size > 0 else ""
                )
                current_chunk = (overlap_text + "\n\n" + paragraph) if overlap_text else paragraph
                chunk_start = pos - len(overlap_text) if overlap_text else pos
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
                    chunk_start = pos

        if current_chunk:
            chunk = BillChunk(
                content=current_chunk,
                chunk_type="paragraph",
                start_position=chunk_start,
                end_position=chunk_start + len(current_chunk),
                importance_score=0.5,
            )
            chunk.ensure_key()
            chunks.append(chunk)

        return chunks

    def _calculate_section_importance(self, section_num: str, content: str) -> float:
        """Importance from content signals only (no front-of-bill bias)."""
        base_score = 0.5

        if len(content) > 1000:
            base_score += 0.1
        if re.search(r"\$[\d,]+", content):
            base_score += 0.2

        key_terms = ["shall", "must", "required", "prohibited", "authorized", "establish"]
        term_count = sum(1 for term in key_terms if term.lower() in content.lower())
        base_score += min(term_count * 0.05, 0.2)

        return min(base_score, 1.0)

    def filter_unanalyzed(
        self, chunks: List[BillChunk], analyzed_keys: Optional[Set[str]]
    ) -> List[BillChunk]:
        if not analyzed_keys:
            return list(chunks)
        return [c for c in chunks if c.ensure_key() not in analyzed_keys]

    def get_chunk_summary(self, chunks: List[BillChunk]) -> str:
        """Create a summary of all chunks for context"""
        summary_parts = []
        for i, chunk in enumerate(chunks):
            if chunk.chunk_type in ["section", "title", "part", "chapter", "subtitle"]:
                summary_parts.append(
                    f"Chunk {i + 1}: {chunk.chunk_type.title()} {chunk.section_number} - "
                    f"{(chunk.section_title or '')[:50]}"
                )
            else:
                summary_parts.append(
                    f"Chunk {i + 1}: {chunk.chunk_type.title()} ({len(chunk.content)} chars)"
                )
        return "\n".join(summary_parts)
