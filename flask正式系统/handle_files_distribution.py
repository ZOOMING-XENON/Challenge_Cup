import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
import os
import string
import json
import re
import requests
from PIL import Image
import io
import mimetypes
import hashlib

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 修改缓存文件路径
CONFIG_DIR = Path(__file__).parent / 'config'
CACHE_FILE = CONFIG_DIR / 'monitor_paths_cache.json'

# 确保配置目录存在
CONFIG_DIR.mkdir(exist_ok=True)

class FileMonitorHandler(FileSystemEventHandler):
    def __init__(self):
        self.processed_files = set()  # 用于记录已处理的文件
        self.pending_files = {}  # 用于记录待检测的文件
        self.processing_files = set()  # 用于记录正在处理的文件
        self.logged_filenames = set()  # 用于记录已经记录过日志的文件名
        self.api_endpoint = "https://api.siliconflow.cn/v1/chat/completions"  # SiliconFlow API 端点
        self.api_key = "sk-mqpsbcvlkcreevemrcmmguauztcphrusyvdlxwfpmvrpkzwr"
        self.blocked_files = set()  # 用于记录已经被阻止的文件
        
        # 创建临时检测目录和备份目录
        self.temp_dir = Path(__file__).parent / 'temp_checking'
        self.backup_dir = Path(__file__).parent / 'blocked_files'
        self.temp_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
        
        # 添加本地敏感词列表
        self.sensitive_keywords = {
            '机密', '秘密', '内部', '禁止外发', '不得外传', 
            '保密', '隐私', '私密', '绝密', '密级',
            '内控', '未公开', '不得公开', '草稿', '初稿',
            'confidential', 'secret', 'internal', 'private', 'draft'
        }

    def _get_base_filename(self, filename):
        """获取文件的基础名称（去掉括号中的序号）"""
        # 匹配文件名末尾的 (数字) 模式
        pattern = r'(.*?)\s*\(\d+\)(\.[^.]*)?$'
        match = re.match(pattern, filename)
        if match:
            # 如果匹配到括号序号，返回去掉序号的基础名称
            base_name = match.group(1)
            extension = match.group(2) or ''
            return base_name + extension
        return filename

    def _quick_check_filename(self, filename):
        """快速检查文件名（本地关键词匹配）"""
        filename_lower = filename.lower()
        for keyword in self.sensitive_keywords:
            if keyword in filename_lower:
                return False
        return True

    def _check_filename(self, filename):
        """分两步检查文件名"""
        # 1. 先进行快速本地检查
        if not self._quick_check_filename(filename):
            logging.warning("文件名不合规（本地检测）")
            return False
            
        # 2. 如果本地检查通过，再调用API进行深度检查
        try:
            # 准备 API 请求
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # 构建提示词
            prompt = f"""请分析这个文件名是否包含敏感词或暗示文件不应该外发的词语（如'机密'、'内部'、'禁止外发'等）。
            如果安全返回'safe'，如果不安全返回'unsafe'。
            文件名：{filename}"""
            
            data = {
                "model": "deepseek-ai/DeepSeek-V3",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 512,
                "temperature": 0.7
            }
            
            # 发送 API 请求
            response = requests.post(self.api_endpoint, headers=headers, json=data)
            result = response.json()
            
            # 解析响应
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].lower()
                is_safe = 'safe' in content
                if not is_safe:
                    logging.warning("文件名不合规")
                return is_safe
            return True
                
        except Exception as e:
            logging.error(f"检查文件名时出错: {e}")
            return True

    def on_any_event(self, event):
        """捕获所有文件事件"""
        # 忽略目录事件和临时文件
        if (event.is_directory or 
            event.src_path.endswith(('.tmp', '~', '.crdownload', '.blocked')) or
            '_t.dat' in event.src_path or
            event.src_path in self.blocked_files):  # 忽略已经被阻止的文件
            return
            
        file_name = os.path.basename(event.src_path)
        
        # 忽略特定格式的临时文件
        if (len(file_name) == 36 and file_name.endswith('_t.dat') or
            file_name.startswith('~') or
            file_name.startswith('._')):
            return
            
        base_filename = self._get_base_filename(file_name)
        
        # 如果文件基础名称已经记录过日志，直接跳过
        if base_filename in self.logged_filenames:
            return
            
        # 如果文件已经处理过，跳过
        if base_filename in self.processed_files:
            return
            
        # 如果文件正在处理中，跳过
        if event.src_path in self.processing_files:
            return
            
        # 监控文件创建和修改事件
        if event.event_type in ['created', 'modified']:
            try:
                if "File" in event.src_path or "FileRecv" in event.src_path:
                    # 标记文件正在处理
                    self.processing_files.add(event.src_path)
                    
                    # 等待文件完全写入完成
                    time.sleep(0.5)
                    
                    if not self._is_file_ready(event.src_path):
                        self.processing_files.remove(event.src_path)
                        return
                    
                    # 将文件移动到临时目录进行检测
                    file_name = os.path.basename(event.src_path)
                    temp_path = self.temp_dir / file_name
                    
                    # 如果临时目录已存在同名文件，添加时间戳
                    if temp_path.exists():
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        temp_path = self.temp_dir / f"{file_name}_{timestamp}"
                    
                    # 移动到临时目录
                    os.rename(event.src_path, temp_path)
                    
                    # 创建占位文件
                    with open(event.src_path, 'w') as f:
                        f.write("文件正在检测中，请稍候...")
                    
                    # 检查文件名
                    if not self._check_filename(file_name):
                        logging.warning(f"\n文件名包含敏感词，阻止发送: {file_name}")
                        self._block_file_transfer(str(temp_path), event.src_path)
                        self.processing_files.remove(event.src_path)
                        return
                    
                    self.logged_filenames.add(base_filename)
                    
                    # 检查文件内容
                    if self._check_file_content(str(temp_path)):
                        # 检测通过，恢复文件
                        os.remove(event.src_path)  # 删除占位文件
                        os.rename(temp_path, event.src_path)  # 恢复原文件
                        logging.info(f"\n文件检测通过，允许发送:")
                        logging.info(f"文件名: {file_name}")
                        size = os.path.getsize(event.src_path)
                        logging.info(f"大小: {self._format_size(size)}")
                    else:
                        logging.warning(f"\n发现违规文件，阻止发送: {file_name}")
                        self._block_file_transfer(str(temp_path), event.src_path)
                    
                    # 记录已处理
                    self.processed_files.add(base_filename)
                    if event.src_path in self.pending_files:
                        del self.pending_files[event.src_path]
                    
                    # 移除处理中标记
                    self.processing_files.remove(event.src_path)
                        
            except Exception as e:
                logging.error(f"处理文件事件时出错: {e}")
                if event.src_path in self.processing_files:
                    self.processing_files.remove(event.src_path)

    def _is_file_ready(self, file_path):
        """检查文件是否写入完成"""
        try:
            # 尝试打开文件进行读取
            with open(file_path, 'rb') as f:
                # 如果文件可以被完整读取，说明写入已完成
                f.read()
                return True
        except (IOError, PermissionError):
            # 文件正在被写入，无法读取
            return False

    def _get_file_hash(self, file_path):
        """计算文件的MD5哈希值"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
        
    def _check_file_content(self, file_path):
        """检查文件内容是否合规"""
        try:
            # 获取文件类型
            mime_type, _ = mimetypes.guess_type(file_path)
            
            if not mime_type:
                return True
                
            # 根据文件类型进行不同的处理
            if mime_type.startswith('image/'):
                return self._check_image_content(file_path)
            elif mime_type.startswith('text/'):
                return self._check_text_content(file_path)
            elif mime_type.startswith('application/pdf'):
                return self._check_pdf_content(file_path)
            else:
                logging.info(f"不支持的文件类型: {mime_type}")
                return True  # 对于不支持的类型，默认允许
                
        except Exception as e:
            logging.error(f"检查文件内容时出错: {e}")
            return True
            
    def _check_image_content(self, file_path):
        """使用 SiliconFlow API 检查图片内容"""
        try:
            # 读取图片并转换为 base64
            with open(file_path, 'rb') as f:
                image_data = f.read()
            import base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
                
            # 准备 API 请求
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # 构建提示词
            prompt = f"请分析这张图片是否包含不当或敏感内容。如果安全返回'safe'，如果不安全返回'unsafe'。图片数据：<image>{image_base64}</image>"
            
            data = {
                "model": "deepseek-ai/DeepSeek-V3",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 512,
                "temperature": 0.7
            }
            
            # 发送 API 请求
            response = requests.post(self.api_endpoint, headers=headers, json=data)
            result = response.json()
            
            # 解析响应
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].lower()
                is_safe = 'safe' in content
                if not is_safe:
                    logging.warning("图片内容不合规")
                return is_safe
            return True
                
        except Exception as e:
            logging.error(f"检查图片内容时出错: {e}")
            return True
            
    def _quick_check_text_content(self, text):
        """快速检查文本内容（本地关键词匹配）"""
        text_lower = text.lower()
        for keyword in self.sensitive_keywords:
            if keyword in text_lower:
                return False
        return True

    def _check_text_content(self, file_path):
        """分两步检查文本内容"""
        try:
            # 读取文本文件
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
                
            # 1. 先进行快速本地检查
            if not self._quick_check_text_content(text):
                logging.warning("文本内容不合规（本地检测）")
                return False
                
            # 2. 如果本地检查通过，再调用API进行深度检查
            # 准备 API 请求
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # 构建提示词
            prompt = f"请分析以下文本内容是否包含敏感或不当信息。如果安全返回'safe'，如果不安全返回'unsafe'。文本内容：{text}"
            
            data = {
                "model": "deepseek-ai/DeepSeek-V3",  # 使用 DeepSeek-V3 模型
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 512,
                "temperature": 0.7
            }
            
            # 发送 API 请求
            response = requests.post(self.api_endpoint, headers=headers, json=data)
            result = response.json()
            
            # 解析响应
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].lower()
                is_safe = 'safe' in content
                if not is_safe:
                    logging.warning("文本内容不合规")
                return is_safe
            return True
                
        except Exception as e:
            logging.error(f"检查文本内容时出错: {e}")
            return True
            
    def _check_pdf_content(self, file_path):
        """检查PDF内容"""
        try:
            # 读取PDF文件
            with open(file_path, 'rb') as f:
                pdf_data = f.read()
                
            # 准备API请求
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'file': pdf_data.hex(),  # 将PDF数据转换为十六进制字符
                'type': 'document'  # 检测类型：文档
            }
            
            # 发送API请求
            response = requests.post(self.api_endpoint, headers=headers, json=data)
            result = response.json()
            
            # 解析响应
            if result.get('is_safe', True):
                return True
            else:
                logging.warning(f"PDF内容不合规: {result.get('reason', '未知原因')}")
                return False
                
        except Exception as e:
            logging.error(f"检查PDF内容时出错: {e}")
            return True

    def _block_file_transfer(self, temp_path, original_path):
        """阻止文件发送并保存备份"""
        try:
            # 将文件添加到已阻止列表
            self.blocked_files.add(original_path)
            
            # 生成备份文件路径
            file_name = os.path.basename(temp_path)
            backup_path = self.backup_dir / file_name
            
            # 如果已存在同名文件，添加时间戳
            if backup_path.exists():
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_path = self.backup_dir / f"{file_name}_{timestamp}"
            
            # 将临时文件移动到备份目录
            os.rename(temp_path, backup_path)
            
            # 替换原文件为警告信息
            with open(original_path, 'w') as f:
                f.write("文件已被安全系统拦截")
            
            # 设置替代文件为只读
            os.chmod(original_path, 0o444)
            
            # 记录备份信息
            logging.info(f"已阻止文件: {original_path}")
            logging.info(f"原文件已备份至: {backup_path}")
            
        except Exception as e:
            logging.error(f"阻止文件发送失败: {e}")
            self.blocked_files.discard(original_path)

    def restore_file(self, backup_path):
        """恢复被阻止的文件"""
        try:
            backup_path = Path(backup_path)
            if not backup_path.exists():
                logging.error(f"备份文件不存在: {backup_path}")
                return False
                
            # 获取原始文件路径
            original_name = backup_path.name
            if '_202' in original_name:  # 如果文件名包含时间戳
                original_name = original_name.split('_202')[0]
                
            # 恢复到原始位置
            original_path = Path(os.path.dirname(str(backup_path).replace('blocked_files', 'FileRecv'))) / original_name
            
            # 如果存在替代文件，先删除
            if original_path.exists():
                os.chmod(original_path, 0o777)  # 修改权限以允许删除
                os.remove(original_path)
                
            # 移动备份文件回原位置
            os.rename(backup_path, original_path)
            
            # 从阻止列表中移除
            self.blocked_files.discard(str(original_path))
            
            logging.info(f"已恢复文件: {original_path}")
            return True
            
        except Exception as e:
            logging.error(f"恢复文件失败: {e}")
            return False

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

def get_available_drives():
    """获取所有可用的驱动器"""
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:"
        if os.path.exists(drive):
            drives.append(drive)
            logging.info(f"找到驱动器: {drive}")
    return drives

def get_file_transfer_paths():
    """获取所有可能的文件传输路径"""
    paths = set()
    
    # 只保留微信和QQ的路径模式
    transfer_patterns = {
        'IM': [
            "WeChat Files", "微信文件", "FileStorage",
            "Tencent/QQ", "QQ/FileRecv", "QQFile",
            "Tencent Files"  # QQ聊天文件保存路径
        ]
    }
    
    # 检查所有驱动器
    for drive in get_available_drives():
        for category, patterns in transfer_patterns.items():
            for pattern in patterns:
                try:
                    for root, dirs, files in os.walk(drive + "\\"):
                        if any(p in root for p in [pattern]):
                            path = Path(root)
                            if path.exists():
                                # 检查是否包含关键子目录
                                key_subdirs = ["FileStorage", "File", "Files", "FileRecv"]
                                for subdir in key_subdirs:
                                    subpath = path / subdir
                                    if subpath.exists():
                                        paths.add(subpath)
                                        logging.info(f"添加{category}监控目录: {subpath}")
                except Exception as e:
                    logging.error(f"扫描{category}目录出错 {drive}: {e}")
                    continue
    
    return list(paths)

def save_paths_to_cache(paths):
    """保存监控路径到缓存文件"""
    try:
        # 确保配置目录存在
        CONFIG_DIR.mkdir(exist_ok=True)
        
        # 将Path对象转换为字符串
        paths_str = [str(path) for path in paths]
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(paths_str, f, ensure_ascii=False, indent=2)
        logging.info(f"监控路径已保存到配置目录: {CACHE_FILE}")
    except Exception as e:
        logging.error(f"保存路径配置失败: {e}")

def load_paths_from_cache():
    """从缓存文件加载监控路径"""
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                paths_str = json.load(f)
                # 验证路径是否仍然存在
                valid_paths = []
                for path_str in paths_str:
                    path = Path(path_str)
                    if path.exists():
                        valid_paths.append(path)
                    else:
                        logging.warning(f"缓存的路径不再存在: {path}")
                
                if valid_paths:
                    logging.info(f"从缓存加载了 {len(valid_paths)} 个有效路径")
                    return valid_paths
    except Exception as e:
        logging.error(f"加载路径缓存失败: {e}")
    return None

def get_monitor_paths():
    """获取所有需要监控的路径"""
    # 首先尝试从缓存加载
    cached_paths = load_paths_from_cache()
    if cached_paths:
        return cached_paths
        
    logging.info("未找到缓存或缓存无效，开始扫描路径...")
    
    # 获取所有文件传输路径
    paths = set(get_file_transfer_paths())
    
    # 保存到缓存
    paths_list = list(paths)
    save_paths_to_cache(paths_list)
    
    return paths_list

def start_monitoring():
    """启动文件监控"""
    logging.info("开始获取监控路径...")
    monitor_paths = get_monitor_paths()
    
    if not monitor_paths:
        logging.error("没有找到任何可监控的路径！")
        return
        
    logging.info(f"找到 {len(monitor_paths)} 个监控路径")
    
    event_handler = FileMonitorHandler()
    observer = Observer()
    
    for path in monitor_paths:
        try:
            observer.schedule(event_handler, str(path), recursive=True)
            logging.info(f"成功设置监控: {path}")
        except Exception as e:
            logging.error(f"设置监控失败 {path}: {e}")
    
    observer.start()
    logging.info("文件监控已启动...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("停止监控")
    observer.join()

if __name__ == "__main__":
    
    start_monitoring()