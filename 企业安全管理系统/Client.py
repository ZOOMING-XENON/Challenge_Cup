from domain_analysis import ai_analysis
from capture import start_capture
from Get_Installed_software_and_Wechat_Info_Mac import watchdog
import os
import threading
import time
import json

# 配置常量
SERVER_URL = "http://127.0.0.1:5000"  # Flask 服务器的 URL
WECHAT_DIR = os.path.expanduser("~/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat")  # 微信文件目录
DOWNLOAD_DIR = os.path.expanduser("~/Downloads")  # 下载目录
ANALYZED_DATA_FILE = "analyzed_data.json"
collected_data = {
    "computer_id": "Mac-001",  # 每台电脑的唯一标识
    "wechat_files": [],        # 微信传输的文件
    "installed_software": [],  # 下载的软件
    "active_window": []        # 工作页面的时间
}

# 辅线任务
def ai_analysis_loop():
    """AI 分析模块"""
    while True:
        try:
            ai_analysis()  # AI 分析模块
        except Exception as e:
            print(f"AI 分析出错: {e}")
            time.sleep(5)  # 等待 5 秒后重试

def watchdog_loop():
    """文件监控模块"""
    while True:
        try:
            watchdog(collected_data, WECHAT_DIR, DOWNLOAD_DIR, SERVER_URL)
            time.sleep(10)  # 文件监控时效性可以弱一点
        except Exception as e:
            print(f"文件监控出错: {e}")
            time.sleep(5)  # 等待 5 秒后重试

# 清空 analyzed_data.json 文件
def clear_analyzed_data():
    """清空 AI 分析结果文件"""
    try:
        with open(ANALYZED_DATA_FILE, "w") as f:
            json.dump([], f)  # 写入空列表
        print(f"已清空 {ANALYZED_DATA_FILE}")
    except Exception as e:
        print(f"清空 {ANALYZED_DATA_FILE} 出错: {e}")

# 主线任务
def capture_web_info_loop():
    """流量捕获模块（必须在主线程中运行）"""
    last_clear_time = time.time()  # 上次清空文件的时间
    while True:
        try:
            print("Starting web traffic capture...")
            start_capture()  # 流量捕获模块
        except Exception as e:
            print(f"流量捕获出错: {e}")
            time.sleep(5)  # 等待 5 秒后重试
            # 每 5 分钟清空 analyzed_data.json
        current_time = time.time() #每五分钟更新一次分析数据，因为浏览量会跳变
        if current_time - last_clear_time >= 300:  # 300 秒 = 5 分钟
            clear_analyzed_data()
            last_clear_time = current_time  # 更新上次清空时间

def main():
    """主程序入口"""
    # 启动辅线线程
    ai_thread = threading.Thread(target=ai_analysis_loop, daemon=True)
    watchdog_thread = threading.Thread(target=watchdog_loop, daemon=True)

    ai_thread.start()
    watchdog_thread.start()

    # 主线任务（流量捕获）
    capture_web_info_loop()

if __name__ == "__main__":
    main()