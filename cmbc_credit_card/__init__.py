from dateutil.parser import parse
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D
import csv
import re

from china_bean_importers.common import *

FOREIGN_CURR_TX = re.compile(
    r"^(?P<desc>.*?)\s*?(?P<country>[A-Z]+)(?P<amount>[-\d.]+)\s*(?P<currency>[A-Z]+)$"
)


class Importer(importer.ImporterProtocol):

    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self.match_keywords = ["卡号末四位", "交易日"]

    def identify(self, file):
        if file.name.upper().endswith(".CSV"):
            self.type = "csv"
            try:
                with open(file.name, "r", encoding="utf-8") as f:
                    self.full_content = f.read()
                    self.content = []
                    for ln in self.full_content.splitlines():
                        if (l := ln.strip()) != "":
                            self.content.append(l)
                    if "csv" in file.name and all(
                        map(lambda c: c in self.full_content, self.match_keywords)
                    ):
                        return True
                return False
            except:
                return False
        elif file.name.upper().endswith(".EML"):
            self.type = "email"
            from bs4 import BeautifulSoup
            import email
            from email import policy
            import quopri, base64
            from html import unescape

            try:
                raw_email = email.message_from_file(
                    open(file.name), policy=policy.default
                )
                # weird encapsulation
                raw_body_html = unescape(
                    base64.b64decode(
                        raw_email.get_body().get_payload()[0].get_body().get_payload()
                    ).decode("gbk")
                )
                raw_body_html = raw_body_html.replace("\xa0", " ")
                soup = BeautifulSoup(raw_body_html, features="lxml")
                self.body = soup.body
                # find 本期账单日
                stmtDateCell = self.body.select("span#fixBand36")[
                    0
                ].parent.nextSibling.font.text
                self.stmt_date = parse(stmtDateCell)
                return "民生信用卡" in raw_email["Subject"]
            except BaseException:
                return False

    def file_account(self, file):
        return "cmbc_credit_card"

    def file_date(self, file):
        if self.type == "csv":
            if len(self.content) > 1:
                return parse(self.content[1].split(",")[1])
        elif self.type == "email":
            return self.stmt_date
        return super().file_date(file)

    def extract(self, file, existing_entries=None):

        # generate beancount posting entries
        tx = list(
            filter(
                None,
                map(
                    lambda e: self.generate_tx(e[1], e[0], file),
                    enumerate(self.extract_text_entries()),
                ),
            )
        )
        return tx

    def extract_text_entries(self):
        """
        extract entries in format of `generate_tx` from csv / eml
        """

        entries = []
        if self.type == "csv":
            for i, row in enumerate(csv.reader(self.content)):
                if i == 0:
                    continue
                # XXX: we can only default current to CNY
                row.append("CNY")
                # row[0]: tx date in MMDD
                # row[1]: post date in YYYYMMDD
                # year of post date might be different from transaction date
                tx_mon = int(row[0][:2])
                post_mon = int(row[1][4:6])
                post_year = row[1][:4]
                if tx_mon > post_mon:
                    my_warn(
                        f"Transaction date {row[0]} is in the future of post date {row[1]}, try to fix",
                        i,
                        row,
                    )
                    row[0] = f"{post_year - 1}{row[0]}"
                else:
                    row[0] = post_year + row[0]
                entries.append(row[:3] + row[4:])  # skip 授权码
        elif self.type == "email":
            currency_ele = self.body.select("span#fixBand29")[:-1]
            detail_table = self.body.select("span#loopBand3")
            my_assert(
                len(currency_ele) == len(detail_table),
                "Length of currency and detail table mismatch",
                0,
                0,
            )
            for i, (currency, detail) in enumerate(zip(currency_ele, detail_table)):
                currency = match_currency_code(
                    currency.font.text.split()[0]
                )  # "人民币 RMB"
                all_cells = list(map(lambda f: f.text, detail.find_all("font")))
                my_assert(
                    len(all_cells) % 5 == 0,
                    "Detail table should have 5 cells on each line",
                    0,
                    all_cells,
                )
                for j in range(0, len(all_cells), 5):
                    tx_date, post_date, narration, amount, card = all_cells[j : j + 5]
                    # both date in "MM/DD" format
                    stmt_year = self.stmt_date.year
                    stmt_mon = self.stmt_date.month
                    tx_year = (
                        stmt_year if int(tx_date[:2]) <= stmt_mon else stmt_year - 1
                    )
                    tx_date = f"{tx_year}/{tx_date}"
                    post_year = (
                        stmt_year if int(post_date[:2]) <= stmt_mon else stmt_year - 1
                    )
                    post_date = f"{post_year}/{post_date}"
                    entries.append(
                        [tx_date, post_date, card, narration, amount, currency]
                    )

        return entries

    def generate_tx(self, row: list, lineno: int, file):
        #   0      1        2       3    4    5
        # 交易日, 记账日, 卡号末四位, 摘要, 金额, 货币

        # parse data line
        metadata: dict = data.new_metadata(file.name, lineno)
        tags = set()

        # parse some basic info
        date = parse(row[0]).date()
        metadata["post_date"] = parse(row[1]).date()
        units = amount.Amount(D(row[4]), row[5])

        _, _, card_number, orig_narration = row[:4]

        if m := FOREIGN_CURR_TX.match(orig_narration):
            # foreign currency transaction
            metadata["original_amount"] = f'{m.group("amount")} {m.group("currency")}'
            metadata["country_code"] = m.group("country")
            payee = orig_narration
            narration = None
        elif "-" in orig_narration:
            # 支付宝 / 财付通 / etc
            hypen_idx = orig_narration.index("-")
            narration, payee = (
                orig_narration[:hypen_idx].strip(),
                orig_narration[hypen_idx + 1 :].strip(),
            )
        else:
            narration = orig_narration
            payee = None

        units = -units  # inverse sign
        account1 = find_account_by_card_number(self.config, card_number)
        my_assert(account1, f"Unknown card number {card_number}", lineno, row)

        # check blacklist
        if in_blacklist(self.config, orig_narration):
            print(
                f"Item skipped due to blacklist: {date} {orig_narration} [{units}]",
                file=sys.stderr,
            )
            return None

        if m := match_destination_and_metadata(self.config, orig_narration, payee):
            (account2, new_meta, new_tags) = m
            metadata.update(new_meta)
            tags = tags.union(new_tags)
        if account2 is None:
            account2 = unknown_account(self.config, units.number < 0)

        return data.Transaction(
            meta=metadata,
            date=date,
            flag=self.FLAG,
            payee=payee,
            narration=narration,
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
