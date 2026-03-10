"""
DeepSeek 引用提取器
只显示引用来源表格和分享链接
"""

import streamlit as st
import asyncio
import pandas as pd
from datetime import datetime
import sys
import os
import base64
import subprocess
import time
from pathlib import Path
import json
from io import StringIO
import contextlib

# ===== 云端部署：安装playwright浏览器 =====
def setup_playwright():
    """确保playwright浏览器已安装"""
    try:
        print("📦 正在检查playwright浏览器...")
        
        # 设置 Playwright 浏览器安装路径到用户目录
        cache_dir = Path.home() / ".cache" / "ms-playwright"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(cache_dir)
        
        print(f"📁 浏览器安装路径: {cache_dir}")
        
        # 检查浏览器是否已存在
        browser_path = cache_dir / "chromium-1091" / "chrome-linux" / "chrome"
        if browser_path.exists():
            print(f"✅ 浏览器已存在: {browser_path}")
            return True
        
        # 安装 Chromium
        print("📥 正在安装 Chromium 浏览器...")
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("✅ playwright浏览器安装成功")
            if result.stdout:
                print(result.stdout)
                
            # 验证安装
            if browser_path.exists():
                print(f"✅ 浏览器验证成功: {browser_path}")
            else:
                print(f"⚠️ 浏览器安装路径不符，查找实际位置...")
                find_result = subprocess.run(
                    ["find", str(cache_dir), "-name", "chrome", "-type", "f"],
                    capture_output=True,
                    text=True
                )
                if find_result.stdout:
                    print(f"🔍 找到浏览器: {find_result.stdout}")
        else:
            print(f"⚠️ 安装失败: {result.stderr}")
            print("🔄 尝试安装所有浏览器...")
            subprocess.run(["playwright", "install"], check=True, timeout=500)
            
    except subprocess.TimeoutExpired:
        print("⏱️ 安装超时，但可能已部分完成")
    except Exception as e:
        print(f"⚠️ playwright安装警告: {e}")
        import traceback
        traceback.print_exc()

# 在Linux环境下执行（Streamlit Cloud）
if sys.platform.startswith('linux'):
    print("🐧 Linux环境检测，开始安装playwright浏览器...")
    setup_playwright()
else:
    print(f"🖥️ Windows环境，跳过playwright安装")
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
    
    /* 日志区域样式 */
    .log-container {
        background-color: #1e1e1e;
        color: #00ff00;
        font-family: 'Courier New', monospace;
        padding: 10px;
        border-radius: 5px;
        height: 200px;
        overflow-y: auto;
        font-size: 12px;
        line-height: 1.4;
        margin: 10px 0;
    }
    .log-line {
        margin: 0;
        white-space: pre-wrap;
        word-wrap: break-word;
    }
    .log-info {
        color: #00ff00;
    }
    .log-warning {
        color: #ffff00;
    }
    .log-error {
        color: #ff0000;
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

# ===== 日志捕获类 =====
class LogCapture:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.logs = []
        
    def write(self, message):
        if message.strip():
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {message.strip()}"
            self.logs.append(log_entry)
            st.session_state.logs.append(log_entry)
            # 只保留最近50条日志
            if len(st.session_state.logs) > 50:
                st.session_state.logs = st.session_state.logs[-50:]
            self.update_display()
    
    def flush(self):
        pass
    
    def update_display(self):
        log_html = '<div class="log-container">'
        for log in st.session_state.logs[-30:]:  # 只显示最近30条
            log_class = "log-line log-info"
            if "❌" in log or "错误" in log or "失败" in log:
                log_class = "log-line log-error"
            elif "⚠️" in log or "警告" in log:
                log_class = "log-line log-warning"
            log_html += f'<div class="{log_class}">{log}</div>'
        log_html += '</div>'
        self.placeholder.markdown(log_html, unsafe_allow_html=True)

# ===== 侧边栏配置 =====
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
    # ==================
    
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
        st.session_state.logs = []
        st.rerun()

# 进度显示
progress_placeholder = st.empty()
status_placeholder = st.empty()

# ===== 日志显示区域 =====
st.markdown("### 📋 运行日志")
log_placeholder = st.empty()

# 初始化日志捕获
log_capture = LogCapture(log_placeholder)

async def run_analysis(questions, show_browser, delay):
    """运行批量分析"""
    st.session_state.processing = True
    st.session_state.logs = []  # 清空旧日志
    
    analyzer = DeepSeekAnalyzer(headless=not show_browser)
    
    # 重定向 print 到日志
    old_stdout = sys.stdout
    sys.stdout = log_capture
    
    try:
        log_capture.write("🚀 正在启动浏览器...")
        status_placeholder.markdown(
            '<div><span class="loading-spinner"></span><span class="status-text">🚀 正在启动浏览器...</span></div>',
            unsafe_allow_html=True
        )
        await analyzer.start()
        
        log_capture.write("🔐 正在检查登录状态...")
        status_placeholder.markdown(
            '<div><span class="loading-spinner"></span><span class="status-text">🔐 正在检查登录状态...</span></div>',
            unsafe_allow_html=True
        )
        if not await analyzer.ensure_login():
            log_capture.write("❌ 登录失败")
            status_placeholder.error("❌ 登录失败")
            return
        
        for i, question in enumerate(questions):
            progress = (i + 1) / len(questions)
            progress_placeholder.progress(progress)
            
            log_capture.write(f"⏳ 正在处理 [{i+1}/{len(questions)}]: {question[:50]}...")
            status_placeholder.markdown(
                f'<div><span class="loading-spinner"></span><span class="status-text">⏳ 正在处理 [{i+1}/{len(questions)}]: {question[:50]}...</span></div>',
                unsafe_allow_html=True
            )
            
            result = await analyzer.analyze_question(question)
            st.session_state.results.append(result)
            
            if result.get("share_link"):
                log_capture.write(f"✅ 获取到分享链接: {result['share_link']}")
            else:
                log_capture.write("⚠️ 未获取到分享链接")
            
            log_capture.write(f"📚 捕获到 {result.get('citation_count', 0)} 条引用")
            
            if i < len(questions) - 1:
                await asyncio.sleep(delay)
        
        log_capture.write(f"✅ 完成！共处理 {len(questions)} 个问题")
        status_placeholder.success(f"✅ 完成！共处理 {len(questions)} 个问题")
        
    except Exception as e:
        log_capture.write(f"❌ 出错: {e}")
        status_placeholder.error(f"❌ 出错: {e}")
    finally:
        await analyzer.close()
        st.session_state.processing = False
        # 恢复标准输出
        sys.stdout = old_stdout

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
