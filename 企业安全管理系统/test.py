from Get_Installed_software_and_Wechat_Info_Mac import watchdog
import os
SERVER_URL = "http://127.0.0.1:5000"# Flask 服务器的 URL
WECHAT_DIR = os.path.expanduser("~/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat")  # 微信文件目录
DOWNLOAD_DIR = os.path.expanduser("~/Downloads")  # 下载目录
collected_data = {
    "computer_id": "Mac-001",  # 每台电脑的唯一标识
    "wechat_files": [],       # 微信传输的文件
    "installed_software": [], # 下载的软件
    "active_window": []       # 工作页面的时间
}
while True:
    watchdog(collected_data,WECHAT_DIR,DOWNLOAD_DIR,SERVER_URL)