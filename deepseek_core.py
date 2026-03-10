"""
DeepSeek 核心自动化模块
只捕获引用来源，生成分享链接
"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

load_dotenv()

class DeepSeekAnalyzer:
    def __init__(self, headless: bool = True, timeout: int = 60):
        self.headless = headless
        self.timeout = timeout * 1000
        self.cookies_dir = Path("cookies")
        self.cookies_dir.mkdir(exist_ok=True)
        self.cookie_file = self.cookies_dir / "cookies.json"
        
        # 使用 persistent context 的目录
        self.user_data_dir = self.cookies_dir / "browser_data"
        self.user_data_dir.mkdir(exist_ok=True)
        
        self.playwright = None
        self.context = None
        self.page = None
        
        # 存储捕获的数据
        self.citation_list = []  # 引用列表
        self.current_share_link = ""  # 当前问题的分享链接
        self.question_count = 0  # 记录问题序号
        self.is_english = False  # 判断是否为英文界面
        
    async def start(self):
        """启动浏览器并设置监听"""
        print("🚀 启动浏览器...")
        self.playwright = await async_playwright().start()
        
        # 启动参数
        launch_options = {
            'headless': self.headless,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        }
        
        # 创建持久化上下文
        self.context = await self.playwright.chromium.launch_persistent_context(
            str(self.user_data_dir),
            **launch_options,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            permissions=['clipboard-read', 'clipboard-write']
        )
        
        # 设置网络监听
        await self.setup_network_listener()
        
        # 获取页面
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        self.page.set_default_timeout(self.timeout)
        
        print("✅ 浏览器启动完成")
        return self
    
    async def setup_network_listener(self):
        """设置网络请求监听器 - 只捕获引用"""
        
        async def handle_response(response):
            """处理响应数据"""
            url = response.url
            
            # 捕获 SSE 流中的引用列表
            if '/api/v0/chat/completion' in url:
                headers = response.headers
                content_type = headers.get('content-type', '')
                
                if 'text/event-stream' in content_type:
                    try:
                        text = await response.text()
                        lines = text.split('\n')
                        
                        for line in lines:
                            if line.startswith('data: '):
                                data_str = line[6:]
                                try:
                                    data = json.loads(data_str)
                                    
                                    # 捕获引用列表
                                    if data.get('p') == 'response/fragments/-1/results':
                                        results = data.get('v', [])
                                        for result in results:
                                            citation = {
                                                'title': result.get('title', ''),
                                                'url': result.get('url', ''),
                                                'site': result.get('site_name', ''),
                                                'snippet': result.get('snippet', ''),
                                                'cite_index': result.get('cite_index', 0)
                                            }
                                            self.citation_list.append(citation)
                                        
                                except json.JSONDecodeError:
                                    pass
                    except Exception as e:
                        pass
        
        self.context.on('response', lambda response: asyncio.create_task(handle_response(response)))
    
    def is_cookies_valid(self):
        """检查是否有持久化数据"""
        if not self.user_data_dir.exists():
            return False
        
        has_files = any(self.user_data_dir.iterdir())
        if has_files:
            print("✅ 发现已保存的浏览器数据")
            return True
        return False
    
    async def load_cookies(self) -> bool:
        """persistent context 自动加载"""
        return self.is_cookies_valid()
    
    async def save_cookies(self):
        """persistent context 自动保存"""
        print("✅ 浏览器数据已自动保存到:", self.user_data_dir)
    
    async def ensure_login(self) -> bool:
        """确保已登录"""
        print("\n========== 开始登录流程 ==========")
        
        print("【1】访问主页...")
        await self.page.goto('https://chat.deepseek.com')
        await asyncio.sleep(1)
        
        print("【2】检查登录状态...")
        try:
            await self.page.wait_for_selector('textarea', timeout=2000)
            print("✅ 已登录，无需再次登录")
            
            # 检测界面语言
            await self.detect_language()
            return True
        except:
            print("🔐 未登录，开始手动登录流程")
        
        print("【3】跳转到登录页...")
        await self.page.goto('https://chat.deepseek.com/sign_in')
        await asyncio.sleep(2)
        
        print("【4】检测登录界面类型...")
        has_inputs = await self.page.evaluate('''
            () => {
                const inputs = document.querySelectorAll('input[type="text"], input[type="password"]');
                return inputs.length >= 2;
            }
        ''')
        
        if has_inputs:
            print("✅ 检测到已经是密码登录界面，直接输入账号密码")
        else:
            print("🔄 检测到社交登录界面，需要切换到密码登录")
            try:
                await self.page.evaluate('''
                    () => {
                        const buttons = document.querySelectorAll('button.ds-sign-in-form__social-button');
                        for (let btn of buttons) {
                            const svg = btn.querySelector('svg');
                            if (svg) {
                                const path = svg.querySelector('path');
                                if (path) {
                                    const d = path.getAttribute('d') || '';
                                    if (d.includes('8.65039')) {
                                        btn.click();
                                        return;
                                    }
                                }
                            }
                        }
                        if (buttons.length >= 2) buttons[1].click();
                    }
                ''')
                print("✅ 已点击密码登录按钮")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"❌ 点击密码登录按钮失败: {e}")
                return False
        
        print("【5】输入账号密码...")
        username = os.getenv("DEEPSEEK_USER")
        password = os.getenv("DEEPSEEK_PWD")
        
        if not username or not password:
            print("❌ 请设置环境变量 DEEPSEEK_USER 和 DEEPSEEK_PWD")
            return False
        
        try:
            await asyncio.sleep(0.5)
            inputs = await self.page.query_selector_all('input')
            print(f"找到 {len(inputs)} 个输入框")
            
            if len(inputs) >= 2:
                await inputs[0].fill(username)
                masked_username = username[:4] + "****" + username[-4:] if len(username) > 8 else "****"
                print(f"✅ 账号已输入: {masked_username}")
                await inputs[1].fill(password)
                print("✅ 密码已输入")
            else:
                print("❌ 输入框不足")
                return False
        except Exception as e:
            print(f"❌ 输入账号密码失败: {e}")
            return False
        
        print("【6】点击登录按钮...")
        try:
            login_texts = ['登录', '登陆', 'Sign in', 'Log in', 'Sign In', 'Log In']
            login_btn = None
            buttons = await self.page.query_selector_all('button')
            
            for btn in buttons:
                btn_text = await btn.text_content()
                if btn_text:
                    btn_text = btn_text.strip()
                    for text in login_texts:
                        if text in btn_text:
                            login_btn = btn
                            print(f"✅ 找到登录按钮: '{btn_text}'")
                            break
                    if login_btn:
                        break
            
            if not login_btn:
                login_btn = await self.page.query_selector('button[type="submit"]')
                if login_btn:
                    print("✅ 找到提交按钮")
            
            if not login_btn and len(buttons) > 0:
                login_btn = buttons[-1]
                print("✅ 使用最后一个按钮")
            
            if login_btn:
                await login_btn.click()
                print("✅ 已点击登录按钮")
            else:
                print("❌ 找不到登录按钮")
                return False
        except Exception as e:
            print(f"❌ 点击登录按钮失败: {e}")
            return False
        
        print("【7】等待登录成功...")
        for i in range(15):
            await asyncio.sleep(1)
            try:
                await self.page.wait_for_selector('textarea', timeout=1000)
                print("✅ 登录成功！")
                
                # 检测界面语言
                await self.detect_language()
                return True
            except:
                print(f"⏳ 等待登录... ({i+1}/15)")
                continue
        
        print("❌ 登录超时")
        return False
    
    # ===== 语言检测 - 基于新对话按钮 =====
    async def detect_language(self):
        """检测界面语言 - 基于新对话按钮"""
        try:
            print("🌐 正在检测界面语言...")
            
            await asyncio.sleep(2)
            
            new_chat_text = await self.page.evaluate('''
                () => {
                    const buttons = document.querySelectorAll('button, [role="button"]');
                    for (let btn of buttons) {
                        const text = btn.textContent || '';
                        if (text.includes('New chat')) {
                            return 'en';
                        }
                        if (text.includes('新对话')) {
                            return 'zh';
                        }
                    }
                    return 'unknown';
                }
            ''')
            
            if new_chat_text == 'en':
                self.is_english = True
                print("🌐 检测到英文界面 (新对话按钮: New chat)")
            elif new_chat_text == 'zh':
                self.is_english = False
                print("🌐 检测到中文界面 (新对话按钮: 新对话)")
            else:
                self.is_english = True
                print("🌐 无法确定界面语言，默认英文")
            
            print(f"   → 当前语言设置: {'英文' if self.is_english else '中文'}")
                
        except Exception as e:
            print(f"⚠️ 语言检测失败: {e}")
            self.is_english = True
    
    # ===== 打开新对话 =====
    async def new_conversation(self, question_index):
        """强制开启新对话"""
        print(f"\n🔄 准备第 {question_index+1} 个问题，开启新对话...")
        
        try:
            result = await self.page.evaluate('''
                () => {
                    const newChatBtn = document.querySelector('div._5a8ac7a.a084f19e');
                    if (newChatBtn) {
                        newChatBtn.click();
                        return 'button_found';
                    }
                    
                    const buttons = document.querySelectorAll('button, [role="button"]');
                    for (let btn of buttons) {
                        const text = btn.textContent || '';
                        if (text.includes('新对话') || text.includes('New chat')) {
                            btn.click();
                            return 'text_found';
                        }
                    }
                    return 'not_found';
                }
            ''')
            
            print(f"✅ 新对话操作: {result}")
            
            if result == 'not_found':
                print("🔄 没找到新对话按钮，尝试通过URL重置")
                await self.page.goto('https://chat.deepseek.com')
                await asyncio.sleep(2)
            
            await asyncio.sleep(3)
            
            try:
                await self.page.wait_for_selector('textarea', timeout=5000)
                print("✅ 新对话已准备就绪")
            except:
                print("⚠️ 输入框未出现，刷新页面")
                await self.page.reload()
                await asyncio.sleep(3)
                
        except Exception as e:
            print(f"⚠️ 开启新对话出错: {e}")
            await self.page.reload()
            await asyncio.sleep(3)
    
    async def wait_for_answer_complete(self):
        """等待AI回答完全生成"""
        print("等待AI生成完整回答...")
        
        try:
            await self.page.wait_for_selector('button:has-text("停止生成")', timeout=10000)
            print("✅ 检测到开始生成")
            await self.page.wait_for_selector('button:has-text("停止生成")', state='hidden', timeout=30000)
            print("✅ 检测到生成完成")
            await asyncio.sleep(1)
            return True
            
        except Exception as e:
            print(f"⚠️ 按钮检测方式失败: {e}")
        
        print("监控内容变化...")
        last_length = 0
        stable_count = 0
        
        for i in range(30):
            try:
                messages = await self.page.query_selector_all('.ds-markdown, .markdown-body')
                if messages:
                    last_msg = messages[-1]
                    current_text = await last_msg.text_content() or ""
                    current_length = len(current_text.strip())
                    
                    if current_length > 0:
                        print(f"⏳ 内容长度: {current_length} 字符")
                        
                        if current_length == last_length:
                            stable_count += 1
                            if stable_count >= 3:
                                print("✅ 内容稳定，生成完成")
                                await asyncio.sleep(1)
                                return True
                        else:
                            stable_count = 0
                        
                        last_length = current_length
            except Exception as e:
                pass
            
            await asyncio.sleep(1)
        
        print("⚠️ 等待超时，继续执行")
        return True
    
    async def click_share_button(self):
        """点击分享按钮"""
        try:
            result = await self.page.evaluate('''
                () => {
                    const buttons = document.querySelectorAll('[role="button"]');
                    for (let btn of buttons) {
                        const svg = btn.querySelector('svg');
                        if (svg) {
                            const path = svg.querySelector('path');
                            if (path) {
                                const d = path.getAttribute('d') || '';
                                if (d.includes('M7.95889 1.52285')) {
                                    btn.click();
                                    return true;
                                }
                            }
                        }
                    }
                    return false;
                }
            ''')
            if result:
                print("✅ 点击分享按钮")
                await asyncio.sleep(2)
                return True
            return False
        except Exception as e:
            print(f"❌ 点击分享按钮出错: {e}")
            return False

    async def click_create_share(self):
        """点击创建分享按钮 - 支持中英文"""
        try:
            if self.is_english:
                result = await self.page.evaluate('''
                    () => {
                        const buttons = document.querySelectorAll('button, [role="button"]');
                        for (let btn of buttons) {
                            const text = btn.textContent || '';
                            if (text.includes('Create public link')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }
                ''')
                print(f"🔍 英文界面，查找 'Create public link' 按钮...")
            else:
                result = await self.page.evaluate('''
                    () => {
                        const buttons = document.querySelectorAll('button, [role="button"]');
                        for (let btn of buttons) {
                            const text = btn.textContent || '';
                            if (text.includes('创建分享')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }
                ''')
                print(f"🔍 中文界面，查找 '创建分享' 按钮...")
            
            if result:
                print(f"✅ 点击创建分享按钮成功")
                await asyncio.sleep(2)
                return True
            print("❌ 未找到创建分享按钮")
            return False
        except Exception as e:
            print(f"❌ 点击创建分享出错: {e}")
            return False

    async def click_create_and_copy(self):
        """点击创建并复制按钮 - 支持中英文"""
        try:
            await asyncio.sleep(2)
            
            if self.is_english:
                copy_texts = ['Create and copy', 'Copy']
                for text in copy_texts:
                    result = await self.page.evaluate('''
                        (target) => {
                            const buttons = document.querySelectorAll('button, [role="button"]');
                            for (let btn of buttons) {
                                const btnText = btn.textContent || '';
                                if (btnText.includes(target)) {
                                    btn.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    ''', text)
                    
                    if result:
                        print(f"✅ 点击 '{text}'")
                        return True
            else:
                result = await self.page.evaluate('''
                    () => {
                        const buttons = document.querySelectorAll('button, [role="button"]');
                        for (let btn of buttons) {
                            const text = btn.textContent || '';
                            if (text.includes('创建并复制')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }
                ''')
                if result:
                    print("✅ 点击 '创建并复制'")
                    return True
            
            return False
        except Exception as e:
            print(f"❌ 点击创建并复制出错: {e}")
            return False

    # ===== 修复版DOM获取分享链接 - 基于文本内容 =====
    async def get_share_link_from_dom(self):
        """从DOM中直接获取分享链接 - 基于文本内容"""
        print("从页面获取分享链接...")
        
        try:
            # 等待弹窗加载
            await asyncio.sleep(3)
            
            # 基于文本内容查找包含分享链接的span
            share_link = await self.page.evaluate('''
                () => {
                    // 查找所有span元素
                    const spans = document.querySelectorAll('span');
                    for (const span of spans) {
                        const text = span.textContent || '';
                        // 查找包含分享链接的文本
                        if (text.includes('chat.deepseek.com/share/')) {
                            // 提取纯链接（以防有额外文字）
                            const match = text.match(/https:\\/\\/chat\\.deepseek\\.com\\/share\\/[a-zA-Z0-9_]+/);
                            if (match) {
                                return match[0];
                            }
                        }
                    }
                    
                    // 备用：查找所有div
                    const divs = document.querySelectorAll('div');
                    for (const div of divs) {
                        const text = div.textContent || '';
                        if (text.includes('chat.deepseek.com/share/')) {
                            const match = text.match(/https:\\/\\/chat\\.deepseek\\.com\\/share\\/[a-zA-Z0-9_]+/);
                            if (match) {
                                return match[0];
                            }
                        }
                    }
                    
                    return null;
                }
            ''')
            
            if share_link:
                print(f"✅ 从弹窗获取到分享链接: {share_link}")
                return share_link
            
            print("❌ 未找到分享链接")
            return None
            
        except Exception as e:
            print(f"❌ 获取分享链接出错: {e}")
            return None
    
    async def analyze_question(self, question: str) -> Dict:
        """分析单个问题，返回引用列表和分享链接"""
        print(f"\n🔍 分析: {question}")
        
        self.citation_list = []
        self.current_share_link = ""
        
        try:
            await self.new_conversation(self.question_count)
            
            input_box = await self.page.wait_for_selector('textarea')
            await input_box.fill(question)
            await input_box.press('Enter')
            print("📤 问题已发送")
            
            await self.wait_for_answer_complete()
            print("✅ 回答完全生成")
            
            await asyncio.sleep(2)
            print(f"📚 已捕获 {len(self.citation_list)} 条引用")
            
            # 先点击按钮获取分享链接
            print("🔄 开始获取分享链接...")
            
            if not await self.click_share_button():
                print("❌ 点击分享按钮失败")
                return {
                    "question": question,
                    "citations": self.citation_list,
                    "citation_count": len(self.citation_list),
                    "share_link": "",
                    "timestamp": datetime.now().isoformat()
                }
            
            if not await self.click_create_share():
                print("❌ 点击创建分享按钮失败")
                return {
                    "question": question,
                    "citations": self.citation_list,
                    "citation_count": len(self.citation_list),
                    "share_link": "",
                    "timestamp": datetime.now().isoformat()
                }
            
            if not await self.click_create_and_copy():
                print("❌ 点击创建并复制按钮失败")
                return {
                    "question": question,
                    "citations": self.citation_list,
                    "citation_count": len(self.citation_list),
                    "share_link": "",
                    "timestamp": datetime.now().isoformat()
                }
            
            await asyncio.sleep(2)
            
            # 从DOM获取链接
            share_link = await self.get_share_link_from_dom()
            
            if share_link:
                self.current_share_link = share_link
                print(f"✅ 分享链接: {share_link}")
                self.question_count += 1
            else:
                print("⚠️ DOM方式获取失败")
            
            return {
                "question": question,
                "citations": self.citation_list,
                "citation_count": len(self.citation_list),
                "share_link": self.current_share_link,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ 分析出错: {e}")
            return {
                "question": question,
                "citations": [],
                "citation_count": 0,
                "share_link": "",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def get_share_link(self):
        """获取分享链接 - 剪贴板方式（保留）"""
        print("获取分享链接（剪贴板方式）...")
        
        try:
            if not await self.click_share_button():
                return None
            await asyncio.sleep(2)
            
            if not await self.click_create_share():
                return None
            await asyncio.sleep(3)
            
            if not await self.click_create_and_copy():
                return None
            await asyncio.sleep(2)
            
            for attempt in range(3):
                try:
                    text = await self.page.evaluate('async () => await navigator.clipboard.readText()')
                    if text and isinstance(text, str) and text.startswith('https://chat.deepseek.com/share/'):
                        print(f"✅ 获取到分享链接")
                        return text
                except Exception as e:
                    print(f"⏳ 等待剪贴板... ({attempt+1}/3)")
                await asyncio.sleep(1)
            
            return None
        except Exception as e:
            print(f"❌ 获取链接过程出错: {e}")
            return None
    
    async def batch_analyze(self, questions: List[str], delay: int = 2) -> List[Dict]:
        """批量分析问题"""
        results = []
        
        for i, q in enumerate(questions):
            print(f"\n{'='*50}")
            print(f"进度 [{i+1}/{len(questions)}]")
            
            result = await self.analyze_question(q)
            results.append(result)
            
            if i < len(questions) - 1:
                await asyncio.sleep(delay)
        
        return results
    
    async def close(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        print("👋 浏览器已关闭")
