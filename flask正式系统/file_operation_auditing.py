import sys
import io
import os
import re
import json
import time
import hashlib
import logging
import platform
import sqlite3
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from threading import Lock, Thread, Event
from dataclasses import dataclass
from typing import Dict, List
from collections import defaultdict
from queue import Queue

from flask import Flask, render_template_string, jsonify, request
import psutil
from watchdog.observers.polling import PollingObserver  # 改用轮询观察者
from watchdog.events import FileSystemEventHandler

# 系统编码设置
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 增强日志配置
logging.basicConfig(
    level=logging.DEBUG,  # 设置为DEBUG级别
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('file_audit.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('FileAudit')

# 配置数据类
@dataclass
class AuditConfig:
    path_patterns: List[str]
    exclude_patterns: List[str]
    file_extensions: List[str]
    role_thresholds: Dict[str, Dict]
    global_thresholds: Dict[str, int]
    threshold_period: int = 60
    event_cooldown: float = 0.5

class AuditDatabase:
    def __init__(self, db_name='audit.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.lock = Lock()
        self._init_db()
        logger.debug("数据库初始化完成")

    def _init_db(self):
        with self.conn:
            self.conn.execute('''CREATE TABLE IF NOT EXISTS audit_logs
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                 user TEXT,
                 role TEXT,
                 event_type TEXT,
                 path TEXT,
                 file_hash TEXT,
                 risk_reasons TEXT)''')
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_path ON audit_logs(path)')
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_user ON audit_logs(user)')
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_logs(timestamp)')

    def insert_log(self, log_entry):
        try:
            with self.lock:
                self.conn.execute('''INSERT INTO audit_logs 
                    (user, role, event_type, path, file_hash, risk_reasons)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                    (log_entry['user'], log_entry['role'],
                     log_entry['event_type'], log_entry['path'],
                     log_entry['hash'], log_entry.get('risk')))
                self.conn.commit()
            logger.debug(f"成功写入日志: {log_entry}")
        except Exception as e:
            logger.error(f"数据库写入失败: {str(e)}")

class EventProcessor(Thread):
    """增强版事件处理器"""
    def __init__(self, auditor):
        super().__init__(daemon=True)
        self.auditor = auditor
        self.queue = Queue(maxsize=1000)
        self.cache = {}
        self.cache_lock = Lock()
        self.cache_ttl = 1.5
        logger.debug("事件处理器初始化完成")

    def run(self):
        logger.debug("事件处理线程启动")
        while True:
            event_type, src_path, dest_path = self.queue.get()
            logger.debug(f"从队列获取事件: {event_type} {src_path} -> {dest_path}")
            self.process_event(event_type, src_path, dest_path)

    def process_event(self, event_type, src_path, dest_path):
        cache_key = (event_type, src_path, dest_path)
        with self.cache_lock:
            now = time.time()
            self.cache = {k:v for k,v in self.cache.items() if now - v < self.cache_ttl}
            if cache_key in self.cache:
                logger.debug(f"跳过重复事件: {cache_key}")
                return
            self.cache[cache_key] = now
        
        try:
            logger.debug(f"开始处理事件: {event_type} {src_path}")
            self.auditor.process_event(event_type, src_path, dest_path)
        except Exception as e:
            logger.error(f"事件处理异常: {str(e)}")

class EnhancedFileAuditor(FileSystemEventHandler):
    def __init__(self, config_path='audit_config.json'):
        super().__init__()
        self.config = self._load_config(config_path)
        self.db = AuditDatabase()
        self.processor = EventProcessor(self)
        self.processor.start()
        self.operation_counts = defaultdict(int)
        self.last_reset_time = time.time()
        self.path_regex = [re.compile(p) for p in self.config.path_patterns]
        self.exclude_regex = [re.compile(p) for p in self.config.exclude_patterns]
        logger.debug("文件审计器初始化完成")

    def _load_config(self, config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug("配置文件加载成功")
                return AuditConfig(
                    path_patterns=config.get("path_patterns", ['.*']),  # 默认监控所有路径
                    exclude_patterns=config.get("exclude_patterns", []),
                    file_extensions=config.get("file_extensions", ['.*']),  # 默认所有文件类型
                    role_thresholds=config.get("role_thresholds", {}),
                    global_thresholds=config.get("global_thresholds", {}),
                    threshold_period=config.get("threshold_period", 60),
                    event_cooldown=config.get("event_cooldown", 0.5)
                )
        except Exception as e:
            logger.error(f"配置加载失败: {str(e)}")
            return AuditConfig(['.*'], [], ['.*'], {}, {})  # 默认开放配置

    def on_any_event(self, event):
        try:
            logger.debug(f"原始事件捕获: {event.event_type} {event.src_path}")
            src = event.src_path
            dest = getattr(event, 'dest_path', '') if event.event_type == 'moved' else ''
            self.processor.queue.put((event.event_type, src, dest))
        except Exception as e:
            logger.error(f"事件捕获异常: {str(e)}")

    def process_event(self, event_type, src_path, dest_path):
        path = dest_path if event_type == 'moved' else src_path
        logger.debug(f"处理路径: {path}")
        
        if not path:
            logger.warning("空路径事件")
            return
            
        try:
            # 强制记录所有事件进行测试
            user = os.getlogin() if platform.system() != 'Windows' else os.getenv('USERNAME')
            log_entry = {
                'user': user or 'SYSTEM',
                'role': self._get_user_role(),
                'event_type': event_type,
                'path': path,
                'hash': 'TEST_HASH' if os.path.exists(path) else None,
                'risk': None
            }
            logger.info(f"强制记录事件: {log_entry}")
            self.db.insert_log(log_entry)
            
        except Exception as e:
            logger.error(f"事件处理失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def _get_user_role(self):
        try:
            if platform.system() == 'Windows':
                return 'admin' if os.getenv('USERNAME') == 'Administrator' else 'user'
            else:
                return 'admin' if os.geteuid() == 0 else 'user'
        except:
            return 'unknown'

# Flask应用
app = Flask(__name__, static_folder='static', static_url_path='/static')

@app.route('/api/audit-data')
def get_audit_data():
    """提供审计数据的API接口"""
    user_filter = request.args.get('user', default=None)
    time_range = request.args.get('time_range', default='24h')
    
    try:
        conn = sqlite3.connect('audit.db')
        base_query = '''
            SELECT 
                strftime('%Y-%m-%d %H:%M', timestamp) as time,
                user,
                event_type,
                COUNT(*) as count
            FROM audit_logs
            WHERE timestamp >= datetime('now', ?)
        '''
        params = [f'-{time_range}']
        
        if user_filter:
            base_query += ' AND user = ?'
            params.append(user_filter)
        
        base_query += '''
            GROUP BY time, user, event_type
            ORDER BY time DESC
        '''
        
        df = pd.read_sql(base_query, conn, params=params)
        return jsonify({
            'timeline': df.pivot_table(
                index='time',
                columns=['user', 'event_type'],
                values='count',
                fill_value=0
            ).to_dict(),
            'users': df['user'].unique().tolist(),
            'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        logger.error(f"API请求失败: {str(e)}")
        return jsonify({"error": "数据获取失败"}), 500
    finally:
        conn.close()

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>实时文件审计系统</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/luxon@3.0.4/build/global/luxon.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-luxon@1.2.0/dist/chartjs-adapter-luxon.min.js"></script>
    <style>
        /* 完整样式表 */
        :root {
            --primary: #4361ee;
            --secondary: #3f37c9;
            --light: #f8f9fa;
            --dark: #212529;
        }

        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
            padding: 2rem;
            display: flex;
            justify-content: center;
        }

        .dashboard {
            background: white;
            border-radius: 1rem;
            box-shadow: 0 0.5rem 1rem rgba(0,0,0,0.1);
            padding: 2rem;
            width: 100%;
            max-width: 1200px;
        }

        .header {
            text-align: center;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid #eee;
        }

        .header h1 {
            color: var(--primary);
            font-weight: 700;
            margin-bottom: 0.5rem;
        }

        .filter-bar {
            margin: 1.5rem 0;
            display: flex;
            gap: 1rem;
        }

        .filter-select {
            flex: 1;
            max-width: 300px;
            padding: 0.75rem 1rem;
            border: 1px solid #ddd;
            border-radius: 0.5rem;
            transition: all 0.3s ease;
        }

        .chart-card {
            background: var(--light);
            border-radius: 0.75rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 0.25rem 0.5rem rgba(0,0,0,0.05);
        }

        .chart-title {
            color: var(--dark);
            margin-bottom: 1rem;
            font-weight: 600;
        }

        .footer {
            text-align: center;
            margin-top: 2rem;
            color: #6c757d;
            font-size: 0.9rem;
        }

        canvas {
            max-height: 500px;
        }
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>📁 文件操作实时监控系统</h1>
            <p class="text-muted">最后更新：<span id="updateTime"></span></p>
        </div>

        <div class="filter-bar">
            <select id="userFilter" class="filter-select" onchange="loadData()">
                <option value="">👤 全部用户</option>
            </select>
            <select id="timeFilter" class="filter-select" onchange="loadData()">
                <option value="1h">最近1小时</option>
                <option value="24h" selected>最近24小时</option>
                <option value="7d">最近7天</option>
            </select>
        </div>

        <div class="row g-4">
            <div class="col-lg-8">
                <div class="chart-card">
                    <h5 class="chart-title">📈 操作时间线</h5>
                    <canvas id="timelineChart"></canvas>
                </div>
            </div>
            
            <div class="col-lg-4">
                <div class="chart-card">
                    <h5 class="chart-title">👥 用户分布</h5>
                    <canvas id="userPieChart"></canvas>
                </div>
            </div>
        </div>

        <div class="footer">
            <p>🔄 数据每5秒自动更新 | 版本：2.2.0 | 技术支持：audit@example.com</p>
        </div>
    </div>

    <script>
        // 完整的JavaScript代码
        let timelineChart, userPieChart;
        const colors = {
            created: '#4361ee',
            modified: '#3f37c9',
            deleted: '#ef476f'
        };

        function initCharts() {
            const timelineCtx = document.getElementById('timelineChart').getContext('2d');
            timelineChart = new Chart(timelineCtx, {
                type: 'line',
                data: { datasets: [] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { 
                            position: 'top', 
                            labels: { 
                                font: { size: 14 },
                                usePointStyle: true 
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(50, 50, 50, 0.9)',
                            titleFont: { size: 16 },
                            bodyFont: { size: 14 },
                            mode: 'index',
                            intersect: false
                        }
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: { 
                                unit: 'hour',
                                tooltipFormat: 'MM-dd HH:mm',
                                displayFormats: {
                                    hour: 'MM-dd HH:mm'
                                }
                            },
                            grid: { display: false },
                            ticks: { autoSkip: true }
                        },
                        y: {
                            beginAtZero: true,
                            ticks: { stepSize: 1 },
                            grid: { color: '#f1f3f9' }
                        }
                    },
                    interaction: {
                        mode: 'nearest',
                        axis: 'x',
                        intersect: false
                    }
                }
            });

            const pieCtx = document.getElementById('userPieChart').getContext('2d');
            userPieChart = new Chart(pieCtx, {
                type: 'pie',
                data: { datasets: [] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { 
                            position: 'right',
                            align: 'start'
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return ` ${context.label}: ${context.raw}次`;
                                }
                            }
                        }
                    }
                }
            });
        }

        async function loadData() {
            const user = document.getElementById('userFilter').value;
            const timeRange = document.getElementById('timeFilter').value;
            
            try {
                const resp = await fetch(`/api/audit-data?user=${user}&time_range=${timeRange}`);
                const data = await resp.json();
                
                if(data.error) {
                    console.error('API错误:', data.error);
                    return;
                }

                document.getElementById('updateTime').textContent = data.update_time;
                updateUserFilter(data.users);
                updateCharts(data.timeline);
            } catch (error) {
                console.error('数据加载失败:', error);
            }
        }

        function updateUserFilter(users) {
            const select = document.getElementById('userFilter');
            const currentValue = select.value;
            select.innerHTML = '<option value="">👤 全部用户</option>' + 
                users.map(u => `<option value="${u}" ${u === currentValue ? 'selected' : ''}>${u}</option>`).join('');
        }

        function updateCharts(timelineData) {
            updateTimelineChart(timelineData);
            updatePieChart(timelineData);
        }

        function updateTimelineChart(timelineData) {
            const datasets = [];
            const userEventMap = new Map();

            // 数据处理逻辑
            Object.entries(timelineData).forEach(([time, events]) => {
                Object.entries(events).forEach(([key, count]) => {
                    const [user, eventType] = key.split(',');
                    const seriesKey = `${user}_${eventType}`;
                    
                    if (!userEventMap.has(seriesKey)) {
                        userEventMap.set(seriesKey, {
                            label: `${user} - ${eventType}`,
                            data: [],
                            borderColor: colors[eventType],
                            backgroundColor: `${colors[eventType]}20`,
                            borderWidth: 2,
                            tension: 0.3,
                            pointRadius: 3
                        });
                    }
                    userEventMap.get(seriesKey).data.push({ x: time, y: count });
                });
            });

            timelineChart.data.datasets = Array.from(userEventMap.values());
            timelineChart.update();
        }

        function updatePieChart(timelineData) {
            const userCounts = {};
            Object.values(timelineData).forEach(events => {
                Object.entries(events).forEach(([key, count]) => {
                    const [user] = key.split(',');
                    userCounts[user] = (userCounts[user] || 0) + count;
                });
            });
            
            userPieChart.data = {
                labels: Object.keys(userCounts),
                datasets: [{
                    data: Object.values(userCounts),
                    backgroundColor: Object.keys(userCounts).map((_,i) => 
                        `hsl(${(i * 360 / Object.keys(userCounts).length)}, 70%, 50%)`
                    )
                }]
            };
            userPieChart.update();
        }

        // 初始化
        document.addEventListener('DOMContentLoaded', () => {
            initCharts();
            loadData();
            setInterval(loadData, 5000);
        });
    </script>
</body>
</html>
'''

@app.route('/dashboard')
def enhanced_dashboard():
    """主仪表盘路由"""
    return render_template_string(DASHBOARD_TEMPLATE)

def start_monitoring(paths):
    logger.debug("启动监控服务")
    observer = PollingObserver()  # 强制使用轮询模式
    auditor = EnhancedFileAuditor()

    for path in paths:
        logger.debug(f"尝试监控路径: {path}")
        if os.path.exists(path):
            try:
                observer.schedule(auditor, path, recursive=True)
                logger.info(f"成功监控路径: {path}")
            except Exception as e:
                logger.error(f"路径监控失败: {path} - {str(e)}")
        else:
            logger.warning(f"路径不存在: {path}")

    observer.start()
    logger.debug("观察者线程已启动")

    # 启动Flask服务
    Thread(target=lambda: app.run(
        host='0.0.0.0',
        port=5000,
        use_reloader=False,
        threaded=True
    )).start()

    try:
        while True:
            time.sleep(1)
            logger.debug("监控服务运行中...")
    except KeyboardInterrupt:
        logger.info("接收到终止信号")
        observer.stop()
    finally:
        observer.join()
        logger.info("监控服务已安全停止")

if __name__ == "__main__":
    try:
        logger.info("启动文件监控审计系统...")
        # Windows路径设置
        if platform.system() == 'Windows':
            os.system('chcp 65001 > nul')
            os.environ['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
            monitor_paths = [
                r"C:\AuditTarget",
                os.path.join(os.environ['USERPROFILE'], 'Desktop')
            ]
        else:
            monitor_paths = [
                "/tmp/audit",
                os.path.expanduser("~/Documents")
            ]
        
        # 创建测试目录
        for path in monitor_paths:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                logger.info(f"创建监控目录: {path}")

        start_monitoring(monitor_paths)
    except Exception as e:
        logger.error(f"致命错误: {str(e)}")
        import traceback
        traceback.print_exc()