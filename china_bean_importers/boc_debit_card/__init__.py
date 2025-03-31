from dateutil.parser import parse
from beancount.core import data, amount
from beancount.core.number import D
import re

from china_bean_importers.common import *
from china_bean_importers.importer import PdfImporter


def gen_txn(config, file, parts, lineno, flag, card_acc, real_name):
    # HACK: sometimes parts[10] is so long that it is merged into parts[9] due to PDF parsing
    # check if parts[9] ends with 19 numeric or '-' characters
    if len(parts) == 11:
        if m := re.match(r"^(.*)([\d-]{19})$", parts[9]):
            parts[9] = m.group(1)
            parts.insert(10, m.group(2))

    my_assert(len(parts) == 12, f"Cannot parse line in PDF", lineno, parts)
    # print(parts, file=sys.stderr)
    #    0       1       2    3    4      5      6      7      8       9          10         11
    # 记账日期, 记账时间, 币别, 金额, 余额, 交易名称, 渠道, 网点名称, 附言, 对方账户名, 对方卡号/账号, 对方开户行

    # parts[9]: 对方账户名
    payee = parts[9] if "------" not in parts[9] else "Unknown"
    # parts[8]: 附言
    narration = parts[5] if "------" in parts[8] else parts[8]
    # parts[0]: 记账日期
    date = parse(parts[0]).date()
    # parts[2]: 币别
    currency_code = match_currency_code(parts[2])
    my_assert(
        currency_code is not None,
        f"Cannot handle currency {parts[2]} currently",
        lineno,
        parts,
    )
    # parts[3]: 金额
    units1 = amount.Amount(D(parts[3]), currency_code)
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
        else:
            print(f"Income kept in record", file=sys.stderr)

    metadata = data.new_metadata(file.name, lineno)
    metadata["imported_category"] = parts[5]
    metadata["source"] = parts[6]
    metadata["time"] = parts[1]
    if "------" not in parts[7]:
        metadata["branch_name"] = parts[7]
    if "------" not in parts[10]:
        metadata["payee_account"] = parts[10]
    if "------" not in parts[11]:
        metadata["payee_branch"] = parts[11]

    tags = set()

    if m := match_destination_and_metadata(config, narration, payee):
        (account2, new_meta, new_tags) = m
        metadata.update(new_meta)
        tags = tags.union(new_tags)
    if account2 is None:
        account2 = unknown_account(config, units1.number < 0)

    # Handle transfer to credit/debit cards
    # parts[9]: 对方账户名
    if payee == real_name:
        # parts[10]: 对方卡号/账号
        card_number2 = parts[10][-4:]
        new_account = find_account_by_card_number(config, card_number2)
        if new_account is not None:
            account2 = new_account

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


class Importer(PdfImporter):
    def __init__(self, config) -> None:
        super().__init__(config)
        self.match_keywords = ["中国银行交易流水明细清单"]
        self.file_account_name = "boc_debit_card"
        self.column_offsets = [
            46,
            112,
            172,
            234,
            300,
            339,
            405,
            445,
            517,
            590,
            660,
            740,
        ]
        self.content_start_keyword = "对方开户行"
        self.content_end_keyword = "温馨提示"

    def parse_metadata(self, file):
        match = re.search(
            r"交易区间：\s*([0-9]+-[0-9]+-[0-9]+)\s*至\s*([0-9]+-[0-9]+-[0-9]+)",
            self.full_content,
        )
        assert match
        self.start = parse(match[1])
        self.end = parse(match[2])

        match = re.search(r"客户姓名：\s*(\w+)", self.full_content)
        assert match
        self.real_name = match[1]

        match = re.search(r"[0-9]{19}", self.full_content)
        assert match
        card_number = match[0]
        self.card_acc = find_account_by_card_number(self.config, card_number[-4:])
        my_assert(self.card_acc, f"Unknown card number {card_number}", 0, 0)

    def generate_tx(self, row, lineno, file):
        return gen_txn(
            self.config, file, row, lineno, self.FLAG, self.card_acc, self.real_name
        )
