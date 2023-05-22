from dateutil.parser import parse
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D
import re

from china_bean_importers.common import *


def gen_txn(config, file, parts, lineno, card_acc, flag, real_name):

    # print(f"gen_txn: {parts}", file=sys.stderr)
    # return

    my_assert(len(parts) >= 10 or len(parts) == 5, f'Cannot parse line in PDF', lineno, parts)
    #    0       1       2       3      4        5        6      7        8         9           10
    # 凭证类型, 凭证号码, 交易时间, 摘要, 交易金额, 账户余额, 现转标志, 交易渠道, 交易机构, 对方户名/账号, 对方行名
    # either 11/10 items, or only [2:6] is contained

    # fill to 11 fields
    if len(parts) == 5:
        parts = [''] * 2 + parts + [''] * 4
    if len(parts) == 10:
        parts = parts + ['']

    if '/' in parts[9]:
        payee, payee_account = parts[9].split('/')
    else:
        payee, payee_account = parts[9], ''
    narration = parts[3]
    date = parse(parts[2]).date()
    units1 = amount.Amount(D(parts[4]), "CNY")

    skip = False
    for b in config['importers']['card_narration_blacklist']:
        if b in narration:
            print(f"Item in blacklist: {parts[7:10]} {date} {narration}  [{units1}] --- ", file=sys.stderr, end='')
            if units1 < amount.Amount(D(0), "CNY"):
                print(f"Expense skipped", file=sys.stderr)
                skip = True
            else:
                print(f"Income kept in record", file=sys.stderr)
            break
    if skip:
        return None

    metadata = data.new_metadata(file.name, lineno)
    metadata["time"] = parts[2]
    if parts[7] != '':
        metadata["source"] = parts[7]
    if payee_account != '':
        metadata["payee_account"] = payee_account
    if parts[10] != '':
        metadata["payee_branch"] = parts[10]

    tags = set()

    if m := match_destination_and_metadata(config, narration, payee):
        (account2, new_meta, new_tags) = m
        metadata.update(new_meta)
        tags = tags.union(new_tags)
    if account2 is None:
        account2 = unknown_account(config, units1.number < 0)

    # try to find transfer destination account
    if parts[9] != '':
        card_number2 = parts[9][-4:]
        new_account = find_account_by_card_number(config, card_number2)
        if new_account is not None:
            account2 = new_account
    
    if '退款' in parts[5]:
        tags.add('refund')
 
    txn = data.Transaction(
        meta=metadata, date=date, flag=flag, payee=payee, narration=narration, tags=tags, links=data.EMPTY_SET, postings=[
            data.Posting(account=card_acc, units=units1,
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
        if "pdf" in file.name.lower():
            doc = open_pdf(self.config, file.name)
            if doc is None:
                return False
            contents = doc[0].get_text("text")
            self.words = []
            for page in doc:
                self.words.extend(page.get_text("words"))
            if "个人账户对账单" in contents and "民生银行" in contents:
                match = re.search(
                        '起止日期:([0-9]{4}\/[0-9]{2}\/[0-9]{2}).*([0-9]{4}\/[0-9]{2}\/[0-9]{2})', contents)
                assert(match)
                self.start = parse(match[1])
                self.end = parse(match[2])
                return True

        return False

    def file_account(self, file):
        return "cmbc_debit_card"

    def file_date(self, file):
        return self.start

    def file_name(self, file):
        return "to." + self.end + ".pdf"

    def extract(self, file, existing_entries=None):

        entries = []

        card_number = None
        valid = False
        lineno = 0
        real_name = None

        parts = []
        last_y0 = 0
        last_col = -1
        # x offset of columns
        columns = [22, 56, 97, 173, 335, 413, 448, 482, 533, 568, 696]

        for (x0, y0, x1, y1, content, block_no, line_no, word_no) in self.words:
            # print(f'{x0} {y0} {content}\n', file=sys.stderr)
            # continue
            lineno += 1
            content = content.strip()

            # Find real name
            if content.startswith("客户姓名:") and real_name is None:
                real_name = content.split(":")[1].strip()
            if content.startswith("客户账号:") and card_number is None:
                card_number = content.split(":")[1].strip()[-4:]
                card_acc = find_account_by_card_number(self.config, card_number)
                my_assert(card_acc, f"Unknown card number {card_number}", lineno, parts)

            if card_number is None:
                continue

            if not valid and "对方行名" in content:
                valid = True
            elif valid and "______________________" in content:
                valid = False
            elif valid:
                # find current column
                for i, off in enumerate(columns):
                    if x0 >= off:
                        curr_col = i
                # print(f'curr_col: {curr_col}, last_col: {last_col}', file=sys.stderr)
                if x0 < 100 and len(parts) > 3:
                    # a new entry
                    if len(parts) > 0:
                        txn = gen_txn(self.config, file, parts, lineno,
                                        card_acc, self.FLAG, real_name)
                        entries.append(txn)
                        parts = []
                    parts.append(content)
                else:
                    if curr_col != last_col:
                        parts.append(content)
                    else:
                        if y0 == last_y0:
                            # no newline
                            parts[-1] = parts[-1] + " " + content
                        else:
                            # newline
                            parts[-1] = parts[-1] + content
                last_y0 = y0
                last_col = curr_col
        
        if len(parts) > 0:
            txn = gen_txn(self.config, file, parts, lineno,
                            card_acc, self.FLAG, real_name)
            entries.append(txn)
            parts = []

        return list(filter(lambda e: e is not None, entries))
