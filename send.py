import os
from channel.bark import Bark

class Channel:
    bark = "bark"
    EMAIL = "email"
    TELEGRAM = "telegram"
    TELEGRAM_BOT = "telegram_bot"
    TELEGRAM_BOT_CHANNEL = "telegram_bot_channel"

class Send:
    @classmethod
    def send(self, content, channel: Channel = None):
        # 检查是否显式传递了channel参数
        if channel is not None:
            send_channel = channel
        else:
            # 否则使用环境变量
            send_channel = os.environ.get("SENDCHANNEL", "")

        if send_channel == Channel.bark:
            bark = Bark(
                base_url=os.environ.get("BARKURL", ""),
                device_key=os.environ.get("BARKKEY", ""),
            )
            return bark.simple_push(content)
        else:
            print("未定义推送渠道, 不进行推送")
        
if __name__ == "__main__":
    Send.send(f"💰 软妹币: {1}\n🔰 用户组: {1}\n📝 详细Tip: {1}")