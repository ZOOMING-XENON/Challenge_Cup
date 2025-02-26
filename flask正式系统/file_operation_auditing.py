import os
import re
import sys
import json
import time
import hashlib
import logging
import platform
import sqlite3
import matplotlib
import pandas as pd
from threading import Lock, Thread
from flask import Flask, render_template_string
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List
import psutil
import matplotlib.pyplot as plt

# 配置日志系统（先于任何其他导入）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('file_audit.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('FileAudit')

# 数据类定义
@dataclass
class AuditConfig:
    """审计系统配置类"""
    path_patterns: List[str]
    exclude_patterns: List[str]
    file_extensions: List[str]
    role_thresholds: Dict[str, Dict]
    global_thresholds: Dict[str, int]
    threshold_period: int = 60
    content_keywords: List[str] = None

class AuditDatabase:
    """审计数据持久化类"""
    def __init__(self, db_name='audit.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.lock = Lock()
        self._init_db()

    def _init_db(self):
        """初始化数据库结构"""
        with self.conn:
            self.conn.execute('''CREATE TABLE IF NOT EXISTS audit_logs
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 timestamp DATETIME,
                 user TEXT,
                 role TEXT,
                 event_type TEXT,
                 path TEXT,
                 file_hash TEXT,
                 risk_reasons TEXT)''')

    def insert_log(self, log_entry):
        """插入审计日志"""
        with self.lock:
            self.conn.execute('''INSERT INTO audit_logs 
                (timestamp, user, role, event_type, path, file_hash, risk_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (log_entry['timestamp'], log_entry['user'],
                 log_entry['role'], log_entry['event_type'],
                 log_entry['path'], log_entry['hash'],
                 log_entry['risk']))
            self.conn.commit()

class EnhancedFileAuditor(FileSystemEventHandler):
    """增强版文件审计处理器"""
    def __init__(self, config_path='audit_config.json'):
        super().__init__()
        self.config = self._load_config(config_path)
        self.operation_counts = defaultdict(int)
        self.last_reset_time = time.time()
        self.db = AuditDatabase()
        self.path_regex = [re.compile(p) for p in self.config.path_patterns]
        self.exclude_regex = [re.compile(p) for p in self.config.exclude_patterns]

    def _load_config(self, config_path):
        """加载配置文件（关键修复方法）"""
        try:
            with open(config_path) as f:
                config_data = json.load(f)
                return AuditConfig(
                    path_patterns=config_data.get("path_patterns", []),
                    exclude_patterns=config_data.get("exclude_patterns", []),
                    file_extensions=config_data.get("file_extensions", []),
                    role_thresholds=config_data.get("role_thresholds", {}),
                    global_thresholds=config_data.get("global_thresholds", {}),
                    threshold_period=config_data.get("threshold_period", 60),
                    content_keywords=config_data.get("content_keywords")
                )
        except Exception as e:
            logger.error(f"配置加载失败: {str(e)}")
            return AuditConfig([], [], [], {}, {})

    def is_file_locked(self, filepath):
        """检查文件是否被其他进程锁定"""
        try:
            for proc in psutil.process_iter():
                try:
                    files = proc.open_files()
                    if filepath in [f.path for f in files]:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False
        except Exception as e:
            logger.warning(f"文件锁定检查失败: {str(e)}")
            return False

    def is_file_accessible(self, path):
        """检查文件可访问性"""
        return os.path.exists(path) and os.access(path, os.R_OK)
    
    def calculate_file_hash(self, path):
        """计算文件哈希"""
        if not self.is_file_accessible(path):
            logger.warning(f"文件不可访问: {path}")
            return "unaccessible"
        
        if self.is_file_locked(path):
            logger.warning(f"文件被其他进程锁定: {path}")
            return "locked"

        try:
            hasher = hashlib.sha256()
            with open(path, 'rb') as f:
                while chunk := f.read(4096):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except PermissionError as pe:
            logger.warning(f"权限拒绝访问文件: {path} (建议以管理员身份运行程序)")
            return "permission_denied"
        except Exception as e:
            logger.error(f"哈希计算失败[{type(e).__name__}]: {str(e)}")
            return None

    def check_path_risk(self, path):
        """路径风险检测"""
        if any(r.search(path) for r in self.exclude_regex):
            return False
        return any(r.search(path) for r in self.path_regex) or \
               os.path.splitext(path)[1].lower() in self.config.file_extensions

    def check_threshold(self, event_type):
        """复合阈值检测"""
        current_role = self.get_user_role()
        role_limit = self.config.role_thresholds.get(current_role, {}).get(event_type, 0)
        global_limit = self.config.global_thresholds.get(event_type, 5)
        actual_limit = max(role_limit, global_limit)
        return self.operation_counts[event_type] > actual_limit if actual_limit > 0 else False

    def get_user_role(self):
        """获取用户角色"""
        try:
            if platform.system() == 'Windows':
                return 'admin' if os.getenv('USERNAME') == 'Administrator' else 'staff'
            else:
                return 'admin' if os.getuid() == 0 else 'staff'
        except:
            return 'unknown'

    def on_any_event(self, event):
        """事件处理"""
        try:
            user = os.getlogin()
        except:
            user = 'SYSTEM'

        current_time = time.time()
        path = getattr(event, 'dest_path', event.src_path)
        file_hash = self.calculate_file_hash(event.src_path) if event.event_type != 'deleted' else None

        # 重置计数器
        if current_time - self.last_reset_time > self.config.threshold_period:
            self.operation_counts.clear()
            self.last_reset_time = current_time

        # 风险检测
        risk_reasons = []
        if self.check_path_risk(path):
            risk_reasons.append("敏感文件操作")

        # 操作计数
        self.operation_counts[event.event_type] += 1
        if self.check_threshold(event.event_type):
            risk_reasons.append(f"高频{event.event_type}操作")

        # 日志记录
        log_entry = {
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'user': user,
            'role': self.get_user_role(),
            'event_type': event.event_type,
            'path': path,
            'hash': file_hash,
            'risk': "|".join(risk_reasons) if risk_reasons else None
        }

        if risk_reasons:
            logger.warning(f"风险告警 - {log_entry}")
        else:
            logger.info(f"操作记录 - {log_entry}")

        self.db.insert_log(log_entry)

class AuditVisualizer:
    """数据可视化"""
    @staticmethod
    def generate_dashboard():
        """生成监控面板"""
        try:
            conn = sqlite3.connect('audit.db')
            df = pd.read_sql('SELECT * FROM audit_logs', conn)

            matplotlib.use('Agg')
            plt.figure(figsize=(16, 10))

            # 操作类型分布
            plt.subplot(2, 2, 1)
            df['event_type'].value_counts().plot.pie(autopct='%1.1f%%')
            plt.title('操作类型分布')

            # 风险趋势
            plt.subplot(2, 2, 2)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp')['risk_reasons'].notnull().resample('H').sum().plot()
            plt.title('风险事件趋势')

            # 用户活跃度
            plt.subplot(2, 2, 3)
            df['user'].value_counts().head(5).plot.bar()
            plt.title('活跃用户TOP5')

            # 文件类型风险
            plt.subplot(2, 2, 4)
            df[df['risk_reasons'].notnull()]['path'].apply(
                lambda x: os.path.splitext(x)[1]).value_counts().head(5).plot.bar()
            plt.title('高风险文件类型')

            plt.tight_layout()
            plt.savefig('audit_dashboard.png')
            plt.close()
        except Exception as e:
            logger.error(f"生成仪表盘失败: {str(e)}")

app = Flask(__name__)

@app.route('/dashboard')
def show_dashboard():
    """展示监控面板"""
    try:
        AuditVisualizer.generate_dashboard()
        conn = sqlite3.connect('audit.db')
        df = pd.read_sql('''SELECT 
            strftime('%Y-%m-%d %H:00', timestamp) as hour,
            event_type,
            COUNT(*) as count
            FROM audit_logs
            GROUP BY hour, event_type''', conn)

        table_html = df.pivot(index='hour', columns='event_type', values='count').fillna(0).to_html(
            classes='table table-striped')

        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>文件审计监控系统</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body class="container mt-4">
                <h1 class="mb-4">实时监控面板</h1>
                <img src="/static/audit_dashboard.png" class="img-fluid mb-4">
                <h2>操作统计</h2>
                {{ table|safe }}
            </body>
            </html>
        ''', table=table_html)
    except Exception as e:
        return f"仪表盘加载失败: {str(e)}", 500

def get_observer():
    """获取文件观察者"""
    system = platform.system()
    try:
        if system == 'Windows':
            from watchdog.observers.read_directory_changes import WindowsApiObserver
            return WindowsApiObserver()
        elif system == 'Linux':
            return Observer()
        else:
            return PollingObserver()
    except:
        return PollingObserver()

def start_monitoring(paths):
    """启动监控"""
    auditor = EnhancedFileAuditor()
    observer = get_observer()

    # 注册监控路径
    for path in paths:
        if os.path.exists(path):
            observer.schedule(auditor, path, recursive=True)
            logger.info(f"开始监控目录: {path}")
        else:
            logger.warning(f"路径不存在: {path}")

    # 启动观察者线程
    observer.start()
    
    # 启动Flask服务器
    Thread(target=app.run, kwargs={'host':'0.0.0.0', 'port':5000, 'use_reloader':False}).start()

    try:
        # 保持主线程存活
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    # 默认监控路径
    target_paths = []
    if platform.system() == 'Windows':
        target_paths = [
            r"C:\AuditTarget",
            os.path.join(os.environ['USERPROFILE'], 'Desktop')
        ]
    else:
        target_paths = [
            "/var/audit",
            os.path.expanduser("~/Documents")
        ]
    
    # 启动系统
    start_monitoring(target_paths)