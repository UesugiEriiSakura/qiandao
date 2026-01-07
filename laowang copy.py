import base64
import random
import time
import requests
import re
from DrissionPage import ChromiumPage, ChromiumOptions
from PIL import Image
from io import BytesIO
import cv2
import numpy as np


class LaoWangLogin:
    proxies = {
        'http': 'http://127.0.0.1:7890',
        'https': 'http://127.0.0.1:7890'
    }

    def __init__(self, hostname, username, password, cookie, questionid='0', answer=None, proxies=None):
        self.session = requests.session()
        self.hostname = hostname
        self.username = username
        self.password = password
        self.cookie = cookie
        self.questionid = questionid
        self.answer = answer
        if proxies:
            self.proxies = proxies

    @classmethod
    def user_login(cls, hostname, username, password, cookie, questionid='0', answer=None, proxies=None):
        user = LaoWangLogin(hostname, username, password, cookie, questionid, answer, proxies)
        # 尝试处理验证码
        user.check_verity_code()

        return user
    
    def check_verity_code(self):
        # # 使用DrissionPage访问页面
        # 配置选项
        co = ChromiumOptions()
        co.set_proxy('http://127.0.0.1:7890')
        co.set_argument('--disable-gpu')         # 禁用 GPU（服务器通常没有）
        co.set_argument('--disable-dev-shm-usage') # 解决共享内存不足崩溃
        # co.headless(True) 
        # co.set_argument('--headless=new')
        co.set_argument('--no-sandbox')          # 解决 root 用户运行崩溃
        # co.set_argument('--window-size=1920,1080') 
        # 设置 User-Agent
        co.set_user_agent(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36')
        page = ChromiumPage(co)
        try:
            page.get(f'https://{self.hostname}')
            page.set.cookies(self.cookie)
            print("正在访问...")
            page.get(f'https://{self.hostname}/plugin.php?id=k_misign:sign')
            
            page.wait.load_start()
    
            # 检查是否还在验证页（检测 title 或者特定元素）
            if "Just a moment" in page.title or "正在验证" in page.html or "验证您是真人" in page.html:
                print("遇到验证盾，等待通过...")
                time.sleep(10) # 给它一点时间自动跳转
    
            # 获取真实标题
            print("当前标题:", page.title)

            if 'action=login' in page.html:
                print("✅ 当前用户未登录")
                return False

            sign_button = page.ele('css:a.J_chkitot[href*="operation=qiandao"]', timeout=5)
            if sign_button:
                print("✅ 找到签到按钮")
                sign_button.click()
                print("👆 已点击签到按钮，等待签到结果...")
                time.sleep(2)
                # 点击验证按钮
                if page.wait.ele_displayed('#tncode', timeout=15):
                    print("✅ 找到验证按钮")
                    # 2. 点击按钮
                    btn = page.ele('#tncode', timeout=10)
                    btn.click()
                    print("👆 已点击按钮，等待滑块弹出...")

                    # -------------------------------------------------
                    # 3. 点击后，需要处理弹出的滑块
                    # -------------------------------------------------
                    # 滑块按钮的 class 是 slide_block
                    if page.wait.ele_displayed('.slide_block', timeout=10):
                        print("🧩 滑块已弹出，准备识别和滑动...")
                        # 获取滑块元素
                        slider = page.ele('.slide_block', timeout=10)
                        time.sleep(1)
                        print("👆 滑块已点击，🧩 获取缺口图片...")
                        if (page.wait.ele_displayed('.tncode_canvas_bg', timeout=5)):
                            print("🎭 执行假动作：点击滑块，触发缺口显示...")
                            slider.click()
                            print("💤 等待10S，让页面渲染缺口")
                            time.sleep(10) 
                            bg_ele = page.ele('.tncode_canvas_bg', timeout=10) 
                            mark_ele = page.ele('.tncode_canvas_mark', timeout=10) # 获取小滑块画布
                            if bg_ele:
                                print("🖼️ 正在保存验证码背景图...")
                                print("🖼️ 通过 JS 获取原生 Canvas 数据...")
                                # 注入 JS 代码
                                js_bg = "return document.querySelector('.tncode_canvas_bg').toDataURL('image/png');"
                                js_mark = "return document.querySelector('.tncode_canvas_mark').toDataURL('image/png');"
                                # 执行并获取结果
                                b64_bg = page.run_js(js_bg)
                                b64_mark = page.run_js(js_mark)
                                if b64_bg and b64_mark:
                                    # 解码 Base64 (去掉开头的 'data:image/png;base64,')
                                    img_bytes = base64.b64decode(b64_bg.split(',')[1])
                                    mark_bytes = base64.b64decode(b64_mark.split(',')[1])

                                    print(f"💾 保存成功, {len(img_bytes)} bytes")
                                    # 2. 这里调用你的 OpenCV 识别逻辑
                                    captcha_img = Image.open(BytesIO(img_bytes))
                                    captcha_img.save('bg.png')
                                    mark_img = Image.open(BytesIO(mark_bytes))
                                    mark_img.save('mark.png')
                                    # 计算缺口位置
                                    distance = self.get_gap_by_template_match(captcha_img, mark_img)
                                    print(f"已计算缺口位置{distance}")
                                    print(f"📏 识别距离: {distance}")
                                    if distance > 0:
                                        print(f"🚀 继续拖动剩余距离: {distance}")
                                        # 继续移动剩余距离，然后松开
                                        # 生成一个随机的拖动时长，范围 0.5 ~ 0.8 秒
                                        # tncode 对时间敏感，不能太快也不能太慢
                                        duration = random.uniform(0.6, 1.0)
            
                                        print(f"🚀 开始智能拖动，距离: {distance}, 耗时: {duration:.2f}s")
                                        page.actions.hold(slider).move(distance, duration).release()
                                    else:
                                        print("❌ 距离计算异常，松开鼠标")
                                        page.actions.release()
                                    
                                    # 验证结果检查...
                                    time.sleep(3)
                                    if "验证成功" in page.html:
                                        print("✅ 验证通过！")
                                        time.sleep(1)
                                        if (page.wait.ele_displayed('#submit-btn', timeout=5)):
                                            submit = page.ele('#submit-btn', timeout=10)
                                            print("👆 提交表单...")
                                            submit.click()
                                            time.sleep(10)
                                            if '<span class="btn btnvisted"></span>' in page.html:
                                                print("✅ 签到成功！")
                                            else:
                                                print("❌ 签到失败！")
                                            
                                            time.sleep(20)
                                            return True
                                        else:
                                            print("❌ 没有找到提交按钮")
                                    else:
                                        tncode_refresh = page.ele('.tncode-refresh', timeout=10)
                                        tncode_refresh.click()
                                        print("❌ 验证失败！")
                            else:
                                print("❌ 未找到背景 Canvas")
                        else:
                            print("❌ 点击了按钮，但图片没有加载出来")
                    else:
                        print("❌ 点击了按钮，但滑块没有弹出来")

                else:
                    print("❌ 超时：没有找到 #tncode 按钮")
            else:
                time.sleep(5)
                if '<span class="btn btnvisted"></span>' in page.html:
                    print("✅ 已签到")
                else:
                    print("❌ 未找到签到按钮")
            return False
        except Exception as e:
            print(f"验证码识别失败: {e}")
            return False
        finally:
            if 'page' in locals():
                page.quit()
    def get_gap_by_template_match(self, bg_image, mark_image):
        """
        利用滑块图片(mark)作为模板，在背景(bg)中寻找缺口
        特性：Y轴锁定 + 纯轮廓/灰度混合 + 自适应参数重试机制
        """
        import cv2
        import numpy as np

        # 1. 图像转 OpenCV 格式
        bg = np.array(bg_image)
        mark = np.array(mark_image)

        if len(bg.shape) == 3 and bg.shape[2] == 4:
            bg = cv2.cvtColor(bg, cv2.COLOR_RGBA2BGR)
        elif len(bg.shape) == 3 and bg.shape[2] == 3:
            bg = cv2.cvtColor(bg, cv2.COLOR_RGB2BGR)

        debug_img = bg.copy()

        # =========================================================
        # 第一步：提取滑块坐标
        # =========================================================
        x, y, w, h = 0, 0, 0, 0
        valid_template_found = False
        
        if len(mark.shape) == 3 and mark.shape[2] == 4:
            alpha = mark[:, :, 3]
            _, thresh = cv2.threshold(alpha, 128, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                cx, cy, cw, ch = cv2.boundingRect(contour)
                if 35 < cw < 90 and 35 < ch < 90 and 0.7 < cw/ch < 1.4:
                    x, y, w, h = cx, cy, cw, ch
                    valid_template_found = True
                    cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    break 

        if not valid_template_found:
            print("⚠️ 无法提取滑块，使用兜底逻辑")
            return 0

        # 提取滑块纯 Alpha 形状
        template_alpha = mark[y:y+h, x:x+w, 3]

        # =========================================================
        # 定义核心匹配函数 (支持不同参数)
        # =========================================================
        def try_match(strategy_name, blur_ksize, canny_thresh, dilate_iter, use_gray=False):
            """
            内部函数：尝试使用指定参数进行匹配
            """
            # 1. 准备模板
            if use_gray:
                # 灰度模式：使用 mark 的灰度图作为模板
                # (注意：因为背景复杂，灰度模式通常不如边缘模式，仅作兜底)
                mark_gray = cv2.cvtColor(mark, cv2.COLOR_RGBA2GRAY)
                template_processed = mark_gray[y:y+h, x:x+w]
                bg_processed = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
            else:
                # 边缘模式：制作边缘模板
                _, template_bin = cv2.threshold(template_alpha, 128, 255, cv2.THRESH_BINARY)
                template_edge = cv2.Canny(template_bin, 100, 200)
                if dilate_iter > 0:
                    kernel = np.ones((3, 3), np.uint8)
                    template_processed = cv2.dilate(template_edge, kernel, iterations=dilate_iter)
                else:
                    template_processed = template_edge

                # 处理背景
                bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
                # 高斯模糊
                if blur_ksize > 0:
                    bg_blur = cv2.GaussianBlur(bg_gray, (blur_ksize, blur_ksize), 0)
                else:
                    bg_blur = bg_gray
                
                # 边缘检测
                bg_edge = cv2.Canny(bg_blur, canny_thresh[0], canny_thresh[1])
                # 膨胀
                if dilate_iter > 0:
                    kernel = np.ones((3, 3), np.uint8)
                    bg_processed = cv2.dilate(bg_edge, kernel, iterations=dilate_iter)
                else:
                    bg_processed = bg_edge

            # 2. 锁定 Y 轴搜索区域
            y_margin = 0 # 严格锁定
            x_padding = 5 # 右边距
            
            search_y_start = y
            search_y_end = y + h
            x_start = x + w 
            x_end = bg.shape[1] - x_padding
            
            # 边界保护
            if search_y_end > bg_processed.shape[0]: search_y_end = bg_processed.shape[0]
            
            # 截取搜索条
            search_region = bg_processed[search_y_start:search_y_end, x_start:x_end]
            
            # 尺寸对齐 (防止 Canny 后尺寸微差)
            if search_region.shape[0] != template_processed.shape[0]:
                template_processed = cv2.resize(template_processed, (template_processed.shape[1], search_region.shape[0]))
            
            # 3. 匹配
            res = cv2.matchTemplate(search_region, template_processed, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            matched_x_rel = max_loc[0]
            absolute_x = matched_x_rel + x_start
            
            return absolute_x, max_val

        # =========================================================
        # 第二步：自适应策略循环 (递归/重试逻辑)
        # =========================================================
        
        # 定义策略列表：[名称, 模糊核大小, Canny阈值, 膨胀次数, 是否灰度]
        strategies = [
            # 策略 1: 敏感模式 (抓极淡的阴影) - 之前成功的配置
            ('Sensitive Edge', 5, (20, 60), 1, False),
            
            # 策略 2: 标准模式 (抓清晰轮廓) - 阈值稍高，防止噪点
            ('Standard Edge', 3, (50, 150), 1, False),
            
            # 策略 3: 强力模式 (无模糊，直接干) - 适合纹理不多的背景
            ('Raw Edge', 0, (30, 100), 1, False),
            
            # 策略 4: 极简模式 (不膨胀) - 适合缺口边缘非常细的情况
            ('Thin Edge', 3, (40, 120), 0, False),
            
            # 策略 5: 灰度匹配兜底 (如果边缘检测彻底失效)
            ('Grayscale Fallback', 0, (0,0), 0, True)
        ]

        best_result = (0, 0) # (x, confidence)
        final_strategy_name = ""

        print(f"🧩 开始多策略匹配 (目标置信度 > 0.4)...")

        for strat in strategies:
            name, blur, canny, dilate, is_gray = strat
            
            # 执行匹配
            curr_x, curr_conf = try_match(name, blur, canny, dilate, is_gray)
            
            print(f"  👉 [{name}]: 置信度 {curr_conf:.2f}, 位置 {curr_x}")
            
            # 记录历史最佳
            if curr_conf > best_result[1]:
                best_result = (curr_x, curr_conf)
                final_strategy_name = name
            
            # 【核心逻辑】如果置信度达标，直接中断循环 (相当于递归基准条件)
            if curr_conf > 0.4:
                print(f"✅ 置信度达标，提前结束！")
                break
        
        # =========================================================
        # 第三步：处理最终结果
        # =========================================================
        
        final_x, final_conf = best_result
        print(f"🏆 最终选用 [{final_strategy_name}]: 置信度 {final_conf:.2f}, 位置 {final_x}")

        # 画红框
        cv2.rectangle(debug_img, (final_x, y), (final_x + w, y + h), (0, 0, 255), 2)
        cv2.putText(debug_img, f"{final_strategy_name}: {final_conf:.2f}", (final_x, y - 5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
        
        cv2.imwrite('debug_final_result.png', debug_img)

        real_distance = final_x - x
        if real_distance < 0: return final_x
        
        return real_distance
    
    def form_hash(self):
        rst = self.session.get(f'https://{self.hostname}/member.php?mod=logging&action=login').text
        loginhash = re.search(r'<div id="main_messaqge_(.+?)">', rst).group(1)
        formhash = re.search(r'<input type="hidden" name="formhash" value="(.+?)" />', rst).group(1)
        return loginhash, formhash

    def login(self):
        loginhash, formhash = self.form_hash()
        login_url = f'https://{self.hostname}/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={loginhash}&inajax=1'
        form_data = {
            'formhash': formhash,
            'referer': f'https://{self.hostname}/',
            'loginfield': self.username,
            'username': self.username,
            'password': self.password,
            'questionid': self.questionid,
            'answer': self.answer,
            'cookietime': 2592000
        }
        print(form_data)
        login_rst = self.session.post(login_url, proxies=self.proxies, data=form_data)
        print(login_rst.text)
        if self.session.cookies.get('xxzo_2132_auth'):
            print(f'Welcome {self.username}!')
        else:
            print('Login failed, need to verify captcha')