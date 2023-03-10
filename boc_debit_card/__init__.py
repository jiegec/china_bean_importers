from dateutil.parser import parse
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D
import re

from china_bean_importers.common import *


def gen_txn(config, file, parts, lineno, card_number, flag, real_name):

    my_assert(len(parts) == 12, f'Cannot parse line in PDF', lineno, parts)
    # print(parts, file=sys.stderr)
    #    0       1       2    3    4      5      6      7      8       9          10         11
    # 记账日期, 记账时间, 币别, 金额, 余额, 交易名称, 渠道, 网点名称, 附言, 对方账户名, 对方卡号/账号, 对方开户行

    # parts[9]: 对方账户名
    payee = parts[9] if '------' not in parts[9] else 'Unknown'
    # parts[8]: 附言
    narration = parts[5] if '------' in parts[8] else parts[8]
    # parts[0]: 记账日期
    date = parse(parts[0]).date()
    # parts[2]: 币别
    my_assert(parts[2] == "人民币", f"Cannot handle non-CNY currency {parts[2]} currently", lineno, parts)
    # parts[3]: 金额
    units1 = amount.Amount(D(parts[3]), "CNY")

    for b in config['importers']['card_narration_blacklist']:
        if b in narration:
            print(f"Item skipped due to blacklist: {narration}  [{units1}]", file=sys.stderr)
            continue

    metadata = data.new_metadata(file.name, lineno)
    metadata["imported_category"] = parts[5]
    metadata["source"] = parts[6]
    metadata["time"] = parts[1]
    if '------' not in parts[7]:
        metadata["branch_name"] = parts[7]
    if '------' not in parts[10]:
        metadata["payee_account"] = parts[10] 
    if '------' not in parts[11]:
        metadata["payee_branch"] = parts[11]

    tags = set()
    account1 = find_account_by_card_number(config, card_number)
    my_assert(account1, f"Unknown card number {card_number}", lineno, parts)

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
    
    if '退款' in parts[5]:
        tags.add('refund')
 
    txn = data.Transaction(
        meta=metadata, date=date, flag=flag, payee=payee, narration=narration, tags=tags, links=data.EMPTY_SET, postings=[
            data.Posting(account=account1, units=units1,
                         cost=None, price=None, flag=None, meta=None),
            data.Posting(account=account2, units=None,
                         cost=None, price=None, flag=None, meta=None),
        ])
    return txn


class Importer(importer.ImporterProtocol):
    def __init__(self, config) -> None:
        super().__init__()
        self.config = config

    def identify(self, file):
        if "pdf" in file.name:
            doc = open_pdf(self.config, file.name)
            if doc is None:
                return False
            if "中国银行交易流水明细清单" in doc[0].get_text("text"):
                return True
        return False

    def file_account(self, file):
        return "boc_debit_card"

    def file_date(self, file):
        doc = open_pdf(file.name)
        if doc is not None:
            page = doc[0]
            text = page.get_text("blocks")
            for (x0, y0, x1, y1, content, block_no, block_type) in text:
                match = re.match(
                    '交易区间： ([0-9]+-[0-9]+-[0-9]+) 至 ([0-9]+-[0-9]+-[0-9]+)', content)
                if match:
                    return parse(match[1])
        return super().file_date(file)

    def file_name(self, file):
        doc = open_pdf(file.name)
        if doc is not None:
            page = doc[0]
            text = page.get_text("blocks")
            for (x0, y0, x1, y1, content, block_no, block_type) in text:
                match = re.match(
                    '交易区间： ([0-9]+-[0-9]+-[0-9]+) 至 ([0-9]+-[0-9]+-[0-9]+)', content)
                if match:
                    return "to." + match[2] + ".pdf"
        return super().file_name(file)

    def extract(self, file, existing_entries=None):
        entries = []
        doc = open_pdf(self.config, file.name)
        if doc is None:
            return entries

        card_number = None
        begin = False
        lineno = 0
        real_name = None
        real_name_next = False
        for i in range(doc.page_count):
            parts = []
            page = doc[i]
            text = page.get_text("words")
            last_y0 = 0
            # y position of columns
            columns = [46, 112, 172, 234, 300,
                       339, 405, 445, 518, 590, 660, 740]
            for (x0, y0, x1, y1, content, block_no, line_no, word_no) in text:
                # print(f'{x0} {y0} {content}\n', file=sys.stderr)
                lineno += 1
                content = content.strip()

                # Find real name
                if content == "客户姓名：" and real_name is None:
                    real_name_next = True
                elif real_name_next:
                    real_name_next = False
                    real_name = content

                match = re.search('[0-9]{19}', content)
                if match and card_number is None:
                    card_number = int(match[0][-4:])
                    begin = False
                elif card_number:
                    if not begin and "对方开户行" in content:
                        begin = True
                    elif begin and "温馨提示" in content:
                        begin = False
                    elif begin:
                        if x0 < 50:
                            # a new entry
                            if len(parts) > 0:
                                txn = gen_txn(self.config, file, parts, lineno,
                                              card_number, self.FLAG, real_name)
                                entries.append(txn)
                                parts = []

                            # date
                            parts.append(content)
                        else:
                            if len(parts) < len(columns) and x0 >= columns[len(parts)]:
                                # new column
                                parts.append(content)
                            else:
                                # same column
                                if y0 == last_y0:
                                    # no newline
                                    parts[-1] = parts[-1] + " " + content
                                else:
                                    # newline
                                    parts[-1] = parts[-1] + content
                        last_y0 = y0
            if len(parts) > 0:
                txn = gen_txn(self.config, file, parts, lineno,
                              card_number, self.FLAG, real_name)
                entries.append(txn)
                parts = []
        return entries
