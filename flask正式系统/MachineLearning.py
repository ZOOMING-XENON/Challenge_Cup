def MachineLearning():
    import os
    from stat import S_IRUSR, S_IWUSR, S_IXUSR
    from datetime import datetime
    import XGBoostClassifier

    # 定义文件夹路径
    folder_path = 'uploads'

    # 定义代码文件类型
    code_file_extensions = ['.py', '.js', '.java', '.cpp', '.h', '.html', '.css']


    # 获取文件信息
    def get_file_info(file_path):
        # 获取文件的最近修改时间
        last_modified_time = os.path.getmtime(file_path)
        # 获取文件的大小（字节）
        file_size = os.path.getsize(file_path)
        # 获取文件的扩展名
        file_extension = os.path.splitext(file_path)[1]

        # 判断文件类型 (代码文件)
        if file_extension in code_file_extensions:
            file_type_value = 3  # 高值代表是代码文件
        else:
            file_type_value = 1  # 普通文件的值较低

        # 获取文件权限信息
        file_stats = os.stat(file_path)
        permissions = file_stats.st_mode
        # 判断文件是否有写权限
        if permissions & S_IRUSR and permissions & S_IWUSR:
            permissions_value = 1  # 文件有读写权限
        else:
            permissions_value = 3  # 权限限制较高，设置为高值

        # 将文件的最后修改时间转换为 datetime 对象
        last_modified_datetime = datetime.fromtimestamp(last_modified_time)

        # 获取当前时间
        current_datetime = datetime.now()

        # 计算时间差
        time_difference = current_datetime - last_modified_datetime

        # 将时间差格式化为天数和小时数（可以根据需求调整）
        days = time_difference.days
        hours = time_difference.seconds / 3600  # 计算小时数

        # 将结果作为字符串返回
        time_diff_str = days * 24 + hours

        return time_diff_str, file_size, file_type_value, permissions_value


    # 遍历文件夹并获取所有文件信息
    dict2 = {}
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            last_modified_time, file_size, file_type_value, permissions_value = get_file_info(file_path)
            important = XGBoostClassifier.predict_file_importance(file, last_modified_time, file_size, file_type_value, permissions_value)
            dict2[file] = str(important)
    return dict2
if __name__ == '__main__':
    print(MachineLearning())