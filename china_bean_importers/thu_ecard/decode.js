const options = {
  "starttime": "2023-12-01",
  "endtime": "2024-12-31",
  "idserial": "999999999",
  "pageSize": 1000000,
  "pageNumber": 0,
  "tradetype": "-1",
};
const r = await fetch("https://card.tsinghua.edu.cn/business/querySelfTradeList", {
  "headers": {
      "content-type": "application/json",
  },
  "body": JSON.stringify(options),
  "method": "POST",
  "mode": "cors",
  "credentials": "include"
});

const encryptedData = (await r.json()).data;
const decryptedData = aesUtil.decrypt(encryptedData.substr(16), encryptedData.substr(0, 16));
const result = decryptedData.resultData.rows;
result.sort((a, b) => b.txdate.localeCompare(a.txdate));

console.log(result);
