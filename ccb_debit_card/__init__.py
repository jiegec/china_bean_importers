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
        self.encoding = "utf8"
        self.match_keywords = ["中国建设银行", "交易明细"]
        self.file_account_name = "ccb_debit_card"

    def parse_metadata(self, file):
        if m := re.search("起始日期:(\\d+)", self.full_content):
            self.start = parse(m[1])
        if m := re.search("结束日期:(\\d+)", self.full_content):
            self.end = parse(m[1])
        match = re.search("卡号/账号:([0-9]{19})", self.full_content)
        my_assert(match, "Invalid file, no card number found!", 0, 0)
        card_number = match[0]
        self.card_acc = find_account_by_card_number(self.config, card_number[-4:])
        my_assert(self.card_acc, f"Unknown card number {card_number}", 0, 0)

    def extract(self, file, existing_entries=None):
        entries = []
        begin = False

        for lineno, row in enumerate(csv.reader(self.content)):
            row = [col.strip() for col in row]
            if len(row) <= 2:
                continue
            #   0        1        2        3       4            5           6           7               8
            # 序号,     摘要,     币别,     钞汇,   交易日期,   交易金额,   账户余额,   交易地点/附言,   对方账号与户名

            if row[0] == "序号" and row[1] == "摘要":
                # skip table header
                begin = True
            elif begin:
                # parse data line
                metadata: dict = data.new_metadata(file.name, lineno)
                tags = set()

                # parse some basic info
                (
                    _,
                    narration,
                    cash,
                    cash_type,
                    time,
                    amt,
                    _,
                    attach,
                    payee,
                ) = row[:10]
                time = parse(time)

                if cash == "人民币元":
                    cash = "CNY"
                else:
                    raise Exception("Unknown currency!")

                units = amount.Amount(D(amt), cash)

                # fill metadata
                if cash_type != "":
                    metadata["cash_type"] = cash_type
                metadata["attach"] = attach

                expense = None
                # determine direction
                if units.number < 0:
                    expense = True
                elif units.number > 0:
                    expense = False

                my_assert(expense is not None, f"Unknown transaction type", lineno, row)

                account2, new_meta, new_tags = match_destination_and_metadata(
                    self.config, narration, payee
                )
                metadata.update(new_meta)
                tags = tags.union(new_tags)
                if account2 is None:
                    account2 = unknown_account(self.config, expense)

                # create transaction
                txn = data.Transaction(
                    meta=metadata,
                    date=time.date(),
                    flag=self.FLAG,
                    payee=payee,
                    narration=narration,
                    tags=tags,
                    links=data.EMPTY_SET,
                    postings=[
                        data.Posting(
                            account=self.card_acc,
                            units=units,
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                        data.Posting(
                            account=account2,
                            units=None,
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                )
                entries.append(txn)

        return entries
