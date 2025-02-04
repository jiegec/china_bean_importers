# china_bean_importers

[![Test Python package](https://github.com/jiegec/china_bean_importers/actions/workflows/test_package.yml/badge.svg)](https://github.com/jiegec/china_bean_importers/actions/workflows/test_package.yml)

Beancount 导入脚本，支持的数据源包括：

- 微信支付
- 支付宝（网页端、手机端）
- 中国银行信用卡、借记卡
- 招商银行借记卡
- 建设银行借记卡
- 民生银行借记卡、信用卡
- 工商银行借记卡（测试）
- 清华大学校园卡（新、旧）
- 汇丰香港信用卡、储蓄账户

**说明：本项目尚不支持 Beancount 3 或更新的版本。**

## 使用方法

克隆本仓库或作为 submodule：

```shell
git clone https://github.com/jiegec/china_bean_importers
# or
git submodule add git@github.com:jiegec/china_bean_importers.git
```

安装 importer 和依赖：

```shell
pip install --editable .
```

运行 `cp config.example.py config.py` 复制配置模板，编辑 `config.py` 填入你的配置，**放置在你的项目目录中**。

最后，在 beancount 使用的导入脚本中按需加入：

```python
from china_bean_importers import wechat, alipay_web, alipay_mobile, boc_credit_card, boc_debit_card, cmb_debit_card

from china_bean_importer_config import config # your config file name

CONFIG = [
    wechat.Importer(config),
    alipay_web.Importer(config),
    alipay_mobile.Importer(config),
    boc_credit_card.Importer(config),
    boc_debit_card.Importer(config),
    cmb_debit_card.Importer(config),
]
```

## Importer 配置

上面的例子中，每个 Importer 都由全局配置控制行为，格式如 `config.example.py` 所示。其中部分字段的含义包括：

- `importers`：每个 importer 各自需要的配置，通常包括账户映射、分类映射等。其中 `card_narration_whitelist` 和 `card_narration_blacklist` 两个字段适用于各类信用卡 Importer，用于过滤可能在其他 importer 中出现的交易描述（通常是通过支付软件产生的交易）。
- `card_accounts`：记录各类卡账户的最后四位数字，以自动化地进行账户匹配。如有重复，则默认使用第一个找到的。
- `pdf_passwords`：在 importer 遇到加密的 PDF 时，会自动尝试这些密码进行解密。推荐使用工具去除密码，避免后续的麻烦。
- `unknown_expense/income_account`：无法匹配情况下使用的支出/收入账户。
- `detail_mapping`：用于从交易描述、对手等信息中匹配目标账户、标签等信息，是一个 `BillDetailMapping` 的列表，每个 `BDM` 包含字段：
  - `narration_keywords`：用于匹配交易描述
  - `payee_keywords`：用于匹配交易对手，可以使用 `SAME_AS_NARRATION` 来表示与交易描述使用的关键词一致
  - `destination_account`：在匹配时，对账目使用的目标账户
  - `additional_tags/metadata`：在匹配时，在账目上添加的额外标签和元数据
  - `priority`：默认为 0，值越大则优先级越高
  - `match_logic`：默认为 `"OR"`，即交易描述或交易对手任意一个匹配即可；可以设置为 `"AND"`，即交易描述和交易对手都需要匹配

## 可用 Importer

### 微信支付（`wechat`）

导出方法：我的->支付->钱包->账单->常见问题->下载账单->用于个人对账

下载邮件附件，解压得到 csv 文件，如：

```csv
微信支付账单明细,,,,,,,,
微信昵称：[123412341234],,,,,,,,
起始时间：[2022-11-01 00:00:00] 终止时间：[2023-02-01 00:00:00],,,,,,,,
```

### 支付宝（网页端）（`alipay_web`）

导出方法：访问支付宝官网->登录->查看所有交易记录->筛选->下载 Txt 格式账单

下载后，解压得到 txt 文件，如：

```csv
支付宝交易记录明细查询
账号:[123412341234]
起始日期:[2023-01-26 00:00:00]    终止日期:[2023-02-01 00:00:00]
```

但支付宝网页端导出的数据并没有记录付款账户，因此不适合 beancount，**不推荐使用**。

### 支付宝（手机端）（`alipay_mobile`）

导出方法：我的->账单->...->开具交易流水证明->用于个人对账->申请

下载邮件附件，解压得到 csv 文件，如：

```csv
------------------------支付宝（中国）网络技术有限公司  电子客户回单------------------------
收/支                 ,交易对方                ,对方账号                ,商品说明                ,收/付款方式              ,金额                  ,交易状态                ,交易分类                ,交易订单号     ,商家订单号           ,交易时间            ,
```

### 中国银行信用卡（`boc_credit_card`）

每个月中行会发送信用卡合并账单，下载邮件附件 PDF；或者在中国银行手机客户端-信用卡-历史账单-选择月份-发送电子账单，从邮箱保存，获得 EML 格式的文件。

Importer 可自动识别上述两种格式。

### 中国银行借记卡（`boc_debit_card`）

在中国银行手机客户端，点击更多->助手->交易流水打印->立即申请，记录下 PDF 密码。

下载邮件附件，得到带有密码的 PDF 文件，把密码记录到 `config.py` 中，或者使用工具去除密码。

### 中国建设银行借记卡（`ccb_debit_card`）

手机客户端导出方法：我的->银行卡->管理->明细导出->明细导出申请->选择发送方式为 Excel。申请成功后，查询导出历史，得到解压密码。

下载邮件附件，输入密码解压 ZIP 文件，得到 XLS，转换为 CSV 格式。

### 招商银行借记卡（`cmb_debit_card`）

在手机银行客户端，点击首页->流水打印->高级筛选->显示完整卡号->显示收入及支出汇总金额->同意协议并提交，记录下解压密码。

下载邮件附件，输入密码解压 ZIP 文件，得到 PDF。

### 民生银行借记卡（`cmbc_debit_card`）

在手机银行客户端，点击收支明细->（右上角菜单）交易明细->导出（下载电子版明细）->交易类型全部->排版方式横版->同意协议并提交。

下载邮件附件，解压 ZIP 文件，得到 PDF。

### 民生银行信用卡（`cmbc_crebit_card`）

Importer 支持以下两种格式：

1. 民生银行发送至邮箱的电子账单 EML 文件（**推荐**，可自动识别货币）。

2. 手动将查询（[民生银行信用卡](https://creditcard.cmbc.com.cn/home/cn/web/product/index.shtml)-登录-账单查询）的账单转换为 CSV 文件，格式为（带表头，注意各列顺序）：

```csv
交易日,记账日,卡号末四位,授权码,金额,摘要
0104,20230104,XXXX,,-88.88,foo-bar
```

注意此方法默认所有交易货币均为 CNY。

### 汇丰银行（香港）（`hsbc_hk`）

支持汇丰香港储蓄账户/信用卡账单，感谢 [ckyOL](https://blog.ckyol.moe/2023/11/24/HSBCHKcreditCSVImporter/) 提供的经验。

导出方式：登录汇丰网银，点击账户到交易记录页，设定筛选日期进行搜索（信用卡可选择“当期账单”），点击底部下载按钮得到 CSV 文件。导出的文件名必须以 `ACC_` 开头，其中 `ACC` 用于映射不同的账户，需要在 `account_mapping` 配置中存在：

```python
'hsbc_hk': {
    "account_mapping": {
        "One": "Assets:Bank:HSBC",
        "PULSE": "Liabilities:CreditCards:HSBC:Pulse"
    },
}
```

如果在配置中设置 `use_cnh` 为 `True`，则所有人民币的货币符号将记为 CNH，否则默认记为 CNY。

### 清华大学校园卡（旧）（`thu_ecard_old`）

导出方式：校园网环境登录 <ecard.tsinghua.edu.cn>，交易日志查询->导出，并使用 Excel 转存为 CSV 格式。

注意：导出总是包含入学以来所有记录，可根据需要删除此前已经导入的内容。

### 清华大学校园卡（新）（`thu_ecard`）

由于校园卡系统与浏览器交互的数据进行了一定的“加密”（并无实际意义），原始数据的获取需要按照以下步骤进行：

1. 使用统一身份认证登录 card.tsinghua.edu.cn
2. 按 F12 打开浏览器工具，复制 `thu_ecard/decode.js` 的代码，粘贴到控制台中。修改必要的参数：`idserial` 改为本人学工号，`starttime` 和 `endtime` 改为需要的日期范围（闭区间）。然后执行。
3. 将控制台中打印的 JSON 转换为 CSV 格式存储（可使用在线工具 [1](https://data.page/json/csv)、[2](https://www.convertcsv.com/json-to-csv.htm)、[3](https://konklone.io/json/)，或使用 Pandas 等库）。

## 测试 Importer

### 微众银行借记卡（尚未实现）

手机客户端导出方法：左上角菜单->证明开具->微众卡交易流水。

下载邮件附件，输入密码解压 ZIP 文件，得到 PDF。
