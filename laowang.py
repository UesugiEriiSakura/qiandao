from asyncio.log import logger
import base64
import os

# os.environ["QT_QPA_PLATFORM"] = "offscreen"
# os.environ["DISPLAY"] = ":0.0"
import random
import re
import sys
import time
import requests
from DrissionPage import ChromiumPage, ChromiumOptions
import cv2
import numpy as np
from captcha_recognizer.slider import Slider

from send import Send


class LaoWangSign:
    proxies = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
    retry_count = 0
    matching_method = "cv"

    def __init__(
        self,
        hostname,
        username,
        password,
        cookie,
        questionid="0",
        answer=None,
        proxies=None,
    ):
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
    def user_sign(
        cls,
        hostname,
        username,
        password,
        cookie,
        questionid="0",
        answer=None,
        proxies=None,
        matching_method="cv",
    ):
        user = LaoWangSign(
            hostname, username, password, cookie, questionid, answer, proxies
        )
        user.matching_method = matching_method
        # 尝试处理验证码
        user.check_verity_code()

        return user

    def handle_language_popup(self, page: ChromiumPage):
        """检查并处理语言选择弹窗"""
        try:
            # 检查是否存在语言选择按钮
            lang_btn = page.ele("text:简体中文（繁转简）", timeout=2)
            if lang_btn:
                print("🌐 发现语言选择弹窗，点击 '简体中文（繁转简）'...")
                lang_btn.click()
                print("⏳ 等待页面重新加载...")
                page.wait.load_start()
                time.sleep(2)
                return True
        except Exception as e:
            print(f"⚠️ 处理语言弹窗时出错: {e}")
        return False

    def check_verity_code(self):
        # # 使用DrissionPage访问页面
        # 配置选项
        co = ChromiumOptions()
        is_ci = (
            os.getenv("CI") == "true"
            or os.getenv("GITHUB_ACTIONS") == "true"
            or os.getenv("GITLAB_CI") == "true"
            or os.getenv("TRAVIS") == "true"
        )
        if not is_ci:
            print("设置网络代理.")
            co.set_proxy("http://127.0.0.1:7890")
        co.set_argument("--disable-gpu")  # 禁用 GPU（服务器通常没有）
        co.set_argument("--disable-dev-shm-usage")  # 解决共享内存不足崩溃
        # co.headless(True)
        # co.set_argument("--headless=new")
        co.set_argument("--no-sandbox")  # 解决 root 用户运行崩溃
        # co.set_argument('--window-size=1920,1080')
        # 设置 User-Agent
        co.set_user_agent(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        )
        page = ChromiumPage(co)
        try:
            page.run_cdp("Network.clearBrowserCookies")
            page.get(f"https://{self.hostname}")
            page.set.cookies(self.cookie)
            print("正在访问...")
            page.get(f"https://{self.hostname}/plugin.php?id=k_misign:sign")

            page.wait.load_start()
            self.handle_language_popup(page)

            # 检查是否还在验证页
            if (
                "Just a moment" in page.title
                or "正在验证" in page.html
                or "验证您是真人" in page.html
            ):
                print("遇到验证盾，等待通过...")
                time.sleep(10)

            # 获取真实标题
            print("当前标题:", page.title)
            self.retry_count = 0
            if "action=login" in page.html:
                print("⚠️ 当前用户未登录")
                login = self.login(page)
                if login:
                    print("✅ 登录成功")
                    time.sleep(5)
                    if "每日签到老王论坛" not in page.title:
                        print("⚠️ 当前页面不是每日签到页面, 即将跳转到签到页面...")
                        page.get(f"https://{self.hostname}/plugin.php?id=k_misign:sign")
                        time.sleep(5)
                else:
                    print("❌ 登录失败")
                    Send.send("登录失败")
                    return False

            self.handle_language_popup(page)
            sign_button = page.ele(
                'css:a.J_chkitot[href*="operation=qiandao"]', timeout=10
            )
            if sign_button:
                print("✅ 找到签到按钮")
                sign_button.click()
                print("👆 已点击签到按钮，等待签到结果...")
                time.sleep(2)
                result = self.click_tncode(page)
                if result:
                    self.handle_language_popup(page)
                    if page.wait.ele_displayed("#submit-btn", timeout=5):
                        submit = page.ele("#submit-btn", timeout=10)
                        print("👆 提交表单...")
                        submit.click()
                        time.sleep(10)
                        if '<span class="btn btnvisted"></span>' in page.html:
                            print("✅ 签到成功！")
                            self.parse_person_info(page)
                        else:
                            print("❌ 签到失败！")
                            Send.send("签到失败， 未找到签到成功标志")
                        return True
                    else:
                        print("❌ 没有找到提交按钮")
                        Send.send("未知异常, 没有找到提交按钮")
            else:
                time.sleep(5)
                if '<span class="btn btnvisted"></span>' in page.html:
                    print("✅ 已签到")
                    self.parse_person_info(page)
                else:
                    print(page.html)
                    print("❌ 未找到签到按钮")
                    Send.send("未知异常, 未找到签到按钮")
            return False
        except Exception as e:
            print(f"验证码识别失败: {e}")
            Send.send(f"验证码识别失败: {e}")
            return False
        finally:
            if "page" in locals():
                page.quit()

    def click_tncode(self, page: ChromiumPage) -> bool:
        # 点击验证按钮
        self.handle_language_popup(page)
        if page.wait.ele_displayed("#tncode", timeout=15):
            print("✅ 找到验证按钮")
            btn = page.ele("#tncode", timeout=10)
            btn.click()
            print("👆 已点击按钮，等待滑块弹出...")

            return self.verify_captcha(page, retry=True)
        else:
            print("❌ 超时：没有找到 #tncode 按钮")
        return False

    def verify_captcha(self, page: ChromiumPage, retry=False) -> bool:
        self.retry_count = self.retry_count + 1
        print(f"开始第{self.retry_count}次验证滑块...")
        if page.wait.ele_displayed(".slide_block", timeout=10):
            print("🧩 滑块已弹出，准备识别和滑动...")
            # 获取滑块元素
            slider = page.ele(".slide_block", timeout=10)
            if page.wait.ele_displayed(".tncode_canvas_bg", timeout=5):
                print("🎭 执行假动作：点击滑块，触发缺口显示...")
                slider.click()
                print("💤 等待5S，让页面渲染缺口")
                time.sleep(5)
                if self.matching_method == "model":
                    bg_ele = page.ele(".tncode_canvas_bg", timeout=10)
                    if bg_ele:
                        bg_bytes = bg_ele.get_screenshot(as_bytes=True)
                        print("尝试模型匹配全图")
                        box, confidence = Slider().identify(source=bg_bytes, show=False)
                        print(f"缺口坐标: {box}")
                        print("置信度", confidence)
                    else:
                        print("❌ 未找到背景 Canvas")
                else:
                    print("🖼️ 正在保存验证码背景图...")
                    # 注入 JS 代码
                    js_bg = "return document.querySelector('.tncode_canvas_bg').toDataURL('image/png');"
                    js_mark = "return document.querySelector('.tncode_canvas_mark').toDataURL('image/png');"
                    # 执行并获取结果
                    b64_bg = page.run_js(js_bg)
                    b64_mark = page.run_js(js_mark)
                    if b64_bg and b64_mark:
                        # 解码 Base64
                        img_bytes = base64.b64decode(b64_bg.split(",")[1])
                        mark_bytes = base64.b64decode(b64_mark.split(",")[1])

                        print(f"💾 保存成功, {len(img_bytes)} bytes")
                        # 2. 调用OpenCV 识别
                        distance = self.get_gap_by_template_match(mark_bytes, img_bytes)

                        print(f"已计算缺口位置{distance}")
                        print(f"📏 识别距离: {distance}")
                        if distance > 0:
                            print(f"🚀 继续拖动剩余距离: {distance}")
                            # 继续移动剩余距离，然后松开
                            # 生成一个随机的拖动时长，范围 0.6 ~ 1.2 秒
                            # tncode 对时间敏感，不能太快也不能太慢
                            duration = random.uniform(0.6, 1.2)

                            print(
                                f"🚀 开始智能拖动，距离: {distance}, 耗时: {duration:.2f}s"
                            )
                            page.actions.hold(slider).move(distance, duration).release()
                        else:
                            print("❌ 距离计算异常，松开鼠标")
                            page.actions.release()

                        # 验证结果检查...
                        time.sleep(3)
                        if "验证成功" in page.html:
                            print("✅ 验证通过！")
                            return True
                        else:
                            if retry and self.retry_count <= 5:
                                print("❌ 验证失败，重新验证...")
                                tncode_refresh = page.ele(".tncode_refresh", timeout=10)
                                tncode_refresh.click()
                                print("💤 点击图片刷新按钮，待 5S 后重新识别")
                                time.sleep(5)
                                return self.verify_captcha(page, retry=True)
                            else:
                                print("❌ 验证失败！")
            else:
                print("❌ 点击了按钮，但图片没有加载出来")
        else:
            print("❌ 点击了按钮，但滑块没有弹出来")

        return False

    def get_gap_by_template_match(self, mark_bytes, bg_bytes):
        # 使用 IMREAD_UNCHANGED 读取，以防图片包含透明通道(Alpha)
        # mark = cv2.imread(mark_path, cv2.IMREAD_UNCHANGED)
        # bg = cv2.imread(bg_path)
        # 将 bytes 转为 numpy array
        mark_arr = np.frombuffer(mark_bytes, np.uint8)
        bg_arr = np.frombuffer(bg_bytes, np.uint8)
        mark = cv2.imdecode(mark_arr, cv2.IMREAD_UNCHANGED)
        bg = cv2.imdecode(bg_arr, cv2.IMREAD_COLOR)

        if mark is None or bg is None:
            print("错误：无法读取图片")
            return

        print("Step 1: 提取滑块形状...")
        # 判断是否包含 Alpha 通道 (透明背景)
        if mark.shape[2] == 4:
            # 如果是 PNG 透明图，直接取第4个通道(Alpha)作为掩码
            print("检测到透明通道，直接使用Alpha层")
            mask = mark[:, :, 3]
        else:
            # 如果是 JPG 或黑底图，转灰度后取阈值
            print("未检测到透明通道，使用灰度阈值法")
            mark_gray = cv2.cvtColor(mark, cv2.COLOR_BGR2GRAY)
            # 只要像素值大于 10 (不是纯黑)，就认为是滑块的一部分
            _, mask = cv2.threshold(mark_gray, 10, 255, cv2.THRESH_BINARY)

        # 寻找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            print("错误：无法提取滑块轮廓")
            return

        # 取最大轮廓
        c = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(c)
        print(f"   滑块尺寸: {w}x{h}")

        # 裁切掩码作为模板
        template_roi = mask[y : y + h, x : x + w]

        # 提取边缘Mask (Canny)
        template_edge = cv2.Canny(template_roi, 100, 200)

        print("Step 2: 处理背景...")
        # 计算滑块在背景中的Y轴位置， 宽容度5
        # 先锁定Y轴区域，再处理图片
        print(f"滑块在背景中的Y轴起始位置: {y}， 滑块在背景中的Y轴结束位置: {y+h}")
        search_y_start = max(0, y - 5)
        search_y_end = min(bg.shape[0], y + h + 5)
        bg_strip = bg[search_y_start:search_y_end, :]

        bg_gray = cv2.cvtColor(bg_strip, cv2.COLOR_BGR2GRAY)
        # 直方图均衡化 (增强缺口阴影对比度)
        bg_eq = cv2.equalizeHist(bg_gray)
        # 边缘检测
        bg_edge = cv2.Canny(bg_eq, 50, 200)

        print("Step 3: 匹配中...")
        res = cv2.matchTemplate(bg_edge, template_edge, cv2.TM_CCOEFF_NORMED)
        # 屏蔽左侧区域,防止匹配到滑块起始位置
        # 屏蔽宽度设为滑块宽度的 1.2 倍
        safe_margin = int(w * 1.2)
        if res.shape[1] > safe_margin:
            res[:, :safe_margin] = -1.0

        # 可视化热力图
        res_vis = cv2.normalize(res, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        best_x = max_loc[0]
        best_y = search_y_start + max_loc[1]

        print("Step 4: 输出结果...")
        result_img = bg.copy()
        cv2.rectangle(
            result_img, (best_x, best_y), (best_x + w, best_y + h), (0, 0, 255), 2
        )

        # 画一下搜索区域辅助线
        cv2.rectangle(
            result_img, (0, search_y_start), (bg.shape[1], search_y_end), (0, 255, 0), 1
        )

        print("-" * 30)
        print(f"【最终结果】")
        print(f"缺口坐标: X={best_x}")
        print("-" * 30)

        return best_x

    def parse_person_info(self, page: ChromiumPage):
        print("5S 后，开始解析个人资料")
        time.sleep(5)
        deanvwmy = page.ele(".deanvwmy", timeout=10)
        if deanvwmy:
            space_url = deanvwmy.link
            print(f"✅ 访问空间: {space_url}")
            page.get(space_url)
        rmb_em = page.ele("tag:em@@text():软妹币")

        if rmb_em:
            rmb_li = rmb_em.parent()
            full_text = rmb_li.text

            # 使用正则提取其中的数字
            # \d+ 表示匹配连续的数字
            match = re.search(r"(\d+)", full_text)

            if match:
                rmb_count = match.group(1)
                print(f"💰 软妹币: {rmb_count}")
            else:
                print(f"⚠️ 正则未匹配到，原始文本为: {full_text}")
        else:
            print("❌ 未找到包含‘软妹币’的标签")

        group_label = page.ele("text:用户组")
        if group_label:
            group_info_span = group_label.next("tag:span")

            if group_info_span:
                # 获取名称
                group_name = group_info_span.text

                # 获取属性 tip
                group_tip = group_info_span.attr("tip")

                print(f"🔰 用户组: {group_name}")
                print(f"📝 详细Tip: {group_tip}")
        Send.send(f"✅ 签到成功\n💰 软妹币: {rmb_count}\n🔰 用户组: {group_name}\n📝 Tips: {group_tip}")

    def login(self, page: ChromiumPage) -> bool:
        # 清除所有Cookie
        page.run_cdp("Network.clearBrowserCookies")
        login_url = f"https://{self.hostname}/member.php?mod=logging&action=login"
        print(f"跳转登录页: {login_url}")
        page.get(login_url)

        page.wait.load_start()
        self.handle_language_popup(page)

        print(page.title)

        print("📝 正在填写账号密码...")
        user_input = page.ele('css:input[id^="username_"]', timeout=10)
        if user_input:
            print("✅ 找到用户名输入框")
            user_input.input(self.username)
        else:
            print("❌ 未找到用户名输入框，请检查页面是否还在加载")
            return False
        pass_input = page.ele('css:input[id^="password3_"]', timeout=10)
        if pass_input:
            print("✅ 找到密码输入框")
            pass_input.input(self.password)
        else:
            print("❌ 未找到密码输入框，请检查页面是否还在加载")
            return False
        if self.questionid != "0":
            print("🔒 选择安全提问...")

            # 直接根据 value 选择
            page.ele('css:select[id^="loginquestionid_"]').select.by_value(
                self.questionid
            )

            # 稍微等待一下输入框显示
            ans_input = page.wait.ele_displayed('css:input[id^="loginanswer_"]')
            if ans_input:
                page.ele('css:input[id^="loginanswer_"]').input(self.answer)
        print("🛡️ 点击验证码...")
        if self.click_tncode(page):
            print("📝 提交登录表单...")
            page.ele("#captcha_submit").click()
            print("⏳ 等待登录跳转...")
            time.sleep(5)
            if "action=login" not in page.html:
                print("🎉 登录 Cookie 已写入！")
                # 双重保险：强制刷新一次，确保 Cookie 生效
                page.refresh()
                return True
            else:
                print("❌ 登录失败")
                # 如果没等到用户菜单，检查是否有错误提示
                err_msg = page.ele(".alert_error", timeout=10)
                if err_msg:
                    print(f"❌ 登录报错: {err_msg.text}")
                else:
                    print("❌ 登录超时，未检测到登录状态变更")
        else:
            print("❌ 验证码失败")

        return False


if __name__ == "__main__":
    try:
        # laowang.vip 签到
        laowang_url = os.environ.get("LAOWANG_HOSTNAME", "")
        laowang_username = os.environ.get("LAOWANG_USERNAME", "")
        laowang_password = os.environ.get("LAOWANG_PASSWORD", "")
        laowang_cookie = os.environ.get("LAOWANG_COOKIE", "")
        matching_method = os.environ.get("MATCHING_METHOD", "cv")
        laowang_password = "base64://" + base64.b64encode(
            laowang_password.encode("utf-8")
        ).decode("utf-8")
        LaoWangSign.user_sign(
            laowang_url,
            laowang_username,
            laowang_password,
            laowang_cookie,
            matching_method=matching_method,
        )

    except Exception as e:
        logger.error(e)
        sys.exit(1)
