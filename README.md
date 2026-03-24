# 十五元快餐 · 收款分析工具

上传收款助手截图，自动识别每笔订单的金额、时间、支付方式，并按餐费 / 打包盒 / 饮料分类，生成 Excel 报表。

## 在线使用

部署完成后，打开网址即可使用，无需安装任何东西。

## 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/yycisyyc/receipt-analyzer.git
cd receipt-analyzer

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
cp secrets.toml.example .streamlit/secrets.toml
# 编辑 .streamlit/secrets.toml，填入你的阿里云百炼 API Key

# 4. 启动
streamlit run app.py
```

浏览器会自动打开 http://localhost:8501

## 部署到 Streamlit Cloud（推荐）

只需操作一次，之后发链接给别人就行：

1. 把这个仓库推到 GitHub（`https://github.com/yycisyyc/receipt-analyzer`）
2. 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 账号登录
3. 点 **New app**，选择仓库 `yycisyyc/receipt-analyzer`，主文件填 `app.py`
4. 点左下角 **Advanced settings**，在 Secrets 里填入：
   ```
   DASHSCOPE_API_KEY = "sk-你的API Key"
   ```
5. 点 **Deploy**，等待部署完成
6. 拿到网址（类似 `https://receipt-analyzer.streamlit.app`），发给需要的人即可

## 分类规则

| 金额情况 | 分类 |
|---------|------|
| 15 的整数倍（15、30、45…） | 全部为餐费 |
| 比 15 的整数倍多 1~n 元（n=餐数） | 多出的算打包盒费（1元/个） |
| 比 15 的整数倍多超过 n 元 | 多出的算饮料费 |

示例：
- 15 元 → 餐费 15
- 16 元 → 餐费 15 + 打包盒 1
- 18 元 → 餐费 15 + 饮料 3
- 30 元 → 餐费 30
- 32 元 → 餐费 30 + 打包盒 2
- 34 元 → 餐费 30 + 饮料 4
