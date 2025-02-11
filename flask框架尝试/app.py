from flask import Flask,render_template,request,redirect
from pyasn1_modules.rfc2459 import emailAddress

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






#路由
@app.route('/')
def hello_world():  # put application's code here
    return 'Hello World!'

@app.route('/login',methods=['GET','POST'])
def login():
    #return 'Login Page'
    if request.method == 'POST':
       email_address = request.form.get('email_address')
       password = request.form.get('password')
       # 用数据库校验账号密码
       print('Receive Infomation from the web/n','email:',email_address,'/n password:',password)
       #登陆成功之后，应该跳转到管理页面
       return redirect('/admin')
    return render_template('login.html')

@app.route('/admin')
def admin():
    return render_template('admin.html',users=users) #把临时数据库信息传递到admin页面里



if __name__ == '__main__':
    app.run()
