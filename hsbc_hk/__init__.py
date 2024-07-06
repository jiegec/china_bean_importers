from beancount.core import data, amount
from beancount.core.number import D
import csv
from datetime import datetime
from pathlib import Path

from china_bean_importers.common import *
from china_bean_importers.importer import CsvImporter


def parse_date(str):
    DATE_FORMAT = "%d/%m/%Y"
    return datetime.strptime(str, DATE_FORMAT)


class Importer(CsvImporter):

    def __init__(self, config) -> None:
        super().__init__(config)
        self.encoding = "utf-8"
        self.match_keywords = ["Billing currency", "Description"]
        self.file_account_name = "hsbc_hk"

    def identify(self, file):
        acc_name = Path(file.name).stem.split("_")[0]
        if mapping := self.config["importers"]["hsbc_hk"].get("account_mapping"):
            if acc := mapping.get(acc_name):
                self.account1 = acc
            else:
                my_warn(
                    f"Account mapping not found for {acc_name}, skipping...",
                    file.name,
                    "",
                )
                return False
        else:
            raise ValueError("Account mapping not set in importer config")
        return super().identify(file)

    def parse_metadata(self, file):
        self.reader = csv.DictReader(self.content)
        self.parsed_content = list(self.reader)
        if "Transaction date" in self.reader.fieldnames:
            self.type = "Credit"
            self.date_field = "Transaction date"
        elif "Date" in self.reader.fieldnames:
            self.type = "Debit"
            self.date_field = "Date"
        else:
            raise ValueError("Unknown file format")

        # unify date for sorting
        for i, c in enumerate(self.parsed_content):
            c["D"] = parse_date(c[self.date_field])
            c["line_no"] = i + 1

        self.parsed_content = sorted(self.parsed_content, key=lambda x: x["D"])
        self.start = self.parsed_content[0]["D"]
        self.end = self.parsed_content[-1]["D"]

    def extract(self, file, existing_entries=None):
        entries = []
        use_cnh = self.config["importers"]["hsbc_hk"].get("use_cnh", False)

        for c in self.parsed_content:

            # parse data line
            metadata: dict = data.new_metadata(file.name, c["line_no"])
            tags = set()

            line_no = c["line_no"]
            date = c["D"].date()
            currency = c["Billing currency"].strip()
            # use CNH instead of CNY if specified in config
            if currency == "CNY" and use_cnh:
                currency = "CNH"
            units = amount.Amount(D(c["Billing amount"].strip()), currency)
            narration = c["Description"].strip()
            payee = ""

            if "UNIONPAY" in narration:
                metadata["payment_method"] = "云闪付"
            elif "APPLEPAY" in narration:
                metadata["payment_method"] = "Apple Pay"

            if self.type == "Credit":
                status = c["Transaction status"]
                if status != "POSTED":
                    my_warn(f"Unposted transaction status {status}", line_no, c)
                    tags.add("need-confirmation")
                metadata["post_date"] = parse_date(c["Post date"]).date()
                if (country := c["Country / region"].strip()) != "":
                    metadata["country"] = country
                if (area := c["Area / district"].strip()) != "":
                    metadata["area"] = area
                payee = c["Merchant name"].strip()
            elif self.type == "Debit":
                balance = amount.Amount(D(c["Balance"].strip()), currency)
                metadata["balance_after"] = balance

            # find account2
            expense = units.number < 0
            account2 = unknown_account(self.config, expense)
            new_account, new_meta, new_tags = match_destination_and_metadata(
                self.config, narration, payee
            )
            if new_account:
                account2 = new_account
            metadata.update(new_meta)
            tags = tags.union(new_tags)

            # create transaction
            txn = data.Transaction(
                meta=metadata,
                date=date,
                flag=self.FLAG,
                payee=payee,
                narration=narration,
                tags=tags,
                links=data.EMPTY_SET,
                postings=[
                    data.Posting(
                        account=self.account1,
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
