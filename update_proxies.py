#!/usr/bin/env python3
"""
在 GitHub Actions 里运行：重新抓取公开代理 -> 逐个验活 -> 只保留存活的 -> 按延迟排序写回仓库。
本地沙箱直连受限测不了，但 Actions 的 runner 可以直连，所以验活放在这里做。

安全阀：某个协议验活后存活数 < MIN_KEEP 时，不覆盖该协议的旧文件，避免检测服务
（如 httpbin）临时故障时把池子清空。
"""
import concurrent.futures
import json
import re
import time
from datetime import datetime, timezone

import requests

TEST_URL = "http://httpbin.org/ip"   # 验活目标：能完整返回 JSON 才算活
TIMEOUT = 6                          # 单个代理超时（秒）
WORKERS = 120                        # 并发
MIN_KEEP = 20                        # 安全阀阈值

SOURCES = {
    "http": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/proxy.txt",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    ],
    "socks4": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000&country=all",
    ],
    "socks5": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country=all",
    ],
}

PAT = re.compile(r"^(\d{1,3}\.){3}\d{1,3}:\d{1,5}$")


def valid(line: str) -> bool:
    if not PAT.match(line):
        return False
    ip, port = line.rsplit(":", 1)
    return all(0 <= int(x) <= 255 for x in ip.split(".")) and 1 <= int(port) <= 65535


def fetch_candidates(protocol: str) -> list:
    found = set()
    # 把仓库里现有的也纳入复检（有些长寿节点不在新抓取里）
    try:
        with open(f"{protocol}.txt") as f:
            found.update(l.strip() for l in f if valid(l.strip()))
    except FileNotFoundError:
        pass
    for url in SOURCES[protocol]:
        try:
            text = requests.get(url, timeout=30).text
            found.update(l.strip() for l in text.splitlines() if valid(l.strip()))
            print(f"[{protocol}] source ok: {url[:60]}...")
        except Exception as e:
            print(f"[{protocol}] source FAILED {url[:60]}...: {e}")
    return sorted(found)


def check(args):
    protocol, proxy = args
    url = f"{protocol}://{proxy}"
    start = time.time()
    try:
        r = requests.get(TEST_URL, proxies={"http": url, "https": url}, timeout=TIMEOUT)
        if r.status_code == 200 and "origin" in r.text:
            return proxy, round(time.time() - start, 2)
    except Exception:
        pass
    return None


def verify(protocol: str, candidates: list) -> list:
    print(f"[{protocol}] checking {len(candidates)} candidates...")
    ok = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for res in ex.map(check, [(protocol, p) for p in candidates]):
            if res:
                ok.append(res)
    ok.sort(key=lambda x: x[1])  # 最快的排最前，爬虫取前面的就行
    print(f"[{protocol}] alive: {len(ok)}/{len(candidates)}")
    return ok


def main():
    result, status = {}, []
    for protocol in ("http", "socks4", "socks5"):
        candidates = fetch_candidates(protocol)
        alive = verify(protocol, candidates)
        if len(alive) >= MIN_KEEP:
            with open(f"{protocol}.txt", "w") as f:
                f.write("\n".join(p for p, _ in alive) + "\n")
            result[protocol] = [p for p, _ in alive]
            status.append(f"| {protocol} | {len(candidates)} | {len(alive)} | updated |")
        else:
            # 安全阀触发：保留旧文件
            try:
                old = [l.strip() for l in open(f"{protocol}.txt") if l.strip()]
            except FileNotFoundError:
                old = []
            result[protocol] = old
            status.append(f"| {protocol} | {len(candidates)} | {len(alive)} | kept old ({len(old)}), below safety threshold |")
            print(f"[{protocol}] SAFETY: only {len(alive)} alive, keeping old file")

    with open("all_proxies.txt", "w") as f:
        for protocol in ("http", "socks4", "socks5"):
            f.write("\n".join(f"{protocol}://{p}" for p in result[protocol]) + "\n")
    with open("proxies.json", "w") as f:
        json.dump(result, f, indent=2)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open("STATUS.md", "w") as f:
        f.write(f"# 最近一次自动验活\n\n时间：{now}（GitHub Actions 每 6 小时运行一次）\n\n")
        f.write("| 协议 | 抓取候选 | 验活存活 | 结果 |\n|---|---|---|---|\n")
        f.write("\n".join(status) + "\n\n")
        f.write("说明：http.txt / socks4.txt / socks5.txt 里只保留验活通过的节点，按响应速度排序，最快的在最前面。\n")
    print("done")


if __name__ == "__main__":
    main()
