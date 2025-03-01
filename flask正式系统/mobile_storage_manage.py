import win32file
import win32api
import win32con
import wmi
import time
import logging
from pathlib import Path
import json
from datetime import datetime
import psutil
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import win32clipboard

# 修改日志配置
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG 级别
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class USBMonitor:
    def __init__(self):
        self.c = wmi.WMI()
        self.usb_devices = {}  # 存储已知USB设备
        self.observers = {}  # 存储每个驱动器的观察者
        self.known_drive_letters = set()  # 存储已知的驱动器盘符
        
        # 修改记录目录路径
        base_records_dir = Path(__file__).parent / 'outgoing_file_records'
        self.records_dir = base_records_dir / 'usb_records'
        self.records_dir.mkdir(exist_ok=True, parents=True)
        
        # 初始化文件监控
        self.file_handler = USBFileHandler(self)

    def start_monitoring(self):
        """开始监控USB设备"""
        logging.info("开始USB设备监控...")
        try:
            while True:
                self._check_usb_devices()
                time.sleep(2)  # 每2秒检查一次
        except KeyboardInterrupt:
            logging.info("停止USB设备监控")
            for observer in self.observers.values():
                observer.stop()
                observer.join()

    def _check_usb_devices(self):
        """检查USB设备变化"""
        # 获取当前所有USB存储设备
        current_devices = {}
        for disk in self.c.Win32_DiskDrive():
            if "USB" in disk.InterfaceType:
                # 只在首次检测到设备时获取盘符
                if disk.DeviceID not in self.usb_devices:
                    device_info = self._get_device_info(disk)
                    if device_info['drive_letter']:
                        current_devices[disk.DeviceID] = device_info
                        logging.info(f"检测到新USB设备: {device_info['name']}")
                        self._record_device_event(device_info, "connected")
                        self._start_file_monitoring(device_info['drive_letter'])
                else:
                    # 已知设备，直接使用之前的信息
                    current_devices[disk.DeviceID] = self.usb_devices[disk.DeviceID]

        # 检查断开的设备
        for device_id in list(self.usb_devices.keys()):
            if device_id not in current_devices:
                device_info = self.usb_devices[device_id]
                logging.info(f"USB设备已断开: {device_info['name']}")
                self._record_device_event(device_info, "disconnected")
                self._stop_file_monitoring(device_info['drive_letter'])
                del self.usb_devices[device_id]

        self.usb_devices = current_devices

    def _get_device_info(self, disk):
        """获取设备详细信息"""
        device_info = {
            'name': disk.Caption,
            'serial': disk.SerialNumber.strip() if disk.SerialNumber else 'Unknown',
            'size': self._format_size(int(disk.Size)) if disk.Size else 'Unknown',
            'manufacturer': disk.Manufacturer if disk.Manufacturer else 'Unknown',
            'model': disk.Model if disk.Model else 'Unknown',
            'drive_letter': self._get_drive_letter(disk.DeviceID),
            'connection_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return device_info

    def _get_drive_letter(self, device_id):
        """获取设备盘符"""
        try:
            # 直接获取所有逻辑磁盘
            for logical_disk in self.c.Win32_LogicalDisk():
                # 检查驱动器类型是否为可移动设备(2)
                if logical_disk.DriveType == 2 and str(logical_disk.DeviceID) not in self.known_drive_letters:  # 2 表示可移动设备
                    self.known_drive_letters.add(str(logical_disk.DeviceID))
                    logging.info(f"找到U盘盘符: {logical_disk.DeviceID}")
                    return str(logical_disk.DeviceID)
            
            return None
            
        except Exception as e:
            logging.error(f"获取驱动器盘符失败: {e}")
            logging.exception(e)
            return None

    def _format_size(self, size_bytes):
        """格式化存储大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"

    def _record_device_event(self, device_info, event_type):
        """记录设备事件"""
        try:
            record = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'event_type': event_type,
                'device_info': device_info
            }
            
            # 保存到日志文件
            date_str = datetime.now().strftime("%Y%m%d")
            record_file = self.records_dir / f"usb_events_{date_str}.json"
            
            existing_records = []
            if record_file.exists():
                try:
                    with open(record_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if content:  # 检查文件是否为空
                            existing_records = json.loads(content)
                except json.JSONDecodeError:
                    logging.warning(f"JSON文件损坏或为空，创建新记录")
                    existing_records = []
            
            existing_records.append(record)
            
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(existing_records, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logging.error(f"记录设备事件失败: {e}")

    def _start_file_monitoring(self, drive_letter):
        """开始监控文件操作"""
        if drive_letter:
            try:
                # 如果已有观察者，先停止
                if drive_letter in self.observers:
                    self.observers[drive_letter].stop()
                    self.observers[drive_letter].join()
                
                # 创建新的观察者
                observer = Observer()
                watch_path = f"{drive_letter}\\"
                logging.info(f"准备监控路径: {watch_path}")
                
                # 添加监控
                observer.schedule(self.file_handler, watch_path, recursive=True)
                observer.start()
                
                # 保存观察者
                self.observers[drive_letter] = observer
                
                logging.info(f"成功启动监控驱动器: {drive_letter}")
            except Exception as e:
                logging.error(f"启动文件监控失败: {e}")
                logging.exception(e)

    def _stop_file_monitoring(self, drive_letter):
        """停止文件监控"""
        if drive_letter and drive_letter in self.observers:
            try:
                self.observers[drive_letter].stop()
                self.observers[drive_letter].join()
                del self.observers[drive_letter]
                logging.info(f"停止监控驱动器: {drive_letter}")
            except Exception as e:
                logging.error(f"停止文件监控失败: {e}")

class USBFileHandler(FileSystemEventHandler):
    def __init__(self, usb_monitor):
        super().__init__()
        self.usb_monitor = usb_monitor
        self.file_operations = {}
        self.pending_events = {}
        self.operation_lock = threading.Lock()
        self.file_access_history = {}
        
    def _track_file_access(self, file_path):
        """跟踪文件的访问模式"""
        try:
            file_name = os.path.basename(file_path)
            current_time = time.time()
            
            # 尝试以不同模式打开文件
            access_info = {'time': current_time, 'patterns': []}
            
            # 先尝试以独占方式打开
            try:
                handle = win32file.CreateFile(
                    file_path,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,  # 不共享
                    None,
                    win32file.OPEN_EXISTING,
                    win32file.FILE_ATTRIBUTE_NORMAL,
                    None
                )
                access_info['patterns'].append('exclusive')
                win32file.CloseHandle(handle)
                logging.debug(f"[访问检查] 文件 {file_name} 可以独占访问")
            except win32file.error as e:
                if e.winerror == 32:  # ERROR_SHARING_VIOLATION
                    access_info['patterns'].append('in_use')
                    logging.debug(f"[访问检查] 文件 {file_name} 正在被其他进程使用")
                    
                    # 如果文件被占用，尝试以共享方式打开
                    try:
                        handle = win32file.CreateFile(
                            file_path,
                            win32file.GENERIC_READ,
                            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                            None,
                            win32file.OPEN_EXISTING,
                            win32file.FILE_ATTRIBUTE_NORMAL,
                            None
                        )
                        access_info['patterns'].append('shared_read')
                        win32file.CloseHandle(handle)
                        logging.debug(f"[访问检查] 文件 {file_name} 可以共享读取")
                    except:
                        logging.debug(f"[访问检查] 文件 {file_name} 无法以任何方式访问")
            
            # 记录访问历史
            if file_name not in self.file_access_history:
                self.file_access_history[file_name] = []
            self.file_access_history[file_name].append(access_info)
            
            # 只保留最近的访问记录
            self.file_access_history[file_name] = \
                self.file_access_history[file_name][-5:]
            
            logging.debug(f"[访问历史] 文件 {file_name} 的访问历史更新为: {self.file_access_history[file_name]}")
            return access_info
            
        except Exception as e:
            logging.error(f"[访问检查] 跟踪文件访问失败: {str(e)}")
            return None
    
    def on_modified(self, event):
        if not event.is_directory:
            file_name = os.path.basename(event.src_path)
            logging.debug(f"[修改事件] 收到文件修改事件: {file_name}")
            
            # 在修改事件中记录文件访问状态
            access_info = self._track_file_access(event.src_path)
            if access_info and 'in_use' in access_info['patterns']:
                # 如果文件正在被占用，可能是准备移出
                self.file_access_history[file_name] = [access_info]
                logging.debug(f"[修改事件] 检测到文件可能准备移出: {file_name}")
            
            with self.operation_lock:
                if file_name in self.pending_events:
                    self.pending_events[file_name]['modified_count'] += 1
                    logging.debug(f"[修改事件] 文件修改计数: {self.pending_events[file_name]['modified_count']}")
                elif file_name in self.file_operations:
                    self._record_file_operation(event.src_path, "modified")
    
    def on_deleted(self, event):
        if not event.is_directory:
            file_name = os.path.basename(event.src_path)
            file_path = event.src_path
            logging.debug(f"[删除事件] 收到文件删除事件: {file_name}")
            
            def check_delete():
                # 在删除事件发生时，先快速检查几次文件状态
                for i in range(3):
                    try:
                        # 尝试以独占方式打开文件
                        handle = win32file.CreateFile(
                            file_path,
                            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                            0,  # 不共享
                            None,
                            win32file.OPEN_EXISTING,
                            win32file.FILE_ATTRIBUTE_NORMAL,
                            None
                        )
                        win32file.CloseHandle(handle)
                        time.sleep(0.1)  # 短暂等待
                    except win32file.error as e:
                        if e.winerror == 32:  # ERROR_SHARING_VIOLATION
                            logging.debug(f"[删除事件] 检测到文件正在被访问，判定为移出操作")
                            self._record_file_operation(file_path, "moved_out")
                            return
                        elif e.winerror != 2:  # 不是 ERROR_FILE_NOT_FOUND
                            logging.debug(f"[删除事件] 文件访问错误: {e.winerror}")
                
                # 如果文件没有被占用，检查剪切板
                try:
                    win32clipboard.OpenClipboard()
                    if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_HDROP):
                        clipboard_files = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
                        clipboard_filenames = [os.path.basename(f) for f in clipboard_files]
                        logging.debug(f"[删除事件] 剪切板文件列表: {clipboard_filenames}")
                        if file_name in clipboard_filenames:
                            logging.debug(f"[删除事件] 在剪切板中找到文件，判定为移出操作")
                            self._record_file_operation(file_path, "moved_out")
                            return
                except Exception as e:
                    logging.debug(f"[删除事件] 检查剪切板失败: {str(e)}")
                finally:
                    try:
                        win32clipboard.CloseClipboard()
                    except:
                        pass
                
                # 如果所有检查都未发现移出迹象，判定为删除操作
                logging.debug(f"[删除事件] 判定为删除操作")
                self._record_file_operation(file_path, "deleted")
            
            threading.Thread(target=check_delete).start()

    def _record_file_operation(self, file_path, operation_type, src_path=None):
        """记录文件操作"""
        try:
            operation_desc = {
                "created": "新建文件",
                "modified": "修改文件",
                "moved_in": "文件移入U盘",
                "moved_out": "文件移出U盘",
                "deleted": "删除文件",
                "renamed": "重命名文件"
            }
            
            record = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'operation': operation_type,  # 保存原始操作类型
                'file_path': file_path,
                'file_name': os.path.basename(file_path),
                'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                'source_path': src_path
            }
            
            # 保存到日志文件
            date_str = datetime.now().strftime("%Y%m%d")
            record_file = self.usb_monitor.records_dir / f"usb_file_operations_{date_str}.json"
            
            existing_records = []
            if record_file.exists():
                try:
                    with open(record_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if content:
                            existing_records = json.loads(content)
                except json.JSONDecodeError:
                    logging.warning(f"JSON文件损坏或为空，创建新记录")
            
            existing_records.append(record)
            
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(existing_records, f, ensure_ascii=False, indent=2)
            
            # 使用 operation_desc 来显示更友好的日志信息
            logging.info(f"{operation_desc.get(operation_type, operation_type)}: {os.path.basename(file_path)}")
                
        except Exception as e:
            logging.error(f"记录文件操作失败: {e}")
            logging.exception(e)

if __name__ == "__main__":
    usb_monitor = USBMonitor()
    usb_monitor.start_monitoring()
