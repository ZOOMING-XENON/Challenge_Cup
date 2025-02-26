import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# 读取 CSV 文件并进行数据预处理
df = pd.read_csv('file_info_with_importance.csv', encoding='utf-8-sig')
# 选择特征列和目标列
X = df[['Last Modified Time', 'File Size (Bytes)', 'File Type Value', 'Permissions Value']]
y = df['important']

# 拆分数据集为训练集和测试集
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# XGBoost 分类器
model = xgb.XGBClassifier(objective='binary:logistic', random_state=42, eval_metric='logloss')

# 训练模型
model.fit(X_train, y_train)

""""
# 评估模型
y_pred = model.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)
print(f'Accuracy: {accuracy * 100:.2f}%')

# 打印特征重要性（可选）
import matplotlib.pyplot as plt
xgb.plot_importance(model, importance_type='weight')
plt.show()
"""
# 提供用户输入特征值进行预测
def predict_file_importance(file_name, last_modified_time, file_size, file_type_value, permissions_value):
    """
    根据输入的特征值预测文件的重要性（important）。
    """
    # 准备预测输入数据
    input_data = np.array([[last_modified_time, file_size, file_type_value, permissions_value]])

    # 使用训练好的模型进行预测
    prediction = model.predict(input_data)
    prediction_proba = model.predict_proba(input_data)
    return prediction[0]
    """
    # 输出预测结果
    result = 'Important' if prediction[0] == 1 else 'Not Important'
    print(f"Prediction: {result}")
    print(f"Prediction Probability: {prediction_proba[0][1]:.4f}")"""


