#!/usr/bin/env python3
"""
Google AI Studio 自动化入口
独立模块，不依赖项目中任何现有功能
"""

import os
import sys
import time
import logging
import json
import threading
from typing import Optional

from DrissionPage import ChromiumPage, ChromiumOptions, SessionPage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AIStudioBot:
    """
    Google AI Studio 自动化操作类
    完全独立，不依赖项目其他模块
    """
    
    def __init__(
        self,
        headless: bool = True,
        window_size: tuple = (1920, 1080),
        user_data_dir: Optional[str] = None
    ):
        """
        初始化 AIStudioBot
        
        Args:
            headless: 是否启用无头模式
            window_size: 浏览器窗口大小 (宽, 高)
            user_data_dir: 用户数据目录路径，用于保持登录态
        """
        self.headless = headless
        self.window_size = window_size
        self.user_data_dir = user_data_dir
        self.page: Optional[ChromiumPage] = None
        self._models_cache: Optional[dict] = None  # 缓存可用模型列表
        self._prompts_cache: Optional[list] = None  # 缓存可用提示词列表
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_listener = False
    
    def _create_browser_options(self) -> ChromiumOptions:
        """
        创建浏览器配置选项
        
        Returns:
            ChromiumOptions: 配置好的浏览器选项
        """
        co = ChromiumOptions()
        
        # 无头模式配置
        if self.headless:
            co.headless(True)
        
        # 代理配置 - 从环境变量读取，支持 http 和 https
        # 同时兼容大小写环境变量名（HTTP_PROXY/http_proxy, HTTPS_PROXY/https_proxy）
        http_proxy = os.getenv('HTTP_PROXY') if os.getenv('HTTP_PROXY') is not None else os.getenv('http_proxy')
        https_proxy = os.getenv('HTTPS_PROXY') if os.getenv('HTTPS_PROXY') is not None else os.getenv('https_proxy')
        
        # 优先使用 HTTPS_PROXY，其次使用 HTTP_PROXY
        proxy_url = https_proxy if https_proxy is not None else http_proxy
        
        if proxy_url is not None:
            co.set_proxy(proxy_url)
            logger.info(f"已设置代理: {proxy_url}")
        else:
            logger.info("未设置代理环境变量(HTTP_PROXY/http_proxy/HTTPS_PROXY/https_proxy)，将直接连接")
        
        # 设置窗口大小
        co.set_argument(f'--window-size={self.window_size[0]},{self.window_size[1]}')
        
        # 用户数据目录（保持登录态）
        if self.user_data_dir:
            co.set_user_data_path(self.user_data_dir)
        
        # 反检测相关配置
        co.set_argument('--disable-blink-features=AutomationControlled')
        # co.set_argument('--disable-web-security')
        co.set_argument('--disable-features=IsolateOrigins,site-per-process')
        
        # 禁用不必要的功能以提升性能
        co.set_argument('--disable-extensions')
        co.set_argument('--disable-plugins')
        # co.set_argument('--disable-images')  # 如需加载图片可注释此行
        
        # 设置 User-Agent
        co.set_user_agent(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        )
        
        return co
    
    def start(self) -> None:
        """
        启动浏览器并访问 Google AI Studio
        """
        logger.info("正在启动浏览器...")
        
        try:
            co = self._create_browser_options()
            self.page = ChromiumPage(co)
            
            # 设置响应回调处理器，统一监听所有 API 请求
            self._setup_api_listener()

            logger.info("浏览器启动成功")
            logger.info(f"访问目标: https://aistudio.google.com/")
            
            # 访问 Google AI Studio
            self.page.get("https://aistudio.google.com/")
            
            # 等待页面加载完成
            self._wait_for_page_load()
            
            logger.info(f"页面加载完成，当前标题: {self.page.title}")
            logger.info(f"当前URL: {self.page.url}")
            
            # 等待一段时间让页面自动发起 ListModels 和 ListPrompts 请求
            # 回调函数会自动处理响应
            logger.info("等待页面自动加载模型列表和提示词列表...")
            time.sleep(3)
            
        except Exception as e:
            logger.error(f"启动失败: {e}")
            self.quit()
            raise
    
    def _setup_api_listener(self) -> None:
        """
        设置 API 的持续监听器
        启动后台守护线程，监听模型列表和提示词列表请求
        """
        if not self.page:
            logger.warning("浏览器页面未初始化，无法设置监听器")
            return
        
        # 启动监听，指定目标 URL 特征（支持列表同时监听多个）
        self.page.listen.start(['ListModels', 'ListPrompts'])
        self._stop_listener = False
        
        # 启动后台监听线程
        self._listener_thread = threading.Thread(
            target=self._api_listener_loop, 
            daemon=True,
            name="APIListener"
        )
        self._listener_thread.start()
        logger.info("后台 API 监听线程已启动")

    def _api_listener_loop(self) -> None:
        """
        统一的后台监听循环体
        持续迭代捕获到的数据包并根据 URL 分发处理逻辑
        """
        logger.info("开始持续监听 API 请求...")
        try:
            # steps() 会持续等待并返回匹配的数据包
            for res in self.page.listen.steps():
                if self._stop_listener:
                    break
                
                if not res:
                    continue
                
                url = res.request.url
                if 'ListModels' in url:
                    self._handle_listmodels_response(res)
                elif 'ListPrompts' in url:
                    self._handle_listprompts_response(res)
                    
        except Exception as e:
            if not self._stop_listener:
                logger.error(f"API 监听循环异常退出: {e}")

    def _handle_listmodels_response(self, response) -> None:
        """
        处理监听到的 HTTP 响应
        自动识别并处理 ListModels API 响应
        
        Args:
            response: DrissionPage 的响应对象
        """
        try:
            # 检查是否是 ListModels 请求
            if not hasattr(response, 'request') or not hasattr(response.request, 'url'):
                return
            
            if 'ListModels' not in response.request.url:
                return
            
            logger.info(f"捕获到 ListModels 请求: {response.request.url}")
            
            # 检查响应状态
            if not hasattr(response, 'response'):
                logger.warning("响应对象不完整")
                return
            
            if response.response.status != 200:
                logger.warning(f"ListModels 请求返回非200状态码: {response.response.status}")
                return
            
            # 解析响应体
            try:
                response_body = response.response.body
                if isinstance(response_body, str):
                    models_data = json.loads(response_body)
                else:
                    models_data = response_body
                
                logger.info(f"成功获取模型列表，共 {len(models_data)} 个模型")
                
                # 转换为 OpenAI 风格格式并缓存
                self._update_models_cache_from_api(models_data)
                
                logger.info("模型列表已更新到缓存")
                
            except json.JSONDecodeError as e:
                logger.error(f"解析响应 JSON 失败: {e}")
                if hasattr(response.response, 'body') and response.response.body:
                    logger.debug(f"响应内容: {str(response.response.body)[:500]}")
            except Exception as e:
                logger.error(f"处理 ListModels 响应时出错: {e}")
                
        except Exception as e:
            logger.error(f"响应回调处理出错: {e}")

    def _handle_listprompts_response(self, response) -> None:
        """
        处理监听到的 HTTP 响应
        自动识别并处理 ListPrompts API 响应
        
        Args:
            response: DrissionPage 的响应对象
        """
        try:
            # 检查是否是 ListPrompts 请求
            if not hasattr(response, 'request') or not hasattr(response.request, 'url'):
                return
            
            if 'ListPrompts' not in response.request.url:
                return
            
            logger.info(f"捕获到 ListPrompts 请求: {response.request.url}")
            
            # 检查响应状态
            if not hasattr(response, 'response'):
                logger.warning("响应对象不完整")
                return
            
            if response.response.status != 200:
                logger.warning(f"ListPrompts 请求返回非200状态码: {response.response.status}")
                return
            
            # 解析响应体
            try:
                response_body = response.response.body
                if isinstance(response_body, str):
                    prompts_data = json.loads(response_body)
                else:
                    prompts_data = response_body
                
                logger.info(f"成功获取提示词列表，共 {len(prompts_data[0]) if prompts_data else 0} 个提示词")
                
                # 转换为内部格式并缓存
                self._update_prompts_cache_from_api(prompts_data)
                
                logger.info("提示词列表已更新到缓存")
                
            except json.JSONDecodeError as e:
                logger.error(f"解析响应 JSON 失败: {e}")
                if hasattr(response.response, 'body') and response.response.body:
                    logger.debug(f"响应内容: {str(response.response.body)[:500]}")
            except Exception as e:
                logger.error(f"处理 ListPrompts 响应时出错: {e}")
                
        except Exception as e:
            logger.error(f"响应回调处理出错: {e}")

    def _update_prompts_cache_from_api(self, prompts_data: list) -> None:
        """
        从 ListPrompts API 响应更新提示词列表缓存
        
        ListPrompts API 返回的数据格式为嵌套数组，结构为：
        [
            [
                [prompt1_data],
                [prompt2_data],
                ...
            ]
        ]
        
        每个提示词包含以下字段（按索引）：
        [0] - prompt ID (如 "prompts/1e6UM7HMSfcIWjg6P6_3uCe9YIOJpN_I8")
        [4][0] - 提示词标题 (如 "Hello, How Can I Help?")
        [4][2][0] - 作者姓名 (如 "sakura")
        [4][4][0][0] - 创建时间戳 (如 "1772698859")
        [4][4][1][0] - 修改时间戳 (如 "1772698859")
        [4][8][0][1] - 版本号 (如 "1")
        [4][8][2][1] - 是否有图片 (如 "false")
        
        Args:
            prompts_data: ListPrompts API 返回的原始提示词数据列表
        """
        if not prompts_data or not isinstance(prompts_data, list) or len(prompts_data) == 0:
            self._prompts_cache = []
            return
        
        # 获取实际的提示词列表
        actual_prompts = prompts_data[0] if isinstance(prompts_data[0], list) else prompts_data
        
        formatted_prompts = []
        
        for prompt in actual_prompts:
            if not isinstance(prompt, list) or len(prompt) < 5:
                logger.debug(f"跳过无效的提示词数据: {prompt}")
                continue
            
            # 解析提示词字段
            prompt_id_full = prompt[0] if prompt[0] else ""
            prompt_metadata = prompt[4] if len(prompt) > 4 and isinstance(prompt[4], list) else []
            
            # 获取提示词信息
            title = prompt_metadata[0] if len(prompt_metadata) > 0 and prompt_metadata[0] else "Untitled"
            author_info = prompt_metadata[2] if len(prompt_metadata) > 2 and isinstance(prompt_metadata[2], list) else []
            author = author_info[0] if len(author_info) > 0 and author_info[0] else "Unknown"
            
            # 获取时间戳 - 修复：正确解析时间戳数据结构
            timestamps = prompt_metadata[4] if len(prompt_metadata) > 4 and isinstance(prompt_metadata[4], list) else []
            created_timestamp_str = None
            modified_timestamp_str = None
            
            # 时间戳数据结构是 [[timestamp, nanoseconds], [timestamp, nanoseconds]]
            # 其中第一项是创建时间，第二项是修改时间
            if len(timestamps) > 0 and isinstance(timestamps[0], list) and len(timestamps[0]) > 0:
                created_timestamp_str = timestamps[0][0]
            if len(timestamps) > 1 and isinstance(timestamps[1], list) and len(timestamps[1]) > 0:
                modified_timestamp_str = timestamps[1][0]
            
            # 将时间戳字符串转换为整数，如果失败则使用默认值
            try:
                created_timestamp = int(created_timestamp_str) if created_timestamp_str and created_timestamp_str.isdigit() else 0
            except (ValueError, TypeError):
                logger.warning(f"无法解析创建时间戳: {created_timestamp_str}")
                created_timestamp = 0
                
            try:
                modified_timestamp = int(modified_timestamp_str) if modified_timestamp_str and modified_timestamp_str.isdigit() else 0
            except (ValueError, TypeError):
                logger.warning(f"无法解析修改时间戳: {modified_timestamp_str}")
                modified_timestamp = 0
            
            # 获取元数据
            metadata = prompt_metadata[8] if len(prompt_metadata) > 8 and isinstance(prompt_metadata[8], list) else []
            version = "1"  # 默认版本
            has_images = False
            
            # 解析元数据
            for meta_pair in metadata:
                if isinstance(meta_pair, list) and len(meta_pair) >= 2:
                    key, value = meta_pair[0], meta_pair[1]
                    if key == "version":
                        version = value
                    elif key == "hasImages":
                        has_images = value.lower() == "true"
        
            # 提取简化的提示词ID（去掉 "prompts/" 前缀）
            simple_prompt_id = prompt_id_full.replace("prompts/", "") if isinstance(prompt_id_full, str) else ""
            
            formatted_prompts.append({
                "id": simple_prompt_id,
                "full_id": prompt_id_full,
                "title": title,
                "author": author,
                "created_at": created_timestamp,
                "updated_at": modified_timestamp,
                "version": version,
                "has_images": has_images
            })
        
        self._prompts_cache = formatted_prompts
        logger.info(f"已缓存 {len(formatted_prompts)} 个提示词")

    def _wait_for_page_load(self, timeout: int = 10, max_retries: int = 4) -> bool:
        """
        等待页面加载完成
        
        等待页面中出现 omnibar 输入框和 Home 导航元素，如果在指定时间内未出现，
        则重新加载页面，最多重试指定次数
        
        Args:
            timeout: 每次等待的超时时间（秒），默认10秒
            max_retries: 最大重试次数，默认3次
            
        Returns:
            bool: 是否加载成功
        """
        logger.info(f"等待页面加载（检测主界面元素，超时{timeout}秒，最多重试{max_retries}次）...")
        
        for attempt in range(max_retries):
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    # 检查是否出现 omnibar 输入框（主界面特征元素1）
                    omnibar = self.page.ele(
                        'css:div.omnibar-container',
                        timeout=0.5
                    )
                    
                    # 检查是否出现 Home 导航链接（主界面特征元素2）
                    home_link = self.page.ele(
                        'css:a.ms-button-borderless.active-override[href="/"]',
                        timeout=0.5
                    )

                    welcome = self.page.ele(
                        'css:p.ng-star-inserted:contains("Welcome")',
                        timeout=0.5
                    )
                    
                    if omnibar and home_link:
                        logger.info("页面加载成功，检测到主界面元素 (omnibar + Home)")
                        # 额外等待一下确保动态内容完全加载
                        time.sleep(1)
                        return True
                    elif omnibar:
                        logger.debug("检测到 omnibar，等待 Home 元素和欢迎元素加载中...")
                    elif home_link:
                        logger.debug("检测到 Home 链接，等待 omnibar和Home 元素...")
                    elif welcome:
                        logger.debug("检测到 欢迎 元素，等待 Home 元素和omnibar...")
                        
                except Exception:
                    pass
                
                # 短暂等待后再次检查
                time.sleep(0.5)
            
            # 当前尝试超时
            if attempt < max_retries - 1:
                logger.warning(f"第 {attempt + 1} 次等待超时，尝试重新加载页面...")
                try:
                    # 优先检查 Home 导航链接是否已存在且已选中（active-override）
                    home_link_active = self.page.ele(
                        'css:a.ms-button-borderless.active-override[href="/"]',
                        timeout=2
                    )
                    
                    if home_link_active:
                        logger.info("Home 导航链接已处于选中状态，无需点击，使用 page.get 重新加载...")
                        self.page.get("https://aistudio.google.com/")
                        time.sleep(2)
                    else:
                        # 检查 Home 导航链接是否存在但未选中
                        home_link = self.page.ele(
                            'css:a.ms-button-borderless[href="/"]',
                            timeout=2
                        )
                        
                        if home_link:
                            logger.info("检测到 Home 导航链接（未选中），优先点击跳转...")
                            home_link.click()
                            time.sleep(2)
                        else:
                            # Home 链接不存在，使用 page.get 重新加载
                            logger.info("未检测到 Home 导航链接，使用 page.get 重新加载...")
                            self.page.get("https://aistudio.google.com/")
                            time.sleep(2)
                except Exception as e:
                    logger.error(f"重新加载页面时出错: {e}")
            else:
                logger.warning(f"第 {attempt + 1} 次等待超时，已达到最大重试次数")
        
        logger.error(f"页面加载失败，{max_retries} 次尝试后仍未检测到主界面元素")
        return False
    
    def click_get_started(self, timeout: int = 10) -> bool:
        """
        点击"开始使用"按钮 (data-test-id="get-started-button")
        
        Args:
            timeout: 等待元素出现的超时时间（秒）
            
        Returns:
            bool: 是否点击成功
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return False
        
        logger.info("查找 Get Started 按钮...")
        
        try:
            # 通过 data-test-id 定位按钮
            button = self.page.ele(
                f'@data-test-id=get-started-button',
                timeout=timeout
            )
            
            if button:
                logger.info("找到 Get Started 按钮，正在点击...")
                button.click()
                
                # 等待页面响应
                time.sleep(2)
                logger.info(f"点击完成，当前URL: {self.page.url}")
                return True
            else:
                logger.warning("未找到 Get Started 按钮")
                return False
                
        except Exception as e:
            logger.error(f"点击按钮时出错: {e}")
            return False
    
    def is_logged_in(self) -> bool:
        """
        检查是否已登录
        通过检查页面元素判断登录状态
        
        Returns:
            bool: 是否已登录
        """
        if not self.page:
            return False
        
        # 检查是否在欢迎页面（需要登录）
        try:
            current_url = self.page.url
            
            # 检查是否需要登录的页面
            if current_url == "https://aistudio.google.com/welcome":
                logger.debug("当前在welcome页面，需要登录")
                return False
            
            # 520错误页面也需要重新登录
            if current_url == "https://aistudio.google.com/520":
                logger.debug("当前在520错误页面，需要登录")
                return False
            
            # 检查是否已进入AI Studio主界面
            if self.page.title == "Google AI Studio":
                # 进一步检查是否有登录态特有的元素
                # 检查欢迎语或导航栏
                welcome = self.page.ele('xpath://p[contains(text(), "Welcome back")]', timeout=2)
                navbar = self.page.ele('css:ms-navbar', timeout=2)
                home_active = self.page.ele('css:a.active-override[href="/"]', timeout=2)
                
                if welcome or (navbar and home_active):
                    return True
            
            return False
                
        except Exception as e:
            logger.warning(f"检查登录状态时出错: {e}")
            return False
    
    def handle_520_error(self) -> bool:
        """
        处理520错误页面
        清除cookie并跳转到welcome页面
        
        Returns:
            bool: 是否处理成功
        """
        try:
            current_url = self.page.url
            if current_url != "https://aistudio.google.com/520":
                return False
            
            logger.info("处理520错误页面，清除cookie并跳转...")
            # 清除当前页面的所有 cookie
            try:
                self.page.run_cdp('Network.clearBrowserCookies')
                logger.info("已清除当前页面cookie")
            except Exception as e:
                logger.warning(f"清除cookie时出错: {e}")
            
            # 跳转到 welcome 页面
            try:
                self.page.get("https://aistudio.google.com/welcome")
                time.sleep(2)  # 等待页面加载
                logger.info("已跳转到 welcome 页面")
                return True
            except Exception as e:
                logger.warning(f"跳转页面时出错: {e}")
                return False
        except Exception as e:
            logger.warning(f"处理520错误时出错: {e}")
            return False
    
    def is_2fa_page(self) -> bool:
        """
        检查当前是否在两步验证(2FA)页面
        
        Returns:
            bool: 是否在2FA页面
        """
        if not self.page:
            return False
        
        try:
            # 检查URL是否包含两步验证相关路径
            if "/v3/signin/challenge" in self.page.url:
                logger.info("检测到两步验证页面(URL)")
                return True
            
            # 检查页面标题
            title = self.page.title
            if "两步验证" in title or "2-Step" in title or "2FA" in title:
                logger.info("检测到两步验证页面(标题)")
                return True
            
            # 检查页面中是否有两步验证相关元素
            # 通过data-challengeid属性判断
            challenge_elements = self.page.eles('@data-challengeid')
            if challenge_elements:
                logger.info(f"检测到两步验证选项: {len(challenge_elements)} 个")
                return True
            
            # 检查是否有"选择您想要使用的登录方式"文本
            if self.page.ele('text:选择您想要使用的登录方式', timeout=2):
                logger.info("检测到两步验证选择界面")
                return True
            
            # 检查是否有"尝试的失败次数过多"提示
            if self.page.ele('text:尝试的失败次数过多', timeout=2):
                logger.warning("检测到登录失败次数过多提示")
                return True
                
        except Exception as e:
            logger.debug(f"检查2FA页面时出错: {e}")
        
        return False
    
    def get_2fa_methods(self) -> list:
        """
        获取可用的两步验证方式列表
        
        Returns:
            list: 验证方式列表，每个元素包含名称、类型和元素对象
        """
        methods = []
        
        if not self.page:
            return methods
        
        try:
            # 查找所有带有data-challengeid的元素
            challenge_items = self.page.eles('css:li.aZvCDf')
            
            for idx, item in enumerate(challenge_items, 1):
                try:
                    # 获取验证方式容器
                    method_div = item.ele('css:.VV3oRb')
                    if not method_div:
                        continue
                    
                    # 获取challenge ID和类型
                    challenge_id = method_div.attr('data-challengeid')
                    challenge_type = method_div.attr('data-challengetype')
                    is_disabled = method_div.attr('aria-disabled') == 'true'
                    
                    # 获取验证方式名称
                    name_elem = method_div.ele('css:.l5PPKe')
                    name = name_elem.text if name_elem else f"方式 {idx}"
                    
                    # 清理名称文本
                    name = name.strip().replace('\n', ' ')
                    
                    method_info = {
                        'index': idx,
                        'name': name,
                        'challenge_id': challenge_id,
                        'challenge_type': challenge_type,
                        'disabled': is_disabled,
                        'element': method_div
                    }
                    
                    methods.append(method_info)
                    logger.info(f"发现验证方式 {idx}: {name} (ID:{challenge_id}, 类型:{challenge_type}, {'禁用' if is_disabled else '可用'})")
                    
                except Exception as e:
                    logger.debug(f"解析验证方式 {idx} 时出错: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"获取验证方式列表时出错: {e}")
        
        return methods
    
    def select_2fa_method(self, method_index: int = None, method_name: str = None) -> bool:
        """
        选择两步验证方式
        
        Args:
            method_index: 验证方式的索引（从1开始）
            method_name: 验证方式的名称关键词（如"短信"、"手机"等）
            
        Returns:
            bool: 是否选择成功
        """
        methods = self.get_2fa_methods()
        
        if not methods:
            logger.error("未找到可用的验证方式")
            return False
        
        # 如果指定了索引
        if method_index is not None:
            for method in methods:
                if method['index'] == method_index and not method['disabled']:
                    return self._click_2fa_method(method)
            logger.error(f"指定的验证方式索引 {method_index} 不存在或已被禁用")
            return False
        
        # 如果指定了名称关键词
        if method_name:
            for method in methods:
                if method_name in method['name'] and not method['disabled']:
                    return self._click_2fa_method(method)
            logger.error(f"未找到包含关键词 '{method_name}' 的可用验证方式")
            return False
        
        # 默认选择第一个可用的验证方式
        for method in methods:
            if not method['disabled']:
                logger.info(f"自动选择第一个可用的验证方式: {method['name']}")
                return self._click_2fa_method(method)
        
        logger.error("没有可用的验证方式")
        return False
    
    def _click_2fa_method(self, method: dict) -> bool:
        """
        点击选择指定的验证方式
        
        Args:
            method: 验证方式信息字典
            
        Returns:
            bool: 是否点击成功
        """
        try:
            logger.info(f"正在选择验证方式: {method['name']}")
            method['element'].click()
            
            # 等待页面响应
            time.sleep(2)
            logger.info(f"已选择验证方式，当前URL: {self.page.url}")
            
            return True
            
        except Exception as e:
            logger.error(f"选择验证方式时出错: {e}")
            return False
    
    def handle_2fa_interactive(self, timeout: int = 300) -> bool:
        """
        交互式处理两步验证
        支持终端输入选择验证方式和验证码
        
        Args:
            timeout: 等待超时时间（秒）
            
        Returns:
            bool: 是否处理成功
        """
        logger.info("=" * 60)
        logger.info("检测到两步验证(2FA)")
        logger.info("=" * 60)
        
        # 获取并显示可用的验证方式
        methods = self.get_2fa_methods()
        
        # 如果未找到验证方式，可能是已经进入了具体的验证方式页面
        if not methods:
            logger.info("未找到可用的验证方式列表，检查是否已默认进入具体验证页面...")
            
            # 检查是否已经在具体的验证方式页面（如手机通知验证页面）
            page_text = self.page.run_js('return document.body.innerText') or ""
            
            # 检查是否是手机通知验证页面
            if "查看您的" in page_text and "发送了通知" in page_text:
                print("\n" + "=" * 60)
                print("检测到已进入手机通知验证页面")
                print("=" * 60)
                print("Google 已向您的手机发送了通知。")
                print("请在手机上点按通知中的'是'来验证身份。")
                print("\n或者您可以选择：")
                print("  1. 等待手机验证完成")
                print("  2. 点击'试试其他方式'切换到其他验证方式")
                print("=" * 60)
                
                while True:
                    try:
                        user_input = input('\n请选择 (1-2, 直接回车默认等待手机验证): ').strip()
                        
                        if user_input == "" or user_input == "1":
                            print('\n等待手机验证完成...')
                            return self._wait_for_2fa_completion(timeout)
                        
                        elif user_input == "2":
                            print('\n正在切换到其他验证方式...')
                            break  # 跳出循环，执行下面的点击逻辑
                        
                        else:
                            print('❌ 无效的选择，请输入 1 或 2')
                            
                    except KeyboardInterrupt:
                        print("\n用户取消操作")
                        return False
            
            # 尝试点击"试试其他方式"按钮返回到验证方式选择页面
            try:
                # 尝试通过多种方式查找"试试其他方式"按钮
                other_way_button = None
                
                # 方式1: 通过 jsname 和文本内容
                try:
                    buttons = self.page.eles('css:button[jsname="LgbsSe"]', timeout=3)
                    for btn in buttons:
                        button_text = btn.text or ""
                        if "试试其他方式" in button_text and btn.attr('disabled') is None:
                            other_way_button = btn
                            logger.info("找到'试试其他方式'按钮(jsname遍历)")
                            break
                except Exception as e:
                    logger.debug(f"通过jsname查找按钮失败: {e}")
                
                # 方式2: 通过按钮文本直接查找
                if not other_way_button:
                    try:
                        other_way_button = self.page.ele('text:试试其他方式', timeout=3)
                        logger.info("找到'试试其他方式'按钮(文本查找)")
                    except:
                        pass
                
                # 方式3: 通过 span 内的文本查找
                if not other_way_button:
                    try:
                        spans = self.page.eles('css:span.VfPpkd-vQzf8d', timeout=3)
                        for span in spans:
                            if "试试其他方式" in (span.text or ""):
                                # 找到span后，获取其父按钮元素
                                parent = span.parent()
                                if parent and parent.tag == 'button':
                                    other_way_button = parent
                                    logger.info("找到'试试其他方式'按钮(span父元素)")
                                    break
                    except:
                        pass
                
                if other_way_button:
                    logger.info("点击'试试其他方式'按钮，返回验证方式选择页面...")
                    other_way_button.click()
                    time.sleep(3)  # 等待页面刷新
                    logger.info("已点击按钮，重新查找验证方式...")
                    # 重新获取验证方式
                    methods = self.get_2fa_methods()
                else:
                    logger.warning("未找到'试试其他方式'按钮")
                    
            except Exception as e:
                logger.debug(f"查找或点击'试试其他方式'按钮时出错: {e}")
        
        if not methods:
            logger.error("未找到可用的验证方式，请在浏览器中手动完成验证")
            return self._wait_for_2fa_completion(timeout)
        
        # 显示可用的验证方式
        print("\n" + "=" * 60)
        print("可用的两步验证方式:")
        print("=" * 60)
        available_methods = []
        for method in methods:
            status = "[禁用]" if method['disabled'] else "[可用]"
            if not method['disabled']:
                available_methods.append(method)
                print(f"  {method['index']}. {method['name']}")
            else:
                print(f"  {method['index']}. {status} {method['name']}")
        print("=" * 60)
        
        if not available_methods:
            logger.error("没有可用的验证方式")
            return False
        
        # 让用户选择验证方式
        selected_method = None
        while selected_method is None:
            try:
                user_input = input(f"\n请选择验证方式 (输入编号 1-{len(methods)}, 直接回车选择第一个可用): ").strip()
                
                if user_input == "":
                    # 默认选择第一个可用的
                    selected_method = available_methods[0]
                    print(f"自动选择: {selected_method['name']}")
                else:
                    selected_index = int(user_input)
                    # 查找对应索引的方法
                    for method in methods:
                        if method['index'] == selected_index:
                            if method['disabled']:
                                print(f"❌ 该验证方式已被禁用，请选择其他方式")
                            else:
                                selected_method = method
                            break
                    
                    if selected_method is None:
                        print(f"❌ 无效的编号，请输入 1-{len(methods)} 之间的数字")
                        
            except ValueError:
                print("❌ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n用户取消操作")
                return False
        
        # 选择验证方式
        if not self._click_2fa_method(selected_method):
            logger.error("选择验证方式失败")
            return False
        
        print(f"\n已选择: {selected_method['name']}")
        print("等待页面加载...")
        time.sleep(3)
        
        # 检查是否进入了通行密钥确认页面
        if self._is_passkey_confirmation_page():
            print("\n检测到通行密钥确认页面")
            if not self._handle_passkey_confirmation():
                return False
        
        # 尝试自动输入验证码
        if self._try_enter_verification_code():
            # 验证码输入成功，等待验证完成
            return self._wait_for_2fa_completion(timeout)
        else:
            # 自动输入失败，进入等待模式
            print("\n无法自动输入验证码，请在浏览器中手动完成验证")
            return self._wait_for_2fa_completion(timeout)
    
    def _is_passkey_confirmation_page(self) -> bool:
        """
        检查当前是否在通行密钥确认页面
        
        Returns:
            bool: 是否在通行密钥确认页面
        """
        try:
            # 检查页面特征
            # 1. 检查标题或文本是否包含"通行密钥"或"passkey"
            page_text = self.page.run_js('return document.body.innerText')
            if "通行密钥" in page_text or "passkey" in page_text.lower():
                return True
            
            # 2. 检查是否有特定的确认按钮
            confirm_button = self.page.ele('css:button:contains("继续")', timeout=2)
            if confirm_button:
                # 再检查是否有"试试其他方式"按钮，这是通行密钥页面的特征
                other_way_button = self.page.ele('css:button:contains("试试其他方式")', timeout=2)
                if other_way_button:
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"检查通行密钥页面时出错: {e}")
            return False
    
    def _handle_passkey_confirmation(self) -> bool:
        """
        处理通行密钥确认页面
        让用户选择是继续使用通行密钥，还是尝试其他方式
        
        Returns:
            bool: 是否处理成功
        """
        print("\n" + "=" * 60)
        print("通行密钥验证")
        print("=" * 60)
        print("页面提示: 请使用您的通行密钥证实是您本人在登录")
        print("\n选项:")
        print("  1. 继续 - 使用通行密钥验证（需要在浏览器中操作）")
        print("  2. 试试其他方式 - 切换到其他验证方式（如短信验证码）")
        print("=" * 60)
        
        while True:
            try:
                user_input = input('\n请选择 (1-2, 直接回车默认选择"试试其他方式"): ').strip()
                
                if user_input == "" or user_input == "2":
                    # 选择试试其他方式
                    print('\n正在切换到其他验证方式...')
                    try:
                        other_way_button = self.page.ele('css:button:contains("试试其他方式")', timeout=5)
                        other_way_button.click()
                        time.sleep(3)
                        print('✓ 已切换到其他验证方式')
                        return True
                    except Exception as e:
                        logger.error(f'点击"试试其他方式"按钮失败: {e}')
                        return False
                
                elif user_input == "1":
                    # 选择继续使用通行密钥
                    print('\n请在你的设备上完成通行密钥验证...')
                    print('提示: 你的设备会要求你使用指纹、面孔或屏锁设置来验证身份')
                    try:
                        continue_button = self.page.ele('css:button:contains("继续")', timeout=5)
                        continue_button.click()
                        print('✓ 已点击继续，请在设备上完成验证')
                        time.sleep(3)
                        return True
                    except Exception as e:
                        logger.error(f'点击"继续"按钮失败: {e}')
                        return False
                
                else:
                    print('❌ 无效的选择，请输入 1 或 2')
                    
            except KeyboardInterrupt:
                print("\n用户取消操作")
                return False
            except Exception as e:
                logger.error(f"处理通行密钥确认页面时出错: {e}")
                return False
    
    def _try_enter_verification_code(self) -> bool:
        """
        尝试让用户在终端输入验证码并自动填入
        
        Returns:
            bool: 是否成功输入验证码
        """
        try:
            # 检查是否有验证码输入框
            code_input = self.page.ele('css:input[type="tel"], input[type="text"][name*="code"], input[name*="totpPin"], input[autocomplete="one-time-code"]', timeout=5)
            
            if not code_input:
                # 可能是其他类型的验证（如Google Prompt），无法自动输入
                return False
            
            print("\n" + "=" * 60)
            print("请在终端输入收到的验证码")
            print("=" * 60)
            
            # 获取用户输入的验证码
            while True:
                try:
                    verification_code = input("请输入验证码 (输入q取消): ").strip()
                    
                    if verification_code.lower() == 'q':
                        print("取消验证码输入")
                        return False
                    
                    # 验证输入格式 - 放宽限制，支持4-10位任意字符
                    if len(verification_code) < 4 or len(verification_code) > 10:
                        print("❌ 验证码长度应在4-10位之间，请重新输入")
                        continue
                    
                    # 检查是否只包含字母数字（排除特殊字符）
                    if not verification_code.isalnum():
                        print("❌ 验证码只能包含字母和数字，请重新输入")
                        continue
                    
                    break
                    
                except KeyboardInterrupt:
                    print("\n用户取消操作")
                    return False
            
            # 输入验证码
            code_input.clear()
            code_input.input(verification_code)
            print(f"✓ 验证码已输入: {verification_code}")
            
            # 查找并点击下一步/验证按钮
            time.sleep(1)
            
            # 尝试多种方式查找提交按钮
            submit_button = None
            for selector in [
                'css:button[type="submit"]',
                'css:button:contains("下一步")',
                'css:button:contains("Next")',
                'css:button:contains("验证")',
                'css:button:contains("Verify")',
                'css:#idvPreregisteredPhoneNext',
                'css:#totpNext',
                'css:[data-primary-action-label] button'
            ]:
                try:
                    submit_button = self.page.ele(selector, timeout=2)
                    if submit_button:
                        break
                except:
                    continue
            
            if submit_button:
                submit_button.click()
                print("✓ 已提交验证码")
                time.sleep(3)
                return True
            else:
                print("⚠ 未找到提交按钮，请在浏览器中手动点击")
                return False
                
        except Exception as e:
            logger.debug(f"尝试输入验证码时出错: {e}")
            return False
    
    def _wait_for_2fa_completion(self, timeout: int) -> bool:
        """
        等待两步验证完成
        
        Args:
            timeout: 等待超时时间（秒）
            
        Returns:
            bool: 是否验证成功
        """
        print(f"\n等待验证完成（超时时间: {timeout}秒）...")
        print("提示: 如果验证成功，程序会自动继续")
        
        start_time = time.time()
        check_interval = 3
        
        while time.time() - start_time < timeout:
            time.sleep(check_interval)
            
            # 检查是否进入了"简化您的登录流程"页面（通行密钥注册页面）
            if self._is_passkey_enrollment_page():
                print("\n检测到'简化您的登录流程'页面（通行密钥注册）")
                if self._click_not_now_button():
                    print("已点击'以后再说'，继续等待登录完成...")
                    time.sleep(2)  # 等待页面跳转
                    continue
            
            # 检查是否已离开2FA页面
            if not self.is_2fa_page():
                current_url = self.page.url if self.page else "unknown"
                
                # 检查是否是520错误页面（cookie未生效）
                if current_url == "https://aistudio.google.com/520":
                    logger.info("检测到520错误页面，cookie可能尚未生效，等待后重试...")
                    time.sleep(5)  # 等待服务器同步
                    # 先访问 accounts.google.com 让浏览器同步 cookie
                    try:
                        logger.info("尝试访问 accounts.google.com 同步 cookie...")
                        self.page.get("https://accounts.google.com/")
                        time.sleep(2)
                        logger.info("accounts.google.com 当前URL: {}".format(self.page.url))
                        # 然后再访问 AI Studio
                        logger.info("再访问 AI Studio 主页面...")
                        self.page.get("https://aistudio.google.com/")
                        time.sleep(3)
                        logger.info("AI Studio 当前URL: {}".format(self.page.url))
                    except Exception as e:
                        logger.warning(f"访问页面时出错: {e}")
                    continue  # 继续循环检查
                
                # 再检查是否已登录
                if self.is_logged_in():
                    logger.info("两步验证完成，已成功登录！")
                    # 刷新页面确保 cookie 完全生效
                    logger.info("刷新页面以确保登录状态稳定...")
                    self.page.refresh()
                    time.sleep(3)
                    # 再次确认登录状态
                    if self.is_logged_in():
                        logger.info("登录状态已确认稳定")
                        return True
                    else:
                        logger.warning("刷新后登录状态丢失，继续等待...")
                else:
                    # 可能在其他页面，继续等待
                    logger.debug(f"当前页面: {current_url}，继续等待...")
            # 显示剩余时间
            elapsed = int(time.time() - start_time)
            if elapsed % 30 == 0:  # 每30秒提示一次
                remaining = timeout - elapsed
                print(f"等待中... 已用 {elapsed}秒，剩余 {remaining}秒")
        
        print("\n⚠ 两步验证等待超时")
        return False
    
    def _is_passkey_enrollment_page(self) -> bool:
        """
        检测是否进入了通行密钥注册页面（简化您的登录流程）
        
        Returns:
            bool: 是否是通行密钥注册页面
        """
        try:
            if not self.page:
                return False
            
            # 检查URL特征
            current_url = self.page.url or ""
            if "/speedbump/passkeyenrollment" in current_url:
                return True
            
            # 检查页面标题
            page_title = self.page.title or ""
            if "简化您的登录流程" in page_title or "passkey" in page_title.lower():
                return True
            
            # 检查页面文本内容
            page_text = self.page.run_js('return document.body.innerText') or ""
            if "简化您的登录流程" in page_text and "通行密钥" in page_text:
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"检测通行密钥注册页面时出错: {e}")
            return False
    
    def _click_not_now_button(self) -> bool:
        """
        点击"以后再说"按钮跳过通行密钥注册
        
        Returns:
            bool: 是否点击成功
        """
        try:
            # 方式1: 通过 jsname 和文本内容查找
            try:
                buttons = self.page.eles('css:button[jsname="LgbsSe"]', timeout=3)
                for btn in buttons:
                    button_text = btn.text or ""
                    if "以后再说" in button_text and btn.attr('disabled') is None:
                        logger.info("找到'以后再说'按钮(jsname遍历)")
                        btn.click()
                        return True
            except Exception as e:
                logger.debug(f"通过jsname查找按钮失败: {e}")
            
            # 方式2: 通过按钮文本直接查找
            try:
                not_now_button = self.page.ele('text:以后再说', timeout=3)
                if not_now_button and not_now_button.attr('disabled') is None:
                    logger.info("找到'以后再说'按钮(文本查找)")
                    not_now_button.click()
                    return True
            except:
                pass
            
            # 方式3: 通过 span 内的文本查找
            try:
                spans = self.page.eles('css:span.VfPpkd-vQzf8d', timeout=3)
                for span in spans:
                    if "以后再说" in (span.text or ""):
                        # 找到span后，获取其父按钮元素
                        parent = span.parent()
                        if parent and parent.tag == 'button':
                            logger.info("找到'以后再说'按钮(span父元素)")
                            parent.click()
                            return True
            except:
                pass
            
            # 方式4: 通过 data-secondary-action-label 属性查找
            try:
                container = self.page.ele('css:div[data-secondary-action-label="以后再说"]', timeout=3)
                if container:
                    # 在容器内查找按钮
                    not_now_btn = container.ele('css:button', timeout=2)
                    if not_now_btn and not_now_btn.attr('disabled') is None:
                        logger.info("找到'以后再说'按钮(data-secondary-action-label)")
                        not_now_btn.click()
                        return True
            except:
                pass
            
            logger.warning("未找到可点击的'以后再说'按钮")
            return False
            
        except Exception as e:
            logger.error(f"点击'以后再说'按钮时出错: {e}")
            return False
    
    def get_page_info(self) -> dict:
        """
        获取当前页面信息
        
        Returns:
            dict: 包含页面标题、URL、状态等信息
        """
        if not self.page:
            return {}
        
        return {
            'title': self.page.title,
            'url': self.page.url,
            'user_agent': self.page.run_js('return navigator.userAgent'),
            'viewport': self.page.run_js(
                'return {width: window.innerWidth, height: window.innerHeight}'
            )
        }
    
    def enter_email(self, email: Optional[str] = None, timeout: int = 10) -> bool:
        """
        在 Google 登录页面输入邮箱账号
        
        Args:
            email: 邮箱地址，如未提供则从环境变量 GOOGLE_EMAIL 读取
            timeout: 等待元素出现的超时时间（秒）
            
        Returns:
            bool: 是否输入成功
        """
        # 从环境变量读取账号（如果参数为 None）
        if email is None:
            email = os.getenv('GOOGLE_EMAIL')
        
        if not email:
            logger.error("未提供邮箱账号，请设置 GOOGLE_EMAIL 环境变量或传入 email 参数")
            return False
        
        if not self.page:
            logger.warning("浏览器未启动")
            return False
        
        logger.info("查找邮箱输入框...")
        
        try:
            # 通过 id 定位邮箱输入框
            email_input = self.page.ele('#identifierId', timeout=timeout)
            
            if email_input:
                logger.info("找到邮箱输入框，正在输入账号...")
                email_input.clear()
                email_input.input(email)
                
                logger.info("邮箱输入完成")
                return True
            else:
                logger.warning("未找到邮箱输入框")
                return False
                
        except Exception as e:
            logger.error(f"输入邮箱时出错: {e}")
            return False
    
    def click_next_after_email(self, timeout: int = 10) -> bool:
        """
        点击邮箱输入后的"下一步"按钮
        
        Args:
            timeout: 等待元素出现的超时时间（秒）
            
        Returns:
            bool: 是否点击成功
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return False
        
        logger.info("查找下一步按钮...")
        
        try:
            # 通过按钮文本定位（Google 登录页的下一步按钮）
            # 可能的定位方式：
            # 1. 通过文本内容
            next_button = self.page.ele('text:下一步', timeout=timeout)
            if not next_button:
                next_button = self.page.ele('text:Next', timeout=timeout)
            
            if next_button:
                logger.info("找到下一步按钮，正在点击...")
                next_button.click()
                
                # 等待密码输入页面加载
                time.sleep(2)
                logger.info(f"点击完成，当前URL: {self.page.url}")
                return True
            else:
                logger.warning("未找到下一步按钮")
                return False
                
        except Exception as e:
            logger.error(f"点击下一步时出错: {e}")
            return False
    
    def enter_password(self, password: Optional[str] = None, timeout: int = 10) -> bool:
        """
        在 Google 登录页面输入密码
        
        Args:
            password: 密码，如未提供则从环境变量 GOOGLE_PASSWORD 读取
            timeout: 等待元素出现的超时时间（秒）
            
        Returns:
            bool: 是否输入成功
        """
        # 从环境变量读取密码（如果参数为 None）
        if password is None:
            password = os.getenv('GOOGLE_PASSWORD')
        
        if not password:
            logger.error("未提供密码，请设置 GOOGLE_PASSWORD 环境变量或传入 password 参数")
            return False
        
        if not self.page:
            logger.warning("浏览器未启动")
            return False
        
        logger.info("查找密码输入框...")
        
        try:
            # 通过 name 属性定位密码输入框
            password_input = self.page.ele('@name=Passwd', timeout=timeout)
            
            if password_input:
                logger.info("找到密码输入框，正在输入密码...")
                password_input.clear()
                password_input.input(password)
                
                logger.info("密码输入完成")
                return True
            else:
                logger.warning("未找到密码输入框")
                return False
                
        except Exception as e:
            logger.error(f"输入密码时出错: {e}")
            return False
    
    def click_next_after_password(self, timeout: int = 10) -> bool:
        """
        点击密码输入后的"下一步"按钮完成登录
        
        Args:
            timeout: 等待元素出现的超时时间（秒）
            
        Returns:
            bool: 是否点击成功
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return False
        
        logger.info("查找密码页的下一步按钮...")
        
        try:
            # 尝试多种方式定位下一步按钮
            # 方式1：通过文本（中文/英文）
            next_button = self.page.ele('text:下一步', timeout=timeout)
            if not next_button:
                next_button = self.page.ele('text:Next', timeout=timeout)
            
            # 方式2：通过按钮类型和属性（如果文本定位失败）
            if not next_button:
                # Google 登录按钮通常有特定的 data-id 或 type
                next_button = self.page.ele('@type=submit', timeout=3)
            
            if next_button:
                logger.info("找到下一步按钮，正在点击...")
                next_button.click()
                
                # 等待登录完成，页面跳转
                time.sleep(3)
                logger.info(f"点击完成，当前URL: {self.page.url}")
                
                return True
            else:
                logger.warning("未找到下一步按钮")
                return False
                
        except Exception as e:
            logger.error(f"点击下一步时出错: {e}")
            return False

    def get_task_type_options(self, timeout: int = 5) -> list[dict]:
        """
        获取任务类型下拉框的选项列表
        
        先让输入框获取焦点，然后等待下拉框出现，获取所有选项信息
        
        Args:
            timeout: 等待下拉框出现的超时时间（秒）
            
        Returns:
            list[dict]: 选项信息列表，每个选项包含 label、description、id
                例如: [
                    {"label": "/build", "description": "Vibe code an app", "id": "omnibar-item-0"},
                    {"label": "Defining Time for Humans", "description": "Chat session", "id": "omnibar-item-4"}
                ]
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return []
        
        try:
            # 1. 定位输入框并获取焦点
            logger.info("定位搜索输入框...")
            input_box = self.page.ele(
                'xpath://input[@placeholder="Start a chat or vibe code an app"]',
                timeout=timeout
            )
            
            if not input_box:
                logger.warning("未找到搜索输入框")
                return []
            
            # 点击输入框获取焦点
            input_box.click()
            logger.info("已点击搜索输入框，等待下拉框出现...")
            
            # 2. 等待下拉框出现
            time.sleep(1)
            
            # 3. 获取下拉框
            menu_overlay = self.page.ele(
                'css:div.menu-overlay',
                timeout=timeout
            )
            
            if not menu_overlay:
                logger.warning("未找到下拉框 menu-overlay")
                return []
            
            # 4. 获取所有选项元素 li[role="option"]
            option_elements = menu_overlay.eles('css:li[role="option"]')
            
            if not option_elements:
                logger.warning("未找到任何选项元素")
                return []
            
            # 5. 提取选项详细信息
            options = []
            for ele in option_elements:
                try:
                    # 获取选项ID
                    option_id = ele.attr('id') or ''
                    
                    # 获取标签文本 (.item-label)
                    label_ele = ele.ele('css:.item-label', timeout=0.5)
                    label = label_ele.text.strip() if label_ele else ''
                    
                    # 获取描述文本 (.item-description)
                    desc_ele = ele.ele('css:.item-description', timeout=0.5)
                    description = desc_ele.text.strip() if desc_ele else ''
                    
                    # 只添加有标签的选项
                    if label:
                        options.append({
                            'id': option_id,
                            'label': label,
                            'description': description
                        })
                except Exception as e:
                    logger.debug(f"解析选项时出错: {e}")
                    continue
            
            logger.info(f"获取到 {len(options)} 个任务类型选项")
            for opt in options:
                logger.debug(f"  - {opt['label']}: {opt['description']}")
            return options
            
        except Exception as e:
            logger.error(f"获取任务类型选项时出错: {e}")
            return []

    def select_task_type(self, option_identifier: str, timeout: int = 5) -> bool:
        """
        点击下拉框中指定的任务类型选项
        
        支持通过 label、description 或 id 来定位选项
        
        Args:
            option_identifier: 选项标识，可以是:
                - label (如 "/build", "Defining Time for Humans")
                - description (如 "Vibe code an app")
                - id (如 "omnibar-item-0")
            timeout: 等待元素的超时时间（秒）
            
        Returns:
            bool: 是否点击成功
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return False
        
        try:
            # 1. 确保下拉框已显示（先获取焦点）
            input_box = self.page.ele(
                'xpath://input[@placeholder="Start a chat or vibe code an app"]',
                timeout=timeout
            )
            
            if not input_box:
                logger.warning("未找到搜索输入框")
                return False
            
            # 点击输入框确保下拉框显示
            input_box.click()
            time.sleep(0.5)
            
            # 2. 在下拉框中查找指定标识的选项
            logger.info(f"查找任务类型: {option_identifier}")
            
            option = None
            
            # 策略1: 通过 id 直接定位
            if option_identifier.startswith('omnibar-item-'):
                option = self.page.ele(
                    f'css:div.menu-overlay li#{option_identifier}',
                    timeout=2
                )
            
            # 策略2: 通过 label 文本定位
            if not option:
                option = self.page.ele(
                    f'css:div.menu-overlay li[role="option"] .item-label:contains("{option_identifier}")',
                    timeout=2
                )
                # 如果找到label，需要获取其父级li元素
                if option:
                    option = option.parent()
            
            # 策略3: 通过 description 文本定位
            if not option:
                desc_ele = self.page.ele(
                    f'css:div.menu-overlay li[role="option"] .item-description:contains("{option_identifier}")',
                    timeout=2
                )
                if desc_ele:
                    option = desc_ele.parent()
            
            # 策略4: 通过 aria-label 属性定位
            if not option:
                option = self.page.ele(
                    f'css:div.menu-overlay li[role="option"][aria-label*="{option_identifier}"]',
                    timeout=2
                )
            
            if option:
                logger.info(f"找到任务类型，正在点击: {option_identifier}")
                option.click()
                time.sleep(1)
                logger.info(f"成功选择任务类型: {option_identifier}")
                return True
            else:
                logger.warning(f"未找到任务类型: {option_identifier}")
                return False
                
        except Exception as e:
            logger.error(f"选择任务类型时出错: {e}")
            return False

    def get_model_options(self, timeout: int = 5) -> list[dict]:
        """
        获取模型选择下拉框的选项列表
        
        在选择任务类型后，等待模型选择下拉框出现，获取所有模型选项信息
        
        Args:
            timeout: 等待下拉框出现的超时时间（秒）
            
        Returns:
            list[dict]: 模型选项信息列表，每个选项包含 label、description、id、category
                例如: [
                    {"label": "Gemini 3 Flash Preview", "description": "Start a chat with Gemini 3 Flash Preview", "id": "omnibar-item-1", "category": "Featured"},
                    {"label": "Gemini 3.1 Pro Preview", "description": "Start a chat with Gemini 3.1 Pro Preview", "id": "omnibar-item-3", "category": "Featured"}
                ]
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return []
        
        try:
            # 1. 等待模型选择下拉框出现
            logger.info("等待模型选择下拉框...")
            time.sleep(1)
            
            # 2. 获取下拉框
            menu_overlay = self.page.ele(
                'css:div.menu-overlay',
                timeout=timeout
            )
            
            if not menu_overlay:
                logger.warning("未找到模型选择下拉框 menu-overlay")
                return []
            
            # 3. 获取所有选项元素 li[role="option"]
            option_elements = menu_overlay.eles('css:li[role="option"]')
            
            if not option_elements:
                logger.warning("未找到任何模型选项元素")
                return []
            
            # 4. 提取选项详细信息
            options = []
            current_category = ""
            
            for ele in option_elements:
                try:
                    # 获取选项ID
                    option_id = ele.attr('id') or ''
                    
                    # 获取标签文本 (.item-label)
                    label_ele = ele.ele('css:.item-label', timeout=0.5)
                    label = label_ele.text.strip() if label_ele else ''
                    
                    # 获取描述文本 (.item-description)
                    desc_ele = ele.ele('css:.item-description', timeout=0.5)
                    description = desc_ele.text.strip() if desc_ele else ''
                    
                    # 只添加有标签的选项
                    if label:
                        options.append({
                            'id': option_id,
                            'label': label,
                            'description': description,
                            'category': current_category
                        })
                except Exception as e:
                    logger.debug(f"解析模型选项时出错: {e}")
                    continue
            
            logger.info(f"获取到 {len(options)} 个模型选项")
            for opt in options:
                logger.debug(f"  - {opt['label']}: {opt['description']}")
            return options
            
        except Exception as e:
            logger.error(f"获取模型选项时出错: {e}")
            return []

    def select_model(self, model_identifier: str, timeout: int = 5) -> bool:
        """
        点击下拉框中指定的模型选项
        
        支持通过 label、description 或 id 来定位模型选项
        
        Args:
            model_identifier: 模型标识，可以是:
                - label (如 "Gemini 3 Flash Preview", "Imagen 4")
                - description (如 "Start a chat with Gemini 3 Flash Preview")
                - id (如 "omnibar-item-1")
            timeout: 等待元素的超时时间（秒）
            
        Returns:
            bool: 是否点击成功
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return False
        
        try:
            logger.info(f"查找模型: {model_identifier}")
            
            option = None
            
            # 策略1: 通过 id 直接定位
            if model_identifier.startswith('omnibar-item-'):
                option = self.page.ele(
                    f'css:div.menu-overlay li#{model_identifier}',
                    timeout=2
                )
            
            # 策略2: 通过 label 文本定位
            if not option:
                label_ele = self.page.ele(
                    f'css:div.menu-overlay li[role="option"] .item-label:contains("{model_identifier}")',
                    timeout=2
                )
                # 如果找到label，需要获取其父级li元素
                if label_ele:
                    option = label_ele.parent()
            
            # 策略3: 通过 description 文本定位
            if not option:
                desc_ele = self.page.ele(
                    f'css:div.menu-overlay li[role="option"] .item-description:contains("{model_identifier}")',
                    timeout=2
                )
                if desc_ele:
                    option = desc_ele.parent()
            
            # 策略4: 通过 aria-label 属性定位
            if not option:
                option = self.page.ele(
                    f'css:div.menu-overlay li[role="option"][aria-label*="{model_identifier}"]',
                    timeout=2
                )
            
            if option:
                logger.info(f"找到模型，正在点击: {model_identifier}")
                option.click()
                time.sleep(1)
                logger.info(f"成功选择模型: {model_identifier}")
                return True
            else:
                logger.warning(f"未找到模型: {model_identifier}")
                return False
                
        except Exception as e:
            logger.error(f"选择模型时出错: {e}")
            return False

    def get_available_models(self) -> dict:
        """
        获取可用的模型列表（从缓存中）
        
        返回之前通过 get_model_options 获取并缓存的模型列表，
        以 OpenAI 风格的 list models 格式返回
        
        Returns:
            dict: OpenAI 风格的模型列表响应，格式如下:
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "gemini-3-flash-preview",
                            "object": "model",
                            "created": 1700000000,
                            "owned_by": "google"
                        },
                        ...
                    ]
                }
        """
        if self._models_cache is None:
            logger.warning("模型列表缓存为空，请先调用 get_model_options 获取模型列表")
            return {"object": "list", "data": []}
        
        logger.info(f"从缓存返回 {len(self._models_cache.get('data', []))} 个模型")
        return self._models_cache

    def create_new_chat(self, model: str, prompt: str = "") -> Optional[str]:
        """
        创建一个新的对话
        
        通过访问 https://aistudio.google.com/prompts/new_chat?model=xxx&prompt=xxx
        创建新对话，等待页面重定向后返回 prompt_id
        
        Args:
            model: 模型ID，如 "gemini-3.1-flash-lite-preview"
            prompt: 初始提示词（可选）
            
        Returns:
            str: 新创建对话的 prompt_id，如 "1_x7QIHebk9kmPOW73o5_9qIr_Lhbv4Lm"
            None: 创建失败
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return None
        
        try:
            # 构建URL
            url = f"https://aistudio.google.com/prompts/new_chat?model={model}"
            if prompt:
                # URL编码prompt
                import urllib.parse
                url += f"&prompt={urllib.parse.quote(prompt)}"
            
            logger.info(f"创建新对话: {url}")
            self.page.get(url)
            
            # 等待页面加载和重定向
            # 初始URL是 new_chat，重定向后会变成 prompts/xxx
            max_wait = 30
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                current_url = self.page.url
                
                # 检查是否已经重定向到具体的prompt页面
                if "/prompts/" in current_url and "new_chat" not in current_url:
                    # 提取prompt_id
                    prompt_id = self._extract_prompt_id(current_url)
                    if prompt_id:
                        logger.info(f"新对话创建成功，prompt_id: {prompt_id}")
                        return prompt_id
                
                # 检查是否还在加载中
                if "new_chat" in current_url:
                    logger.debug("等待页面重定向...")
                
                time.sleep(1)
            
            logger.warning(f"创建对话超时，当前URL: {self.page.url}")
            return None
            
        except Exception as e:
            logger.error(f"创建新对话时出错: {e}")
            return None

    def _extract_prompt_id(self, url: str) -> Optional[str]:
        """
        从URL中提取prompt_id
        
        Args:
            url: 如 "https://aistudio.google.com/prompts/1_x7QIHebk9kmPOW73o5_9qIr_Lhbv4Lm"
            
        Returns:
            str: prompt_id，如 "1_x7QIHebk9kmPOW73o5_9qIr_Lhbv4Lm"
            None: 提取失败
        """
        try:
            if "/prompts/" in url:
                parts = url.split("/prompts/")
                if len(parts) > 1:
                    prompt_id = parts[1].split("?")[0].split("#")[0]
                    return prompt_id
            return None
        except Exception as e:
            logger.error(f"提取prompt_id时出错: {e}")
            return None

    def get_current_prompt_id(self) -> Optional[str]:
        """
        获取当前页面的prompt_id
        
        Returns:
            str: 当前对话的prompt_id
            None: 当前不在对话页面
        """
        if not self.page:
            return None
        return self._extract_prompt_id(self.page.url)

    def navigate_to_chat(self, prompt_id: str) -> bool:
        """
        导航到指定的对话
        
        Args:
            prompt_id: 对话ID，如 "1_x7QIHebk9kmPOW73o5_9qIr_Lhbv4Lm"
            
        Returns:
            bool: 是否成功导航
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return False
        
        try:
            url = f"https://aistudio.google.com/prompts/{prompt_id}"
            logger.info(f"导航到对话: {url}")
            self.page.get(url)
            
            # 等待页面加载
            time.sleep(3)
            
            # 验证是否成功导航
            current_prompt_id = self.get_current_prompt_id()
            if current_prompt_id == prompt_id:
                logger.info(f"成功导航到对话: {prompt_id}")
                return True
            else:
                logger.warning(f"导航后prompt_id不匹配: 期望 {prompt_id}, 实际 {current_prompt_id}")
                return False
                
        except Exception as e:
            logger.error(f"导航到对话时出错: {e}")
            return False

    def send_message(self, message: str, prompt_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        发送消息到对话
        
        Args:
            message: 要发送的消息内容
            prompt_id: 对话ID，如果为None则使用当前页面
            
        Returns:
            tuple: (是否成功, 当前prompt_id)
        """
        if not self.page:
            logger.warning("浏览器未启动")
            return False, None
        
        try:
            # 如果指定了prompt_id，先导航到该对话
            if prompt_id:
                current_id = self.get_current_prompt_id()
                if current_id != prompt_id:
                    if not self.navigate_to_chat(prompt_id):
                        return False, None
            
            # 定位输入框
            # AI Studio的输入框可能有不同的选择器
            input_selectors = [
                'css:textarea[placeholder*="message"]',
                'css:textarea[placeholder*="Message"]',
                'css:.input-area textarea',
                'css:[contenteditable="true"]',
                'css:textarea',
            ]
            
            input_box = None
            for selector in input_selectors:
                try:
                    input_box = self.page.ele(selector, timeout=2)
                    if input_box:
                        break
                except:
                    continue
            
            if not input_box:
                logger.warning("未找到消息输入框")
                return False, self.get_current_prompt_id()
            
            # 输入消息
            logger.info(f"输入消息: {message[:50]}...")
            input_box.clear()
            input_box.input(message)
            time.sleep(0.5)
            
            # 发送消息（按Enter或点击发送按钮）
            # 尝试按Enter键
            self.page.key_down('return')
            self.page.key_up('return')
            
            logger.info("消息已发送")
            time.sleep(2)  # 等待发送完成
            
            # 返回当前的prompt_id（可能在发送后发生了变化）
            current_prompt_id = self.get_current_prompt_id()
            return True, current_prompt_id
            
        except Exception as e:
            logger.error(f"发送消息时出错: {e}")
            return False, self.get_current_prompt_id()

    def _fetch_models_via_listen(self) -> dict:
        """
        使用 DrissionPage 的 listen 功能监听并捕获 ListModels API 响应
        
        该方法通过设置响应回调函数，持续监听浏览器发出的网络请求，
        捕获模型列表 API 的响应数据。这样可以自动携带所有必要的认证头和请求头。
        
        Returns:
            dict: OpenAI 风格的模型列表 {"object": "list", "data": [...]}
        """
        if not self.page:
            logger.error("浏览器页面未初始化")
            return {"object": "list", "data": []}
        
        logger.info("开始监听 ListModels API 请求...")
        
        try:
            # 启动监听，指定目标 URL 特征
            self.page.listen.start('ListModels')
            
            # 等待 ListModels API 响应
            logger.info("等待 ListModels API 响应...")
            response = self.page.listen.wait(timeout=10)
            
            if response and 'ListModels' in response.request.url:
                logger.info(f"捕获到 ListModels 请求: {response.request.url}")
                
                # 检查响应状态
                if response.response.status == 200:
                    # 解析响应体
                    try:
                        response_body = response.response.body
                        if isinstance(response_body, str):
                            models_data = json.loads(response_body)
                        else:
                            models_data = response_body
                        
                        logger.info(f"成功获取模型列表，共 {len(models_data)} 个模型")
                        
                        # 转换为 OpenAI 风格格式并缓存
                        self._update_models_cache_from_api(models_data)
                        
                        return self._models_cache
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"解析响应 JSON 失败: {e}")
                else:
                    logger.warning(f"ListModels 请求返回非200状态码: {response.response.status}")
            
            logger.warning("未能捕获到有效的 ListModels API 响应")
            if self._models_cache:
                return self._models_cache
            return {"object": "list", "data": []}
            
        except Exception as e:
            logger.error(f"监听 ListModels API 时出错: {e}")
            if self._models_cache:
                return self._models_cache
            return {"object": "list", "data": []}
        finally:
            # 确保停止监听
            try:
                self.page.listen.stop()
            except:
                pass

    def _update_models_cache_from_api(self, models_data: list) -> None:
        """
        从 API 响应更新模型列表缓存
        
        ListModels API 返回的数据格式为嵌套数组，结构为：
        [
            [
                [model1_data],
                [model2_data],
                ...
            ],
            ...
        ]
        
        每个模型包含以下字段（按索引）：
        [0] - 模型ID (如 "models/gemini-3.1-pro-preview")
        [1] - null
        [2] - 版本号 (如 "3.1-pro-preview-01-2026")
        [3] - 显示名称 (如 "Gemini 3.1 Pro Preview")
        [4] - 完整描述
        [5] - 输入token限制 (如 1048576)
        [6] - 输出token限制 (如 65536)
        [7] - 支持的方法列表
        [37] - 模型描述信息
        
        Args:
            models_data: ListModels API 返回的原始模型数据列表（嵌套数组格式）
        """
        if not models_data:
            self._models_cache = {"object": "list", "data": []}
            return
        
        # 处理嵌套数组结构：[[[model1], [model2]], ...]
        # 首先展平嵌套结构，获取实际的模型列表
        actual_models = []
        
        # 第一层：models_data 是列表
        for item in models_data:
            if isinstance(item, list):
                # 第二层：item 可能是 [model1, model2, ...] 或 [[model1], [model2], ...]
                for sub_item in item:
                    if isinstance(sub_item, list):
                        # 检查这是模型数据还是另一层嵌套
                        # 模型数据的第一个元素应该是字符串（如 "models/gemini-xxx"）
                        if len(sub_item) > 0 and isinstance(sub_item[0], str) and sub_item[0].startswith("models/"):
                            actual_models.append(sub_item)
                        elif len(sub_item) > 0 and isinstance(sub_item[0], list):
                            # 还有一层嵌套，继续展平
                            for model in sub_item:
                                if isinstance(model, list) and len(model) > 0 and isinstance(model[0], str) and model[0].startswith("models/"):
                                    actual_models.append(model)
        
        if not actual_models:
            logger.warning("未能从响应中解析出有效的模型数据")
            self._models_cache = {"object": "list", "data": []}
            return
        
        formatted_models = []
        current_time = int(time.time())
        
        for model in actual_models:
            if not isinstance(model, list) or len(model) < 4:
                logger.debug(f"跳过无效的模型数据: {model}")
                continue
            
            # 解析模型字段（按数组索引）
            model_id_full = model[0] if model[0] else ""  # 如 "models/gemini-3.1-pro-preview"
            version = model[2] if len(model) > 2 and model[2] else ""  # 版本号
            display_name = model[3] if len(model) > 3 and model[3] else ""  # 显示名称
            full_description = model[4] if len(model) > 4 and model[4] else ""  # 完整描述
            
            # 提取简化的模型ID（去掉 "models/" 前缀）
            model_id = model_id_full.replace("models/", "") if isinstance(model_id_full, str) else ""
            
            # 获取模型描述（通常在索引37位置）
            description = ""
            if len(model) > 37 and model[37]:
                desc_field = model[37]
                if isinstance(desc_field, list) and len(desc_field) > 9:
                    description = desc_field[9] if desc_field[9] else ""
            
            # 获取输入/输出限制
            input_limit = model[5] if len(model) > 5 and model[5] else 0
            output_limit = model[6] if len(model) > 6 and model[6] else 0
            
            # 获取支持的方法
            supported_methods = model[7] if len(model) > 7 and isinstance(model[7], list) else []
            
            formatted_models.append({
                "id": model_id,
                "object": "model",
                "created": current_time,
                "owned_by": "google",
                "display_name": display_name,
                "version": version,
                "description": description or full_description,
                "context_window": {
                    "input_tokens": input_limit,
                    "output_tokens": output_limit
                },
                "supported_methods": supported_methods,
                "original_id": model_id_full
            })
        
        self._models_cache = {
            "object": "list",
            "data": formatted_models
        }
        
        logger.info(f"已缓存 {len(formatted_models)} 个模型")

    def _update_models_cache(self, model_options: list[dict]) -> None:
        """
        更新模型列表缓存
        
        将 get_model_options 获取的原始选项转换为 OpenAI 风格格式并缓存
        
        Args:
            model_options: get_model_options 返回的原始选项列表
        """
        if not model_options:
            self._models_cache = {"object": "list", "data": []}
            return
        
        models_data = []
        current_time = int(time.time())
        
        for opt in model_options:
            label = opt.get('label', '')
            # 将模型名称转换为 OpenAI 风格的 ID
            # 例如 "Gemini 3 Flash Preview" -> "gemini-3-flash-preview"
            model_id = label.lower().replace(' ', '-').replace('.', '-')
            
            # 跳过非模型选项（如 "Explore other models in the playground"）
            if 'explore' in model_id or 'see all' in model_id:
                continue
            
            models_data.append({
                "id": model_id,
                "object": "model",
                "created": current_time,
                "owned_by": "google",
                "description": opt.get('description', ''),
                "original_label": label
            })
        
        self._models_cache = {
            "object": "list",
            "data": models_data
        }
        
        logger.info(f"已缓存 {len(models_data)} 个模型")

    def ensure_logged_in(self) -> bool:
        """
        确保用户已登录到 Google AI Studio
        
        执行完整的登录流程检测和处理：
        1. 检查是否已登录
        2. 处理 520 错误页面
        3. 处理两步验证 (2FA)
        4. 执行普通登录流程（点击 Get Started、输入邮箱密码等）
        5. 保存登录成功的 cookie
        
        Returns:
            bool: 是否成功登录
        """
        logger.info("=" * 50)
        logger.info("开始执行登录流程检查...")
        logger.info("=" * 50)
        
        # 检查是否已经登录
        if self.is_logged_in():
            logger.info("已检测到登录状态")
            return True
        
        # 检查是否在 520 错误页面
        if self.page and self.page.url == "https://aistudio.google.com/520":
            logger.info("检测到 520 错误页面，处理中...")
            self.handle_520_error()
        
        # 检查是否在两步验证页面
        if self.is_2fa_page():
            logger.info("检测到两步验证页面，开始处理...")
            
            # 尝试自动选择验证方式
            preferred_method = os.getenv('AISTUDIO_2FA_METHOD', '')
            
            if preferred_method:
                logger.info(f"尝试使用配置的验证方式: {preferred_method}")
                if not self.select_2fa_method(method_name=preferred_method):
                    self.handle_2fa_interactive()
            else:
                self.handle_2fa_interactive()
            
            # 再次检查登录状态
            if self.is_logged_in():
                logger.info("两步验证处理完成，登录成功！")
                return True
            else:
                logger.warning("两步验证后仍未检测到登录状态")
                return False
        
        # 检查是否需要点击 Get Started 按钮（普通登录流程）
        logger.info("未检测到登录状态，尝试点击 Get Started 按钮...")
        clicked = self.click_get_started(timeout=10)
        
        if clicked:
            time.sleep(3)
            
            # 检查是否进入了 2FA 页面
            if self.is_2fa_page():
                logger.info("进入两步验证流程")
                self.handle_2fa_interactive()
                if self.is_logged_in():
                    return True
                return False
            
            # 普通登录流程
            return self._perform_standard_login()
        else:
            logger.info("页面上没有 Get Started 按钮，可能已登录或页面结构变化")
            return self.is_logged_in()
    
    def _perform_standard_login(self) -> bool:
        """
        执行标准登录流程（输入邮箱和密码）
        
        Returns:
            bool: 是否登录成功
        """
        # 输入邮箱账号
        email_entered = self.enter_email()
        
        if not email_entered:
            logger.error("邮箱输入失败")
            return False
        
        # 点击下一步
        time.sleep(1)
        next_clicked = self.click_next_after_email()
        
        if not next_clicked:
            logger.error("点击下一步失败")
            return False
        
        logger.info("进入密码输入页面")
        time.sleep(2)
        
        # 输入密码
        password_entered = self.enter_password()
        
        if not password_entered:
            logger.error("密码输入失败")
            return False
        
        # 点击密码页的下一步完成登录
        time.sleep(1)
        login_clicked = self.click_next_after_password()
        
        if not login_clicked:
            logger.error("点击登录按钮失败")
            return False
        
        logger.info("登录流程完成，等待页面跳转...")
        time.sleep(3)
        
        # 检查是否进入 2FA 页面
        if self.is_2fa_page():
            logger.info("需要进行两步验证")
            self.handle_2fa_interactive()
        
        # 最终检查登录状态
        if self.is_logged_in():
            logger.info("登录成功！")
            return True
        
        # 检查是否是 520 错误页面
        if self.page and self.page.url == "https://aistudio.google.com/520":
            logger.warning("登录后出现 520 错误，处理中...")
            self.handle_520_error()
            return self.is_logged_in()
        
        logger.warning("登录状态检测未完成，可能需要处理二次验证")
        return False
    
    def quit(self) -> None:
        """
        关闭浏览器并清理资源
        """
        # 停止监听线程
        self._stop_listener = True
        
        if self.page:
            logger.info("正在关闭浏览器...")
            try:
                # 尝试停止监听器（如果正在运行）
                try:
                    self.page.listen.stop()
                except:
                    pass
                
                self.page.quit()
            except Exception as e:
                logger.warning(f"关闭浏览器时出错: {e}")
            finally:
                self.page = None
                logger.info("浏览器已关闭")


def main():
    """
    主入口函数
    """
    # 从环境变量读取配置（如有需要）
    headless_mode = os.getenv('AISTUDIO_HEADLESS', 'true').lower() == 'true'
    user_data = os.getenv('AISTUDIO_USER_DATA')  # 可选：用户数据目录
    
    bot = None
    
    try:
        # 创建实例
        bot = AIStudioBot(
            headless=headless_mode,
            user_data_dir=user_data
        )
        
        # 启动并访问
        bot.start()
        
        # 获取页面信息
        info = bot.get_page_info()
        logger.info(f"页面信息: {info}")
        
        # 执行登录流程
        logger.info("开始执行登录流程...")
        login_success = bot.ensure_logged_in()
        
        if login_success:
            logger.info("=" * 50)
            logger.info("AIStudioBot 初始化完成，已登录")
            logger.info("=" * 50)

            # # 获取任务类型选项
            # task_options = bot.get_task_type_options()
            # print("可用任务类型:", task_options)
            
            # # 通过 label 选择
            # bot.select_task_type("/chat")

            # time.sleep(1)  # 等待模型下拉框出现
            # model_options = bot.get_model_options()
            # print("可用模型:", model_options)

            # # 更新模型缓存
            # bot._update_models_cache(model_options)

            # bot.select_model("Gemini 3 Flash Preview")  # 通过 label

            # 从缓存获取可用模型列表（OpenAI风格）
            models = bot.get_available_models()
            for model in models['data']:
                print(f"{model['id']}: {model['display_name']}")
                print(f"  描述: {model['description'][:100]}...")
                print(f"  Token限制: {model['context_window']['input_tokens']} / {model['context_window']['output_tokens']}")
                print()
            print(json.dumps(models, indent=2, ensure_ascii=False))

            # 获取模型ID列表
            model_ids = [m['id'] for m in models['data']]
            print(f"可用模型: {model_ids}")

        else:
            logger.warning("=" * 50)
            logger.warning("AIStudioBot 初始化完成，但登录可能未完成")
            logger.warning("部分功能可能受限")
            logger.warning("=" * 50)
        
        
        # TODO: 在此处添加自动化操作逻辑
        # 例如：
        # - 创建新对话
        # - 发送消息等
        
        # 保持运行（调试用），生产环境可删除或改为条件判断
        if os.getenv('AISTUDIO_KEEP_ALIVE'):
            logger.info("保持运行中，按 Ctrl+C 退出...")
            while True:
                time.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    except Exception as e:
        logger.error(f"运行出错: {e}")
        sys.exit(1)
    finally:
        if bot:
            bot.quit()


if __name__ == "__main__":
    main()
