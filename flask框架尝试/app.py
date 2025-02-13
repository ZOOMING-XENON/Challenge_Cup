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
def start():  # put application's code here
    return render_template('start.html')

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

@app.route('/add',methods=['GET','POST'])#一定要加上,methods=['GET','POST']
# Flask 中 @app.route 装饰器默认只处理 GET 请求。也就是说，如果你不明确指定 methods 参数，
# 那么这个路由只能响应客户端发起的 GET 请求
def add():
    if request.method == 'POST':
       Name = request.form.get('Name')#request对象可以拿到前浏览器传递给服务器的所有数据
       Working_hours = request.form.get('Working_hours')
       Upload_file_numbers = request.form.get('Upload_file_numbers')
       Risky_web_visits = request.form.get('Risky_web_visits')
       print('Info: Name:',Name,'Working_hours:',Working_hours,'Upload_file_numbers:',Upload_file_numbers,'Risky_web_visits:',Risky_web_visits)
       #把新的信息添加到数据库里！！！
       users.append( {'name': Name, 'working_hours': Working_hours, 'upload_file_numbers': Upload_file_numbers, 'risky_web_visits': Risky_web_visits})
       return redirect('/admin')
    return render_template('add.html') #把临时数据库信息传递到admin页面里


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


@app.route('/edit',methods=['GET','POST'])
def edit():
    username = request.args.get('name')
    if request.method == 'POST':
        Name = request.form.get('Name')  # request对象可以拿到前浏览器传递给服务器的所有数据
        Working_hours = request.form.get('Working_hours')
        Upload_file_numbers = request.form.get('Upload_file_numbers')
        Risky_web_visits = request.form.get('Risky_web_visits')
        for user in users:
            if user['name'] == username:

                user['working_hours'] = Working_hours
                user['upload_file_numbers'] = Upload_file_numbers
                user['risky_web_visits'] = Risky_web_visits

        return redirect('/admin')#改好了返回admin

    print(username)
    for user in users:
        if user['name'] == username:#找到该用户后跳转到编辑页面并且传递该用户当前的信息
            return render_template('edit.html',user=user)#把数据传到本html里





if __name__ == '__main__':
    app.run()
