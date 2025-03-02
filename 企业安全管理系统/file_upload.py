import os
from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField
from werkzeug.utils import secure_filename
import unicodedata

# 定义允许的文件扩展名
ALLOWED_EXTENSIONS = {'exe', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx','jpg','png','jpeg','dmg','zip'}

class CommandForm(FlaskForm):
    """定义文件上传表单"""
    exe_file = FileField('选择文件')  # 修改标签文字，因为不再限制文件类型
    submit = SubmitField('上传')

def allowed_file(filename):
    """检查文件扩展名是否合法"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def secure_chinese_filename(filename):
    """处理中文文件名"""
    # 将文件名转换为规范化的 Unicode 格式
    filename = unicodedata.normalize('NFKC', filename)
    # 获取文件扩展名
    name, ext = os.path.splitext(filename)
    # 移除不安全的字符，但保留中文字符
    safe_name = ''.join(char for char in name if char.isalnum() or char.isspace() or '\u4e00' <= char <= '\u9fff')
    # 如果文件名为空，使用默认名称
    if not safe_name:
        safe_name = 'unnamed'
    return safe_name + ext

def save_file(uploaded_file, upload_folder):
    """保存上传的文件到指定目录"""
    if uploaded_file and allowed_file(uploaded_file.filename):
        # 使用支持中文的文件名处理函数
        filename = secure_chinese_filename(uploaded_file.filename)
        filepath = os.path.join(upload_folder, filename)
        
        # 如果文件已存在，添加数字后缀
        counter = 1
        while os.path.exists(filepath):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{counter}{ext}"
            filepath = os.path.join(upload_folder, filename)
            counter += 1
            
        try:
            uploaded_file.save(filepath)# 调用文件对象的 save 方法
            return filepath
        except Exception as e:
            print(f"保存文件时出错: {str(e)}")
            return None
    return None 