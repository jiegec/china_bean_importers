from dateutil.parser import parse
from beancount.core import data, amount
from beancount.core.number import D
import re

from china_bean_importers.common import *
from china_bean_importers.importer import PdfImporter


def gen_txn(config, file, parts, lineno, flag, card_acc, real_name):
    if len(parts) != 9:
        return

    # parts[1]: 对方户名
    payee = parts[1]
    # parts[2]: 对方账号
    payee_account = parts[2]
    # parts[4]: 摘要
    narration = parts[4]
    # parts[5]: 备注
    if parts[5]:
        narration += " " + parts[5]
    # parts[0]: 记账日期
    date = parse(parts[0]).date()
    # parts[7]: 金额
    units1 = data.Amount(D(parts[7]), "CNY")
    # parts[8]: 余额
    balance = data.Amount(D(parts[8]), "CNY")

    metadata = data.new_metadata(file.name, lineno)
    metadata["balance"] = str(balance)
    tags = set()

    if m := match_destination_and_metadata(config, narration, payee):
        (account2, new_meta, new_tags) = m
        metadata.update(new_meta)
        tags = tags.union(new_tags)
    if account2 is None:
        account2 = unknown_account(config, True)

    # Handle transfer to credit/debit cards
    if payee.startswith(real_name) and payee_account:
        new_account = find_account_by_card_number(config, payee_account)
        if new_account is not None:
            account2 = new_account

    # Append card number
    payee += " " + payee_account

    txn = data.Transaction(
        meta=metadata,
        date=date,
        flag=flag,
        payee=payee,
        narration=narration,
        tags=tags,
        links=data.EMPTY_SET,
        postings=[
            data.Posting(
                account=card_acc,
                units=units1,
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
    return txn


class Importer(PdfImporter):
    def __init__(self, config) -> None:
        import re

        super().__init__(config)
        self.match_keywords = ["微众银行"]
        self.file_account_name = "webank_debit_card"
        self.column_offsets = [30, 80, 140, 220, 280, 340, 380, 460, 520]
        self.content_start_keyword = "Counterparty"  # "Counterparty"
        self.content_end_regex = re.compile(
            r"^(打印时间)$"
        )
        self.content_end_keyword = "————"  # match last page

    def parse_metadata(self, file):
        match = re.search(r"Account Name：\n(\w+)", self.full_content)
        assert match
        self.real_name = match[1]

        match = re.search(r"Account/Card No.：([0-9]{19})", self.full_content)
        assert match
        card_number = match[1]
        self.card_acc = find_account_by_card_number(self.config, card_number[-4:])
        my_assert(self.card_acc, f"Unknown card number {card_number}", 0, 0)

    def generate_tx(self, row, lineno, file):
        return gen_txn(
            self.config, file, row, lineno, self.FLAG, self.card_acc, self.real_name
        )
