import os
from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField
from werkzeug.utils import secure_filename

# 定义允许的文件扩展名
ALLOWED_EXTENSIONS = {'exe', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}

class CommandForm(FlaskForm):
    #继承了FlaskForm
    """定义文件上传表单"""
    exe_file = FileField('上传EXE文件')  # 定义一个文件字段，用于上传 EXE 文件
    submit = SubmitField('上传')  # 定义一个提交按钮，显示为"上传"

def allowed_file(filename):
    """检查文件扩展名是否合法"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    #返回一个布尔值，看这个文件有‘.'且文件的扩展名是ALLOWED_EXTENSIONS中之一

def save_file(uploaded_file, upload_folder):
    """保存上传的文件到指定目录"""
    if uploaded_file and allowed_file(uploaded_file.filename):
        filename = secure_filename(uploaded_file.filename)  # 确保文件名安全
        filepath = os.path.join(upload_folder, filename)  # 构建文件保存路径
        uploaded_file.save(filepath)  # 调用文件对象的 save 方法将文件保存到指定路径
        return filepath  # 返回文件保存路径
    return None  # 如果文件不合法，返回 None 