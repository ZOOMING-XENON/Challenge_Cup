import os
import time
import json
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import psutil
import win32gui  # 仅适用于Windows系统

# Flask服务器的URL
SERVER_URL = "http://127.0.0.1:5000//receive_data"

# 监控的目录（微信文件存储目录和下载目录）
WECHAT_DIR = r"C:\Users\<用户名>\Documents\WeChat Files"  # 替换为实际的微信文件目录
DOWNLOAD_DIR = r"C:\Users\<用户名>\Downloads"  # 替换为实际的下载目录

# 存储收集到的数据
collected_data = {
    "computer_id": "PC-001",  # 每台电脑的唯一标识
    "browsing_history": [],   # 浏览的网页
    "wechat_files": [],       # 微信传输的文件
    "installed_software": [], # 下载的软件
    "active_window": []       # 工作页面的时间
}

# 监控文件系统变化的类
class FileChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        """当文件被修改时触发"""
        if event.is_directory:  # 忽略目录
            return
        file_path = event.src_path
        if file_path.startswith(WECHAT_DIR):  # 如果是微信文件
            collected_data["wechat_files"].append(file_path)
        elif file_path.startswith(DOWNLOAD_DIR):  # 如果是下载的文件
            collected_data["installed_software"].append(file_path)

# 获取当前活动窗口的标题
def get_active_window_title():
    """获取当前活动窗口的标题"""
    window = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(window)
    return title

# 获取已安装的软件列表
def get_installed_software():
    """获取已安装的软件列表"""
    software_list = []
    for proc in psutil.process_iter(['name']):
        software_list.append(proc.info['name'])
    return software_list

# 发送数据到服务器
def send_data_to_server():
    """将收集到的数据发送到Flask服务器"""
    try:
        response = requests.post(SERVER_URL, json=collected_data)
        if response.status_code == 200:
            print("数据发送成功！")
        else:
            print(f"数据发送失败，状态码：{response.status_code}")
    except Exception as e:
        print(f"发送数据时出错：{e}")

# 主函数
def main():
    # 初始化文件系统监控
    event_handler = FileChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WECHAT_DIR, recursive=True)
    observer.schedule(event_handler, path=DOWNLOAD_DIR, recursive=True)
    observer.start()

    try:
        while True:
            # 获取当前活动窗口的标题
            active_window_title = get_active_window_title()
            collected_data["active_window"].append({
                "window_title": active_window_title,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })

            # 获取已安装的软件列表
            collected_data["installed_software"] = get_installed_software()

            # 每10秒发送一次数据到服务器
            time.sleep(10)
            send_data_to_server()

            # 清空临时数据，避免重复发送
            collected_data["browsing_history"].clear()
            collected_data["wechat_files"].clear()
            collected_data["active_window"].clear()

    except KeyboardInterrupt:
        # 用户按下Ctrl+C时停止监控
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()