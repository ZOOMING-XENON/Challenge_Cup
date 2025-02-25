import hashlib
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass
import threading
import time
import clamd
from elasticsearch import Elasticsearch
from datetime import datetime
import nipyapi
from nipyapi import canvas, templates

# 配置审计日志
logging.basicConfig(
    filename='security_audit.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class FileMetadata:
    file_path: Path
    file_type: str
    owner: str
    classification: str = "INTERNAL"

class NetworkMonitor:
    def __init__(self, interface="eth0"):
        self.interface = interface
        self.running = False
        self._monitor_thread = None
        
    def start_monitoring(self):
        """启动Snort监控"""
        self.running = True
        self._monitor_thread = threading.Thread(target=self._run_snort)
        self._monitor_thread.start()
        
    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        if self._monitor_thread:
            self._monitor_thread.join()
            
    def _run_snort(self):
        """运行Snort进程"""
        if not self._check_snort_installed():
            logging.error("Snort未安装或未添加到PATH中")
            return

        cmd = [
            'snort',
            '-i', self.interface,
            '-c', 'snort.conf',
            '-R', 'rules/local.rules',
            '-A', 'fast',
            '-l', 'logs',
            '--daq-dir', '/usr/local/lib/daq',
            '--daq', 'afpacket',
            '-k', 'none'
        ]
        
        process = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            while self.running:
                output = process.stdout.readline()
                if output:
                    self._handle_alert(output.decode().strip())
                    
        except FileNotFoundError:
            logging.error("无法启动Snort，请确保已正确安装")
        except Exception as e:
            logging.error(f"运行Snort时发生错误: {str(e)}")
        finally:
            if process:
                process.terminate()

    def _check_snort_installed(self):
        """检查Snort是否已安装"""
        try:
            subprocess.run(['snort', '--version'], 
                          capture_output=True, 
                          check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _handle_alert(self, alert_line):
        """处理Snort告警"""
        if "[**]" in alert_line:  # Snort告警标记
            logging.warning(f"检测到敏感数据传输: {alert_line}")
            # 这里可以添加阻断逻辑
            self._block_transmission(alert_line)
            
    def _block_transmission(self, alert):
        """实现阻断逻辑"""
        # 示例：使用iptables阻断特定连接
        try:
            if "信用卡号码" in alert:
                src_ip = self._extract_ip(alert)
                subprocess.run([
                    'iptables',
                    '-A', 'OUTPUT',
                    '-s', src_ip,
                    '-j', 'DROP'
                ])
                logging.info(f"已阻断来自 {src_ip} 的敏感数据传输")
        except Exception as e:
            logging.error(f"阻断失败: {str(e)}")

class SecurityScanner:
    def __init__(self):
        self.cache = {}
        self.network_monitor = NetworkMonitor()
        self.clam = clamd.ClamdNetworkSocket()
        
        # 修改 Elasticsearch 连接
        try:
            self.es = Elasticsearch(['http://localhost:9200'])  # 添加 http:// 协议
        except Exception as e:
            logging.error(f"Elasticsearch 连接失败: {str(e)}")
            self.es = None
        
        # 初始化 NiFi 连接
        try:
            nipyapi.config.nifi_config.host = 'http://localhost:8080/nifi-api'
            nipyapi.security.service.create_access_token(
                username='admin',
                password='password'
            )
        except Exception as e:
            logging.error(f"NiFi 连接失败: {str(e)}")

    def start(self):
        """启动安全扫描服务"""
        self.network_monitor.start_monitoring()
        
    def stop(self):
        """停止服务"""
        self.network_monitor.stop_monitoring()

    def process_file(self, metadata: FileMetadata) -> dict:
        """处理文件传输请求"""
        file_hash = self._calculate_hash(metadata.file_path)
        
        # 检查缓存
        if cached := self.cache.get(file_hash):
            return cached
            
        # 多引擎扫描
        snort_result = self._check_file_with_snort(metadata.file_path)
        clam_result = self._scan_with_clamav(metadata.file_path)
        
        # 合并扫描结果
        scan_result = {
            "action": "BLOCK" if (snort_result["action"] == "BLOCK" or 
                                clam_result["action"] == "BLOCK") else "ALLOW",
            "alerts": snort_result.get("alerts", []),
            "threat": clam_result.get("threat", None)
        }
        
        # 记录到 Elasticsearch
        self._log_to_elasticsearch(metadata, scan_result)
        
        # 缓存结果
        self.cache[file_hash] = scan_result
        return scan_result

    def _calculate_hash(self, file_path: Path) -> str:
        """计算文件内容哈希值"""
        hasher = hashlib.sha256()
        with file_path.open('rb') as f:
            while chunk := f.read(4096):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _check_file_with_snort(self, file_path: Path) -> dict:
        """使用 Snort 检查文件内容"""
        try:
            # 调用 Snort 进行检查
            result = subprocess.run(
                ['snort', '-r', str(file_path), '-c', 'snort.conf', '-A', 'console'],
                capture_output=True,
                text=True
            )
            
            # 分析 Snort 输出
            alerts = []
            if result.stdout:
                alerts = self._parse_snort_output(result.stdout)
                
            return {
                "action": "BLOCK" if alerts else "ALLOW",
                "alerts": alerts
            }
            
        except Exception as e:
            logging.error(f"Snort 扫描失败: {str(e)}")
            return {"action": "BLOCK", "reason": "扫描错误"}
    
    def _scan_with_clamav(self, file_path: Path) -> dict:
        """使用 ClamAV 扫描文件"""
        try:
            result = self.clam.scan(str(file_path))
            return {
                "action": "BLOCK" if result[str(file_path)][0] == 'FOUND' else "ALLOW",
                "threat": result[str(file_path)][1] if result[str(file_path)][0] == 'FOUND' else None
            }
        except Exception as e:
            logging.error(f"ClamAV 扫描失败: {str(e)}")
            return {"action": "BLOCK", "reason": "病毒扫描失败"}

    def _log_to_elasticsearch(self, metadata: FileMetadata, scan_result: dict):
        """记录扫描结果到 Elasticsearch"""
        if not self.es:
            logging.warning("Elasticsearch 未连接，跳过日志记录")
            return
            
        doc = {
            'timestamp': datetime.now(),
            'file_name': str(metadata.file_path),
            'file_type': metadata.file_type,
            'owner': metadata.owner,
            'action': scan_result['action'],
            'alerts': scan_result.get('alerts', []),
            'virus_scan': scan_result.get('threat', None)
        }
        try:
            self.es.index(index='dlp-logs', document=doc)
        except Exception as e:
            logging.error(f"ES 日志记录失败: {str(e)}")

    def _parse_snort_output(self, output: str) -> list:
        """解析 Snort 输出获取告警信息"""
        alerts = []
        for line in output.splitlines():
            if "[**]" in line:  # Snort 告警标记
                alerts.append(line.strip())
        return alerts

# 示例策略文件 (dlp_policies.yaml)
"""
policies:
  data_exfiltration:
    rules:
      - pattern: CREDIT_CARD
        max_count: 0
        action: block
        message: "信用卡信息禁止外发"
        
      - pattern: SSN
        max_count: 1
        action: watermark
        watermark_text: "CONFIDENTIAL"
        
    exceptions:
      - department: Legal
        bypass_level: 2
"""

if __name__ == "__main__":
    # 启动监控
    scanner = SecurityScanner()
    try:
        scanner.start()
        print("安全监控已启动...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止监控...")
        scanner.stop()
