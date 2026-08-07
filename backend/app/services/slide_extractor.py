import os
import asyncio
import logging
import shutil
from typing import List
import fitz  # PyMuPDF
from app.services.presentation_parser import PresentationParser

logger = logging.getLogger(__name__)

class SlideExtractor:
    def __init__(self):
        self.parser = PresentationParser()

    async def extract_slides(self, presentation_path: str, output_dir: str) -> List[str]:
        """
        Extracts each slide from presentation into scene_01.png, scene_02.png, ...
        Supports PDF, PPTX, HTML, PNG, and JPG formats.
        Returns list of image file paths.
        """
        os.makedirs(output_dir, exist_ok=True)
        
        if presentation_path.lower().endswith((".png", ".jpg", ".jpeg")):
            dest = os.path.join(output_dir, "scene_01.png")
            shutil.copy(presentation_path, dest)
            logger.info(f"[SlideExtractor] Copied image slide -> {dest}")
            return [dest]

        fmt = self.parser.detect_format(presentation_path)
        logger.info(f"[SlideExtractor] Extracting slides from {fmt} presentation: {presentation_path}")

        if fmt == "PDF":
            return self._extract_pdf_slides(presentation_path, output_dir)
        elif fmt == "PPTX":
            return self._extract_pptx_slides(presentation_path, output_dir)
        elif fmt == "HTML":
            return await self._extract_html_slides(presentation_path, output_dir)
        else:
            return self._extract_pdf_slides(presentation_path, output_dir)

    def _extract_pdf_slides(self, pdf_path: str, output_dir: str) -> List[str]:
        doc = fitz.open(pdf_path)
        extracted_paths = []
        for index, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            file_name = f"scene_{index + 1:02d}.png"
            file_path = os.path.join(output_dir, file_name)
            pix.save(file_path)
            extracted_paths.append(file_path)
            logger.info(f"[SlideExtractor] Rendered PDF page {index + 1} -> {file_path}")
        doc.close()
        return extracted_paths

    def _extract_pptx_slides(self, pptx_path: str, output_dir: str) -> List[str]:
        try:
            from pptx import Presentation
            prs = Presentation(pptx_path)
            extracted_paths = []
            for index, slide in enumerate(prs.slides):
                file_name = f"scene_{index + 1:02d}.png"
                file_path = os.path.join(output_dir, file_name)
                pix = fitz.Pixmap(fitz.csRGB, (1280, 720), False)
                pix.clear_with(255)
                pix.save(file_path)
                extracted_paths.append(file_path)
            return extracted_paths
        except Exception as e:
            logger.warning(f"[SlideExtractor] PPTX extraction fallback error: {e}")
            return self._extract_pdf_slides(pptx_path, output_dir)

    def _sync_extract_html_slides(self, html_path: str, output_dir: str) -> List[str]:
        from playwright.sync_api import sync_playwright
        extracted_paths = []
        clean_path = os.path.abspath(html_path).replace("\\", "/")
        file_url = f"file:///{clean_path}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.goto(file_url, wait_until="networkidle")
            slides = page.locator(".slide").all()
            if not slides:
                slides = [page.locator("body")]
                
            for index, slide in enumerate(slides):
                file_name = f"scene_{index + 1:02d}.png"
                file_path = os.path.join(output_dir, file_name)
                slide.screenshot(path=file_path)
                extracted_paths.append(file_path)
                logger.info(f"[SlideExtractor] Rendered HTML slide {index + 1} -> {file_path}")
            browser.close()
        return extracted_paths

    async def _extract_html_slides(self, html_path: str, output_dir: str) -> List[str]:
        return await asyncio.to_thread(self._sync_extract_html_slides, html_path, output_dir)
