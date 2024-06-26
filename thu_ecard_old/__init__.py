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
        self.match_keywords = ["终端编号"]
        self.file_account_name = "thu_ecard_old"

    def parse_metadata(self, file):
        if len(self.content) > 2:
            if m := re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2})", self.content[1]):
                self.start = parse(m[1])
            if m := re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2})", self.content[-2]):
                self.end = parse(m[1])

    def extract(self, file, existing_entries=None):
        entries = []

        for lineno, row in enumerate(csv.reader(self.content)):
            row = [col.strip() for col in row]

            #  0      1        2        3       4        5
            # 序号, 交易地点, 交易类型, 终端编号, 交易时间, 交易金额

            # skip table header and footer
            if lineno == 0:
                continue
            elif lineno == len(self.content) - 1:
                break

            # parse data line
            metadata: dict = data.new_metadata(file.name, lineno)
            tags = set()

            # parse some basic info
            time = parse(row[4])
            units = amount.Amount(D(row[5]), "CNY")
            _, payee, type, terminal = row[:4]
            metadata["terminal"] = terminal
            metadata["time"] = time.time().isoformat()
            metadata["payment_method"] = "清华大学校园卡"

            expense = None

            if type == "消费" or "自助缴费" in type:
                expense = True
            elif "领取" in type or type == "支付宝充值":
                expense = False

            my_assert(expense is not None, f"Unknown transaction type", lineno, row)

            if expense:
                units = -units

            source_config = self.config["importers"]["thu_ecard"]
            account1 = source_config["account"]
            account2 = unknown_account(self.config, expense)
            new_account, new_meta, new_tags = match_destination_and_metadata(
                self.config, type, payee
            )
            if new_account:
                account2 = new_account
            metadata.update(new_meta)
            tags = tags.union(new_tags)

            # TODO: obtain a mapping from terminal no. to location?

            # create transaction
            txn = data.Transaction(
                meta=metadata,
                date=time.date(),
                flag=self.FLAG,
                payee=payee,
                narration=type,
                tags=tags,
                links=data.EMPTY_SET,
                postings=[
                    data.Posting(
                        account=account1,
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
