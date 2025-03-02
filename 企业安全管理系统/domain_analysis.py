import json
import re
from openai import OpenAI


def ai_analysis():

    # 初始化 DeepSeek API 客户端
    client = OpenAI(api_key="sk-eb532507ee7b420cb3ea43d60a3a2e29", base_url="https://api.deepseek.com")

    # 读取 captured_traffic.json 文件
    try:
        with open("captured_traffic.json", "r") as file:
            traffic_data = json.load(file)
    except FileNotFoundError:
        print("Error: captured_traffic.json file not found.")
        exit(1)
    except json.JSONDecodeError:
        print("Error: captured_traffic.json is not a valid JSON file.")
        exit(1)

    # 检查 analyzed_data.json 文件是否存在，如果存在则读取已有数据
    try:
        with open("analyzed_data.json", "r") as file:
            analysis_results = json.load(file)
    except FileNotFoundError:
        analysis_results = []  # 如果文件不存在，初始化空列表
    except json.JSONDecodeError:
        print("Warning: analyzed_data.json is not a valid JSON file. Initializing empty list.")
        analysis_results = []

    # 用于存储已分析的域名集合
    analyzed_domains = {item["url"] for item in analysis_results}

    # 遍历每个域名并调用 DeepSeek API 进行分析
    for entry in traffic_data:
        if entry.get("type") == "request":  # 确保只处理请求类型的数据
            domain = entry.get("domain")
            access_count = entry.get("access_count")
            url = entry.get("url")
            if not domain:
                print(f"Warning: Missing 'domain' field in entry: {entry}")
                continue

            # 如果域名已经分析过，跳过
            if domain in analyzed_domains:
                print(f"Skipping already analyzed domain: {domain}")
                continue

            try:
                # 构造 API 请求内容
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user",
                         "content": f"Analyze the domain '{domain}' and provide a score between 0 and 1, where 0 means 'fully focused on work' and 1 means 'completely slacking off or dangerous web actions'."
                                    f"the score should also consider '{access_count}' and '{url}',too many visits to a website may mean danger. And the url may reveal the more specific action"
                                    f"Use the least words to describe the function of the website."
                                    f"Return the result ​**ONLY**​ as a valid JSON object, without any additional text or Markdown formatting, like this:"
                                    f"{{\"score\": 0.7, \"function\": \"watching films\",\"risk\": \"too many visits and potential payment\"}}"},
                    ],
                    stream=False
                )

                # 提取打分结果
                result = response.choices[0].message.content.strip()
                print(f"Raw API response for {domain}: {result}")

                # 清理响应中的非 JSON 字符
                result = re.sub(r"[^\{].*?\{", "{", result)  # 移除 JSON 前的额外文本
                result = re.sub(r"\}[^}].*", "}", result)  # 移除 JSON 后的额外文本

                # 解析 JSON 结果
                try:
                    data = json.loads(result)
                    score = data.get("score")
                    function = data.get("function")
                    risk = data.get("risk")
                    access_count = entry.get("access_count")

                    if score is None or function is None:
                        print(f"Error: Missing 'score' or 'function' in API response for {domain}.")
                    else:
                        # 将结果添加到列表中
                        analysis_results.append({
                            "url": domain,
                            "score": score,
                            "function": function,
                            "risk": risk,
                            "access_count": access_count  # 初始化访问次数为 1
                        })
                        analyzed_domains.add(domain)  # 将域名添加到已分析集合中

                        # 实时写入 JSON 文件
                        with open("analyzed_data.json", "w") as file:
                            json.dump(analysis_results, file, indent=4)  # 使用 indent=4 美化 JSON 格式

                        # 输出结果
                        print(f"Domain: {domain}, Score: {score}, Function: {function}, Risk: {risk}")
                except json.JSONDecodeError:
                    print(f"Error: API response for {domain} is not a valid JSON.")
            except Exception as e:
                print(f"Error calling DeepSeek API for {domain}: {e}")

    print("Analysis completed. Results saved to analyzed_data.json.")
