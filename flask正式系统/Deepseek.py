def Deepseek():
    import os
    from ollama import Client

    # 获取文件夹中的所有文件名
    folder_path = 'uploads'  # 文件夹路径
    file_names = os.listdir(folder_path)  # 获取文件夹中的文件名列表

    client = Client(
        host='http://localhost:11434',  # 本地模型服务地址
        headers={'x-some-header': 'some-value'}
    )


    def predict_backup(file_name):
        # 向模型发送文件名并获取预测结果
        response = client.chat(
            model='deepseek-r1:1.5b',
            messages=[{
                'role': 'user',
                'content': f'我是一家科技公司，我需要备份的文件类型诸如源代码与开发文件、数据库文件、配置文件、合同与法律文件、财务与会计文件等。请你根据我给的文件名判断一下是否需要备份，我需要你只输出0（不需要备份）或1（需要备份），不要输出其他任何文本，文件名: {file_name}',
            },]
        )

        # 提取模型返回的内容并返回
        a_str = str(response['message']['content'])
        return a_str[-1]

    dict1 = {}
    # 批量处理文件夹中的文件
    for file_name in file_names:
        file_path = os.path.join(folder_path, file_name)
        prediction = predict_backup(file_name)
        if prediction != "1" and prediction != "0": prediction = "0"
        dict1[file_name] = prediction
    return dict1
if __name__ == '__main__':
    print(Deepseek())