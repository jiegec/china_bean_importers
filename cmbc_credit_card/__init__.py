from dateutil.parser import parse
from beancount.core import data, amount
from beancount.core.number import D
import csv
import re

from china_bean_importers.common import *
from china_bean_importers.importer import CsvImporter

class Importer(CsvImporter):

    def __init__(self, config) -> None:
        super().__init__(config)
        self.match_keywords = ['卡号末四位', '授权码']
        self.file_account_name = 'cmbc_credit_card'

    def parse_metadata(self):
        pass

    def extract_rows(self):
        for row in csv.reader(self.content):
            row = [col.strip() for col in row]
            if len(row) != 6:
                continue
            if row[-1] == '摘要':
                continue
            yield row
        
    def generate_tx(self, row: list[str], lineno: int, file):
        
        #   0      1        2        3     4    5
        # 交易日, 记账日, 卡号末四位, 授权码, 金额, 摘要

        # parse data line
        metadata: dict = data.new_metadata(file.name, lineno)
        tags = set()

        # parse some basic info
        date = parse(row[1][:4] + row[0]).date() # XXX: year of accounting date might be different from transaction date
        units = amount.Amount(D(row[4]), "CNY")
        _, _, card_number, _, _, orig_narration = row
        if '-' in orig_narration:
            hypen_idx = orig_narration.index('-')
            narration, payee = orig_narration[:hypen_idx].strip(), orig_narration[hypen_idx+1:].strip()
        else:
            narration = orig_narration
            payee = None

        units = -units # inverse sign
        account1 = find_account_by_card_number(self.config, card_number)
        my_assert(account1, f"Unknown card number {card_number}", lineno, row)

        # check blacklist
        if in_blacklist(self.config, orig_narration):
            print(f"Item skipped due to blacklist: {date} {orig_narration} [{units}]", file=sys.stderr)
            return None

        if m := match_destination_and_metadata(self.config, orig_narration, payee):
            (account2, new_meta, new_tags) = m
            metadata.update(new_meta)
            tags = tags.union(new_tags)
        if account2 is None:
            account2 = unknown_account(self.config, units.number < 0)

        return data.Transaction(meta=metadata, date=date, flag=self.FLAG, payee=payee, narration=narration, tags=tags, links=data.EMPTY_SET, postings=[
                                        data.Posting(account=account1, units=units,
                                                     cost=None, price=None, flag=None, meta=None),
                                        data.Posting(account=account2, units=None,
                                                     cost=None, price=None, flag=None, meta=None),
                                ])
