from beancount.ingest.extract import DUPLICATE_META
from collections import defaultdict


def find_wechat_family(new_entries_list, existing_entries):
    # Collect wechat family transactions
    # key: date, postings[0]
    wechat_family = defaultdict(list)
    for key, new_entries in new_entries_list:
        for entry in new_entries:
            if (entry.narration == "亲属卡" or entry.narration == "亲属卡-退款") \
                    and entry.postings[1].account == "Expenses:Family":
                wechat_family[(entry.date, entry.postings[0])].append(entry)

    # Collect corresponding transactions
    corresponding = defaultdict(list)
    for key, new_entries in new_entries_list:
        for entry in new_entries:
            if "财付通" in entry.narration or "微信支付" in entry.narration:
                corresponding[(entry.date, entry.postings[0])].append(entry)

    mod_entries_list = []
    for key, new_entries in new_entries_list:
        mod_entries = []
        for entry in new_entries:
            # Find matching entry
            if (entry.narration == "亲属卡" or entry.narration == "亲属卡-退款") \
                    and entry.postings[1].account == "Expenses:Family":
                if (entry.date, entry.postings[0]) in corresponding:
                    marked_meta = entry.meta.copy()
                    marked_meta[DUPLICATE_META] = True
                    entry = entry._replace(meta=marked_meta)
            elif "财付通" in entry.narration or "微信支付" in entry.narration:
                if (entry.date, entry.postings[0]) in wechat_family:
                    tags = entry.tags.union({"Family"})
                    entry = entry._replace(tags=tags)
            mod_entries.append(entry)
        mod_entries_list.append((key, mod_entries))
    return mod_entries_list
