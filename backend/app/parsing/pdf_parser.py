from pathlib import Path

from app.parsing.contract import ParsedDocument


class PdfParser:
    def parse(self, path: Path) -> ParsedDocument:
        raise NotImplementedError
