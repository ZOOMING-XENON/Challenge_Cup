import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
# 读取数据
df = pd.read_csv('file_info_expanded.csv', encoding='utf-8-sig')


# 设定权重
weights = {
    'Last Modified Time': 2,  # 时间的权重
    'File Size (Bytes)': 2,    # 文件大小的权重
    'File Type Value': 0.9,      # 文件类型的权重
    'Permissions Value': 0.5     # 权限值的权重
}

# 使用 MinMaxScaler 对 File Size (Bytes) 进行归一化
scaler = MinMaxScaler()

# 归一化文件大小，文件类型值和权限值
df[['Last Modified Time Pro', 'File Size (Bytes) Pro', 'File Type Value Pro', 'Permissions Value Pro']] = scaler.fit_transform(
    df[['Last Modified Time', 'File Size (Bytes)', 'File Type Value', 'Permissions Value']])

# 计算综合得分
df['Score'] = (0 - df['Last Modified Time Pro'] * weights['Last Modified Time'] +
               df['File Size (Bytes) Pro'] * weights['File Size (Bytes)'] +
               df['File Type Value Pro'] * weights['File Type Value'] +
               df['Permissions Value Pro'] * weights['Permissions Value'])

# 设置阈值并打标签
threshold = 0.6  # 阈值，可以根据实际情况调整
df['important'] = np.where(df['Score'] > threshold, 1, 0)

# 保存结果
df.to_csv('file_info_with_importance.csv', index=False, encoding='utf-8-sig')

print(df[['File Name', 'Score', 'important']].head())
