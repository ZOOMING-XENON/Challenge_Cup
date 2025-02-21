import json
import time
import psutil
import win32gui
import win32process
import os
import requests
from datetime import datetime

def get_active_window():
    """获取当前活动窗口的标题"""
    try:
        window = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(window)
        title = win32gui.GetWindowText(window)
        return title if title else "无标题窗口"
    except:
        return "无法获取窗口信息"

def get_wechat_files():
    """获取微信文件夹中的文件"""
    wechat_path = os.path.join(os.environ['USERPROFILE'], 'Documents', 'WeChat Files')
    files = []
    
    if os.path.exists(wechat_path):
        for root, _, filenames in os.walk(wechat_path):
            for filename in filenames:
                # 只获取最近24小时内修改的文件
                file_path = os.path.join(root, filename)
                try:
                    mtime = os.path.getmtime(file_path)
                    if time.time() - mtime <= 24 * 3600:  # 24小时内
                        files.append(filename)
                except:
                    continue
    return files

def get_installed_software():
    """获取已安装的软件列表"""
    software_list = []
    try:
        import winreg
        # 检查两个注册表路径
        paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        
        for path in paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
                for i in range(0, winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        try:
                            software_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            if software_name.strip():
                                software_list.append(software_name)
                        except:
                            continue
                        finally:
                            winreg.CloseKey(subkey)
                    except:
                        continue
                winreg.CloseKey(key)
            except:
                continue
    except:
        pass
    return list(set(software_list))  # 去重

def get_computer_id():
    """获取计算机唯一标识"""
    try:
        # 使用主板序列号作为计算机ID
        import wmi
        c = wmi.WMI()
        board = c.Win32_BaseBoard()[0]
        return f"WIN-{board.SerialNumber}"
    except:
        # 如果无法获取主板序列号，使用计算机名
        return f"WIN-{os.environ['COMPUTERNAME']}"

def main():
    server_url = "http://127.0.0.1:5000/receive_data"  # 根据实际情况修改服务器地址
    computer_id = get_computer_id()
    
    print(f"开始监控计算机: {computer_id}")
    print("按 Ctrl+C 停止监控")
    
    while True:
        try:
            # 收集数据
            data = {
                "computer_id": computer_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "active_window": get_active_window(),
                "wechat_files": get_wechat_files(),
                "installed_software": get_installed_software()
            }
            
            # 发送数据到服务器
            response = requests.post(server_url, json=data)
            if response.status_code == 200:
                print(f"[{data['timestamp']}] 数据发送成功")
            else:
                print(f"[{data['timestamp']}] 数据发送失败: {response.status_code}")
                
        except KeyboardInterrupt:
            print("\n停止监控")
            break
        except Exception as e:
            print(f"发生错误: {str(e)}")
        
        time.sleep(3)  # 每3秒发送一次数据

if __name__ == "__main__":
    main()
