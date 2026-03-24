import streamlit as st
import base64
import json
import re
import io
import copy
from datetime import datetime
from PIL import Image
from openai import OpenAI
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
VALID_ROOMS = (
    [f"卡{i}" for i in range(1, 7)]
    + ["111", "222", "333", "555", "666", "777", "888", "999"]
    + [f"厅{i}" for i in range(1, 21)]
)

FEE_RATES = {
    "现金": 0, "会员卡": 0,
    "微信": 0.0038, "支付宝": 0.0038, "收钱吧": 0.0038,
    "抖音": 0.06,
    "饿了么": 0, "美团": 0,
}

REPORT_PROMPT = """你是一个手写餐厅日报 OCR 助手。请仔细识别这张手写日报照片中的所有信息。

**照片结构说明**：
- 右上角有日期（年/月/日）
- 表格从左到右的列依次是：序号、用餐时间(中/晚)、包间号、营业额、(空列)、收入、付款方式、实际收款
- 表格下方可能有备注信息
- 一笔订单可能有多种付款方式（如微信+现金），此时需要分别识别每种方式及其对应金额

**包间号只可能是以下值之一**：
卡1, 卡2, 卡3, 卡4, 卡5, 卡6, 111, 222, 333, 555, 666, 777, 888, 999, 厅1~厅20

**付款方式只可能是以下值**：
支付宝, 抖音, 微信, 现金, 饿了么, 美团, 收钱吧, 会员卡

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
      "revenue": 数字(营业额,整单总营业额),
      "revenue_uncertain": false,
      "payments": [
        {"method": "微信", "amount": 500, "uncertain": false},
        {"method": "现金", "amount": 200, "uncertain": false}
      ]
    }
  ],
  "notes": "底部备注内容，没有则为空字符串"
}

**重要规则**：
1. 只提取有实际数据的行，空行跳过
2. 对于你不确定的字段，将对应的 xxx_uncertain 设为 true
3. 如果某个字段完全看不清，填 null 并标记 uncertain 为 true
4. 日期从右上角识别，格式为 YYYY-MM-DD
5. 如果一笔订单只有一种付款方式，payments 数组只有一个元素
6. 如果有多种付款方式，分别列出每种方式和金额
7. 每种付款方式的 amount 是该方式实际收到的金额
8. 只输出 JSON，不要输出任何其他文字"""

# ---------------------------------------------------------------------------
# 样式常量
# ---------------------------------------------------------------------------
_BORDER = Border(left=Side(style="thin"), right=Side(style="thin"),
                 top=Side(style="thin"), bottom=Side(style="thin"))
_CENTER = Alignment(horizontal="center", vertical="center")
_HFILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
_HFONT = Font(bold=True, size=10, color="FFFFFF")
_BFONT = Font(bold=True, size=10)
_MFMT = '#,##0.00'

DAY_HEADERS = ["序号", "中餐/晚餐", "包间号", "营业额", "折扣", "收入",
               "手续费", "充值", "实收", "挂账", "挂账收回",
               "会员卡赠送", "会员卡消费", "会员卡余额", "付款方式", "酒水", "备注"]
DAY_WIDTHS = [6, 10, 8, 10, 8, 10, 10, 8, 10, 8, 10, 10, 10, 10, 12, 8, 14]

SUMMARY_HEADERS = ["序号", "日期", "营业额", "折扣", "收入", "手续费", "充值",
                   "实收", "挂账", "挂账收回", "会员卡赠送", "会员卡消费", "会员卡余额"]
SUMMARY_WIDTHS = [6, 12, 12, 10, 12, 10, 10, 12, 10, 10, 12, 12, 12]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

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


def _get_fee_rate(method: str) -> float:
    method = method.strip()
    return FEE_RATES.get(method, 0.0038)


def _has_uncertain(day_data):
    for row in day_data.get("rows", []):
        for key in row:
            if key.endswith("_uncertain") and row[key]:
                return True
        for p in row.get("payments", []):
            if p.get("uncertain"):
                return True
    return False


def _flatten_rows_for_excel(rows):
    """将带 payments 数组的行展开为每个支付方式一行。同一单序号相同。"""
    flat = []
    for row in rows:
        payments = row.get("payments", [])
        if not payments:
            payments = [{"method": "", "amount": 0}]
        seq = row.get("seq", 0)
        period = row.get("period", "")
        room = row.get("room", "")
        revenue = row.get("revenue") or 0
        is_first = True
        for pay in payments:
            method = pay.get("method", "")
            amount = pay.get("amount") or 0
            is_member = method == "会员卡"
            fee_rate = _get_fee_rate(method)
            income = 0 if is_member else amount
            fee = round(income * fee_rate, 2)
            actual = round(income - fee, 2)

            flat.append({
                "seq": seq,
                "period": period,
                "room": room,
                "revenue": revenue if is_first else 0,
                "income": income,
                "fee": fee,
                "actual": actual,
                "payment": method,
                "amount": amount,
                "is_first": is_first,
            })
            is_first = False
    return flat


def _write_day_sheet(ws, day_data):
    """填写一个日结 sheet。"""
    date_str = day_data.get("date", "")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        ws["K1"] = f"日期：  {dt.year}  年  {dt.month}  月  {dt.day}  日"
    except Exception:
        ws["K1"] = f"日期：{date_str}"
    ws["K1"].font = _BFONT

    for ci, (h, w) in enumerate(zip(DAY_HEADERS, DAY_WIDTHS), 1):
        c = ws.cell(row=2, column=ci, value=h)
        c.font, c.fill, c.alignment, c.border = _HFONT, _HFILL, _CENTER, _BORDER
        ws.column_dimensions[c.column_letter].width = w

    # 预填行 3-27 的边框和序号
    for ri in range(3, 28):
        ws.cell(row=ri, column=1, value=ri - 2).border = _BORDER
        ws.cell(row=ri, column=1).alignment = _CENTER
        for ci in range(2, 18):
            ws.cell(row=ri, column=ci).border = _BORDER
            ws.cell(row=ri, column=ci).alignment = _CENTER

    flat = _flatten_rows_for_excel(day_data.get("rows", []))
    current_excel_row = 3

    for entry in flat:
        if current_excel_row > 27:
            break
        r = current_excel_row
        current_excel_row += 1

        ws.cell(row=r, column=1, value=entry["seq"])
        ws.cell(row=r, column=2, value=entry["period"])
        ws.cell(row=r, column=3, value=entry["room"])

        if entry["is_first"] and entry["revenue"]:
            ws.cell(row=r, column=4, value=entry["revenue"]).number_format = _MFMT

        if entry["is_first"] and entry["revenue"] and entry["income"]:
            discount = round(entry["revenue"] - sum(
                e["income"] for e in flat if e["seq"] == entry["seq"]
            ), 2)
            if discount > 0:
                ws.cell(row=r, column=5, value=discount).number_format = _MFMT

        ws.cell(row=r, column=6, value=entry["income"]).number_format = _MFMT
        ws.cell(row=r, column=7, value=entry["fee"]).number_format = _MFMT
        ws.cell(row=r, column=9, value=entry["actual"]).number_format = _MFMT
        ws.cell(row=r, column=15, value=entry["payment"])

    # Row 28: 合计
    ws.cell(row=28, column=1, value="合计").font = _BFONT
    ws.cell(row=28, column=1).border = _BORDER
    ws.cell(row=28, column=1).alignment = _CENTER
    for ci in range(4, 18):
        cl = get_column_letter(ci)
        c = ws.cell(row=28, column=ci)
        c.value = f"=SUM({cl}3:{cl}27)"
        c.number_format, c.border, c.alignment, c.font = _MFMT, _BORDER, _CENTER, _BFONT

    # Rows 29-38
    ws.cell(row=29, column=1, value="营业收入：").font = _BFONT
    ws.cell(row=29, column=6, value="采购支出：").font = _BFONT
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
    ws.cell(row=38, column=1, value="合计").font = _BFONT
    ws.cell(row=38, column=3, value="=SUM(C30:C36)")

    notes = day_data.get("notes", "")
    if notes:
        ws.cell(row=29, column=10, value=f"备注：{notes}")


def _write_summary_sheet(ws, day_sheets: list[str]):
    """生成汇总 sheet，引用各日 sheet 的合计行。"""
    for ci, (h, w) in enumerate(zip(SUMMARY_HEADERS, SUMMARY_WIDTHS), 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font, c.fill, c.alignment, c.border = _HFONT, _HFILL, _CENTER, _BORDER
        ws.column_dimensions[c.column_letter].width = w

    # day_sheet -> row 28 column mapping:
    # 日sheet D28=营业额, E28=折扣, F28=收入, G28=手续费, H28=充值, I28=实收,
    # J28=挂账, K28=挂账收回, L28=会员卡赠送, M28=会员卡消费, N28=会员卡余额
    day_col_map = {3: "D", 4: "E", 5: "F", 6: "G", 7: "H", 8: "I",
                   9: "J", 10: "K", 11: "L", 12: "M", 13: "N"}

    for idx, day_num_str in enumerate(sorted(day_sheets, key=lambda x: int(x) if x.isdigit() else 99)):
        row = idx + 4
        ws.cell(row=row, column=1, value=idx + 1).border = _BORDER
        ws.cell(row=row, column=1).alignment = _CENTER
        ws.cell(row=row, column=2, value=int(day_num_str) if day_num_str.isdigit() else day_num_str)
        ws.cell(row=row, column=2).border = _BORDER
        ws.cell(row=row, column=2).alignment = _CENTER

        for summary_col, day_col_letter in day_col_map.items():
            c = ws.cell(row=row, column=summary_col)
            c.value = f"='{day_num_str}'!{day_col_letter}28"
            c.number_format = _MFMT
            c.border = _BORDER
            c.alignment = _CENTER

    # 合计行
    total_row = len(day_sheets) + 4
    for ci in range(3, 14):
        cl = get_column_letter(ci)
        c = ws.cell(row=total_row, column=ci)
        c.value = f"=SUM({cl}4:{cl}{total_row - 1})"
        c.number_format = _MFMT
        c.border = _BORDER
        c.font = _BFONT


def _build_excel(all_days, existing_wb=None):
    """生成完整 Excel，支持合并已有工作簿。"""
    if existing_wb:
        wb = existing_wb
        existing_sheets = set(wb.sheetnames)
    else:
        wb = Workbook()
        wb.remove(wb.active)
        existing_sheets = set()

    for day_data in sorted(all_days, key=lambda d: d.get("date", "")):
        date_str = day_data.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            sheet_name = str(dt.day)
        except Exception:
            sheet_name = date_str or "未知"

        if sheet_name in existing_sheets:
            continue

        ws = wb.create_sheet(sheet_name)
        _write_day_sheet(ws, day_data)

    # 生成/更新汇总表
    if "汇总" in wb.sheetnames:
        del wb["汇总"]
    ws_summary = wb.create_sheet("汇总", 0)

    day_sheets = [s for s in wb.sheetnames if s != "汇总" and s.isdigit()]
    _write_summary_sheet(ws_summary, day_sheets)

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
    if "restaurant_existing_wb" not in st.session_state:
        st.session_state.restaurant_existing_wb = None

    # --- 上传区 ---
    st.markdown("#### 上传文件")

    existing_excel = st.file_uploader(
        "上传已有的报表 Excel（可选，用于合并）",
        type=["xlsx"],
        help="之前生成的 Excel 文件，新日期数据会追加进去，已有日期不会被覆盖",
    )

    uploaded_photos = st.file_uploader(
        "上传手写日报照片（可多选）",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        help="每张照片对应一天的手写日报",
    )

    if uploaded_photos and not st.session_state.restaurant_results:
        st.caption(f"已上传 {len(uploaded_photos)} 张照片" +
                   (f" + 1 个已有 Excel" if existing_excel else ""))

        if st.button("🚀 开始识别", type="primary"):
            # 读取已有 Excel
            if existing_excel:
                try:
                    st.session_state.restaurant_existing_wb = load_workbook(existing_excel)
                except Exception as e:
                    st.error(f"读取已有 Excel 失败: {e}")
                    st.session_state.restaurant_existing_wb = None
            else:
                st.session_state.restaurant_existing_wb = None

            client = OpenAI(api_key=api_key,
                            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
            all_days = []
            prog = st.progress(0, text="正在识别中...")
            total = len(uploaded_photos)
            for idx, f in enumerate(uploaded_photos):
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

            # 检查哪些日期已存在
            if st.session_state.restaurant_existing_wb:
                existing = set(st.session_state.restaurant_existing_wb.sheetnames)
                skipped = []
                for day in all_days:
                    try:
                        dt = datetime.strptime(day["date"], "%Y-%m-%d")
                        if str(dt.day) in existing:
                            skipped.append(day["date"])
                    except Exception:
                        pass
                if skipped:
                    st.warning(f"以下日期在已有 Excel 中已存在，将跳过不覆盖：{', '.join(skipped)}")

            st.session_state.restaurant_results = all_days
            st.session_state.restaurant_confirmed = False
            st.rerun()

    # --- 确认编辑 ---
    if st.session_state.restaurant_results and not st.session_state.restaurant_confirmed:
        all_days = st.session_state.restaurant_results
        st.success(f"共识别 **{len(all_days)}** 天的数据，请检查并修改不准确的内容：")

        for di, day in enumerate(all_days):
            date_str = day.get("date", "未知")
            rows = day.get("rows", [])
            unc = _has_uncertain(day)
            icon = "⚠️" if unc else "✅"

            with st.expander(f"{icon} {date_str}（{day.get('_filename','')}）- {len(rows)} 条记录",
                             expanded=unc):
                all_days[di]["date"] = st.text_input(
                    "日期 (YYYY-MM-DD)", value=date_str, key=f"dt_{di}")

                for ri, row in enumerate(rows):
                    uf = []
                    for k in row:
                        if k.endswith("_uncertain") and row[k]:
                            uf.append(k.replace("_uncertain", ""))
                    for p in row.get("payments", []):
                        if p.get("uncertain"):
                            uf.append(f"付款({p.get('method','?')})")

                    label = f"**第 {row.get('seq','?')} 行**"
                    if uf:
                        label += f" ⚠️ 不确定: {', '.join(uf)}"
                    st.markdown(label)

                    # 使用 4 列布局，避免拥挤
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        row["period"] = st.text_input(
                            "餐段(中/晚)", value=row.get("period", ""),
                            key=f"pd_{di}_{ri}")
                    with c2:
                        row["room"] = st.text_input(
                            "包间号", value=row.get("room", ""),
                            key=f"rm_{di}_{ri}")
                    with c3:
                        row["revenue"] = st.number_input(
                            "营业额", value=float(row.get("revenue") or 0),
                            step=1.0, format="%.0f", key=f"rv_{di}_{ri}")
                    with c4:
                        pass

                    # 支付方式（每种一行）
                    payments = row.get("payments", [{"method": "", "amount": 0}])
                    st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;💳 支付明细：")
                    new_payments = []
                    for pi, pay in enumerate(payments):
                        pc1, pc2 = st.columns(2)
                        with pc1:
                            m = st.text_input(
                                f"方式{pi+1}", value=pay.get("method", ""),
                                key=f"pm_{di}_{ri}_{pi}",
                                help="微信/支付宝/现金/抖音/会员卡/饿了么/美团/收钱吧")
                        with pc2:
                            a = st.number_input(
                                f"金额{pi+1}", value=float(pay.get("amount") or 0),
                                step=1.0, format="%.0f", key=f"pa_{di}_{ri}_{pi}")
                        new_payments.append({"method": m, "amount": a})
                    row["payments"] = new_payments

                    # 添加更多支付方式按钮
                    if st.button(f"➕ 添加支付方式", key=f"add_{di}_{ri}"):
                        row["payments"].append({"method": "", "amount": 0})
                        st.rerun()

                    st.markdown("---")

                all_days[di]["notes"] = st.text_area(
                    "备注", value=day.get("notes", ""), key=f"nt_{di}", height=60)

        if st.button("✅ 确认无误，生成报表", type="primary"):
            st.session_state.restaurant_results = all_days
            st.session_state.restaurant_confirmed = True
            st.rerun()

    # --- 生成 & 下载 ---
    if st.session_state.restaurant_confirmed and st.session_state.restaurant_results:
        st.success("报表生成完成！")
        excel = _build_excel(
            st.session_state.restaurant_results,
            existing_wb=st.session_state.restaurant_existing_wb,
        )
        st.download_button(
            "📥 下载餐厅日报表", data=excel,
            file_name=f"餐厅日报表_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary")
        if st.button("🔄 重新开始"):
            st.session_state.restaurant_results = None
            st.session_state.restaurant_confirmed = False
            st.session_state.restaurant_existing_wb = None
            st.rerun()
