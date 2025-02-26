from flask import Flask, render_template, request, redirect, jsonify, url_for, send_from_directory
from datetime import datetime, timedelta
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField
from werkzeug.utils import secure_filename
import secrets, os
from file_upload import CommandForm, save_file, allowed_file  # 导入文件上传模块
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import json
import shutil
from cryptography.fernet import Fernet
import tkinter as tk
from tkinter import filedialog
import atexit

# 模块说明save_file(uploaded_file, upload_folder):
# render_template是方便路由返回页面的
# 导入一个flask对象
# request对象可以拿到前浏览器传递给服务器的所有数据
# redirect实现网页重定向
app = Flask(__name__)
# 使用flask创建一个app

# 示例数据库，以后装在mysql里面
users = [
    {'name': 'Jack', 'working_hours': 10, 'upload_file_numbers': 2, 'risky_web_visits': 1},
    {'name': 'Alice', 'working_hours': 8, 'upload_file_numbers': 3, 'risky_web_visits': 0},
    {'name': 'Bob', 'working_hours': 9, 'upload_file_numbers': 1, 'risky_web_visits': 2},
    {'name': 'Eve', 'working_hours': 11, 'upload_file_numbers': 4, 'risky_web_visits': 1},
    {'name': 'Charlie', 'working_hours': 7, 'upload_file_numbers': 2, 'risky_web_visits': 0},
    {'name': 'David', 'working_hours': 10, 'upload_file_numbers': 3, 'risky_web_visits': 3},
    {'name': 'Fiona', 'working_hours': 8, 'upload_file_numbers': 1, 'risky_web_visits': 0},
    {'name': 'George', 'working_hours': 9, 'upload_file_numbers': 4, 'risky_web_visits': 1},
    {'name': 'Hannah', 'working_hours': 12, 'upload_file_numbers': 2, 'risky_web_visits': 0},
    {'name': 'Ivan', 'working_hours': 7, 'upload_file_numbers': 3, 'risky_web_visits': 2}
]

# 登陆数据库
login_data = [
    {'username': '2777150844@qq.com', 'password': '0000'},
    {'username': '1', 'password': '1'},
    {'username': None, 'password': None},
]

# 创建一个字典来存储每个 computer_id 的最新数据
computer_data = {}  # 格式: {computer_id: {active_window, wechat_files, installed_software}}

# 创建一个字典来存储每个 computer_id 的微信文件历史
wechat_files_history = {}  # 格式: {computer_id: {filename: {first_seen, last_seen}}}

app.config['SECRET_KEY'] = secrets.token_hex(16)

# 定义管理端 IP 地址
MANAGER_IP = "127.0.0.1:5000"  # 替换为实际的管理端 IP 地址

# 配置上传路径
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')  # 使用绝对路径，生成的UPLOAD_FOLDER是个路径
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 配置文件上传的目标目录，并将该目录的路径存储到 Flask 应用的配置中。当用户上传文件时，应用会将文件保存到这个指定的目录下
# 将计算得到的上传目录路径存储到 Flask 应用的配置对象中，后续代码可以通过 app.config['UPLOAD_FOLDER'] 来获取这个路径，方便进行文件保存等操作。
# 确保上传目录存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 存储任务和状态的全局变量
tasks = {}  # 格式：{ "Machine-001": {"command": "msiexec /i vscode.msi", "status": "pending"} }

# 存储备份计划的列表
backup_schedules = []

# 初始化调度器
scheduler = BackgroundScheduler()
scheduler.start()

# 确保在应用退出时正确关闭调度器
atexit.register(lambda: scheduler.shutdown())

# 在文件开头添加或修改 backup_records 的定义
backup_records = []  # 或者从数据库中加载


def perform_scheduled_backup(schedule_id):
    """执行计划备份"""
    schedule = next((s for s in backup_schedules if s['id'] == schedule_id), None)
    if not schedule:
        return

    try:
        source_dir = app.config['UPLOAD_FOLDER']

        # 根据备份类型确定要备份的文件
        if schedule['backup_type'] == 'full':
            # 获取所有文件
            files_to_backup = []
            for filename in os.listdir(source_dir):
                file_path = os.path.join(source_dir, filename)
                if os.path.isfile(file_path):
                    files_to_backup.append(filename)
        else:
            files_to_backup = schedule['selected_files']

        # 执行备份
        backup_path = schedule['path']
        successful_files = []
        failed_files = []

        # 确保备份目录存在
        os.makedirs(backup_path, exist_ok=True)

        for file in files_to_backup:
            try:
                source_path = os.path.join(source_dir, file)
                target_path = os.path.join(backup_path, file)

                # 复制文件
                if os.path.exists(source_path):
                    shutil.copy2(source_path, target_path)
                    successful_files.append({
                        'name': file,
                        'backup_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'size': os.path.getsize(target_path)
                    })
                else:
                    failed_files.append({'file': file, 'error': '源文件不存在'})
            except Exception as e:
                failed_files.append({'file': file, 'error': str(e)})

        # 更新备份记录
        backup_record = {
            'id': len(backup_records) + 1,
            'schedule_id': schedule_id,
            'backup_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'success' if not failed_files else 'partial',
            'successful_files': successful_files,
            'failed_files': failed_files,
            'path': backup_path
        }

        backup_records.append(backup_record)

        # 更新计划的最后备份时间
        schedule['last_backup'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        schedule['last_status'] = backup_record['status']

    except Exception as e:
        print(f"计划备份失败: {str(e)}")


def encrypt_backup(file_path, key):
    f = Fernet(key)
    with open(file_path, 'rb') as file:
        file_data = file.read()
    encrypted_data = f.encrypt(file_data)
    with open(file_path + '.encrypted', 'wb') as file:
        file.write(encrypted_data)


# 路由
@app.route('/')
def start():  # put application's code here
    return render_template('start.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    # return 'Login Page'
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        print(username, password)
        # 用数据库校验账号密码
        for user in login_data:
            if user['username'] == username and user['password'] == password:
                print("true")
                # 登陆成功之后，应该跳转到管理页面
                return jsonify({'status': 'success', 'redirect': '/admin'})
                # return redirect('/admin')
            # 遍历完整个列表都没有匹配的用户信息，返回登录失败
        return jsonify({'status': 'fail', 'message': '登录失败，请检查邮箱或密码'})
    return render_template('login.html')


@app.route('/admin')
def admin():
    return render_template('admin.html', users=users)  # 把临时数据库信息传递到admin页面里


@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        name = request.form.get('name')
        working_hours = int(request.form.get('working_hours', 0))
        upload_file_numbers = int(request.form.get('upload_file_numbers', 0))
        risky_web_visits = int(request.form.get('risky_web_visits', 0))

        # 添加数据到数据库
        users.append({
            'name': name,
            'working_hours': working_hours,
            'upload_file_numbers': upload_file_numbers,
            'risky_web_visits': risky_web_visits
        })

        return redirect('/admin')
    return render_template('add.html')


@app.route('/delete', methods=['GET', 'POST'])
def delete():
    print(request.method)
    print(request.args)  # 我们在admin里面写的<td><a href="/edit?name={{ user.name }}">edit</a></td>问好后面带的就是
    # 参数，而这个request.args就是得到其中的参数
    print(request.args.get('name'))
    # 再用get函数取得字典中键值对里的item

    # 找到成员并删除
    for user in users:
        if user['name'] == request.args.get('name'):
            users.remove(user)
    return redirect('/admin')


@app.route('/edit', methods=['GET', 'POST'])
def edit():
    if request.method == 'POST':
        original_name = request.form.get('original_name')
        name = request.form.get('name')
        working_hours = int(request.form.get('working_hours', 0))
        upload_file_numbers = int(request.form.get('upload_file_numbers', 0))
        risky_web_visits = int(request.form.get('risky_web_visits', 0))

        # 更新数据库中的记录
        for user in users:
            if user['name'] == original_name:
                user['name'] = name
                user['working_hours'] = working_hours
                user['upload_file_numbers'] = upload_file_numbers
                user['risky_web_visits'] = risky_web_visits
                break

        return redirect('/admin')
    else:
        name = request.args.get('name')
        for user in users:
            if user['name'] == name:
                return render_template('edit.html', user=user)
        return redirect('/admin')  # 如果找不到用户则返回主页


@app.route('/overview')
def overview():
    # 计算统计数据
    total_users = len(users)
    avg_working_hours = sum(user['working_hours'] for user in users) / total_users
    total_uploads = sum(user['upload_file_numbers'] for user in users)
    total_risks = sum(user['risky_web_visits'] for user in users)

    # 准备图表数据
    usernames = [user['name'] for user in users]
    working_hours_data = [user['working_hours'] for user in users]
    risk_data = [user['risky_web_visits'] for user in users]

    return render_template('overview.html',
                           total_users=total_users,
                           avg_working_hours=avg_working_hours,
                           total_uploads=total_uploads,
                           total_risks=total_risks,
                           usernames=usernames,
                           working_hours_data=working_hours_data,
                           risk_data=risk_data)


# 因为客户端发送的信息是到这一个路由，所以需要写一个路由来接收信息
@app.route('/receive_data', methods=['POST'])
def receive_data():
    try:
        data = request.get_json()
        current_time = datetime.now()
        computer_id = data.get('computer_id')

        # 更新该 computer_id 的最新数据
        computer_data[computer_id] = {
            "active_window": data.get('active_window', '无活动窗口'),  # 逗号后是默认内容
            "wechat_files": data.get('wechat_files', []),
            "installed_software": data.get('installed_software', [])
        }

        # 更新该 computer_id 的微信文件历史记录
        if computer_id not in wechat_files_history:
            wechat_files_history[computer_id] = {}

        for file in data.get('wechat_files', []):
            if file not in wechat_files_history[computer_id]:
                wechat_files_history[computer_id][file] = {
                    "first_seen": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_seen": current_time.strftime("%Y-%m-%d %H:%M:%S")
                }
            else:
                wechat_files_history[computer_id][file]["last_seen"] = current_time.strftime("%Y-%m-%d %H:%M:%S")

        # 清理24小时前的记录
        cutoff_time = current_time - timedelta(hours=24)
        for cid in wechat_files_history:
            wechat_files_history[cid] = {
                k: v for k, v in wechat_files_history[cid].items()
                if datetime.strptime(v["last_seen"], "%Y-%m-%d %H:%M:%S") > cutoff_time
            }

        return jsonify({"status": "success", "message": "数据接收成功"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/get_latest_data')
def get_latest_data():
    return jsonify({
        "computers": computer_data,
        "wechat_files_history": wechat_files_history
    })


@app.route('/monitor')
def monitor():
    return render_template('monitor.html')


@app.route('/ransomware')
def ransomware():
    # 假数据：这些数据可以根据实际情况从数据库中提取或计算
    intercepted_attacks = 152  # 已拦截的勒索攻击次数
    restored_files = 120  # 已恢复的文件数量
    protection_status = "启用"  # 防护状态
    threats_detected = 5  # 检测到的潜在威胁

    # 假数据：防护事件（一个列表，包含事件的详细信息）
    protection_events = [
        {'id': '001', 'source': 'IP: 192.168.1.1', 'type': '勒索病毒', 'status': '已拦截',
         'timestamp': '2023-10-12 10:30'},
        {'id': '002', 'source': 'IP: 192.168.1.2', 'type': '勒索病毒', 'status': '已拦截',
         'timestamp': '2023-10-12 11:00'},
        {'id': '003', 'source': 'IP: 192.168.1.3', 'type': '恶意软件', 'status': '已修复',
         'timestamp': '2023-10-12 12:00'},
    ]

    # 假数据：勒索攻击趋势图的数据（每月勒索攻击次数）
    ransomware_attack_data = [20, 35, 50, 40, 60, 70]  # 假设每月的勒索攻击次数
    attack_dates = ['2023-01', '2023-02', '2023-03', '2023-04', '2023-05', '2023-06']  # 对应的日期

    # 渲染页面，传递假数据
    return render_template('ransomware.html',
                           intercepted_attacks=intercepted_attacks,
                           restored_files=restored_files,
                           protection_status=protection_status,
                           threats_detected=threats_detected,
                           protection_events=protection_events,
                           ransomware_attack_data=ransomware_attack_data,
                           attack_dates=attack_dates)


# 文件上传
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """处理文件上传的路由"""
    form = CommandForm()  # 创建表单实例，用于处理文件上传
    if form.validate_on_submit():  # 检查表单是否有效
        uploaded_file = form.exe_file.data  # 获取上传的文件
        if uploaded_file:  # 确保用户选择了文件
            filepath = save_file(uploaded_file, app.config['UPLOAD_FOLDER'])  # 调用 save_file 函数保存文件
            # app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER：将计算得到的上传目录路径存储到 Flask 应用的配置对象中，
            # 后续代码可以通过 app.config['UPLOAD_FOLDER'] 来获取这个路径，方便进行文件保存等操作
            # save_file函数会返回一个完整的文件保存路径，不光含有文件夹的名称还有文件本身的名字
            if filepath:  # 如果文件成功保存
                print(f"文件已保存到: {filepath}")  # 打印文件保存路径
                return redirect('/upload')  # 上传成功后重定向到上传页面

    # 获取已上传的文件列表
    uploaded_files_list = os.listdir(app.config['UPLOAD_FOLDER'])  # 获取上传目录中的所有文件
    return render_template('upload.html', form=form, uploaded_files_list=uploaded_files_list)  # 渲染上传页面，并传递表单和文件列表


@app.route('/success')
def success():
    """上传成功的路由"""
    return "文件上传成功！"  # 返回成功消息


@app.route('/upload_list')
def upload_list():
    """显示上传的文件列表"""
    uploaded_files_list = os.listdir(app.config['UPLOAD_FOLDER'])  # 获取上传目录中的所有文件
    return render_template('upload_list.html', uploaded_files_list=uploaded_files_list)  # 渲染文件列表页面，并传递文件列表

    # 文件部署


@app.errorhandler(500)
def internal_error(error):
    """处理500错误"""
    return "服务器内部错误: {}".format(error), 500  # 返回500错误信息


@app.route('/get_upload_files')
def get_upload_files():
    """获取上传文件夹中的文件列表"""
    try:
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        return jsonify({
            'status': 'success',
            'files': files
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/download_file/<filename>')
def download_file(filename):
    """处理文件下载请求"""
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/backup')
def backup():
    # 获取最近的备份记录
    sorted_records = sorted(backup_records,
                            key=lambda x: x['backup_time'],
                            reverse=True)

    return render_template('backup.html',
                           backup_records=sorted_records)


@app.route('/backup_details/<int:backup_id>')
def backup_details(backup_id):
    # 查找对应的备份记录
    backup_record = next((record for record in backup_records if record['id'] == backup_id), None)

    if backup_record is None:
        return redirect('/backup')

    # 获取备份文件的详细信息
    files_info = []
    if 'path' in backup_record:
        backup_path = backup_record['path']
        try:
            for file in os.listdir(backup_path):
                file_path = os.path.join(backup_path, file)
                if os.path.isfile(file_path):
                    file_info = {
                        'name': file,
                        'size': os.path.getsize(file_path),
                        'modified_time': datetime.fromtimestamp(
                            os.path.getmtime(file_path)
                        ).strftime('%Y-%m-%d %H:%M:%S')
                    }
                    files_info.append(file_info)
        except Exception as e:
            print(f"Error reading backup directory: {str(e)}")

    return render_template('backup_details.html',
                           backup_record=backup_record,
                           files_info=files_info)
import AI_analysis
@app.route('/backup_now')
def backup_now():
    """显示备份文件选择页面"""
    # 获取上传目录中的所有文件及其信息
    uploaded_files_list = []
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.isfile(file_path):
            file_stat = os.stat(file_path)
            # 将文件大小转换为人类可读格式
            size = file_stat.st_size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"

            uploaded_files_list.append({
                'name': filename,
                'size': size_str,
                'upload_time': datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    return render_template('backup_now.html',
                           uploaded_files_list=uploaded_files_list)
@app.route('/ai_recommend', methods=['GET'])
def ai_recommend():
    from MachineLearning import MachineLearning
    try:
        # 执行AI分析，如果需要的话调用 analyze_files 来进行分析
        # analyze_files()  # 如果你有一个需要运行的函数来生成推荐结果

        # 假设 ai_recommendations 是 AI 分析得到的字典
        ai_recommendations = MachineLearning()
        return jsonify(ai_recommendations)  # 返回AI推荐的字典
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/ai_recommend2', methods=['GET']) #处理DeepSeek的按钮
def ai_recommend2():
    from AI_analysis import AI_analysis
    try:
        # 执行AI分析，如果需要的话调用 analyze_files 来进行分析
        # analyze_files()  # 如果你有一个需要运行的函数来生成推荐结果

        # 假设 ai_recommendations 是 AI 分析得到的字典
        ai_recommendations = AI_analysis()
        return jsonify(ai_recommendations)  # 返回AI推荐的字典
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 使用缓存存储已验证的路径状态
path_status_cache = {}


def check_path_availability(path):
    """检查路径是否可用（使用缓存）"""
    # 检查缓存
    if path in path_status_cache:
        # 如果缓存时间不超过5分钟，直接返回缓存的结果
        cache_time, status = path_status_cache[path]
        if (datetime.now() - cache_time).total_seconds() < 300:  # 5分钟缓存
            return status

    try:
        path_obj = Path(path)
        # 只检查路径是否存在，不主动创建
        is_available = path_obj.exists() and os.access(path, os.W_OK)
        status = {'available': is_available, 'error': None}
    except Exception as e:
        status = {'available': False, 'error': str(e)}

    # 更新缓存
    path_status_cache[path] = (datetime.now(), status)
    return status


# 简化备份路径的处理
def get_default_backup_paths():
    """获取默认的备份路径选项"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        paths = [
            {
                'name': '默认备份目录',
                'path': os.path.join(base_dir, 'backups')
            },
            {
                'name': '系统文档',
                'path': os.path.expanduser('~/Documents')
            },
            {
                'name': '下载目录',
                'path': os.path.expanduser('~/Downloads')
            },
            {
                'name': '桌面',
                'path': os.path.expanduser('~/Desktop')
            }
        ]

        # 确保所有路径存在
        for path_info in paths:
            os.makedirs(path_info['path'], exist_ok=True)

        return paths
    except Exception as e:
        print(f"获取默认备份路径时出错: {str(e)}")
        return []


@app.route('/get_backup_locations')
def get_backup_locations():
    """获取可用的备份位置"""
    try:
        locations = get_default_backup_paths()
        return jsonify({
            'status': 'success',
            'locations': locations
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/verify_backup_path', methods=['POST'])
def verify_backup_path():
    """验证备份路径（仅在实际需要时创建目录）"""
    try:
        path = request.json.get('path')
        if not path:
            raise ValueError("路径不能为空")

        path_obj = Path(path)

        # 如果路径不存在，尝试创建
        if not path_obj.exists():
            try:
                path_obj.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'无法创建目录: {str(e)}'
                }), 400

        # 验证写入权限
        if not os.access(path, os.W_OK):
            return jsonify({
                'status': 'error',
                'message': '没有写入权限'
            }), 400

        return jsonify({
            'status': 'success',
            'message': '路径可用'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/perform_backup', methods=['POST'])
def perform_backup():
    """执行实际的备份操作"""
    try:
        data = request.get_json()
        selected_files = data.get('selected_files', [])
        backup_path = data.get('backup_path')

        if not selected_files:
            raise ValueError("未选择任何文件")

        if not backup_path:
            raise ValueError("未选择备份位置")

        # 验证并规范化备份路径
        backup_path = os.path.abspath(backup_path)
        backup_dir = Path(backup_path)

        # 验证路径是否合法且可写
        try:
            if not backup_dir.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ValueError(f"备份路径无效或没有写入权限: {str(e)}")

        # 执行文件备份
        successful_files = []
        failed_files = []
        backed_up_files = []  # 记录成功备份的文件详情

        for file in selected_files:
            try:
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], file)
                target_path = os.path.join(backup_path, file)

                # 复制文件
                shutil.copy2(source_path, target_path)

                # 记录文件信息
                file_stat = os.stat(target_path)
                backed_up_files.append({
                    'name': file,
                    'size': file_stat.st_size,
                    'modified_time': datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    'source_path': source_path,
                    'target_path': target_path
                })

                successful_files.append(file)
            except Exception as e:
                failed_files.append({'file': file, 'error': str(e)})

        # 记录备份历史
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = 'success' if not failed_files else 'partial'

        backup_record = {
            'id': len(backup_records) + 1,
            'backup_time': current_time,
            'status': status,
            'path': backup_path,
            'source_path': app.config['UPLOAD_FOLDER'],
            'files': backed_up_files,  # 添加文件详情
            'failed_files': failed_files  # 添加失败文件信息
        }

        backup_records.append(backup_record)

        return jsonify({
            'status': status,
            'message': '备份完成' if status == 'success' else f'部分文件备份失败 ({len(failed_files)} 个错误)',
            'successful_files': successful_files,
            'failed_files': failed_files,
            'backup_path': backup_path
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/backup_schedules')
def backup_schedules_page():
    """显示备份计划页面"""
    print("当前备份计划列表:", backup_schedules)  # 添加调试日志

    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_backup_path = os.path.join(base_dir, 'static', 'backups')

    # 确保本地备份目录存在
    os.makedirs(local_backup_path, exist_ok=True)

    return render_template(
        'backup_schedules.html',
        schedules=backup_schedules,
        local_backup_path=local_backup_path,
        os=os  # 传递os模块以在模板中使用
    )


@app.route('/add_backup_schedule', methods=['POST'])
def add_backup_schedule():
    try:
        data = request.get_json()

        # 获取表单数据
        name = data.get('name')
        backup_type = data.get('backupType')
        frequency = data.get('frequency')
        backup_time = data.get('time')
        backup_path = data.get('path')

        # 验证必填字段
        if not all([name, backup_type, frequency, backup_time, backup_path]):
            return jsonify({
                'status': 'error',
                'message': '请填写所有必填字段'
            }), 400

        # 如果是全部备份，获取所有文件
        if backup_type == 'full':
            selected_files = []
            for filename in os.listdir(app.config['UPLOAD_FOLDER']):
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.isfile(file_path):
                    selected_files.append(filename)
        else:
            selected_files = data.get('selectedFiles', [])
            # 如果是选择性备份，确保已选择文件
            if not selected_files:
                return jsonify({
                    'status': 'error',
                    'message': '请选择要备份的文件'
                }), 400

        # 创建新的备份计划
        new_schedule = {
            'id': len(backup_schedules) + 1,
            'name': name,
            'backup_type': backup_type,
            'frequency': frequency,
            'time': backup_time,
            'path': backup_path,
            'selected_files': selected_files,
            'status': 'enabled',
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 将新计划添加到列表中
        backup_schedules.append(new_schedule)

        # 如果计划是启用状态，创建定时任务
        if new_schedule['status'] == 'enabled':
            job_id = f"backup_schedule_{new_schedule['id']}"
            hour, minute = backup_time.split(':')

            # 根据频率创建不同的触发器
            if frequency == 'daily':
                trigger = CronTrigger(hour=hour, minute=minute)
            elif frequency == 'weekly':
                trigger = CronTrigger(day_of_week='mon-sun', hour=hour, minute=minute)
            else:  # monthly
                trigger = CronTrigger(day=1, hour=hour, minute=minute)

            # 添加定时任务
            scheduler.add_job(
                perform_scheduled_backup,
                trigger=trigger,
                args=[new_schedule['id']],
                id=job_id
            )

        return jsonify({
            'status': 'success',
            'message': '备份计划创建成功',
            'schedule': new_schedule
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/toggle_backup_schedule', methods=['POST'])
def toggle_backup_schedule():
    """切换备份计划的状态"""
    try:
        data = request.json
        schedule_id = int(data['id'])
        new_status = data['status']

        # 查找要更新的计划
        schedule = next((s for s in backup_schedules if s['id'] == schedule_id), None)
        if not schedule:
            raise ValueError("计划不存在")

        # 更新计划状态
        schedule['status'] = new_status

        # 处理调度任务
        job_id = f"backup_schedule_{schedule_id}"
        if new_status == 'enabled':
            # 如果启用，创建或更新调度任务
            if schedule['frequency'] == 'daily':
                hour, minute = schedule['time'].split(':')
                trigger = CronTrigger(hour=hour, minute=minute)
            elif schedule['frequency'] == 'weekly':
                hour, minute = schedule['time'].split(':')
                trigger = CronTrigger(
                    day_of_week=','.join(map(str, schedule['days'])),
                    hour=hour,
                    minute=minute
                )
            else:  # monthly
                hour, minute = schedule['time'].split(':')
                trigger = CronTrigger(day=1, hour=hour, minute=minute)

            # 移除现有任务（如果存在）
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

            # 添加新任务
            scheduler.add_job(
                perform_scheduled_backup,
                trigger=trigger,
                args=[schedule_id],
                id=job_id
            )
        else:
            # 如果禁用，移除调度任务
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

        return jsonify({
            'status': 'success',
            'message': '状态更新成功'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/update_backup_schedule', methods=['POST'])
def update_backup_schedule():
    """更新备份计划"""
    try:
        data = request.json
        schedule_id = int(data['id'])

        # 查找要更新的计划
        schedule = next((s for s in backup_schedules if s['id'] == schedule_id), None)
        if not schedule:
            raise ValueError("计划不存在")

        # 获取更新数据
        backup_type = data.get('backup_type', 'full')

        # 根据备份类型处理文件列表
        if backup_type == 'full':
            # 获取所有文件
            selected_files = []
            for filename in os.listdir(app.config['UPLOAD_FOLDER']):
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.isfile(file_path):
                    selected_files.append(filename)
        else:
            selected_files = data.get('selected_files', [])
            if not selected_files:
                return jsonify({
                    'status': 'error',
                    'message': '选择性备份时必须选择至少一个文件'
                }), 400

        # 更新计划信息
        schedule.update({
            'name': data['name'],
            'frequency': data['frequency'],
            'time': data['time'],
            'path': data['path'],
            'backup_type': backup_type,
            'selected_files': selected_files,
            'status': data.get('status', 'enabled')
        })

        # 更新调度器中的任务
        job_id = f"backup_schedule_{schedule_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        # 如果计划是启用状态，创建新的触发器
        if schedule['status'] == 'enabled':
            hour, minute = schedule['time'].split(':')

            # 根据频率创建不同的触发器
            if schedule['frequency'] == 'daily':
                trigger = CronTrigger(hour=hour, minute=minute)
            elif schedule['frequency'] == 'weekly':
                trigger = CronTrigger(day_of_week='mon-sun', hour=hour, minute=minute)
            else:  # monthly
                trigger = CronTrigger(day=1, hour=hour, minute=minute)

            # 添加新的任务
            scheduler.add_job(
                perform_scheduled_backup,
                trigger=trigger,
                args=[schedule_id],
                id=job_id
            )

        return jsonify({
            'status': 'success',
            'message': '计划更新成功',
            'schedule': schedule
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# 在应用启动时创建必要的目录
def init_backup_dirs():
    """初始化备份目录"""
    try:
        # 确保static/backups目录存在
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        print(f"备份目录已创建: {backup_dir}")
    except Exception as e:
        print(f"Warning: 无法创建备份目录: {str(e)}")


# 在应用启动时调用初始化函数
init_backup_dirs()


@app.route('/list_upload_files', methods=['GET'])
def list_upload_files():
    try:
        # 获取 uploads 文件夹的路径
        upload_dir = os.path.join(app.root_path, 'uploads')

        # 确保文件夹存在
        if not os.path.exists(upload_dir):
            return jsonify({
                'status': 'error',
                'message': '上传文件夹不存在'
            }), 404

        files = []
        # 遍历文件夹中的所有文件
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            if os.path.isfile(file_path):  # 确保是文件而不是文件夹
                # 获取文件信息
                stat = os.stat(file_path)
                files.append({
                    'name': filename,
                    'path': filename,  # 只存储文件名，不包含完整路径
                    'size': stat.st_size,
                    'upload_time': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })

        return jsonify({
            'status': 'success',
            'files': files
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/open_path_selector', methods=['POST'])
def open_path_selector():
    try:
        # 创建一个隐藏的 tkinter 窗口
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口

        # 打开文件夹选择对话框
        selected_path = filedialog.askdirectory()

        if selected_path:
            return jsonify({
                'status': 'success',
                'path': selected_path
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '未选择路径'
            })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/delete_backup_schedule', methods=['POST'])
def delete_backup_schedule():
    """删除备份计划"""
    try:
        data = request.json
        schedule_id = int(data['id'])

        # 查找并删除计划
        schedule = next((s for s in backup_schedules if s['id'] == schedule_id), None)
        if not schedule:
            raise ValueError("计划不存在")

        # 从列表中移除计划
        backup_schedules.remove(schedule)

        # 从调度器中移除任务
        job_id = f"backup_schedule_{schedule_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        return jsonify({
            'status': 'success',
            'message': '备份计划已删除'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/get_backup_history/<int:schedule_id>')
def get_backup_history(schedule_id):
    """获取特定备份计划的历史记录"""
    try:
        # 从备份记录中筛选出属于该计划的记录
        history = [
            record for record in backup_records
            if record.get('schedule_id') == schedule_id
        ]

        return jsonify({
            'status': 'success',
            'history': history
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/get_backup_files/<int:schedule_id>')
def get_backup_files(schedule_id):
    try:
        # 查找对应的备份计划
        schedule = next((s for s in backup_schedules if s['id'] == schedule_id), None)
        if not schedule:
            return jsonify({'status': 'error', 'message': '找不到备份计划'}), 404

        # 获取源文件夹中的文件信息
        source_dir = app.config['UPLOAD_FOLDER']
        files = []

        # 获取计划中的文件列表
        if schedule['backup_type'] == 'full':
            file_list = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f))]
        else:
            file_list = schedule['selected_files']

        # 获取每个文件的详细信息
        for filename in file_list:
            file_path = os.path.join(source_dir, filename)
            if os.path.exists(file_path):
                file_stat = os.stat(file_path)
                files.append({
                    'name': filename,
                    'size': file_stat.st_size,  # 文件大小（字节）
                    'modified_time': datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    'status': '已备份'  # 默认状态
                })
                # 这里有问题不知道是不是字体问题

                # 检查备份文件是否存在
                backup_file_path = os.path.join(schedule['path'], filename)
                if os.path.exists(backup_file_path):
                    backup_stat = os.stat(backup_file_path)
                    files[-1].update({
                        'backup_size': backup_stat.st_size,
                        'backup_time': datetime.fromtimestamp(backup_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        'status': '已备份'
                    })

        return jsonify({
            'status': 'success',
            'files': files,
            'schedule': schedule
        })
    except Exception as e:
        print(f"获取备份文件列表错误: {str(e)}")  # 添加错误日志
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')  # 添加 host='0.0.0.0' 允许外部访问

'''@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """提供已上传文件的下载链接"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)  # 从指定目录发送文件，允许用户下载


@app.route('/report', methods=['POST'])
def handle_report():
    """接收代理的状态报告"""
    data = request.json
    agent_id = data["agent_id"]
    tasks[agent_id]["status"] = data["status"]
    return jsonify(success=True)

@app.route('/get_task')
def get_task():
    """代理请求任务"""
    agent_id = request.args.get("agent_id")
    if agent_id in tasks:
        return jsonify({"action": "install", "command": tasks[agent_id]["command"]})
    else:
        return jsonify({"action": "wait"})

@app.route('/get_exe_list')
def get_exe_list():
    """获取上传文件夹中的EXE文件列表"""
    exe_files = []
    shared_folder = app.config['UPLOAD_FOLDER']#之前就配置好的上传路径
    for filename in os.listdir(shared_folder):
        if filename.endswith('.exe'):
            exe_files.append(filename)
    return jsonify(exe_files)

@app.route('/deploy', methods=['POST'])
def handle_deploy():
    files = request.form.getlist('files')  # 前端传入的EXE文件名列表
    ips = request.form.get('ips').split(',')  # 目标机器IP列表

    for file in files:
        install_command = f"\\\\{MANAGER_IP}\\shared\\{file} /S"
        for ip in ips:
            agent_id = f"Machine-{ip}"
            tasks[agent_id] = {
                "command": install_command,
                "status": "pending"
            }
    return jsonify(success=True)


'''