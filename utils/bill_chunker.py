import re
import logging
from typing import List, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class BillChunk:
    """Represents a chunk of bill text with metadata"""
    content: str
    chunk_type: str  # 'title', 'summary', 'section', 'paragraph'
    section_number: str = ""
    section_title: str = ""
    start_position: int = 0
    end_position: int = 0
    importance_score: float = 0.0

class BillChunker:
    """Chunks bill text into manageable sections for AI analysis"""
    
    def __init__(self, max_chunk_size: int = 8000, overlap_size: int = 500):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size
    
    def chunk_bill(self, bill_text: str, title: str = "", summary: str = "") -> List[BillChunk]:
        """
        Chunk a bill into manageable sections for AI analysis
        
        Args:
            bill_text: Full bill text
            title: Bill title
            summary: Bill summary
            
        Returns:
            List of BillChunk objects
        """
        chunks = []
        
        # Add title as first chunk if available
        if title:
            chunks.append(BillChunk(
                content=f"Title: {title}",
                chunk_type="title",
                importance_score=1.0
            ))
        
        # Add summary as second chunk if available
        if summary:
            chunks.append(BillChunk(
                content=f"Summary: {summary}",
                chunk_type="summary",
                importance_score=0.9
            ))
        
        # Extract structured sections from bill text
        section_chunks = self._extract_sections(bill_text)
        chunks.extend(section_chunks)
        
        # If no sections found, create paragraph chunks
        if not section_chunks:
            paragraph_chunks = self._chunk_by_paragraphs(bill_text)
            chunks.extend(paragraph_chunks)
        
        # Ensure we don't exceed API limits by combining small chunks
        optimized_chunks = self._optimize_chunks(chunks)
        
        logger.info(f"Created {len(optimized_chunks)} chunks from bill text")
        return optimized_chunks
    
    def _extract_sections(self, bill_text: str) -> List[BillChunk]:
        """Extract structured sections from bill text"""
        sections = []
        
        # Common section patterns in bills
        section_patterns = [
            (r'SECTION\s+(\d+[A-Z]*)\.?\s*(.*?)(?=\n|$)', 'section'),
            (r'SEC\.\s+(\d+[A-Z]*)\.?\s*(.*?)(?=\n|$)', 'section'),
            (r'TITLE\s+(\d+[A-Z]*)\.?\s*(.*?)(?=\n|$)', 'title'),
            (r'PART\s+(\d+[A-Z]*)\.?\s*(.*?)(?=\n|$)', 'part'),
            (r'CHAPTER\s+(\d+[A-Z]*)\.?\s*(.*?)(?=\n|$)', 'chapter'),
            (r'SUBTITLE\s+(\d+[A-Z]*)\.?\s*(.*?)(?=\n|$)', 'subtitle'),
        ]
        
        for pattern, chunk_type in section_patterns:
            matches = list(re.finditer(pattern, bill_text, re.IGNORECASE | re.MULTILINE))
            if matches:
                for i, match in enumerate(matches):
                    section_num = match.group(1)
                    section_title = match.group(2).strip()
                    
                    # Find the content for this section
                    start_pos = match.end()
                    if i + 1 < len(matches):
                        end_pos = matches[i + 1].start()
                    else:
                        end_pos = len(bill_text)
                    
                    section_content = bill_text[start_pos:end_pos].strip()
                    
                    if len(section_content) > 50:  # Only include substantial sections
                        # Calculate importance based on section number and content length
                        importance = self._calculate_section_importance(section_num, section_content)
                        
                        sections.append(BillChunk(
                            content=f"{chunk_type.title()} {section_num}: {section_title}\n\n{section_content}",
                            chunk_type=chunk_type,
                            section_number=section_num,
                            section_title=section_title,
                            start_position=start_pos,
                            end_position=end_pos,
                            importance_score=importance
                        ))
        
        return sections
    
    def _chunk_by_paragraphs(self, bill_text: str) -> List[BillChunk]:
        """Chunk bill text by paragraphs when no clear sections exist"""
        chunks = []
        
        # Split by double newlines (paragraphs)
        paragraphs = re.split(r'\n\s*\n', bill_text)
        
        current_chunk = ""
        chunk_start = 0
        
        for i, paragraph in enumerate(paragraphs):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # If adding this paragraph would exceed max size, create a new chunk
            if len(current_chunk) + len(paragraph) > self.max_chunk_size and current_chunk:
                chunks.append(BillChunk(
                    content=current_chunk,
                    chunk_type="paragraph",
                    start_position=chunk_start,
                    end_position=chunk_start + len(current_chunk),
                    importance_score=0.5
                ))
                
                # Start new chunk with overlap
                overlap_text = current_chunk[-self.overlap_size:] if self.overlap_size > 0 else ""
                current_chunk = overlap_text + "\n\n" + paragraph
                chunk_start = chunk_start + len(current_chunk) - len(overlap_text) - len(paragraph)
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # Add the last chunk
        if current_chunk:
            chunks.append(BillChunk(
                content=current_chunk,
                chunk_type="paragraph",
                start_position=chunk_start,
                end_position=chunk_start + len(current_chunk),
                importance_score=0.5
            ))
        
        return chunks
    
    def _calculate_section_importance(self, section_num: str, content: str) -> float:
        """Calculate importance score for a section"""
        base_score = 0.5
        
        # Early sections are usually more important
        try:
            num = int(re.sub(r'[A-Z]', '', section_num))
            if num <= 5:
                base_score += 0.3
            elif num <= 10:
                base_score += 0.2
        except ValueError:
            pass
        
        # Longer sections might be more important
        if len(content) > 1000:
            base_score += 0.1
        
        # Sections with funding information are important
        if re.search(r'\$[\d,]+', content):
            base_score += 0.2
        
        # Sections with key terms are important
        key_terms = ['shall', 'must', 'required', 'prohibited', 'authorized', 'establish']
        term_count = sum(1 for term in key_terms if term.lower() in content.lower())
        base_score += min(term_count * 0.05, 0.2)
        
        return min(base_score, 1.0)
    
    def _optimize_chunks(self, chunks: List[BillChunk]) -> List[BillChunk]:
        """Optimize chunks to avoid too many small chunks while staying within limits"""
        optimized = []
        current_chunk = ""
        current_importance = 0.0
        
        for chunk in chunks:
            # If this chunk is small and we can combine it with the current chunk
            if (len(current_chunk) + len(chunk.content) <= self.max_chunk_size and 
                len(chunk.content) < self.max_chunk_size // 2):
                
                if current_chunk:
                    current_chunk += "\n\n---\n\n" + chunk.content
                else:
                    current_chunk = chunk.content
                current_importance = max(current_importance, chunk.importance_score)
            else:
                # Add the current combined chunk
                if current_chunk:
                    optimized.append(BillChunk(
                        content=current_chunk,
                        chunk_type="combined",
                        importance_score=current_importance
                    ))
                
                # Start new chunk
                current_chunk = chunk.content
                current_importance = chunk.importance_score
        
        # Add the last chunk
        if current_chunk:
            optimized.append(BillChunk(
                content=current_chunk,
                chunk_type="combined",
                importance_score=current_importance
            ))
        
        return optimized
    
    def get_chunk_summary(self, chunks: List[BillChunk]) -> str:
        """Create a summary of all chunks for context"""
        summary_parts = []
        
        for i, chunk in enumerate(chunks):
            if chunk.chunk_type == "title":
                summary_parts.append(f"Chunk {i+1}: {chunk.content}")
            elif chunk.chunk_type == "summary":
                summary_parts.append(f"Chunk {i+1}: Summary")
            elif chunk.chunk_type in ["section", "title", "part", "chapter"]:
                summary_parts.append(f"Chunk {i+1}: {chunk.chunk_type.title()} {chunk.section_number} - {chunk.section_title[:50]}")
            else:
                summary_parts.append(f"Chunk {i+1}: {chunk.chunk_type.title()} ({len(chunk.content)} chars)")
        
        return "\n".join(summary_parts) 