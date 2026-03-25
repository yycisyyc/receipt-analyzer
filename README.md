# 🍽️ 餐饮工具箱

> **👉 [立即在线试用](https://receipt-analyzer-bsuqzitur9gu7zhpgfhpgj.streamlit.app/#bd92b2cb)** — 无需安装，打开即用

本项目包含两个实用的餐饮经营辅助工具，均基于 AI 视觉识别，上传照片即可自动生成 Excel 报表。

---

## 📦 包含的工具

### 🍚 工具一：十五元快餐 · 收款分析

上传收款助手截图，自动识别每笔订单的金额、时间、支付方式，并按 **餐费 / 打包盒 / 饮料** 分类，生成 Excel 报表。

**分类规则：**

| 金额情况 | 分类 |
|---------|------|
| 15 的整数倍（15、30、45…） | 全部为餐费 |
| 比 15 的整数倍多 1\~n 元（n=餐数） | 多出的算打包盒费（1元/个） |
| 比 15 的整数倍多超过 n 元 | 多出的算饮料费 |

示例：
- 15 元 → 餐费 15
- 16 元 → 餐费 15 + 打包盒 1
- 18 元 → 餐费 15 + 饮料 3
- 30 元 → 餐费 30
- 32 元 → 餐费 30 + 打包盒 2
- 34 元 → 餐费 30 + 饮料 4

### 📋 工具二：餐厅日报表

上传手写日报照片，AI 自动识别包间号、营业额、付款方式等信息，一键生成格式规范的 Excel 日报表。

**支持的信息识别：**
- 日期、用餐时间（中/晚）
- 包间号（卡1\~卡6、111\~999、厅1\~厅20）
- 营业额、收入、实际收款
- 付款方式（现金、微信、支付宝、会员卡、抖音、饿了么、美团等）
- 自动计算手续费

---

## 🚀 在线使用

**👉 [点击这里直接使用](https://receipt-analyzer-bsuqzitur9gu7zhpgfhpgj.streamlit.app/#bd92b2cb)**

已部署在 Streamlit Cloud，打开链接即可使用，无需安装任何东西。

---

## 💻 本地运行

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

---

## ☁️ 部署到 Streamlit Cloud

只需操作一次，之后发链接给别人就行：

1. 把这个仓库推到 GitHub（`https://github.com/yycisyyc/receipt-analyzer`）
2. 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 账号登录
3. 点 **New app**，选择仓库 `yycisyyc/receipt-analyzer`，主文件填 `app.py`
4. 点左下角 **Advanced settings**，在 Secrets 里填入：
   ```
   DASHSCOPE_API_KEY = "sk-你的API Key"
   ```
5. 点 **Deploy**，等待部署完成
6. 拿到网址，发给需要的人即可
