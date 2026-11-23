# 代理池（爬虫学习测试用）

收集时间：2026-11-23 15:57 (Asia/Shanghai)
来源：均为公开免费代理列表（TheSpeedX/PROXY-List、monosans/proxy-list、jetkai/proxy-list、ProxyScrape、clarketm、ShiftyTR、hookzof），已做格式校验和去重。

## 文件

| 文件 | 内容 | 数量 |
|---|---|---|
| http.txt | HTTP/HTTPS 代理，格式 ip:port | 6416 |
| socks4.txt | SOCKS4 代理，格式 ip:port | 3883 |
| socks5.txt | SOCKS5 代理，格式 ip:port | 7931 |
| all_proxies.txt | 全部，带协议前缀 http:// / socks4:// / socks5:// | 18230 |
| proxies.json | 按协议分组的 JSON 版 | 18230 |
| check_proxies.py | 本地可用性检测脚本 | - |

## 重要说明

1. 免费代理不稳定：存活率通常 5%-15%，寿命以小时计。monosans 和 jetkai 的源本身会定时检测，相对优先用；正式用之前先在本地跑 check_proxies.py 过滤一遍。
2. 本次收集环境限制了直连 TCP，无法在沙箱里逐个验活，所以交付的是源站已检测 + 我去重后的全量池，验活请在本地完成（一条命令，见脚本头部）。
3. 只用于学习测试，遵守目标网站的 robots 和频率限制，不要用来绕过付费墙、批量注册或刷量。免费代理不加密，不要经它传账号密码等敏感数据。

## Python 使用示例

```python
import random, requests

proxies_list = [l.strip() for l in open("http.txt") if l.strip()]

def get_with_proxy(url):
    p = random.choice(proxies_list)
    proxy = {"http": f"http://{p}", "https": f"http://{p}"}
    return requests.get(url, proxies=proxy, timeout=10)

print(get_with_proxy("http://httpbin.org/ip").text)
```

Scrapy 里把 proxy 放进 meta 即可：
`yield scrapy.Request(url, meta={"proxy": "http://1.2.3.4:8080"})`

## 直接拉取 (Raw)

```python
import requests
# 任选一个协议文件
url = "https://raw.githubusercontent.com/lankeqya/px-pool/main/http.txt"
proxies = requests.get(url).text.splitlines()
print(len(proxies), proxies[:3])
```

- HTTP: https://raw.githubusercontent.com/lankeqya/px-pool/main/http.txt
- SOCKS4: https://raw.githubusercontent.com/lankeqya/px-pool/main/socks4.txt
- SOCKS5: https://raw.githubusercontent.com/lankeqya/px-pool/main/socks5.txt
- 全部(带协议前缀): https://raw.githubusercontent.com/lankeqya/px-pool/main/all_proxies.txt
- JSON: https://raw.githubusercontent.com/lankeqya/px-pool/main/proxies.json

## 自动验活（GitHub Actions）

本仓库带一个 Actions 工作流 `.github/workflows/update.yml`，每 6 小时自动运行一次：
重新从公开源抓取候选代理 -> 在 Actions 的机器上逐个验活（请求 http://httpbin.org/ip）->
只保留存活节点，按响应速度排序后自动提交回仓库。运行记录和每次的存活数见 STATUS.md。
也可以在仓库的 Actions 页面手动点 Run workflow 立即跑一次。
注意：首次提交后定时任务才会生效；免费代理池经这样过滤后，拉到的基本都是当时存活的，但单个节点随时可能失效，爬虫里仍建议做失败重试和自动剔除。
