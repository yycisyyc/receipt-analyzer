import streamlit as st

st.set_page_config(page_title="餐饮工具箱", page_icon="🍽️", layout="centered")

if "current_page" not in st.session_state:
    st.session_state.current_page = "home"

if st.session_state.current_page == "kuaican":
    import kuaican
    kuaican.run()
elif st.session_state.current_page == "restaurant":
    import restaurant
    restaurant.run()
else:
    st.title("🍽️ 餐饮工具箱")
    st.markdown("---")

    col1, col2 = st.columns(2, gap="large")
    with col1:
        if st.button("🍚\n\n**十五元快餐分析**\n\n上传收款助手截图\n自动分类生成报表",
                      use_container_width=True):
            st.session_state.current_page = "kuaican"
            st.rerun()
    with col2:
        if st.button("📋\n\n**餐厅日报表**\n\n上传手写日报照片\nAI识别生成Excel",
                      use_container_width=True):
            st.session_state.current_page = "restaurant"
            st.rerun()
