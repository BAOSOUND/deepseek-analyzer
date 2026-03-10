"""
DeepSeek 引用提取器
稳定版本 - 使用简单的状态显示
"""

import streamlit as st
import asyncio
import pandas as pd
from datetime import datetime
import sys
import os
import base64
import subprocess
from pathlib import Path
import json

# ===== 云端部署：安装playwright浏览器 =====
def setup_playwright():
    """确保playwright浏览器已安装"""
    try:
        # 直接输出到终端，不经过Streamlit
        print("📦 正在检查playwright浏览器...")
        
        # 设置 Playwright 浏览器安装路径
        cache_dir = Path.home() / ".cache" / "ms-playwright"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(cache_dir)
        
        # 检查浏览器是否已存在
        browser_path = cache_dir / "chromium-1091" / "chrome-linux" / "chrome"
        if browser_path.exists():
            print("✅ 浏览器已存在")
            return
        
        # 安装 Chromium
        print("📥 正在安装 Chromium 浏览器...")
        subprocess.run(
            ["playwright", "install", "chromium"],
            check=True,
            timeout=300
        )
        print("✅ playwright浏览器安装成功")
        
    except Exception as e:
        print(f"⚠️ playwright安装警告: {e}")

# 在Linux环境下执行
if sys.platform.startswith('linux'):
    setup_playwright()
# ======================================

# Windows平台修复
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from deepseek_core import DeepSeekAnalyzer

st.set_page_config(
    page_title="DeepSeek 引用提取器",
    page_icon="🔗",
    layout="wide"
)

# 初始化session state
if 'results' not in st.session_state:
    st.session_state.results = []
if 'processing' not in st.session_state:
    st.session_state.processing = False

# 自定义CSS
st.markdown("""
<style>
    /* 旋转加载动画 */
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    .loading-spinner {
        display: inline-block;
        width: 16px;
        height: 16px;
        border: 2px solid #f3f3f3;
        border-top: 2px solid #3498db;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-right: 8px;
        vertical-align: middle;
    }
    .status-text {
        display: inline-block;
        vertical-align: middle;
    }
    
    .share-link {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
        word-break: break-all;
    }
    .share-link a {
        color: #0066cc;
        text-decoration: none;
    }
    .share-link a:hover {
        text-decoration: underline;
    }
    
    /* 表格样式优化 */
    .stDataFrame {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

st.title("🔗 DeepSeek 引用提取器")

# 侧边栏配置
with st.sidebar:
    # 左侧图标
    icon_path = "blsicon.png"
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        html_code = f'<img src="data:image/png;base64,{img_data}" width="120" alt="宝宝爆是俺拉" title="宝宝爆是俺拉">'
        st.markdown(html_code, unsafe_allow_html=True)
    else:
        st.markdown("### 🔗")
    
    st.markdown("---")
    
    st.markdown("### ⚙️ 配置")
    
    show_browser = st.checkbox(
        "👁️ 显示浏览器",
        value=False,
        help="开启后可以看到浏览器操作过程"
    )
    
    delay = st.number_input(
        "⏱️ 问题间隔（秒）",
        min_value=1,
        max_value=30,
        value=2
    )
    
    st.markdown("---")
    
    # 登录状态提示
    cookies_dir = Path("cookies")
    browser_data_dir = Path("cookies/browser_data")
    if browser_data_dir.exists() and any(browser_data_dir.iterdir()):
        st.success("✅ 已保存登录状态")
    else:
        st.warning("⚠️ 首次运行需要登录")
    
    st.markdown("---")
    st.caption("正在提取时需要时间，宝宝请耐心等待哦！")

# 主界面
st.markdown("### 📝 输入问题")

questions_text = st.text_area(
    "问题列表",
    height=200,
    placeholder="每行一个问题，例如：\nPython异步编程的优点\n机器学习入门方法\n2024年AI发展趋势",
    key="questions_input",
    label_visibility="collapsed"
)

questions = [q.strip() for q in questions_text.split('\n') if q.strip()]

# 控制按钮
col1, col2, col3 = st.columns([1, 1, 5])
with col1:
    start_button = st.button(
        "🚀 开始提取",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.processing or not questions
    )

with col2:
    if st.button("🔄 重置", use_container_width=True, disabled=st.session_state.processing):
        st.session_state.results = []
        st.rerun()

# 进度显示
progress_placeholder = st.empty()
status_placeholder = st.empty()

async def run_analysis(questions, show_browser, delay):
    """运行批量分析"""
    st.session_state.processing = True
    
    analyzer = DeepSeekAnalyzer(headless=not show_browser)
    
    try:
        status_placeholder.markdown(
            '<div><span class="loading-spinner"></span><span class="status-text">🚀 正在启动浏览器...</span></div>',
            unsafe_allow_html=True
        )
        await analyzer.start()
        
        status_placeholder.markdown(
            '<div><span class="loading-spinner"></span><span class="status-text">🔐 正在检查登录状态...</span></div>',
            unsafe_allow_html=True
        )
        if not await analyzer.ensure_login():
            status_placeholder.error("❌ 登录失败")
            return
        
        for i, question in enumerate(questions):
            progress = (i + 1) / len(questions)
            progress_placeholder.progress(progress)
            
            status_placeholder.markdown(
                f'<div><span class="loading-spinner"></span><span class="status-text">⏳ 正在处理 [{i+1}/{len(questions)}]: {question[:50]}...</span></div>',
                unsafe_allow_html=True
            )
            
            result = await analyzer.analyze_question(question)
            st.session_state.results.append(result)
            
            if i < len(questions) - 1:
                await asyncio.sleep(delay)
        
        status_placeholder.success(f"✅ 完成！共处理 {len(questions)} 个问题")
        
    except Exception as e:
        status_placeholder.error(f"❌ 出错: {e}")
    finally:
        await analyzer.close()
        st.session_state.processing = False

# 执行分析
if start_button and questions and not st.session_state.processing:
    asyncio.run(run_analysis(questions, show_browser, delay))

# 显示结果
if st.session_state.results:
    st.markdown("---")
    st.markdown("### 📊 提取结果")
    
    # 准备所有引用的扁平化数据
    all_citations_data = []
    
    for idx, result in enumerate(st.session_state.results):
        with st.expander(f"📌 问题 {idx+1}: {result['question']}", expanded=True):
            # 显示分享链接
            share_link = result.get("share_link", "")
            if share_link:
                st.markdown(f"""
                <div class="share-link">
                    🔗 <strong>分享链接：</strong><a href="{share_link}" target="_blank">{share_link}</a>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("⚠️ 未生成分享链接")
            
            # 显示引用来源表格
            citations = result.get("citations", [])
            if citations:
                st.markdown(f"**📚 引用来源 ({len(citations)} 条)**")
                
                # 创建DataFrame
                display_df = pd.DataFrame()
                display_df["序号"] = [c.get("cite_index", i+1) for i, c in enumerate(citations)]
                display_df["网站"] = [c.get("site", "") for c in citations]
                display_df["标题"] = [c.get("title", "") for c in citations]
                display_df["URL"] = [c.get("url", "") for c in citations]
                display_df["摘要"] = [c.get("snippet", "")[:100] + "..." if c.get("snippet") else "" for c in citations]
                
                # 显示表格
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "URL": st.column_config.LinkColumn("URL")
                    }
                )
                
                # 添加到扁平化数据
                for c in citations:
                    all_citations_data.append({
                        "问题": result['question'],
                        "网站": c.get("site", ""),
                        "标题": c.get("title", ""),
                        "URL": c.get("url", ""),
                        "摘要": c.get("snippet", "")
                    })
            else:
                st.info("📭 未找到引用来源")
    
    # 下载扁平化数据
    if all_citations_data:
        st.markdown("---")
        st.markdown("### 📥 导出引用数据")
        
        df_download = pd.DataFrame(all_citations_data)
        st.info(f"📊 共 {len(df_download)} 条引用记录")
        
        with st.expander("预览导出数据"):
            st.dataframe(df_download.head(10), use_container_width=True)
        
        csv = df_download.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        
        st.download_button(
            "📥 下载引用数据 (CSV)",
            csv,
            f"deepseek_citations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv",
            use_container_width=True
        )

# 底部说明
st.markdown("---")
st.caption("正在提取时需要时间，宝宝请耐心等待哦！")
