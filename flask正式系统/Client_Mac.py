import os
import time
import json
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import psutil
from AppKit import NSWorkspace  # macOS 原生框架，用于获取活动窗口信息
from datetime import datetime

# Flask 服务器的 URL
SERVER_URL = "http://127.0.0.1:5000/receive_data"

# 监控的目录（微信文件存储目录和下载目录）
WECHAT_DIR = os.path.expanduser("~/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat")  # 微信文件目录
DOWNLOAD_DIR = os.path.expanduser("~/Downloads")  # 下载目录

# 存储收集到的数据，显然这是一个JSON格式
collected_data = {
    "computer_id": "Mac-001",  # 每台电脑的唯一标识
    "browsing_history": [],   # 浏览的网页（暂未实现）
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
    """获取当前活动窗口的标题（macOS 实现）"""
    active_app = NSWorkspace.sharedWorkspace().frontmostApplication()#mac原生的操作逻辑
    app_name = active_app.localizedName()
    return app_name

# 获取已安装的软件列表
def get_current_software():
    """获取已安装的软件列表（macOS 实现）"""
    software_list = []
    for proc in psutil.process_iter(['name']):
        software_list.append(proc.info['name'])
    return software_list


def get_installed_software():
    """获取已安装的软件列表（macOS 实现）"""
    software_list = []
    applications_dir = '/Applications'
    if os.path.exists(applications_dir):
        for item in os.listdir(applications_dir):
            if item.endswith('.app'):
                software_list.append(item.replace('.app', ''))
    return software_list

# 发送数据到服务器
def send_data_to_server():
    """将收集到的数据发送到 Flask 服务器"""
    try:
        response = requests.post(SERVER_URL, json=collected_data)
        if response.status_code == 200:
            print("数据发送成功！")
        else:
            print(f"数据发送失败，状态码：{response.status_code}")
    except Exception as e:  #捕获 try 块中抛出的任何异常，并将异常对象赋值给变量 e。这样可以对异常进行处理，避免程序因异常而崩溃
        print(f"发送数据时出错：{e}")

def download_file(server_url, filename, download_dir):
    """下载单个文件"""
    try:
        # 构建下载URL
        download_url = f"{server_url}/download_file/{filename}"
        #引入了 f-string 这种字符串格式化方式。它以 f 或 F 作为前缀，字符串中可以使用大括号 {} 包含表达式，
        # Python 会在运行时将这些表达式替换为其计算结果
        
        # 发送下载请求
        response = requests.get(download_url, stream=True)
        #访问服务器端端下载链接
        if response.status_code == 200:
            # 确保下载目录存在
            os.makedirs(download_dir, exist_ok=True)
            
            # 构建保存路径
            save_path = os.path.join(download_dir, filename)
            
            # 如果文件已存在，跳过下载
            if os.path.exists(save_path):
                print(f"文件已存在，跳过下载: {filename}")
                return True
                
            # 保存文件
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"文件下载成功: {filename}")
            return True
        else:
            print(f"下载失败 {filename}: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"下载文件时出错 {filename}: {str(e)}")
        return False

def check_and_download_files(server_url, download_dir):
    """检查并下载所有新文件"""
    try:
        # 获取可下载文件列表
        response = requests.get(f"{server_url}/get_upload_files")
        if response.status_code == 200:
            files_info = response.json().get('files', [])
            
            # 下载每个文件
            for file_info in files_info:
                filename = file_info['filename']
                download_file(server_url, filename, download_dir)
                #将文件名为filename的文件从服务器下载到download_dir的地方
        else:
            print(f"获取文件列表失败: HTTP {response.status_code}")
    except Exception as e:
        print(f"检查文件更新时出错: {str(e)}")

# 主函数
def main():
    # 初始化文件系统监控
    event_handler = FileChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WECHAT_DIR, recursive=True)
    observer.schedule(event_handler, path=DOWNLOAD_DIR, recursive=True)
    observer.start()
    #recursive=True：表示是否递归地监控指定目录及其子目录下的文件系统事件。如果设置为 True，
    # 则会监控指定目录及其所有子目录中的文件变化；如果设置为 False，则只监控指定目录下的文件变化。

    # 服务器地址
    server_url = "http://127.0.0.1:5000"  # 根据实际情况修改
    
    # 下载目录
    download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', 'SecuritySystem')
    #生成了下载目录～\Downloads\SecuritySystem
    
    print(f"开始监控...")
    print(f"文件将下载到: {download_dir}")
    print("按 Ctrl+C 停止监控")
    
    while True:
        try:
            # 检查并下载新文件
            check_and_download_files(server_url, download_dir)
            
            # 收集并发送监控数据
            data = {
                "computer_id": "Mac-001",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "active_window": get_active_window_title(),
                "wechat_files": collected_data["wechat_files"],
                "installed_software": collected_data["installed_software"]
            }
            
            # 发送数据到服务器
            response = requests.post(f"{server_url}/receive_data", json=data)
            if response.status_code == 200:
                print(f"[{data['timestamp']}] 数据发送成功")
            else:
                print(f"[{data['timestamp']}] 数据发送失败: {response.status_code}")
                
        except KeyboardInterrupt:
            print("\n停止监控")
            break
        except Exception as e:
            print(f"发生错误: {str(e)}")
        
        time.sleep(3)  # 每3秒检查一次

if __name__ == "__main__":
    main()