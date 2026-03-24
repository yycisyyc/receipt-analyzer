import streamlit as st

st.set_page_config(page_title="餐饮工具箱", page_icon="🍽️", layout="centered")

st.title("🍽️ 餐饮工具箱")
st.markdown("请从左侧边栏选择功能，或点击下方卡片进入：")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🍚 十五元快餐分析")
    st.markdown("上传收款助手截图，自动识别并按餐费/打包盒/饮料分类，生成 Excel 报表。")
    st.page_link("pages/1_快餐分析.py", label="进入快餐分析", icon="🍚")

with col2:
    st.markdown("### 📋 餐厅日报表")
    st.markdown("上传手写日报照片，AI 识别后生成标准格式的 Excel 日报表/月报表。")
    st.page_link("pages/2_餐厅报表.py", label="进入餐厅报表", icon="📋")
