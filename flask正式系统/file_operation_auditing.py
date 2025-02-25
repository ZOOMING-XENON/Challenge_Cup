import os
import re
import json
import time
import hashlib
import logging
import platform
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('file_audit.log'),
        logging.StreamHandler()
    ]
)


@dataclass
class AuditConfig:
    path_patterns: List[str]  # 正则表达式路径模式
    exclude_patterns: List[str]  # 排除路径模式
    file_extensions: List[str]  # 敏感文件扩展名
    role_thresholds: Dict[str, Dict]  # 角色操作阈值
    global_thresholds: Dict[str, int]  # 全局操作阈值
    content_keywords: List[str] = None  # 内容关键词（可选）


class AdvancedFileAuditor(FileSystemEventHandler):
    def __init__(self, config_path='audit_config.json'):
        self.config = self.load_config(config_path)
        self.operation_counts = defaultdict(int)
        self.last_reset_time = time.time()

        # 预编译正则表达式
        self.path_regex = [re.compile(p) for p in self.config.path_patterns]
        self.exclude_regex = [re.compile(p) for p in self.config.exclude_patterns]

    def load_config(self, config_path):
        """加载JSON配置文件"""
        try:
            with open(config_path) as f:
                config_data = json.load(f)
                return AuditConfig(
                    path_patterns=config_data.get("path_patterns", []),
                    exclude_patterns=config_data.get("exclude_patterns", []),
                    file_extensions=config_data.get("file_extensions", []),
                    role_thresholds=config_data.get("role_thresholds", {}),
                    global_thresholds=config_data.get("global_thresholds", {}),
                    content_keywords=config_data.get("content_keywords")
                )
        except Exception as e:
            logging.error(f"配置加载失败: {str(e)}")
            return AuditConfig([], [], [], {}, {})

    def get_user_role(self):
        """获取用户角色（示例实现）"""
        # 可替换为企业实际身份系统集成
        return "staff"  # 示例值

    def calculate_file_hash(self, path):
        """计算文件SHA256哈希"""
        if os.path.exists(path):
            hasher = hashlib.sha256()
            with open(path, 'rb') as f:
                while chunk := f.read(4096):
                    hasher.update(chunk)
            return hasher.hexdigest()
        return None

    def check_path_risk(self, path):
        """路径风险检测"""
        # 排除路径优先
        if any(r.search(path) for r in self.exclude_regex):
            return False

        # 敏感路径检测
        path_risk = any(r.search(path) for r in self.path_regex)

        # 文件扩展名检测
        ext_risk = os.path.splitext(path)[1].lower() in self.config.file_extensions

        return path_risk or ext_risk

    def check_threshold(self, event_type):
        """复合阈值检测"""
        current_role = self.get_user_role()
        role_limit = self.config.role_thresholds.get(current_role, {}).get(event_type, 0)
        global_limit = self.config.global_thresholds.get(event_type, 0)

        actual_limit = max(role_limit, global_limit)
        return self.operation_counts[event_type] > actual_limit if actual_limit > 0 else False

    def on_any_event(self, event):
        try:
            user = os.getlogin()
        except:
            user = 'SYSTEM'

        current_time = time.time()
        path = getattr(event, 'dest_path', event.src_path)
        file_hash = self.calculate_file_hash(event.src_path) if event.event_type != 'deleted' else None

        # 每60秒重置计数器
        if current_time - self.last_reset_time > 60:
            self.operation_counts.clear()
            self.last_reset_time = current_time

        # 风险检测
        risk_reasons = []

        # 路径/扩展名风险
        if self.check_path_risk(path):
            risk_reasons.append("敏感文件操作")

        # 操作频率检测
        self.operation_counts[event.event_type] += 1
        if self.check_threshold(event.event_type):
            risk_reasons.append(f"高频{event.event_type}操作")

        # 构建日志条目
        log_entry = {
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'user': f"{user}({self.get_user_role()})",
            'event_type': event.event_type,
            'path': path,
            'hash': file_hash,
            'risk': "|".join(risk_reasons) if risk_reasons else None
        }

        # 记录日志
        if risk_reasons:
            logging.warning(f"风险告警 - {log_entry}")
        else:
            logging.info(f"操作记录 - {log_entry}")


# 配置文件示例（audit_config.json）
"""
{
    "path_patterns": [
        "^/财务/.*",
        "/研发/[^/]+$"
    ],
    "exclude_patterns": [
        "/测试环境/.*"
    ],
    "file_extensions": [".docx", ".xlsx", ".dwg"],
    "global_thresholds": {
        "delete": 5,
        "modify": 10
    },
    "role_thresholds": {
        "staff": {
            "delete": 3,
            "modify": 5
        },
        "admin": {
            "delete": 15
        }
    }
}
"""


def get_observer():
    """根据系统选择最优观察者（需补充）"""
    if platform.system() == 'Linux':
        return Observer()
    elif platform.system() == 'Windows':
        try:
            from watchdog.observers.read_directory_changes import WindowsApiObserver
            return WindowsApiObserver()
        except:
            return PollingObserver()
    else:
        return PollingObserver()


def start_monitoring(paths_to_watch):
    event_handler = AdvancedFileAuditor()
    observer = get_observer()

    for path in paths_to_watch:
        if os.path.exists(path):
            observer.schedule(event_handler, path, recursive=True)
            logging.info(f"开始监控目录: {path}")
        else:
            logging.warning(f"路径不存在: {path}")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    # 多平台路径配置示例
    target_paths = []

    # Windows路径
    if platform.system() == 'Windows':
        target_paths.extend([
            r"C:\公司文件",
            os.path.join(os.environ['USERPROFILE'], 'Desktop')
        ])

    # Linux/macOS路径
    else:
        target_paths.extend([
            "/home/user/docs",
            "/var/audit"
        ])

    # 启动监控
    start_monitoring(target_paths)