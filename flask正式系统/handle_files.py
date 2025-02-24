import hashlib
import logging
from pathlib import Path
from opendlp import ContentScanner, PolicyManager
from dataclasses import dataclass

# 配置审计日志
logging.basicConfig(
    filename='dlp_audit.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class FileMetadata:
    file_path: Path
    file_type: str
    owner: str
    classification: str = "INTERNAL"

class DataLossPreventor:
    def __init__(self, policy_file="dlp_policies.yaml"):
        self.scanner = ContentScanner(
            endpoint="http://localhost:8080",
            timeout=30
        )
        self.policy = PolicyManager.load_from_file(policy_file)
        self.cache = {}  # 用于缓存扫描结果
        
    def _calculate_hash(self, file_path: Path) -> str:
        """计算文件内容哈希值"""
        hasher = hashlib.sha256()
        with file_path.open('rb') as f:
            while chunk := f.read(4096):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _apply_watermark(self, content: bytes, mark: str) -> bytes:
        """添加水印（示例实现）"""
        if self.policy.requires_watermark:
            return content + f"\n--- {mark} ---".encode()
        return content
    
    def _check_policy(self, metadata: FileMetadata) -> dict:
        """执行策略检查"""
        try:
            with metadata.file_path.open('rb') as f:
                result = self.scanner.scan(
                    content=f,
                    context={
                        'user': metadata.owner,
                        'file_type': metadata.file_type,
                        'classification': metadata.classification
                    }
                )
                
            violations = [
                f"{v.pattern_type} (confidence: {v.confidence}%)"
                for v in result.violations
            ]
            
            action = "ALLOW"
            if result.block_reason:
                action = "BLOCK"
            elif result.requires_watermark:
                action = "MODIFY"
                
            return {
                "action": action,
                "violations": violations,
                "watermark": self.policy.watermark_text
            }
            
        except Exception as e:
            logging.error(f"Scan failed: {str(e)}")
            return {"action": "BLOCK", "reason": "Scan Error"}
    
    def process_file(self, metadata: FileMetadata) -> dict:
        """处理文件传输请求"""
        file_hash = self._calculate_hash(metadata.file_path)
        
        # 检查缓存
        if cached := self.cache.get(file_hash):
            logging.info(f"Using cached result for {metadata.file_path}")
            return cached
            
        # 执行策略检查
        scan_result = self._check_policy(metadata)
        
        # 记录审计日志
        log_entry = {
            "file": str(metadata.file_path),
            "hash": file_hash,
            "user": metadata.owner,
            "action": scan_result['action'],
            "violations": scan_result.get('violations', [])
        }
        logging.info(log_entry)
        
        # 缓存结果
        self.cache[file_hash] = scan_result
        return scan_result
    
    def transfer_file(self, src: Path, dest: str, user: str) -> bool:
        """执行安全文件传输"""
        metadata = FileMetadata(
            file_path=src,
            file_type=src.suffix[1:],
            owner=user
        )
        
        result = self.process_file(metadata)
        
        if result['action'] == "BLOCK":
            print(f"传输被阻断：检测到违规内容")
            return False
            
        try:
            with src.open('rb') as f:
                content = f.read()
                
                if result['action'] == "MODIFY":
                    content = self._apply_watermark(
                        content, 
                        result['watermark']
                    )
                
                # 执行实际传输（示例：本地文件复制）
                with open(dest, 'wb') as out_file:
                    out_file.write(content)
                    
            print(f"文件安全传输完成：{src} -> {dest}")
            return True
            
        except Exception as e:
            logging.error(f"传输失败：{str(e)}")
            return False

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
    dlp = DataLossPreventor()
    
    # 测试用例
    test_files = [
        ("sensitive.docx", "user1"),
        ("report.pdf", "user2"),
        ("data.csv", "legal_user")
    ]
    
    for filename, user in test_files:
        src = Path(filename)
        dest = f"/remote/share/{filename}"
        
        if not src.exists():
            print(f"测试文件 {filename} 不存在")
            continue
            
        success = dlp.transfer_file(src, dest, user)
        print(f"传输结果：{'成功' if success else '失败'}")
