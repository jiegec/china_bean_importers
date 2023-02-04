# china_bean_importers

beancount 导入脚本，数据源：

- 微信支付
- 支付宝（网页端）
- 支付宝（手机端）
- 中国银行信用卡
- 中国银行借记卡
- 招商银行借记卡

## 使用方法

克隆本仓库或作为 submodule：

```shell
git clone https://github.com/jiegec/china_bean_importers
# or
git submodule add git@github.com:jiegec/china_bean_importers.git
```

安装依赖：

```shell
pip3 install -r requirements.txt
```

运行 `cp config.example.py config.py` 复制配置模板，编辑 `config.py` 填入你的配置，**放置在你的项目目录中**。

最后，在导入脚本中按需加入：

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

## 数据源

### 微信支付

导出方法：我的->支付->钱包->账单->常见问题->下载账单->用于个人对账

下载邮件附件，解压得到 csv 文件，如：

```csv
微信支付账单明细,,,,,,,,
微信昵称：[123412341234],,,,,,,,
起始时间：[2022-11-01 00:00:00] 终止时间：[2023-02-01 00:00:00],,,,,,,,
```

### 支付宝（网页端）

导出方法：访问支付宝官网->登录->查看所有交易记录->筛选->下载 Txt 格式账单

下载后，解压得到 txt 文件，如：

```csv
支付宝交易记录明细查询
账号:[123412341234]
起始日期:[2023-01-26 00:00:00]    终止日期:[2023-02-01 00:00:00]
```

但支付宝网页端导出的数据并没有记录付款账户，因此不适合 beancount。

### 支付宝（手机端）

导出方法：我的->账单->...->开具交易流水证明->用于个人对账->申请

下载邮件附件，解压得到 csv 文件，如：

```csv
------------------------支付宝（中国）网络技术有限公司  电子客户回单------------------------
收/支                 ,交易对方                ,对方账号                ,商品说明                ,收/付款方式              ,金额                  ,交易状态                ,交易分类                ,交易订单号     ,商家订单号           ,交易时间            ,
```

### 中国银行信用卡

每个月中行会发送信用卡合并账单，下载附件即可。

### 中国银行借记卡

在中国银行手机客户端，点击更多->助手->交易流水打印->立即申请，记录下 PDF 密码。

下载邮件附件，得到带有密码的 PDF 文件，把密码记录到 `config.py` 中。

### 招商银行借记卡

在中国银行手机客户端，点击首页->流水打印->高级筛选->显示完整卡号->显示收入及支出汇总金额->同意协议并提交，记录下解压密码。

下载邮件附件，输入密码解压 ZIP 文件，得到 PDF。

### 中国建设银行借记卡

手机客户端导出方法：我的->银行卡->管理->明细导出->明细导出申请->选择发送方式为 Excel。申请成功后，查询导出历史，得到解压密码。

下载邮件附件，输入密码解压 ZIP 文件，得到 XLS。

### 微众银行借记卡

手机客户端导出方法：左上角菜单->证明开具->微众卡交易流水。

下载邮件附件，输入密码解压 ZIP 文件，得到 PDF。