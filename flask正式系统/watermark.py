import sys
import platform
import traceback
import getpass
import socket
import uuid
import os
import re
import cv2
import numpy as np
import difflib
import random
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox,
    QSystemTrayIcon, QMenu, QStyle
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation,
    QThread, pyqtSignal, QSize
)
from PyQt5.QtGui import (
    QPainter, QColor, QFont,
    QFontMetrics, QIcon, QLinearGradient
)
from rapidocr_onnxruntime import RapidOCR
import psutil
import ctypes
import win32gui
import win32process

# -------------------- 配置参数 --------------------
class SecurityConfig:
    """安全水印系统配置"""
    SENSITIVE_KEYWORDS = ["机密", "秘密", "confidential", "内部文件"]
    SENSITIVE_PATHS = [r"C:\敏感文档", r"D:\保密项目"]
    MONITOR_APPS = ["EXCEL.EXE", "WINWORD.EXE", "AcroRd32.exe", "notepad.exe"]
    
    REQUIRED_MODELS = {
        "det_model": "ch_PP-OCRv3_det_infer.onnx",
        "rec_model": "ch_PP-OCRv3_rec_infer.onnx",
        "cls_model": "ch_ppocr_mobile_v2.0_cls_train.onnx"
    }
    CHECK_INTERVAL = 1000    # 检测间隔（毫秒）
    FADE_DURATION = 800      # 水印淡入淡出时间（毫秒）
    OCR_THRESHOLD = 0.15     # OCR置信度阈值
    DEBUG_MODE = True        # 调试模式
    FORCE_WATERMARK = False  # 强制显示水印（测试用）
    
    OCR_MODEL_DIR = os.path.abspath("./models")
    OCR_GPU = False
    LOCK_FILE = "security_watermark.lock"
    APP_ICON = os.path.abspath("shield.ico") 
    
    # 性能优化参数
    OCR_INTERVAL = 3         # OCR检测间隔（秒）
    SCREENSHOT_SCALE = 0.7   # 截图缩放比例

# -------------------- 系统权限检查 --------------------
def require_admin():
    """Windows系统管理员权限检查（改进版）"""
    if platform.system() != "Windows":
        return

    try:
        if ctypes.windll.shell32.IsUserAnAdmin() != 0:
            print("[权限检查] 当前已具有管理员权限")
            return

        print("[权限检查] 尝试提权...")
        # 获取当前脚本绝对路径
        executable = os.path.abspath(sys.executable)
        params = ' '.join([f'"{arg}"' for arg in sys.argv])
        
        # 使用ShellExecuteEx确保提权后工作目录正确
        SEE_MASK_NOCLOSEPROCESS = 0x00000040
        SW_SHOW = 5
        
        class ShellExecuteInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("fMask", ctypes.c_ulong),
                ("hwnd", ctypes.c_void_p),
                ("lpVerb", ctypes.c_wchar_p),
                ("lpFile", ctypes.c_wchar_p),
                ("lpParameters", ctypes.c_wchar_p),
                ("lpDirectory", ctypes.c_wchar_p),
                ("nShow", ctypes.c_int),
                ("hInstApp", ctypes.c_void_p),
                ("lpIDList", ctypes.c_void_p),
                ("lpClass", ctypes.c_wchar_p),
                ("hKeyClass", ctypes.c_void_p),
                ("dwHotKey", ctypes.c_ulong),
                ("hMonitor", ctypes.c_void_p),
                ("hProcess", ctypes.c_void_p),
            ]

        info = ShellExecuteInfo()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = "runas"
        info.lpFile = executable
        info.lpParameters = params
        info.lpDirectory = os.getcwd()  # 显式指定工作目录
        info.nShow = SW_SHOW

        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            raise ctypes.WinError()

        print(f"[权限检查] 新进程已启动 PID: {info.hProcess}")
        sys.exit(0)
        
    except Exception as e:
        QMessageBox.critical(
            QApplication.activeWindow(),
            "权限错误",
            f"提权失败: {str(e)}\n错误代码: {ctypes.GetLastError()}"
        )
        sys.exit(1)

class InstanceChecker:
    def __init__(self):
        self.lock_file = SecurityConfig.LOCK_FILE
        self.is_admin = ctypes.windll.shell32.IsUserAnAdmin() if platform.system() == "Windows" else False

    def check(self):
        """执行单实例检查"""
        try:
            print(f"[实例检查] 当前锁文件: {self.lock_file}")
            
            # 清理旧实例锁文件（如果当前是管理员权限）
            if self.is_admin:
                normal_lock = SecurityConfig.LOCK_FILE
                if os.path.exists(normal_lock) and normal_lock != self.lock_file:
                    print(f"[实例检查] 清理普通权限锁文件: {normal_lock}")
                    try:
                        os.remove(normal_lock)
                    except Exception as e:
                        print(f"[清理警告] 无法删除旧锁文件: {str(e)}")

            if os.path.exists(self.lock_file):
                print("[实例检查] 发现已有锁文件，进行检查...")
                self._check_running_instance()
            
            # 创建新锁文件
            with open(self.lock_file, 'w') as f:
                f.write(str(os.getpid()))
            print(f"[实例检查] 创建新锁文件 PID: {os.getpid()}")
                
        except Exception as e:
            QMessageBox.critical(
                None,
                "启动失败",
                f"初始化失败: {str(e)}\n请检查文件读写权限"
            )
            sys.exit(1)


    def _check_running_instance(self):
        """检查运行中的实例"""
        try:
            with open(self.lock_file, 'r') as f:
                pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    QMessageBox.critical(
                        None,
                        "运行冲突",
                        "检测到已有实例正在运行！"
                    )
                    sys.exit(1)
        except:
            pass
        
        # 清理无效锁文件
        try:
            os.remove(self.lock_file)
        except:
            pass
        
# -------------------- 检测线程 --------------------
class DetectorThread(QThread):
    detection_result = pyqtSignal(bool)
    status_update = pyqtSignal(str)  # 新增状态信号
    
    def __init__(self, ocr_engine):
        super().__init__()
        self.ocr_engine = ocr_engine
        self.running = True
        self.last_path = ""
        self.last_ocr_time = 0
        self.heartbeat_count = 0  # 新增心跳计数器

    def run(self):
        """主检测循环（完整增强版）"""
        while self.running:
            try:
                # ================= 心跳检测 =================
                self.heartbeat_count += 1
                if self.heartbeat_count % 10 == 0:  # 每15秒发送心跳
                    self.status_update.emit("HEARTBEAT")
                
                # ================= 权限验证 =================
                if not self._check_admin():
                    self.status_update.emit("ADMIN_LOST")
                    self.detection_result.emit(True)
                    QThread.msleep(3000)
                    continue
                
                # ================= 获取窗口内容 =================
                content = self._get_foreground_content()
                current_path = self._extract_file_path(content)
                
                # ================= OCR检测 =================
                ocr_text = ""
                current_time = datetime.now().timestamp()
                try:
                    if current_time - self.last_ocr_time > SecurityConfig.OCR_INTERVAL:
                        self.status_update.emit("OCR_START")
                        ocr_text = self._detect_via_ocr()
                        self.last_ocr_time = current_time
                        self.status_update.emit("OCR_FINISH")
                except Exception as ocr_error:
                    self.status_update.emit(f"OCR_ERROR: {traceback.format_exc()}")
                    ocr_text = ""

                # ================= 调试输出 =================
                if SecurityConfig.DEBUG_MODE:
                    self._debug_output(content, current_path, ocr_text)

                # ================= 综合检测 =================
                detection_results = [
                    self._check_keywords(content),
                    self._check_keywords(ocr_text),
                    self._check_paths(current_path),
                    self._check_apps(content)
                ]
                
                # ================= 发送检测结果 =================
                final_result = any(detection_results) or SecurityConfig.FORCE_WATERMARK
                self.detection_result.emit(final_result)
                self.status_update.emit(f"DETECTION_RESULT: {final_result}")
                
                QThread.msleep(SecurityConfig.CHECK_INTERVAL)

            except Exception as e:
                error_msg = f"THREAD_CRASH: {traceback.format_exc()}"
                self.status_update.emit(error_msg)
                print(f"[严重错误] {error_msg}")
                break  # 防止线程死循环

        # 线程退出清理
        self.status_update.emit("THREAD_STOPPED")
        print("[检测线程] 安全退出")
    # -------------------- 检测方法 --------------------
    def _check_admin(self):
        """验证管理员权限"""
        try:
            if platform.system() == "Windows" and not hasattr(self, '_admin_checked'):
                if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                    return False
                self._admin_checked = True
            return True
        except:
            return False
        

    def _get_foreground_content(self):
        """获取当前窗口信息"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            cmdline = " ".join(process.cmdline()) if process.cmdline() else ""
            return f"{title} | {process.name()} | {process.exe()}"
        except:
            return ""

    def _extract_file_path(self, content):
        """提取文件路径"""
        try:
            parts = content.split("|")
            if len(parts) < 3:
                return ""
            
            # 从窗口标题提取
            title_path = re.findall(r"[A-Za-z]:\\[^|]+", parts[0].strip())
            if title_path:
                return self._normalize_path(title_path[0])
            
            # 从进程路径提取
            return self._normalize_path(parts[2].strip())
        except:
            return ""

    def _normalize_path(self, path):
        """标准化路径处理"""
        try:
            path = os.path.abspath(path)
            if not os.access(path, os.R_OK):
                return ""
            return os.path.normcase(path)
        except:
            return ""

    def _detect_via_ocr(self):
        """OCR识别（容错增强版）"""
        try:
            screen = QApplication.primaryScreen()
            if not screen:
                raise RuntimeError("无法获取屏幕对象")
                
            screenshot = screen.grabWindow(0)
            if screenshot.isNull():
                raise RuntimeError("截图失败")
                
            # 处理缩放比例
            scaled_width = int(screen.size().width() * SecurityConfig.SCREENSHOT_SCALE)
            scaled_height = int(screen.size().height() * SecurityConfig.SCREENSHOT_SCALE)
            if scaled_width <= 0 or scaled_height <= 0:
                scaled_width = screen.size().width()
                scaled_height = screen.size().height()
                
            screenshot = screenshot.scaled(
                scaled_width,
                scaled_height,
                Qt.KeepAspectRatio
            )

            # 转换为OpenCV格式
            qimg = screenshot.toImage()
            buffer = qimg.bits().asstring(qimg.byteCount())
            img = np.frombuffer(buffer, dtype=np.uint8).reshape(
                qimg.height(), qimg.width(), 4)
            
            # 图像增强处理
            processed_img = self._preprocess_image(img)
            
            if SecurityConfig.DEBUG_MODE:
                cv2.imwrite("debug_ocr_preprocessed.jpg", processed_img)
            
            result, _ = self.ocr_engine(processed_img)
            return " ".join([res[1] for res in result if float(res[2]) > SecurityConfig.OCR_THRESHOLD])
        except Exception as e:
            print(f"[OCR错误] {traceback.format_exc()}")
            return ""

    def _preprocess_image(self, img):
        """图像预处理（增强版）"""
        # 锐化处理
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(img, -1, kernel)
        
        # 转换为BGR格式（移除Alpha通道）
        bgr_img = cv2.cvtColor(sharpened, cv2.COLOR_BGRA2BGR)
        
        # 对比度增强
        lab = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        
        # 自适应阈值
        gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
        return cv2.adaptiveThreshold(gray, 255, 
                                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 11, 2)

    def _check_paths(self, current_path):
        """路径检测（增强版）"""
        try:
            if not current_path:
                return False
            
            # 敏感文件类型检测
            sensitive_ext = ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.pdf']
            if any(current_path.lower().endswith(ext) for ext in sensitive_ext):
                return True
            
            # 路径匹配检测
            sensitive_paths = [
                os.path.normcase(os.path.abspath(p)) 
                for p in SecurityConfig.SENSITIVE_PATHS 
                if os.path.exists(p)
            ]
            return any(
                os.path.commonpath([current_path, sp]) == sp
                for sp in sensitive_paths
                if sp
            )
        except:
            return False

    def _check_keywords(self, text):
        """关键词检测"""
        if not text:
            return False
        
        text_lower = text.lower()
        for kw in SecurityConfig.SENSITIVE_KEYWORDS:
            if re.search(rf'\b{re.escape(kw)}\b', text, re.I):
                return True
            if difflib.SequenceMatcher(
                lambda x: x in " \t", text_lower, kw.lower()
            ).ratio() > 0.8:
                return True
        return False

    def _check_apps(self, content):
        """应用检测（增强版）"""
        try:
            # 进程树检测
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            for p in [process] + process.parents():
                if p.name().lower() in [a.lower() for a in SecurityConfig.MONITOR_APPS]:
                    return True
        except:
            pass
        
        # 内容检测
        return any(app.lower() in content.lower() for app in SecurityConfig.MONITOR_APPS)

    def _debug_output(self, content, path, ocr_text):
        """调试信息输出"""
        debug_info = [
            f"\n[检测周期 {datetime.now().strftime('%H:%M:%S')}]",
            f"窗口内容: {content}",
            f"解析路径: {path}",
            f"OCR识别: {ocr_text[:80]}...",
            f"关键词检测: {self._check_keywords(content)} (内容), {self._check_keywords(ocr_text)} (OCR)",
            f"路径检测: {self._check_paths(path)}",
            f"应用检测: {self._check_apps(content)}",
            "-" * 60
        ]
        print("\n".join(debug_info))

    def stop(self):
        self.running = False
        self.status_update.emit("STOPPING")
        if not self.wait(3000):  # 等待3秒安全退出
            self.terminate()
            self.status_update.emit("FORCE_STOPPED")

# -------------------- 主窗口类 --------------------
class SecurityWatermark(QMainWindow):
    def __init__(self):
        super().__init__()
        self.user_info = self._collect_user_info()
        self.active = False
        self.ocr_engine = None
        self.detector_thread = None
        self.base_offset_x = 0
        self.base_offset_y = 0
        
        self.init_ui()
        self.init_window_properties()
        self.init_tray_icon()
        self.init_ocr_system()
        self.show_startup_notification()

        if SecurityConfig.DEBUG_MODE:
            self.test_watermark()

    # -------------------- 初始化方法 --------------------
    def _collect_user_info(self):
        """收集用户信息"""
        try:
            return {
                "username": getpass.getuser(),
                "hostname": socket.gethostname(),
                "ip": socket.gethostbyname_ex(socket.gethostname())[-1][0],
                "mac": ':'.join([f'{(uuid.getnode() >> i) & 0xff:02x}' 
                               for i in range(0, 8 * 6, 8)][::-1])
            }
        except:
            return {"username": "Unknown", "hostname": "Unknown"}

    def init_ui(self):
        """界面初始化"""
        # 获取屏幕信息
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry()
        print(f"[屏幕信息] 实际分辨率: {screen_geo.width()}x{screen_geo.height()}")

        # 初始窗口设置
        self.setGeometry(0, 0, screen_geo.width(), screen_geo.height())
        self.setFixedSize(screen_geo.width(), screen_geo.height())  # 固定窗口尺寸
        
        # 根据配置设置初始透明度
        initial_opacity = 0.85 if SecurityConfig.FORCE_WATERMARK else 0.0
        self.setWindowOpacity(initial_opacity)  # 立即设置初始值
        
        # 调试信息
        print(f"[窗口初始化] 初始不透明度: {self.windowOpacity()}")
        
        # 字体设置
        self.font = QFont('微软雅黑', 28)
        self.font.setBold(True)
        
        # 水印参数
        self.angle = -20
        self.opacity = 0.85  # 注意：这是动画目标值，不是实际窗口属性
        self.spacing = 280

        self.setWindowOpacity(0.0)  # 初始完全透明
        if SecurityConfig.FORCE_WATERMARK:
            self.setWindowOpacity(0.85)
       
        # 临时调试样式（将在延迟后清除）
        self.setStyleSheet("background: red; border: 2px solid blue;")

    def showEvent(self, event):
        """窗口显示事件处理"""
        super().showEvent(event)
        if SecurityConfig.FORCE_WATERMARK:
            # 二次保障设置
            QTimer.singleShot(100, self._force_opacity)
            print("[窗口事件] 全屏显示完成")

    def _force_opacity(self):
        """新增方法：强制设置透明度"""
        if SecurityConfig.FORCE_WATERMARK:
            self.setWindowOpacity(0.85)
            self.update()
            print(f"[强制设置] 当前透明度: {self.windowOpacity()}")
    

    def init_window_properties(self):
        """窗口属性设置"""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

    def init_tray_icon(self):
        """系统托盘图标"""
        self.tray = QSystemTrayIcon(self)
        if os.path.exists(SecurityConfig.APP_ICON):
            self.tray.setIcon(QIcon(SecurityConfig.APP_ICON))
        else:
            self.tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        
        menu = QMenu()
        menu.addAction("运行状态", self.show_status)
        menu.addSeparator()
        menu.addAction("退出", self.close)
        self.tray.setContextMenu(menu)
        self.tray.show()

    # -------------------- 功能方法 --------------------
    def show_startup_notification(self):
        """启动通知"""
        self.tray.showMessage(
            "安全水印服务", 
            f"服务已启动\n用户: {self.user_info['username']}\nIP: {self.user_info['ip']}",
            QSystemTrayIcon.Information, 5000)

    def show_status(self):
        """显示状态"""
        status = QMessageBox()
        status.setIcon(QMessageBox.Information)
        status.setWindowTitle("实时状态")
        admin_status = "管理员权限" if self._check_admin() else "权限不足"
        status.setText(
            f"🛡️ 安全状态: {admin_status}\n"
            f"🔒 水印状态: {'激活' if self.active else '未激活'}\n"
            f"🕒 最后检测: {datetime.now().strftime('%H:%M:%S')}\n"
            f"👤 用户: {self.user_info['username']}\n"
            f"🌐 IP地址: {self.user_info['ip']}"
        )
        status.exec_()

    def _check_admin(self):
        """检查管理员权限"""
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return True

    # -------------------- OCR系统初始化 --------------------
    def init_ocr_system(self):
        """OCR系统初始化（增强版）"""
        try:
            # 路径验证
            self._validate_paths()
            
            # 模型验证
            missing_models = []
            for name, file in SecurityConfig.REQUIRED_MODELS.items():
                model_path = os.path.join(SecurityConfig.OCR_MODEL_DIR, file)
                if not os.path.exists(model_path):
                    missing_models.append(f"{name}({file})")
            
            if missing_models:
                raise FileNotFoundError(
                    f"缺失关键模型文件: {', '.join(missing_models)}\n"
                    f"模型目录: {SecurityConfig.OCR_MODEL_DIR}"
                )

            # OCR引擎初始化
            self.ocr_engine = RapidOCR(
                det_model_path=os.path.join(SecurityConfig.OCR_MODEL_DIR, SecurityConfig.REQUIRED_MODELS["det_model"]),
                rec_model_path=os.path.join(SecurityConfig.OCR_MODEL_DIR, SecurityConfig.REQUIRED_MODELS["rec_model"]),
                cls_model_path=os.path.join(SecurityConfig.OCR_MODEL_DIR, SecurityConfig.REQUIRED_MODELS["cls_model"]),
                use_angle_cls=True,
                use_gpu=SecurityConfig.OCR_GPU
            )

            # OCR功能测试
            if not self._test_ocr():
                raise RuntimeError("OCR功能自检失败")

            self.start_detection()

        except Exception as e:
            self.show_critical_error("OCR初始化失败", str(e))

    def _validate_paths(self):
        """路径验证"""
        print(f"[系统信息] 当前工作目录: {os.getcwd()}")
        print(f"[系统信息] 可执行文件路径: {sys.executable}")
        print(f"[系统信息] 模型绝对路径: {SecurityConfig.OCR_MODEL_DIR}")
        
        if not os.path.isdir(SecurityConfig.OCR_MODEL_DIR):
            raise FileNotFoundError(f"模型目录不存在: {SecurityConfig.OCR_MODEL_DIR}")
        
        if not os.path.exists(SecurityConfig.APP_ICON):
            print(f"[警告] 图标文件缺失: {SecurityConfig.APP_ICON}")
    def _validate_models(self):
        """验证模型文件"""
        required_models = [
            "ch_PP-OCRv3_det_infer.onnx",
            "ch_PP-OCRv3_rec_infer.onnx",
            "ch_ppocr_mobile_v2.0_cls_train.onnx"
        ]
        return all(
            os.path.exists(os.path.join(SecurityConfig.OCR_MODEL_DIR, m))
            for m in required_models
        )

    def _test_ocr(self):
        """OCR功能测试"""
        test_img = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.putText(test_img, "test", (10,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
        result, _ = self.ocr_engine(test_img)
        return result and result[0][1] == "test"

    # -------------------- 水印控制 --------------------
    def start_detection(self):
        """启动检测"""
        self.detector_thread = DetectorThread(self.ocr_engine)
        self.detector_thread.detection_result.connect(self.handle_detection)
        self.detector_thread.start()

    def handle_detection(self, need_activate):
        """处理检测结果"""
        if need_activate != self.active:
            self.active = need_activate
            self.toggle_watermark(need_activate)
            self.update_tray_icon()

    def toggle_watermark(self, show):
        target_opacity = self.opacity if show else 0.0
        self.setWindowOpacity(target_opacity)

        if platform.system() == "Windows":
            try:
                # 定义标志常量
                SWP_NOMOVE = 0x0001
                SWP_NOSIZE = 0x0002
                SWP_SHOWWINDOW = 0x0040
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                
                # 获取并转换窗口句柄
                hwnd = int(self.winId())  # 关键转换
                
                # 调用Windows API
                ctypes.windll.user32.SetWindowPos(
                    hwnd,   # 窗口句柄
                    -1,     # 置顶显示 (HWND_TOPMOST)
                    0,      # X位置
                    0,      # Y位置
                    0,      # 宽度
                    0,      # 高度
                    flags   # 组合标志
                )
            except Exception as e:
                print(f"[Windows API错误] {str(e)}")
                print(f"句柄类型: {type(self.winId())}, 值: {self.winId()}")

        # 强制刷新界面
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hide()
        QApplication.processEvents()
        self.show()
        self.update()

    def handle_detection(self, need_activate):
        """同步状态处理"""
        if need_activate != self.active:
            print(f"[状态变更] {'激活' if need_activate else '关闭'}水印")
            self.active = need_activate
            self.toggle_watermark(need_activate)
            self.update_tray_icon()
            
            # 额外刷新保障
            QTimer.singleShot(100, lambda: [
                self.update(),
                QApplication.processEvents()
            ])
    def update_tray_icon(self):
        """更新托盘图标"""
        icon = QStyle.SP_DialogYesButton if self.active else QStyle.SP_DialogNoButton
        self.tray.setIcon(self.style().standardIcon(icon))

    def paintEvent(self, event):
        """绘制水印（兼容性增强版）"""
        print(f"[绘制状态] Active: {self.active}, Opacity: {self.windowOpacity()}")
        if self.active or SecurityConfig.FORCE_WATERMARK:
            painter = None
            try:
                painter = QPainter(self)
                painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
                
                # 使用固定颜色
                painter.setPen(QColor(255, 50, 50, 200))
                painter.setFont(self.font)
                
                # 动态水印内容
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                watermark_lines = [
                    f"操作员：{self.user_info.get('username', '未知用户')}",
                    f"终端IP：{self.user_info.get('ip', '未知IP')}",
                    f"文档ID：DOC-{uuid.uuid4().hex[:8].upper()}",
                    f"检测时间：{timestamp}",
                    "严禁复制、拍照或外传！"
                ]
                
                # 动态布局参数
                metrics = QFontMetrics(self.font)
                line_height = metrics.height()
                screen_size = self.size()
                
                # 每5秒更新偏移量
                current_second = datetime.now().second
                if current_second % 5 == 0:
                    self.base_offset_x = random.randint(-200, 200)
                    self.base_offset_y = random.randint(-200, 200)
                
                # 优化平铺算法
                grid_size = 800
                for x in range(-grid_size, screen_size.width() + grid_size, grid_size):
                    for y in range(-grid_size, screen_size.height() + grid_size, grid_size):
                        painter.save()
                        painter.translate(
                            x + self.base_offset_x, 
                            y + self.base_offset_y
                        )
                        painter.rotate(self.angle)
                        
                        # 绘制带阴影的文本
                        shadow_color = QColor(0, 0, 0, 150)
                        for i, line in enumerate(watermark_lines):
                            # 阴影
                            painter.setPen(shadow_color)
                            painter.drawText(3, i*line_height + 3, line)
                            # 主文本
                            painter.setPen(QColor(255, 50, 50, 200))
                            painter.drawText(0, i*line_height, line)
                        
                        painter.restore()
            except Exception as e:
                print(f"[绘制错误] {traceback.format_exc()}")
            finally:
                if painter:
                    painter.end()
    # -------------------- 测试方法 --------------------
    def test_watermark(self):
        """强制显示水印60秒（调试用）"""
        print("[调试] 强制显示水印60秒")
        self.toggle_watermark(True)
        QTimer.singleShot(60000, lambda: self.toggle_watermark(False))

    # -------------------- 错误处理 --------------------
    def show_critical_error(self, title, message):
        """显示严重错误"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(title)
        msg.setText("严重错误导致程序无法继续运行")
        msg.setInformativeText(f"{message}\n请检查：\n1. 模型文件是否完整\n2. 管理员权限\n3. 系统兼容性")
        msg.exec_()
        sys.exit(1)

    # -------------------- 退出处理 --------------------
    def closeEvent(self, event):
        """关闭事件处理"""
        try:
            if self.detector_thread:
                self.detector_thread.stop()
                self.detector_thread.wait(3000)
            if os.path.exists(SecurityConfig.LOCK_FILE):
                os.remove(SecurityConfig.LOCK_FILE)
        finally:
            event.accept()

# -------------------- 主程序入口 --------------------
if __name__ == '__main__':
    # 首先初始化QApplication
    app = QApplication(sys.argv)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app.setQuitOnLastWindowClosed(False)

    # 调试信息
    print("="*40)
    print(f"[启动调试] 工作目录: {os.getcwd()}")
    print(f"[启动调试] 启动参数: {sys.argv}")
    
    # 权限检查（需要放在QApplication之后）
    if platform.system() == "Windows":
        require_admin()
        
    # 单实例检测
    checker = InstanceChecker()
    checker.check()

    # 主窗口初始化
    try:
        print("[主程序] 正在初始化主窗口...")
        window = SecurityWatermark()
        window.showFullScreen()
        print("[主程序] 窗口初始化完成")
        
        # MacOS特殊处理
        if platform.system() == "Darwin":
            window.raise_()
            window.activateWindow()

        sys.exit(app.exec_())
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
    finally:
        if os.path.exists(checker.lock_file):
            try:
                os.remove(checker.lock_file)
                print("[清理] 已移除锁文件")
            except Exception as e:
                print(f"[清理错误] {str(e)}")