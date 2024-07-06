from dateutil.parser import parse
from beancount.ingest import importer
from datetime import datetime

from china_bean_importers.common import *


class BaseImporter(importer.ImporterProtocol):
    def __init__(self, config) -> None:
        super().__init__()
        self.config: dict = config
        self.match_keywords: list[str] = None
        self.file_account_name: str = None
        self.full_content: str = ""
        self.content: list[str] = []
        self.start: datetime = None
        self.end: datetime = None
        self.filetype: str = None

    def identify(self, file):
        raise "Unimplemented"

    def parse_metadata(self, file):
        raise "Unimplemented"

    def file_account(self, file):
        if self.file_account_name is None:
            raise "file_account_name not set"
        return self.file_account_name

    def file_date(self, file):
        return self.start

    def file_name(self, file):
        assert self.filetype is not None
        if self.end:
            return f"to.{self.end.date().isoformat()}.{self.filetype}"

    # common methods for table-based import
    def extract(self, file, existing_entries=None):
        return list(
            filter(
                lambda x: x is not None,
                [
                    self.generate_tx(r, i, file)
                    for i, r in enumerate(self.extract_rows())
                ],
            )
        )

    def extract_rows(self) -> list[list[str]]:
        raise "Unimplemented"

    def generate_tx(self, row: list[str], lineno: int, file):
        raise "Unimplemented"


class CsvImporter(BaseImporter):
    def __init__(self, config) -> None:
        super().__init__(config)
        self.encoding: str = "utf-8"
        self.filetype = "csv"

    def identify(self, file):
        if self.match_keywords is None:
            raise "match_keywords not set"
        try:
            with open(file.name, "r", encoding=self.encoding) as f:
                self.full_content = f.read()
                self.content = []
                for ln in self.full_content.splitlines():
                    if (l := ln.strip()) != "":
                        self.content.append(l)
                if "csv" in file.name and all(
                    map(lambda c: c in self.full_content, self.match_keywords)
                ):
                    self.parse_metadata(file)
                    return True
        except BaseException:
            return False


class PdfImporter(BaseImporter):
    def __init__(self, config) -> None:
        import re

        super().__init__(config)
        self.filetype = "pdf"
        self.column_offsets: list[int] = None
        self.content_start_keyword: str = None
        self.content_start_regex = None
        self.content_end_keyword: str = None
        self.content_end_regex = None

    def identify(self, file):
        if self.match_keywords is None:
            raise "match_keywords not set"

        if "pdf" not in file.name.lower():
            return False

        doc = open_pdf(self.config, file.name)
        if doc is None:
            return False

        self.full_content = ""
        self.content = []
        for page in doc:
            self.content.extend(page.get_text("words"))
            self.full_content += page.get_text("text")

        if all(map(lambda c: c in self.full_content, self.match_keywords)):
            self.parse_metadata(file)
            return True

    def extract_rows(self):
        assert self.column_offsets
        assert self.content_start_keyword or self.content_start_regex
        assert self.content_end_keyword or self.content_end_regex

        entries = []
        parts = []
        valid = False
        last_y0 = 0
        last_col = -1

        for x0, y0, x1, y1, content, block_no, line_no, word_no in self.content:
            content = content.strip()

            if not valid and (
                (self.content_start_keyword and self.content_start_keyword in content)
                or (
                    self.content_start_regex and self.content_start_regex.match(content)
                )
            ):
                valid = True
            elif valid and (
                (self.content_end_keyword and self.content_end_keyword in content)
                or (self.content_end_regex and self.content_end_regex.match(content))
            ):
                valid = False
            elif valid:
                # find current column
                for i, off in enumerate(self.column_offsets):
                    if x0 >= off:
                        curr_col = i
                if curr_col > last_col:
                    # new column in existing row
                    parts.append(content)
                elif curr_col == last_col:
                    # same column in existing row
                    if y0 == last_y0:
                        # no newline
                        parts[-1] = parts[-1] + " " + content
                    else:
                        # newline
                        parts[-1] = parts[-1] + content
                else:
                    # new row
                    if len(parts) > 0:
                        entries.append(parts)
                        parts = []
                    parts.append(content)
                last_y0 = y0
                last_col = curr_col

        if len(parts) > 0:
            entries.append(parts)
            parts = []

        return entries


class PdfTableImporter(BaseImporter):
    def __init__(self, config) -> None:
        import re

        super().__init__(config)
        self.filetype = "pdf"
        self.vertical_lines: list[int] = None
        self.header_first_cell: str = None
        self.header_first_cell_regex = None

    def identify(self, file):
        if self.match_keywords is None:
            raise "match_keywords not set"

        if "pdf" not in file.name.lower():
            return False

        doc = open_pdf(self.config, file.name)
        if doc is None:
            return False
        doc = self.preprocess_doc(doc)

        self.full_content = ""
        self.content = []
        self.doc = doc
        for page in doc:
            self.content.extend(page.get_text("words"))
            self.full_content += page.get_text("text")

        if all(map(lambda c: c in self.full_content, self.match_keywords)):
            self.populate_rows(doc)
            self.parse_metadata(file)
            return True
        else:
            return False

    def preprocess_doc(self, doc):
        return doc

    def populate_rows(self, doc):
        self.rows = []
        for page in doc:
            for tbl in page.find_tables(vertical_lines=self.vertical_lines).tables:
                # TODO: Check vertical offset
                self.rows.extend(
                    filter(lambda x: not self.is_row_filtered(x), tbl.extract())
                )

    def is_row_filtered(self, row):
        if len(row) == 0:
            return True
        if self.header_first_cell is not None and self.header_first_cell == row[0]:
            return True
        if self.header_first_cell_regex is not None and self.header_first_cell.match(
            row[0]
        ):
            return True
        return False

    def extract_rows(self):
        rows = []
        for page in self.doc:
            for tbl in page.find_tables().tables:
                # TODO: Check vertical offset
                rows.extend(
                    map(
                        lambda row: [cell.replace("\n", "").strip() for cell in row],
                        filter(lambda x: not self.is_row_filtered(x), tbl.extract()),
                    )
                )
        return rows
