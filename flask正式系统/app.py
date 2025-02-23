from flask import Flask,render_template,request,redirect,jsonify, url_for, send_from_directory
from datetime import datetime, timedelta
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField
from werkzeug.utils import secure_filename
import secrets, os
from file_upload import CommandForm, save_file,allowed_file # 导入文件上传模块
#模块说明save_file(uploaded_file, upload_folder):
#render_template是方便路由返回页面的
# 导入一个flask对象
#request对象可以拿到前浏览器传递给服务器的所有数据
#redirect实现网页重定向
app = Flask(__name__)
#使用flask创建一个app

#示例数据库，以后装在mysql里面
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

#登陆数据库
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
#配置文件上传的目标目录，并将该目录的路径存储到 Flask 应用的配置中。当用户上传文件时，应用会将文件保存到这个指定的目录下
#将计算得到的上传目录路径存储到 Flask 应用的配置对象中，后续代码可以通过 app.config['UPLOAD_FOLDER'] 来获取这个路径，方便进行文件保存等操作。
# 确保上传目录存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 存储任务和状态的全局变量
tasks = {}  # 格式：{ "Machine-001": {"command": "msiexec /i vscode.msi", "status": "pending"} }


#路由
@app.route('/')
def start():  # put application's code here
    return render_template('start.html')

@app.route('/login',methods=['GET','POST'])
def login():
    #return 'Login Page'
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
               #return redirect('/admin')
            # 遍历完整个列表都没有匹配的用户信息，返回登录失败
       return jsonify({'status': 'fail', 'message': '登录失败，请检查邮箱或密码'})
    return render_template('login.html')


@app.route('/admin')
def admin():
    return render_template('admin.html',users=users) #把临时数据库信息传递到admin页面里

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

@app.route('/delete',methods=['GET','POST'])
def delete():
    print(request.method)
    print(request.args)  #我们在admin里面写的<td><a href="/edit?name={{ user.name }}">edit</a></td>问好后面带的就是
    #参数，而这个request.args就是得到其中的参数
    print(request.args.get('name'))
    #再用get函数取得字典中键值对里的item

    #找到成员并删除
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

#因为客户端发送的信息是到这一个路由，所以需要写一个路由来接收信息
@app.route('/receive_data', methods=['POST'])
def receive_data():
    try:
        data = request.get_json()
        current_time = datetime.now()
        computer_id = data.get('computer_id')
        
        # 更新该 computer_id 的最新数据
        computer_data[computer_id] = {
            "active_window": data.get('active_window', '无活动窗口'),#逗号后是默认内容
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
        {'id': '001', 'source': 'IP: 192.168.1.1', 'type': '勒索病毒', 'status': '已拦截', 'timestamp': '2023-10-12 10:30'},
        {'id': '002', 'source': 'IP: 192.168.1.2', 'type': '勒索病毒', 'status': '已拦截', 'timestamp': '2023-10-12 11:00'},
        {'id': '003', 'source': 'IP: 192.168.1.3', 'type': '恶意软件', 'status': '已修复', 'timestamp': '2023-10-12 12:00'},
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


#文件上传






@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """处理文件上传的路由"""
    form = CommandForm()  # 创建表单实例，用于处理文件上传
    if form.validate_on_submit():  # 检查表单是否有效
        uploaded_file = form.exe_file.data  # 获取上传的文件
        if uploaded_file:  # 确保用户选择了文件
            filepath = save_file(uploaded_file, app.config['UPLOAD_FOLDER'])  # 调用 save_file 函数保存文件
            #app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER：将计算得到的上传目录路径存储到 Flask 应用的配置对象中，
            # 后续代码可以通过 app.config['UPLOAD_FOLDER'] 来获取这个路径，方便进行文件保存等操作
            #save_file函数会返回一个完整的文件保存路径，不光含有文件夹的名称还有文件本身的名字
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
    exe_files = os.listdir(app.config['UPLOAD_FOLDER'])  # 获取上传目录中的所有文件
    return render_template('upload_list.html', exe_files=exe_files)  # 渲染文件列表页面，并传递文件列表







    #文件部署
@app.route('/uploads/<filename>')
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


@app.errorhandler(500)
def internal_error(error):
    """处理500错误"""
    return "服务器内部错误: {}".format(error), 500  # 返回500错误信息

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')  # 添加 host='0.0.0.0' 允许外部访问
