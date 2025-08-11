import os
import magic
import hashlib
from typing import Tuple, Optional, List
from PyPDF2 import PdfReader
from docx import Document as DocxDocument
import markdown
from app.config import settings

def validate_file(file_content: bytes, filename: str) -> Tuple[bool, Optional[str]]:
    """Validate file type and size"""
    # Check file size
    if len(file_content) > settings.max_file_size:
        return False, f"File size exceeds {settings.max_file_size} bytes"
    
    # Check file type
    allowed_types = {
        'application/pdf': ['.pdf'],
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
        'text/plain': ['.txt'],
        'text/markdown': ['.md'],
        'image/jpeg': ['.jpg', '.jpeg'],
        'image/png': ['.png'],
    }
    
    try:
        mime_type = magic.from_buffer(file_content, mime=True)
        file_ext = os.path.splitext(filename)[1].lower()
        
        for allowed_mime, allowed_exts in allowed_types.items():
            if mime_type == allowed_mime and file_ext in allowed_exts:
                return True, None
        
        return False, f"File type {mime_type} not supported"
    except Exception as e:
        return False, f"Error validating file: {str(e)}"

def extract_text_content(file_path: str, file_type: str) -> str:
    """Extract text content from various file types"""
    try:
        if file_type == 'application/pdf':
            return extract_pdf_text(file_path)
        elif file_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            return extract_docx_text(file_path)
        elif file_type == 'text/plain':
            return extract_txt_text(file_path)
        elif file_type == 'text/markdown':
            return extract_markdown_text(file_path)
        else:
            return ""
    except Exception as e:
        print(f"Error extracting text from {file_path}: {str(e)}")
        return ""

def extract_pdf_text(file_path: str) -> str:
    """Extract text from PDF file"""
    text = ""
    with open(file_path, 'rb') as file:
        pdf_reader = PdfReader(file)
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
    return text.strip()

def extract_docx_text(file_path: str) -> str:
    """Extract text from DOCX file"""
    doc = DocxDocument(file_path)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text.strip()

def extract_txt_text(file_path: str) -> str:
    """Extract text from TXT file"""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def extract_markdown_text(file_path: str) -> str:
    """Extract text from Markdown file"""
    with open(file_path, 'r', encoding='utf-8') as file:
        md_content = file.read()
        # Convert markdown to plain text (remove markdown syntax)
        html = markdown.markdown(md_content)
        # Simple HTML tag removal (could be improved with BeautifulSoup)
        import re
        text = re.sub('<[^<]+?>', '', html)
        return text

def generate_file_hash(file_content: bytes) -> str:
    """Generate SHA-256 hash of file content"""
    return hashlib.sha256(file_content).hexdigest()

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into chunks for vector embedding"""
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        if end > text_length:
            end = text_length
        
        chunk = text[start:end]
        chunks.append(chunk)
        
        # Move start position considering overlap
        start = end - overlap
        if start >= text_length:
            break
    
    return chunks
