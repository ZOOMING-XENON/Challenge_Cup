import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

# 读取原始 CSV 文件
df = pd.read_csv('file_info.csv', encoding='utf-8-sig')

# 设置生成新数据的数量（扩充的倍数）
num_new_records = 200

# 获取当前时间，用于生成 Last Modified Time
current_time = datetime.now()

# 创建一个空的列表，用于存放新的数据
new_data = []

# 循环生成新的数据
for _ in range(num_new_records):
    # 随机选择原始数据中的一行作为基础数据
    original_row = df.sample(n=1).iloc[0]

    # 获取原始数据的各列值
    last_modified_time = original_row['Last Modified Time']
    file_size = original_row['File Size (Bytes)']
    file_type_value = original_row['File Type Value']
    permissions_value = original_row['Permissions Value']

    # 生成新的 Last Modified Time (越小，即时间越早)
    time_diff = random.randint(1, 10)  # 随机选择1到10天的时间差
    new_last_modified_time = last_modified_time - time_diff*24
    if new_last_modified_time < 0: new_last_modified_time = 0

    # 生成新的 File Size (Bytes) (越大)
    new_file_size = file_size * random.uniform(1.5, 3.0)  # 原文件大小的1.5到3倍

    # 生成新的 File Type Value (只能为1或10)
    new_file_type_value = random.choice([1, 3])  # 从1或10中随机选择

    # 生成新的 Permissions Value (只能为1或10)
    new_permissions_value = random.choice([1, 3])  # 从1或10中随机选择

    # 将新数据添加到 new_data 列表
    new_data.append(
        [original_row['File Name'], new_last_modified_time, new_file_size, new_file_type_value, new_permissions_value])

# 将新数据转换为 DataFrame
new_df = pd.DataFrame(new_data, columns=['File Name', 'Last Modified Time', 'File Size (Bytes)', 'File Type Value',
                                         'Permissions Value'])

# 将新的数据添加到原始 DataFrame 中
df_expanded = pd.concat([df, new_df], ignore_index=True)

# 保存新的 DataFrame 到新的 CSV 文件
df_expanded.to_csv('file_info_expanded.csv', index=False, encoding='utf-8-sig')

print("数据扩展完成，已保存到 'file_info_expanded.csv'.")
