from flask import Flask,render_template,request,redirect

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





if __name__ == '__main__':
    app.run(debug=True, port=5001)  # 添加 debug=True
