from mitmproxy import http
import json
import threading
import re
from urllib.parse import urlparse, urlunparse
import time

#def capture_web_info():
# 存储捕获的流量数据
captured_data = []
# 线程锁，确保文件写操作安全
file_lock = threading.Lock()
# JSON 文件路径
OUTPUT_FILE = "captured_traffic.json"
# 存储已捕获的域名集合
captured_domains = set()
# 当前用户访问的主域名
current_main_domain = None
# 存储每个 URL 的访问次数
url_access_counts = {}


def extract_main_domain(url):
    """提取主域名（如 www.gugu3.com -> gugu3.com）"""
    parsed = urlparse(url)
    domain_parts = parsed.netloc.split('.')
    if len(domain_parts) > 2:
        return '.'.join(domain_parts[-2:])  # 取最后两部分作为主域名
    return parsed.netloc


def is_browser_request(user_agent):
    """判断是否为浏览器请求"""
    browser_patterns = [
        r'Mozilla/.*Chrome/.*Safari/',
        r'Mozilla/.*Firefox/',
        r'Mozilla/.*Safari/',
        r'Mozilla/.*Edge/',
        r'Mozilla/.*Opera/'
    ]
    return any(re.search(pattern, user_agent) for pattern in browser_patterns)


def should_capture(flow: http.HTTPFlow):
    """判断是否需要捕获"""
    global current_main_domain

    # 只处理GET请求
    if flow.request.method != "GET":
        return False

    # 首次访问或没有Referer时确定主域名
    referer = flow.request.headers.get("Referer", "")
    if not referer:
        current_main_domain = extract_main_domain(flow.request.pretty_url)
        return True

    # 检查当前请求是否属于主域名
    current_domain = extract_main_domain(flow.request.pretty_url)
    return current_domain == current_main_domain


def normalize_url(url):
    """规范化 URL，移除查询参数和片段"""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, None, None, None))


def append_to_file(data):
    """将数据追加到 JSON 文件中"""
    with file_lock:
        try:
            with open(OUTPUT_FILE, "r") as f:
                existing_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing_data = []

        # 查找是否已有相同规范化 URL 的记录
        normalized_url = normalize_url(data["url"])
        domain = data["domain"]
        found = False
        for item in existing_data:
            if item["domain"] == domain:
                item["access_count"] += 1  # 更新访问次数
                found = True
                break

        # 如果没有找到，添加新记录
        if not found:
            data["url"] = normalized_url  # 存储规范化 URL
            data["access_count"] = 1
            existing_data.append(data)

        # 写回文件
        try:
            with open(OUTPUT_FILE, "w") as f:
                json.dump(existing_data, f, indent=2)
        except Exception as e:
            print(f"Error writing to file: {e}")


def request(flow: http.HTTPFlow) -> None:
    """捕获请求"""
    user_agent = flow.request.headers.get("User-Agent", "")
    if is_browser_request(user_agent) and should_capture(flow):
        full_url = flow.request.pretty_url
        main_domain = extract_main_domain(full_url)

        # 记录访问次数
        normalized_url = normalize_url(full_url)
        with file_lock:
            if normalized_url not in url_access_counts:
                url_access_counts[normalized_url] = 0
            url_access_counts[normalized_url] += 1

        request_data = {
            "type": "request",
            "domain": main_domain,
            "url": normalized_url,  # 存储规范化 URL
            "access_count": url_access_counts[normalized_url]  # 记录访问次数
        }
        captured_data.append(request_data)
        print(f"Captured Main Domain: {main_domain}, Access Count: {url_access_counts[normalized_url]}")
        append_to_file(request_data)

# 运行 mitmproxy
from mitmproxy.tools.main import mitmdump

def start_capture():
    """启动 mitmproxy 捕获流量"""
    mitmdump(["-s", __file__])


if __name__ == "__main__":
    start_capture()