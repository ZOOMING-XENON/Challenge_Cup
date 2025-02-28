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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class USBMonitor:
    def __init__(self):
        self.c = wmi.WMI()
        self.usb_devices = {}  # 存储已知USB设备
        
        # 修改记录目录路径
        base_records_dir = Path(__file__).parent / 'outgoing_file_records'
        self.records_dir = base_records_dir / 'usb_records'
        self.records_dir.mkdir(exist_ok=True, parents=True)  # parents=True 确保父目录存在
        
        # 初始化文件监控
        self.file_handler = USBFileHandler(self)
        self.observer = Observer()
        
    def start_monitoring(self):
        """开始监控USB设备"""
        logging.info("开始USB设备监控...")
        try:
            while True:
                self._check_usb_devices()
                time.sleep(2)  # 每2秒检查一次
        except KeyboardInterrupt:
            logging.info("停止USB设备监控")
            self.observer.stop()
            self.observer.join()

    def _check_usb_devices(self):
        """检查USB设备变化"""
        # 获取当前所有USB存储设备
        current_devices = {}
        for disk in self.c.Win32_DiskDrive():
            if "USB" in disk.InterfaceType:
                device_info = self._get_device_info(disk)
                current_devices[disk.DeviceID] = device_info
                
                # 如果是新设备，记录并开始监控
                if disk.DeviceID not in self.usb_devices:
                    logging.info(f"检测到新USB设备: {device_info['name']}")
                    self._record_device_event(device_info, "connected")
                    self._start_file_monitoring(device_info['drive_letter'])

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
        for partition in self.c.Win32_DiskPartition():
            if partition.DiskIndex == device_id:
                for logical_disk in self.c.Win32_LogicalDisk():
                    if logical_disk.DeviceID == partition.DeviceID:
                        return logical_disk.DeviceID
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
                with open(record_file, 'r', encoding='utf-8') as f:
                    existing_records = json.load(f)
                    
            existing_records.append(record)
            
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(existing_records, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logging.error(f"记录设备事件失败: {e}")

    def _start_file_monitoring(self, drive_letter):
        """开始监控文件操作"""
        if drive_letter:
            try:
                self.observer.schedule(self.file_handler, drive_letter, recursive=True)
                self.observer.start()
                logging.info(f"开始监控驱动器: {drive_letter}")
            except Exception as e:
                logging.error(f"启动文件监控失败: {e}")

    def _stop_file_monitoring(self, drive_letter):
        """停止文件监控"""
        if drive_letter:
            try:
                # 停止对应驱动器的监控
                for watch in self.observer.watches:
                    if drive_letter in watch.path:
                        self.observer.unschedule(watch)
                logging.info(f"停止监控驱动器: {drive_letter}")
            except Exception as e:
                logging.error(f"停止文件监控失败: {e}")

class USBFileHandler(FileSystemEventHandler):
    def __init__(self, usb_monitor):
        self.usb_monitor = usb_monitor
        
    def on_created(self, event):
        if not event.is_directory:
            self._record_file_operation(event.src_path, "created")
            
    def on_modified(self, event):
        if not event.is_directory:
            self._record_file_operation(event.src_path, "modified")
            
    def on_deleted(self, event):
        if not event.is_directory:
            self._record_file_operation(event.src_path, "deleted")
            
    def on_moved(self, event):
        if not event.is_directory:
            self._record_file_operation(event.dest_path, "moved", event.src_path)
            
    def _record_file_operation(self, file_path, operation_type, src_path=None):
        """记录文件操作"""
        try:
            record = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'operation': operation_type,
                'file_path': file_path,
                'file_name': os.path.basename(file_path),
                'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                'source_path': src_path if src_path else None
            }
            
            # 保存到日志文件
            date_str = datetime.now().strftime("%Y%m%d")
            record_file = self.usb_monitor.records_dir / f"usb_file_operations_{date_str}.json"
            
            existing_records = []
            if record_file.exists():
                with open(record_file, 'r', encoding='utf-8') as f:
                    existing_records = json.load(f)
                    
            existing_records.append(record)
            
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(existing_records, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logging.error(f"记录文件操作失败: {e}")

if __name__ == "__main__":
    usb_monitor = USBMonitor()
    usb_monitor.start_monitoring()
