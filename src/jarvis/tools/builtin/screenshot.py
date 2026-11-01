"""Screenshot tool implementation for OCR capture."""

from typing import Dict, Any, Optional
import os
import tempfile
import subprocess
import shutil
from ...debug import debug_log
from ..base import Tool, ToolContext
from ..types import ToolExecutionResult

class ScreenshotTool(Tool):
    """Tool for capturing screenshots and performing OCR."""

    @property
    def name(self) -> str:
        return "screenshot"

    @property
    def description(self) -> str:
        return "Capture a selected screen region and OCR the text. Use only if the OCR will materially help."

    @property
    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def run(self, args: Optional[Dict[str, Any]], context: ToolContext) -> ToolExecutionResult:
        """Execute the screenshot tool."""
        context.user_print("📸 Capturing a screenshot for OCR…")
        debug_log("screenshot: capturing OCR...", "screenshot")
        # Inline OCR capture logic (previously in separate helper)
        ocr_text: str = ""
        sc = shutil.which("screencapture")
        if not sc:
            return ToolExecutionResult(
                success=False, reply_text=None,
                error_message="Capture d'écran non disponible : commande screencapture absente."
            )
        tmpdir = tempfile.mkdtemp(prefix="atlas_ocr_")
        png_path = os.path.join(tmpdir, "shot.png")
        try:
            cmd = [sc, "-i", png_path]
            try:
                ret = subprocess.run(cmd)
            except OSError:
                ret = None
            if not ret or ret.returncode != 0 or not os.path.exists(png_path):
                return ToolExecutionResult(
                    success=False, reply_text=None,
                    error_message="Capture annulée ou impossible."
                )
            tess = shutil.which("tesseract")
            if not tess:
                return ToolExecutionResult(
                    success=False, reply_text=None,
                    error_message="OCR indisponible : Tesseract absent."
                )
            try:
                import pytesseract  # type: ignore
                from PIL import Image  # type: ignore
                with Image.open(png_path) as im:
                    text = pytesseract.image_to_string(im)
                    if text and text.strip():
                        ocr_text = text.strip()
            except Exception as exc:
                debug_log(f"screenshot: OCR failed: {type(exc).__name__}", "screenshot")
                return ToolExecutionResult(
                    success=False, reply_text=None,
                    error_message="La reconnaissance du texte a échoué."
                )
        finally:
            try:
                if os.path.exists(png_path):
                    os.remove(png_path)
                os.rmdir(tmpdir)
            except Exception:
                pass
        debug_log(f"screenshot: ocr_chars={len(ocr_text)}", "screenshot")
        context.user_print("✅ Screenshot processed.")
        # Return raw OCR text as tool result (no LLM processing here)
        return ToolExecutionResult(success=True, reply_text=ocr_text or "Aucun texte détecté.")
