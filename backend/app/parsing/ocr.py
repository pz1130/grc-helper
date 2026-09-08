"""OCR fallback for PDFs without a usable text layer."""

from pathlib import Path

from app.parsing.contract import ParseError

OCR_CONFIDENCE_THRESHOLD = 0.70
_DPI = 200


def ocr_pdf(path: Path) -> tuple[list[str], float]:
    """Return OCR words as lines and the average confidence in the 0-1 range."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise ParseError(
            "该 PDF 没有文本层，需要 OCR，但容器内未安装 tesseract/poppler。"
            "请改用「手动粘贴纯文本」兜底，或在镜像中安装这两个依赖。"
        ) from exc

    lines: list[str] = []
    confidences: list[float] = []
    for image in convert_from_path(str(path), dpi=_DPI):
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        for value, raw_confidence in zip(data["text"], data["conf"], strict=False):
            if not value.strip():
                continue
            lines.append(value)
            confidence = float(raw_confidence)
            if confidence >= 0:
                confidences.append(confidence / 100.0)

    average = sum(confidences) / len(confidences) if confidences else 0.0
    return lines, average
