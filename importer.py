from beancount.ingest import importer
from datetime import datetime


class CsvImporter(importer.ImporterProtocol):

    def __init__(self, config) -> None:
        super().__init__()
        self.config: dict = config
        self.encoding: str = 'utf-8'
        self.file_account_name: str = None
        self.title_keyword: str = None
        self.full_content: str = ''
        self.content: list[str] = []
        self.start: datetime = None
        self.end: datetime = None

    def identify(self, file):
        if self.title_keyword is None:
            raise 'title_keyword not set'
        try:
            with open(file.name, 'r', encoding=self.encoding) as f:
                full_content = f.read()
                self.content = full_content.splitlines()
                if "csv" in file.name and self.title_keyword in self.content[0]:
                    self.parse_metadata()
                    return True
        except:
            return False

    def parse_metadata(self):
        raise 'Unimplemented'

    def file_account(self, file):
        if self.file_account_name is None:
            raise 'file_account_name not set'
        return self.file_account_name

    def file_date(self, file):
        return self.start

    def file_name(self, file):
        if self.end:
            return f"to.{self.end.date().isoformat()}.csv"

    def extract(self, file, existing_entries=None):
        raise 'Unimplemented'
