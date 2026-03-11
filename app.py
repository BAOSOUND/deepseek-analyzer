"""
DeepSeek 引用提取器
优化版 - 修复登录状态和重置按钮
"""

import streamlit as st
import asyncio
import pandas as pd
from datetime import datetime
import sys
import os
import base64
import subprocess
import shutil
from pathlib import Path
import json
from io import StringIO
import contextlib

# ===== 云端部署：安装playwright浏览器 =====
def setup_playwright():
    """确保playwright浏览器已安装"""
    try:
        # 设置 Playwright 浏览器安装路径到用户目录
        cache_dir = Path.home() / ".cache" / "ms-playwright"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(cache_dir)
        
        # 检查浏览器是否已存在
        browser_path = cache_dir / "chromium-1091" / "chrome-linux" / "chrome"
        if browser_path.exists():
            return True
        
        # 安装 Chromium
        subprocess.run(
            ["playwright", "install", "chromium"],
            check=True,
            timeout=300
        )
            
    except Exception as e:
        pass

# 在Linux环境下执行（Streamlit Cloud）
if sys.platform.startswith('linux'):
    setup_playwright()
# ======================================

# Windows平台修复
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from deepseek_core import DeepSeekAnalyzer

# ✅ 必须是第一个 Streamlit 命令
st.set_page_config(
    page_title="DeepSeek 引用提取器",
    page_icon="🔗",
    layout="wide"
)

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
    
    /* 日志区域样式 - 简洁版 */
    .log-container {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 15px;
        height: 300px;
        overflow-y: auto;
        font-family: 'Courier New', monospace;
        font-size: 13px;
        line-height: 1.6;
        margin: 10px 0;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.05);
    }
    .log-line {
        margin: 4px 0;
        padding: 2px 0;
        border-bottom: 1px dotted #dee2e6;
        color: #495057;
    }
    .log-line:last-child {
        border-bottom: none;
    }
    .log-timestamp {
        color: #6c757d;
        font-weight: normal;
        margin-right: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🔗 DeepSeek 引用提取器")

# 初始化session state
if 'results' not in st.session_state:
    st.session_state.results = []
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'reset_trigger' not in st.session_state:
    st.session_state.reset_trigger = 0
if 'login_status' not in st.session_state:
    st.session_state.login_status = False
if 'log_expanded' not in st.session_state:
    st.session_state.log_expanded = False
if 'analysis_task' not in st.session_state:
    st.session_state.analysis_task = None

# ===== 检查登录状态 =====
def check_login_status():
    """检查是否有真实的登录数据"""
    browser_data_dir = Path("cookies/browser_data")
    if not browser_data_dir.exists():
        return False
    
    # 检查是否有Local Storage数据（真正的登录凭证）
    local_storage = browser_data_dir / "Local Storage" / "leveldb"
    if local_storage.exists() and any(local_storage.iterdir()):
        # 检查是否有实际的登录token文件
        for file in local_storage.iterdir():
            if file.stat().st_size > 1000:  # 真正的登录数据通常大于1KB
                return True
    
    # 检查是否有Cookies文件
    cookies_file = browser_data_dir / "Cookies"
    if cookies_file.exists() and cookies_file.stat().st_size > 500:  # 真正的cookies文件大于500B
        return True
    
    return False

# ===== 清除登录状态 =====
def clear_login_status():
    """清除保存的登录数据"""
    browser_data_dir = Path("cookies/browser_data")
    if browser_data_dir.exists():
        shutil.rmtree(browser_data_dir)
        st.session_state.login_status = False
        st.rerun()

# 更新登录状态
st.session_state.login_status = check_login_status()

# 侧边栏配置
with st.sidebar:
    # ===== 左侧图标 =====
    icon_path = "blsicon.png"
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        html_code = f'<img src="data:image/png;base64,{img_data}" width="120" alt="宝宝爆是俺拉" title="宝宝爆是俺拉">'
        st.markdown(html_code, unsafe_allow_html=True)
    else:
        st.markdown("### 🔗")
    
    st.markdown("---")
    
    # ===== 登录状态显示 =====
    st.markdown("### 🔐 登录状态")
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.session_state.login_status:
            st.success("✅ 已登录")
        else:
            st.warning("⚠️ 未登录")
    
    with col2:
        if st.session_state.login_status:
            if st.button("🗑️ 清除", use_container_width=True):
                clear_login_status()
    
    st.markdown("---")
    
    # ===== 配置选项 =====
    st.markdown("### ⚙️ 配置")
    
    show_browser = st.checkbox(
        "👁️ 显示浏览器",
        value=False
    )
    
    delay = st.number_input(
        "⏱️ 问题间隔（秒）",
        min_value=1,
        max_value=30,
        value=2
    )
    
    st.markdown("---")
    st.caption("正在提取时需要时间，宝宝请耐心等待哦！")

# 主界面
st.markdown("### 📝 输入问题")

questions_text = st.text_area(
    "问题列表",
    height=150,
    placeholder="每行一个问题",
    key=f"questions_input_{st.session_state.reset_trigger}",
    label_visibility="collapsed"
)

questions = [q.strip() for q in questions_text.split('\n') if q.strip()]

# 控制按钮
col1, col2, col3 = st.columns([1, 1, 5])
with col1:
    # 开始按钮：默认激活，只有processing时禁用
    start_button = st.button(
        "🚀 开始提取",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.processing or not questions
    )

with col2:
    # 重置按钮：始终可用，点击后清除所有状态
    if st.button("🔄 重置", use_container_width=True):
        # 如果有正在运行的任务，强制停止
        if st.session_state.processing:
            st.session_state.processing = False
        
        # 清除所有数据
        st.session_state.results = []
        st.session_state.logs = []
        st.session_state.reset_trigger += 1  # 清空输入框
        
        # 重新运行以刷新界面
        st.rerun()

# 进度显示
progress_placeholder = st.empty()
status_placeholder = st.empty()

# ===== 日志显示区域 - 默认收起 =====
with st.expander("📋 运行日志", expanded=st.session_state.log_expanded):
    log_placeholder = st.empty()

# ===== 精简版日志捕获类 =====
class LogCapture:
    def __init__(self, placeholder, logs_list):
        self.placeholder = placeholder
        self.logs_list = logs_list
        
    def write(self, message):
        if message.strip():
            timestamp = datetime.now().strftime("%H:%M:%S")
            lines = message.strip().split('\n')
            for line in lines:
                if line.strip():
                    log_entry = f"[{timestamp}] {line.strip()}"
                    self.logs_list.append(log_entry)
            
            if len(self.logs_list) > 50:
                self.logs_list[:] = self.logs_list[-50:]
            
            self.update_display()
    
    def flush(self):
        pass
    
    def update_display(self):
        log_html = '<div class="log-container">'
        for log in self.logs_list[-30:]:
            if ']' in log:
                time_part = log[:log.index(']')+1]
                msg_part = log[log.index(']')+1:].strip()
            else:
                time_part = ""
                msg_part = log
            
            log_html += f'<div class="log-line"><span class="log-timestamp">{time_part}</span>{msg_part}</div>'
        log_html += '</div>'
        self.placeholder.markdown(log_html, unsafe_allow_html=True)

# 创建日志捕获实例
log_capture = LogCapture(log_placeholder, st.session_state.logs)

async def run_analysis(questions, show_browser, delay):
    """运行批量分析"""
    st.session_state.processing = True
    st.session_state.logs = []
    
    # 自动展开日志区域
    st.session_state.log_expanded = True
    
    analyzer = DeepSeekAnalyzer(headless=not show_browser)
    
    # 重定向 stdout
    old_stdout = sys.stdout
    sys.stdout = log_capture
    
    try:
        log_capture.write("开始批量处理任务")
        
        # 更新顶部状态显示
        status_placeholder.markdown(
            '<div><span class="loading-spinner"></span><span class="status-text">正在检查登录状态...</span></div>',
            unsafe_allow_html=True
        )
        
        await analyzer.start()
        
        if not await analyzer.ensure_login():
            log_capture.write("❌ 登录失败")
            status_placeholder.error("❌ 登录失败")
            return
        
        # 登录成功后更新侧边栏状态
        st.session_state.login_status = True
        
        for i, question in enumerate(questions):
            # 检查是否被重置按钮中断
            if not st.session_state.processing:
                log_capture.write("⏸️ 处理被中断")
                break
            
            progress = (i + 1) / len(questions)
            progress_placeholder.progress(progress)
            
            # 更新顶部状态为处理中
            status_placeholder.markdown(
                f'<div><span class="loading-spinner"></span><span class="status-text">正在处理第 {i+1}/{len(questions)} 个问题...</span></div>',
                unsafe_allow_html=True
            )
            
            result = await analyzer.analyze_question(question)
            st.session_state.results.append(result)
            
            if i < len(questions) - 1:
                await asyncio.sleep(delay)
        
        if st.session_state.processing:  # 如果没被中断
            log_capture.write(f"✅ 全部完成！共处理 {len(questions)} 个问题")
            status_placeholder.success(f"✅ 完成！共处理 {len(questions)} 个问题")
            progress_placeholder.empty()
        
    except Exception as e:
        log_capture.write(f"❌ 出错: {str(e)}")
        status_placeholder.error(f"❌ 出错: {str(e)}")
    finally:
        await analyzer.close()
        st.session_state.processing = False
        sys.stdout = old_stdout

# 执行分析
if start_button and questions and not st.session_state.processing:
    asyncio.run(run_analysis(questions, show_browser, delay))

# 显示结果
if st.session_state.results:
    st.markdown("---")
    st.markdown("### 📊 提取结果")
    
    all_citations_data = []
    
    for idx, result in enumerate(st.session_state.results):
        with st.expander(f"📌 问题 {idx+1}: {result['question']}", expanded=True):
            share_link = result.get("share_link", "")
            if share_link:
                st.markdown(f"""
                <div class="share-link">
                    🔗 <strong>分享链接：</strong><a href="{share_link}" target="_blank">{share_link}</a>
                </div>
                """, unsafe_allow_html=True)
            
            citations = result.get("citations", [])
            if citations:
                st.markdown(f"**📚 引用来源 ({len(citations)} 条)**")
                
                display_df = pd.DataFrame()
                display_df["序号"] = [c.get("cite_index", i+1) for i, c in enumerate(citations)]
                display_df["网站"] = [c.get("site", "") for c in citations]
                display_df["标题"] = [c.get("title", "") for c in citations]
                display_df["URL"] = [c.get("url", "") for c in citations]
                display_df["摘要"] = [c.get("snippet", "")[:100] + "..." if c.get("snippet") else "" for c in citations]
                
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "URL": st.column_config.LinkColumn("URL")
                    }
                )
                
                for c in citations:
                    all_citations_data.append({
                        "问题": result['question'],
                        "网站": c.get("site", ""),
                        "标题": c.get("title", ""),
                        "URL": c.get("url", ""),
                        "摘要": c.get("snippet", "")
                    })
    
    if all_citations_data:
        st.markdown("---")
        st.markdown("### 📥 导出引用数据")
        
        df_download = pd.DataFrame(all_citations_data)
        st.info(f"📊 共 {len(df_download)} 条引用记录")
        
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
