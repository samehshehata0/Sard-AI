import os
import asyncio
import logging
import shutil
import hashlib
from typing import List
import pymupdf as fitz
from PIL import Image, ImageDraw
from app.core.config import settings
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
        if not presentation_path or not os.path.isfile(presentation_path):
            raise FileNotFoundError("Presentation artifact does not exist")
        os.makedirs(output_dir, exist_ok=True)
        
        if presentation_path.lower().endswith((".png", ".jpg", ".jpeg")):
            dest = os.path.join(output_dir, "scene_01.png")
            shutil.copy(presentation_path, dest)
            logger.info(f"[SlideExtractor] Copied image slide -> {dest}")
            return self.remove_duplicate_slides([dest])

        fmt = self.parser.detect_format(presentation_path)
        logger.info(f"[SlideExtractor] Extracting slides from {fmt} presentation: {presentation_path}")

        if fmt == "PDF":
            paths = self._extract_pdf_slides(presentation_path, output_dir)
        elif fmt == "PPTX":
            paths = self._extract_pptx_slides(presentation_path, output_dir)
        elif fmt == "HTML":
            paths = await self._extract_html_slides(presentation_path, output_dir)
        else:
            paths = self._extract_pdf_slides(presentation_path, output_dir)

        unique_paths = self.remove_duplicate_slides(paths)
        if not unique_paths:
            raise RuntimeError("No usable slides were extracted")
        logger.info(
            "[Sard] Extracted %s unique slides (from %s pages)",
            len(unique_paths),
            len(paths),
        )
        return unique_paths

    def extract_slide_texts(self, presentation_path: str) -> List[str]:
        if not presentation_path.lower().endswith(".pdf"):
            return []
        doc = fitz.open(presentation_path)
        try:
            return [page.get_text("text").strip() for page in doc]
        finally:
            doc.close()

    def _normalized_hash(self, image_path: str) -> str:
        with Image.open(image_path) as image:
            normalized = image.convert("RGB").resize((320, 180))
            return hashlib.sha256(normalized.tobytes()).hexdigest()

    def remove_duplicate_slides(self, paths: List[str]) -> List[str]:
        unique_paths: List[str] = []
        hashes: set[str] = set()
        for path in paths:
            try:
                image_hash = self._normalized_hash(path)
            except Exception as exc:
                logger.warning("[Sard] Could not hash slide %s: %s", path, exc)
                continue
            if image_hash in hashes:
                logger.warning("[Sard] Skipping duplicate slide: %s", path)
                continue
            hashes.add(image_hash)
            unique_paths.append(path)
        return unique_paths

    def _extract_pdf_slides(self, pdf_path: str, output_dir: str) -> List[str]:
        doc = fitz.open(pdf_path)
        extracted_paths = []
        for index, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            file_name = f"scene_{index + 1:02d}.png"
            file_path = os.path.join(output_dir, file_name)
            pix.save(file_path)
            self._remove_provider_footer(file_path)
            extracted_paths.append(file_path)
            logger.info(f"[SlideExtractor] Rendered PDF page {index + 1} -> {file_path}")
        doc.close()
        return extracted_paths

    def _remove_provider_footer(self, image_path: str) -> None:
        """Covers only NotebookLM's tiny bottom-right provider watermark."""
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            width, height = image.size
            left = int(width * (1.0 - settings.NOTEBOOKLM_FOOTER_WIDTH_RATIO))
            top = int(height * (1.0 - settings.NOTEBOOKLM_FOOTER_HEIGHT_RATIO))
            sample_x = min(width - 1, max(left, int(width * 0.9)))
            sample_y = max(0, top - 2)
            fill = image.getpixel((sample_x, sample_y))
            ImageDraw.Draw(image).rectangle((left, top, width, height), fill=fill)
            image.save(image_path)

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
            browser = p.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)
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
