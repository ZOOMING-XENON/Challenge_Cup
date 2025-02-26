import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# 读取 CSV 文件
df = pd.read_csv('file_info_expanded.csv', encoding='utf-8-sig')

# 提取需要的列
# 假设文件中的列名是：'File Name', 'Last Modified Time', 'File Size (Bytes)', 'File Type Value', 'Permissions Value'

# 提取特征：文件大小、文件类型值、权限值以及计算出的时间差
X = df[['Last Modified Time', 'File Size (Bytes)', 'File Type Value', 'Permissions Value']]

# 标准化特征
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# KMeans++ 聚类分析
kmeans = KMeans(init='k-means++', n_clusters=2, random_state=42)  # 假设聚为3类
kmeans.fit(X_scaled)
df['Cluster'] = kmeans.labels_

# 根据聚类结果为每个文件分配 0 或 1
df['important'] = df['Cluster'].map({0: 1, 1: 0})

# 使用 PCA 降维到二维
pca = PCA(n_components=2)
X_pca = pca.fit_transform(X_scaled)

# 创建新的 DataFrame 存储 PCA 降维后的数据和聚类结果
df_pca = pd.DataFrame(X_pca, columns=['PCA 1', 'PCA 2'])
df_pca['Cluster'] = df['Cluster']

# 绘制散点图
plt.figure(figsize=(8, 6))
scatter = plt.scatter(df_pca['PCA 1'], df_pca['PCA 2'], c=df_pca['Cluster'], cmap='viridis', s=50)
plt.title('KMeans++ Clustering after PCA')
plt.xlabel('PCA 1')
plt.ylabel('PCA 2')
plt.colorbar(scatter, label='Cluster')

# 显示图表
plt.show()
# 将数据保存到新的 CSV 文件
df.to_csv('file_info_with_importance.csv', index=False, encoding='utf-8-sig')

print("文件已保存到 'file_info_with_importance.csv'.")