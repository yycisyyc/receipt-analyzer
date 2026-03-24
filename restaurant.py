import streamlit as st
import base64
import json
import re
import io
from datetime import datetime
from PIL import Image
from openai import OpenAI
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

VALID_ROOMS = (
    [f"卡{i}" for i in range(1, 7)]
    + ["111", "222", "333", "555", "666", "777", "888", "999"]
    + [f"厅{i}" for i in range(1, 21)]
)

REPORT_PROMPT = """你是一个手写餐厅日报 OCR 助手。请仔细识别这张手写日报照片中的所有信息。

**照片结构说明**：
- 右上角有日期（年/月/日）
- 表格从左到右的列依次是：序号、用餐时间(中/晚)、包间号、营业额、(空列)、收入、付款方式、实际收款
- 表格下方可能有备注信息

**包间号只可能是以下值之一**：
卡1, 卡2, 卡3, 卡4, 卡5, 卡6, 111, 222, 333, 555, 666, 777, 888, 999, 厅1~厅20

**付款方式只可能是以下值（可多选，用"/"分隔）**：
支付宝, 抖音, 微信, 现金, 饿了么, 美团, 收钱吧

请以严格的 JSON 格式输出，结构如下：
{
  "date": "YYYY-MM-DD",
  "rows": [
    {
      "seq": 1,
      "period": "中或晚",
      "period_uncertain": false,
      "room": "包间号",
      "room_uncertain": false,
      "revenue": 数字(营业额),
      "revenue_uncertain": false,
      "income": 数字(收入),
      "income_uncertain": false,
      "payment": "付款方式",
      "payment_uncertain": false,
      "actual": 数字(实际收款),
      "actual_uncertain": false
    }
  ],
  "notes": "底部备注内容，没有则为空字符串"
}

**重要规则**：
1. 只提取有实际数据的行，空行跳过
2. 对于你不确定的字段，将对应的 xxx_uncertain 设为 true
3. 如果某个字段完全看不清，填 null 并标记 uncertain 为 true
4. 日期从右上角识别，格式为 YYYY-MM-DD
5. 营业额和收入是数字，不要带逗号或其他符号
6. 只输出 JSON，不要输出任何其他文字"""


def _img_b64(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def _call_vl(client, b64, prompt):
    c = client.chat.completions.create(
        model="qwen-vl-max",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return c.choices[0].message.content


def _parse_json(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"无法解析:\n{raw[:500]}")


def _has_uncertain(day_data):
    for row in day_data.get("rows", []):
        for key in row:
            if key.endswith("_uncertain") and row[key]:
                return True
    return False


def _build_excel(all_days):
    wb = Workbook()
    border = Border(left=Side(style="thin"), right=Side(style="thin"),
                    top=Side(style="thin"), bottom=Side(style="thin"))
    center = Alignment(horizontal="center", vertical="center")
    hfill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    hfont = Font(bold=True, size=10, color="FFFFFF")
    bfont = Font(bold=True, size=10)
    mfmt = '#,##0.00'

    HEADERS = ["序号", "中餐/晚餐", "包间号", "营业额", "折扣", "收入",
               "手续费", "充值", "实收", "挂账", "挂账收回",
               "会员卡赠送", "会员卡消费", "会员卡余额", "付款方式", "酒水", "备注"]
    WIDTHS = [6, 10, 8, 10, 8, 10, 10, 8, 10, 8, 10, 10, 10, 10, 12, 8, 14]

    sorted_days = sorted(all_days, key=lambda d: d.get("date", ""))
    first_sheet = True

    for day_data in sorted_days:
        date_str = day_data.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            sheet_name = str(dt.day)
        except Exception:
            sheet_name = date_str or "未知"

        if first_sheet:
            ws = wb.active
            ws.title = sheet_name
            first_sheet = False
        else:
            ws = wb.create_sheet(sheet_name)

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            ws["K1"] = f"日期：  {dt.year}  年  {dt.month}  月  {dt.day}  日"
        except Exception:
            ws["K1"] = f"日期：{date_str}"
        ws["K1"].font = bfont

        for ci, (h, w) in enumerate(zip(HEADERS, WIDTHS), 1):
            c = ws.cell(row=2, column=ci, value=h)
            c.font, c.fill, c.alignment, c.border = hfont, hfill, center, border
            ws.column_dimensions[c.column_letter].width = w

        for ri in range(3, 28):
            ws.cell(row=ri, column=1, value=ri - 2).border = border
            ws.cell(row=ri, column=1).alignment = center
            for ci in range(2, 18):
                ws.cell(row=ri, column=ci).border = border
                ws.cell(row=ri, column=ci).alignment = center

        for row in day_data.get("rows", []):
            seq = row.get("seq", 0)
            if seq < 1 or seq > 25:
                continue
            r = seq + 2
            revenue = row.get("revenue")
            income = row.get("income")
            actual = row.get("actual")

            ws.cell(row=r, column=2, value=row.get("period", ""))
            ws.cell(row=r, column=3, value=row.get("room", ""))
            if revenue is not None:
                ws.cell(row=r, column=4, value=revenue).number_format = mfmt
            if revenue is not None and income is not None and revenue - income > 0:
                ws.cell(row=r, column=5, value=round(revenue - income, 2)).number_format = mfmt
            if income is not None:
                ws.cell(row=r, column=6, value=income).number_format = mfmt
                ws.cell(row=r, column=7, value=f"=F{r}*0.0038").number_format = mfmt
                ws.cell(row=r, column=9, value=f"=F{r}-G{r}").number_format = mfmt
            ws.cell(row=r, column=15, value=row.get("payment", ""))
            if actual is not None:
                ws.cell(row=r, column=9, value=actual).number_format = mfmt

        ws.cell(row=28, column=1, value="合计").font = bfont
        ws.cell(row=28, column=1).border = border
        ws.cell(row=28, column=1).alignment = center
        for ci in range(4, 18):
            cl = ws.cell(row=2, column=ci).column_letter
            c = ws.cell(row=28, column=ci)
            c.value = f"=SUM({cl}3:{cl}27)"
            c.number_format, c.border, c.alignment, c.font = mfmt, border, center, bfont

        ws.cell(row=29, column=1, value="营业收入：").font = bfont
        ws.cell(row=29, column=6, value="采购支出：").font = bfont
        ws.cell(row=30, column=1, value="收钱吧")
        ws.cell(row=30, column=2, value="微信/支付宝")
        ws.cell(row=30, column=6, value="食材（肉，水产，蔬菜，调味品，饮料）")
        ws.cell(row=32, column=2, value="现金")
        ws.cell(row=33, column=2, value="抖音/团券")
        ws.cell(row=33, column=6, value="其它费用")
        ws.cell(row=34, column=2, value="会员卡")
        ws.cell(row=34, column=6, value="设备、维修")
        ws.cell(row=35, column=6, value="水电燃气费")
        ws.cell(row=36, column=6, value="工资")
        ws.cell(row=37, column=6, value="营销")
        ws.cell(row=38, column=1, value="合计").font = bfont
        ws.cell(row=38, column=3, value="=SUM(C30:C36)")

        notes = day_data.get("notes", "")
        if notes:
            ws.cell(row=29, column=10, value=f"备注：{notes}")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ========== UI 入口 ==========

def run():
    st.title("📋 餐厅日报表")
    st.caption("上传手写日报照片，AI 识别后生成标准 Excel 日报表")

    if st.button("⬅️ 返回主页"):
        st.session_state.current_page = "home"
        st.rerun()

    api_key = st.secrets.get("DASHSCOPE_API_KEY", "") if hasattr(st, "secrets") else ""
    if not api_key:
        api_key = st.text_input("请输入阿里云百炼 API Key（sk- 开头）", type="password")
    if not api_key:
        st.info("请先配置 API Key 才能使用。")
        st.stop()

    if "restaurant_results" not in st.session_state:
        st.session_state.restaurant_results = None
    if "restaurant_confirmed" not in st.session_state:
        st.session_state.restaurant_confirmed = False

    # --- Step 1: 上传 ---
    uploaded = st.file_uploader("上传手写日报照片（可多选）", type=["png", "jpg", "jpeg"],
                                accept_multiple_files=True, help="每张照片对应一天的手写日报")

    if uploaded and not st.session_state.restaurant_results:
        st.caption(f"已上传 {len(uploaded)} 张照片")
        if st.button("🚀 开始识别", type="primary"):
            client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
            all_days = []
            prog = st.progress(0, text="正在识别中...")
            total = len(uploaded)
            for idx, f in enumerate(uploaded):
                prog.progress(idx / total, text=f"正在识别第 {idx+1}/{total} 张: {f.name}...")
                image = Image.open(f)
                try:
                    raw = _call_vl(client, _img_b64(image), REPORT_PROMPT)
                    day = _parse_json(raw)
                    day["_filename"] = f.name
                    all_days.append(day)
                except Exception as e:
                    st.error(f"识别 {f.name} 失败: {e}")
            prog.progress(1.0, text="全部识别完成！")
            st.session_state.restaurant_results = all_days
            st.session_state.restaurant_confirmed = False
            st.rerun()

    # --- Step 2 & 3: 确认 ---
    if st.session_state.restaurant_results and not st.session_state.restaurant_confirmed:
        all_days = st.session_state.restaurant_results
        st.success(f"共识别 **{len(all_days)}** 天的数据，请检查并修改不准确的内容：")
        any_unc = False

        for di, day in enumerate(all_days):
            date_str = day.get("date", "未知日期")
            rows = day.get("rows", [])
            unc = _has_uncertain(day)
            if unc:
                any_unc = True
            icon = "⚠️" if unc else "✅"
            with st.expander(f"{icon} {date_str}（{day.get('_filename','')}）- {len(rows)} 条记录",
                             expanded=unc):
                new_date = st.text_input("日期", value=date_str, key=f"date_{di}", help="YYYY-MM-DD")
                all_days[di]["date"] = new_date

                for ri, row in enumerate(rows):
                    uf = [k.replace("_uncertain", "") for k in row if k.endswith("_uncertain") and row[k]]
                    label = f"**第 {row.get('seq','?')} 行**"
                    if uf:
                        label += f" ⚠️ 不确定: {', '.join(uf)}"
                    st.markdown(label)

                    cols = st.columns([1, 1.2, 1.5, 1.5, 1.5, 2])
                    with cols[0]:
                        row["period"] = st.selectbox("餐段", ["中", "晚"], key=f"p_{di}_{ri}",
                                                     index=0 if row.get("period") == "中" else 1)
                    with cols[1]:
                        rv = row.get("room", "")
                        opts = [""] + VALID_ROOMS
                        try: idx = opts.index(rv)
                        except ValueError: opts.insert(1, rv); idx = 1
                        row["room"] = st.selectbox("包间号", opts, index=idx, key=f"r_{di}_{ri}")
                    with cols[2]:
                        row["revenue"] = st.number_input("营业额", value=float(row.get("revenue") or 0),
                                                         step=1.0, key=f"rv_{di}_{ri}")
                    with cols[3]:
                        row["income"] = st.number_input("收入", value=float(row.get("income") or 0),
                                                        step=1.0, key=f"ic_{di}_{ri}")
                    with cols[4]:
                        row["actual"] = st.number_input("实收", value=float(row.get("actual") or 0),
                                                        step=1.0, key=f"ac_{di}_{ri}")
                    with cols[5]:
                        row["payment"] = st.text_input("付款方式", value=row.get("payment", ""),
                                                       key=f"pm_{di}_{ri}", help="多个用/分隔")

                all_days[di]["notes"] = st.text_area("备注", value=day.get("notes", ""),
                                                     key=f"n_{di}", height=68)

        if any_unc:
            st.warning("⚠️ 有标记为不确定的字段，请检查后确认。")
        if st.button("✅ 确认无误，生成报表", type="primary"):
            st.session_state.restaurant_results = all_days
            st.session_state.restaurant_confirmed = True
            st.rerun()

    # --- Step 4 & 5: 生成 & 下载 ---
    if st.session_state.restaurant_confirmed and st.session_state.restaurant_results:
        st.success("报表生成完成！")
        excel = _build_excel(st.session_state.restaurant_results)
        st.download_button("📥 下载餐厅日报表", data=excel,
                           file_name=f"餐厅日报表_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary")
        if st.button("🔄 重新开始"):
            st.session_state.restaurant_results = None
            st.session_state.restaurant_confirmed = False
            st.rerun()
