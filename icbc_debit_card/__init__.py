from dateutil.parser import parse
from beancount.core import data, amount
from beancount.core.number import D
import re

from china_bean_importers.common import *
from china_bean_importers.importer import PdfTableImporter


def gen_txn(config, file, parts, lineno, flag, card_acc, real_name):
    my_assert(len(parts) == 13, f"Cannot parse line in PDF", lineno, parts)
    # print(parts, file=sys.stderr)
    # 0         1     2     3     4     5     6     7     8              9     10        11        12
    # 交易日期, 帐号, 储种, 序号, 币种, 钞汇, 摘要, 地区, 收入/支出金额, 余额, 对方户名, 对方帐号, 渠道

    payee = parts[10] if "（空）" not in parts[10] else "Unknown"
    narration = parts[6]
    # Split date and time
    date_str = parts[0][:10]
    time_str = parts[0][10:]
    date = parse(date_str).date()

    # parts[2]: 币别
    currency_code = match_currency_code(parts[4])
    my_assert(
        currency_code is not None,
        f"Cannot handle currency {parts[4]} currently",
        lineno,
        parts,
    )

    units1 = amount.Amount(D(parts[8]), currency_code)

    # check blacklist
    if in_blacklist(config, narration):
        print(
            f"Item in blacklist: {date} {narration} [{units1}]",
            file=sys.stderr,
            end=" -- ",
        )
        if units1 < amount.Amount(D(0), currency_code):
            print(f"Expense skipped", file=sys.stderr)
            return None
        elif "退款" in parts[5]:
            print(f"Refund skipped", file=sys.stderr)
            return None
        else:
            print(f"Income kept in record", file=sys.stderr)

    metadata = data.new_metadata(file.name, lineno)
    metadata["time"] = time_str
    metadata["deposit_type"] = parts[2]
    metadata["source"] = parts[12]
    metadata["account"] = parts[1]

    if "（空）" not in parts[11]:
        metadata["payee_account"] = parts[11]

    tags = set()

    if m := match_destination_and_metadata(config, narration, payee):
        (account2, new_meta, new_tags) = m
        metadata.update(new_meta)
        tags = tags.union(new_tags)
    if account2 is None:
        account2 = unknown_account(config, units1.number < 0)

    # TODO: Handle transfer to credit/debit cards
    # if payee == real_name:
    #     # parts[10]: 对方卡号/账号
    #     card_number2 = parts[10][-4:]
    #     new_account = find_account_by_card_number(config, card_number2)
    #     if new_account is not None:
    #         account2 = new_account

    if "退款" in parts[5]:
        tags.add("refund")

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


class Importer(PdfTableImporter):
    def __init__(self, config) -> None:
        super().__init__(config)
        self.match_keywords = ["中国工商银行借记账户历史明细（电子版）"]
        self.file_account_name = "icbc_debit_card"
        self.vertical_lines = None
        self.header_first_cell = "交易日期"

    def parse_metadata(self, file):
        match = re.search(
            r"起止日期：\s*([0-9]+-[0-9]+-[0-9]+)\s*—\s*([0-9]+-[0-9]+-[0-9]+)",
            self.full_content,
        )
        assert match
        self.start = parse(match[1])
        self.end = parse(match[2])

        match = re.search(r"户名：\s*(\w+)", self.full_content)
        assert match
        self.real_name = match[1]

        match = re.search(r"卡号\s*([0-9]{19})", self.full_content)
        assert match
        card_number = match[1]
        self.card_acc = find_account_by_card_number(self.config, card_number[-4:])
        my_assert(self.card_acc, f"Unknown card number {card_number}", 0, 0)

    def generate_tx(self, row, lineno, file):
        return gen_txn(
            self.config, file, row, lineno, self.FLAG, self.card_acc, self.real_name
        )
