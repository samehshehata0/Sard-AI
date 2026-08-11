import os
import logging

logger = logging.getLogger(__name__)

class PresentationParser:
    def detect_format(self, file_path: str) -> str:
        """
        Detects whether file is PDF, PPTX, or HTML.
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return "PDF"
        elif ext in [".pptx", ".ppt"]:
            return "PPTX"
        elif ext in [".html", ".htm"]:
            return "HTML"
        else:
            # Inspection by magic bytes / content fallback
            with open(file_path, "rb") as f:
                header = f.read(16)
                if header.startswith(b"%PDF"):
                    return "PDF"
                elif header.startswith(b"PK\x03\x04"):
                    return "PPTX"
                elif b"<html" in header.lower() or b"<!doctype html" in header.lower():
                    return "HTML"
        logger.info(f"[PresentationParser] Detected format {ext} for {file_path}")
        return "PDF"
