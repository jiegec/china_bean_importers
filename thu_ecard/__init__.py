from dateutil.parser import parse
from beancount.core import data, amount
from beancount.core.number import D
import csv

from china_bean_importers.common import *
from china_bean_importers.importer import CsvImporter


class Importer(CsvImporter):
    def __init__(self, config) -> None:
        super().__init__(config)
        self.match_keywords = ["mername"]
        self.file_account_name = "thu_ecard"
        self.all_ids = set()

    def parse_metadata(self, file):
        if len(self.content) > 2:
            if m := common_date_pattern.search(self.content[1]):
                self.end = parse(m[1])
            if m := common_date_pattern.search(self.content[-1]):
                self.start = parse(m[1])

    def extract(self, file, existing_entries=None):
        entries = []

        def to_yuan(fen) -> str:
            from decimal import Decimal

            d = (Decimal(fen) / 100).quantize(Decimal(".01"))
            return d

        for lineno, row in enumerate(csv.reader(self.content)):
            row = [col.strip() for col in row]

            #    0         1         2        3          4          5       6       7
            # summary, posjourno, idserial, txaccno, inputuserid, pcode, poscode, accno
            #    8         9    10      11        12           13      14     15,      16
            # txcode, cardno, txdate, txname, stationcode, identityno, sts, balance, journo
            #   17        18     19    20     21        22       23
            # regdate, departid, id, txamt, meraddr, username, mername

            # skip table header and footer
            if lineno == 0:
                continue
            elif lineno == len(self.content) - 1:
                break

            # detect duplicate items by pos_journo
            pos_journo = row[1].strip()
            if pos_journo != "":
                if pos_journo in self.all_ids:
                    my_warn(f"Duplicate pos_journo detected: {pos_journo}", lineno, row)
                    continue
                self.all_ids.add(pos_journo)

            # parse data line
            metadata: dict = data.new_metadata(file.name, lineno)
            tags = set()

            # parse some basic info
            summary = row[0]
            time = parse(row[10])
            units = amount.Amount(D(to_yuan(row[20])), "CNY")
            balance = amount.Amount(D(to_yuan(row[15])), "CNY")
            payee = row[23]
            addr = row[21]
            tx_type = row[11]
            if summary != tx_type:
                summary = f"{summary}_{tx_type}"

            metadata["balance"] = str(balance)
            metadata["location"] = addr
            metadata["time"] = time.time().isoformat()
            metadata["payment_method"] = "清华大学校园卡"

            expense = None

            if any(["消费", "补卡"], lambda k: k in summary):
                expense = True
            elif any(["充值", "代发", "圈存"], lambda k: k in summary):
                expense = False

            my_assert(expense is not None, f"Unknown transaction type", lineno, row)

            if expense:
                units = -units

            source_config = self.config["importers"]["thu_ecard"]
            account1 = source_config["account"]
            account2 = unknown_account(self.config, expense)
            new_account, new_meta, new_tags = match_destination_and_metadata(
                self.config, summary, payee
            )
            if new_account:
                account2 = new_account
            metadata.update(new_meta)
            tags = tags.union(new_tags)

            # create transaction
            txn = data.Transaction(
                meta=metadata,
                date=time.date(),
                flag=self.FLAG,
                payee=payee,
                narration=summary,
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
