import requests
from typing import Optional


class Bark:
    """
    Bark推送服务类，用于向iOS设备发送推送通知
    """

    def __init__(
        self, base_url, device_key: Optional[str] = None
    ):
        """
        初始化Bark推送服务

        Args:
            base_url: Bark服务的基础URL，默认为官方api.day.app
            device_key: 设备密钥，可以在初始化时设置，也可以在每次调用时传入
        """
        base_url = base_url or "https://api.day.app"
        self.base_url = base_url.rstrip("/")
        self.device_key = device_key

    def _build_url(self, endpoint: str) -> str:
        """构建完整的请求URL"""
        return f"{self.base_url}/{endpoint}"

    def _send_request(self, endpoint: str, method: str = "GET", **params) -> dict:
        """
        发送HTTP请求到Bark服务

        Args:
            endpoint: API端点
            method: HTTP方法
            **params: URL参数

        Returns:
            服务器响应结果
        """
        url = self._build_url(endpoint)

        # 过滤掉值为None的参数
        params = {k: v for k, v in params.items() if v is not None}

        try:
            if method.upper() == "GET":
                response = requests.get(url, params=params)
            elif method.upper() == "POST":
                response = requests.post(url, data=params)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"发送Bark推送失败: {e}")
            return {"success": False, "error": str(e)}

    def push(
        self,
        title: Optional[str] = None,
        body: str = "",
        device_key: Optional[str] = None,
        group: Optional[str] = None,
        icon: Optional[str] = None,
        sound: Optional[str] = None,
        level: Optional[str] = None,
        badge: Optional[int] = None,
        url: Optional[str] = None,
        automatically_copy: Optional[int] = None,
        copy: Optional[str] = None,
        is_archive: Optional[int] = None,
        method: str = "GET",
    ) -> dict:
        """
        通用推送方法

        Args:
            title: 推送标题
            body: 推送内容
            device_key: 设备密钥，如果初始化时已设置可以不传
            group: 推送分组
            icon: 自定义图标URL
            sound: 自定义铃声
            level: 通知级别 (active, timeSensitive, passive)
            badge: 应用图标徽标数
            url: 点击推送后跳转的URL
            automatically_copy: 是否自动复制推送内容到剪贴板 (1=是, 0=否)
            copy: 指定要复制到剪贴板的内容
            is_archive: 是否保存到历史记录 (1=是, 0=否)
            method: HTTP方法 ('GET' 或 'POST')

        Returns:
            服务器响应结果
        """
        device_key = device_key or self.device_key
        if not device_key:
            raise ValueError("必须提供device_key，可在初始化时设置或在方法中传入")

        # 构造API端点
        if title:
            endpoint = f"{device_key}/{title}/{body}"
        else:
            endpoint = f"{device_key}/{body}"

        # 构造URL参数
        params = {
            "group": group,
            "icon": icon,
            "sound": sound,
            "level": level,
            "badge": badge,
            "url": url,
            "automaticallyCopy": automatically_copy,
            "copy": copy,
            "isArchive": is_archive,
        }

        return self._send_request(endpoint, method, **params)

    def simple_push(self, body: str, device_key: Optional[str] = None) -> dict:
        """
        简单推送，只需要内容

        Args:
            body: 推送内容
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(body=body, device_key=device_key)

    def title_body_push(
        self, title: str, body: str, device_key: Optional[str] = None
    ) -> dict:
        """
        标题+内容推送

        Args:
            title: 推送标题
            body: 推送内容
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(title=title, body=body, device_key=device_key)

    def push_with_url(
        self, title: str, body: str, url: str, device_key: Optional[str] = None
    ) -> dict:
        """
        带跳转链接的推送

        Args:
            title: 推送标题
            body: 推送内容
            url: 点击推送后跳转的链接
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(title=title, body=body, url=url, device_key=device_key)

    def push_with_copy(
        self,
        title: str,
        body: str,
        automatically_copy: int = 1,
        copy: Optional[str] = None,
        device_key: Optional[str] = None,
    ) -> dict:
        """
        自动复制内容的推送

        Args:
            title: 推送标题
            body: 推送内容
            automatically_copy: 是否自动复制 (1=是, 0=否)，默认为1
            copy: 如果提供，则复制此内容而不是推送内容
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(
            title=title,
            body=body,
            automatically_copy=automatically_copy,
            copy=copy,
            device_key=device_key,
        )

    def push_with_group(
        self, title: str, body: str, group: str, device_key: Optional[str] = None
    ) -> dict:
        """
        分组推送

        Args:
            title: 推送标题
            body: 推送内容
            group: 推送分组
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(title=title, body=body, group=group, device_key=device_key)

    def push_with_sound(
        self, title: str, body: str, sound: str, device_key: Optional[str] = None
    ) -> dict:
        """
        自定义铃声推送

        Args:
            title: 推送标题
            body: 推送内容
            sound: 自定义铃声名称
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(title=title, body=body, sound=sound, device_key=device_key)

    def push_with_icon(
        self, title: str, body: str, icon: str, device_key: Optional[str] = None
    ) -> dict:
        """
        自定义图标推送

        Args:
            title: 推送标题
            body: 推送内容
            icon: 自定义图标URL
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(title=title, body=body, icon=icon, device_key=device_key)

    def important_push(
        self, title: str, body: str, device_key: Optional[str] = None
    ) -> dict:
        """
        重要通知推送（iOS 15+）

        Args:
            title: 推送标题
            body: 推送内容
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(
            title=title, body=body, level="timeSensitive", device_key=device_key
        )

    def archive_push(
        self, title: str, body: str, device_key: Optional[str] = None
    ) -> dict:
        """
        保存到历史记录的推送

        Args:
            title: 推送标题
            body: 推送内容
            device_key: 设备密钥

        Returns:
            服务器响应结果
        """
        return self.push(title=title, body=body, is_archive=1, device_key=device_key)


# 示例使用
if __name__ == "__main__":
    # 创建Bark实例，传入设备密钥
    bark = Bark(device_key="your_device_key_here")

    # 各种推送示例
    # 简单推送
    # bark.simple_push("签到成功")

    # 标题+内容推送
    # bark.title_body_push("签到结果", "今日签到成功")

    # 带链接推送
    # bark.push_with_url("签到结果", "今日签到成功", "https://www.example.com")

    # 自动复制推送
    # bark.push_with_copy("验证码", "您的验证码是123456", copy="123456")

    # 分组推送
    # bark.push_with_group("系统通知", "服务器状态正常", "server_status")

    # 重要通知推送
    # bark.important_push("紧急通知", "系统即将维护")

    # 保存到历史记录的推送
    # bark.archive_push("日志", "执行了一次定时任务")
