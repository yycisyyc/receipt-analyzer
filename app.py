import streamlit as st

st.set_page_config(page_title="餐饮工具箱", page_icon="🍽️", layout="centered")

st.title("🍽️ 餐饮工具箱")

st.markdown("""
**👈 请从左侧边栏选择功能：**

---

### 🍚 十五元快餐分析
上传收款助手截图，自动识别并按餐费/打包盒/饮料分类，生成 Excel 报表。

### 📋 餐厅日报表
上传手写日报照片，AI 识别后生成标准格式的 Excel 日报表。

---
*点击左侧边栏中的页面名称即可进入对应功能。*
""")
