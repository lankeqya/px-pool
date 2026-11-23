#!/usr/bin/env python3
"""
严选版：质量优先于数量（在 GitHub Actions 里运行）

免费代理的现实：抓回来的候选里通常只有 5%-15% 能通，能稳定走 HTTPS、
速度还过得去的更少。所以这里不追求大池子，而是：
  1. 优先从本身已每小时验活的源（monosans / jetkai）抓候选，其余源作补充，
     每类候选上限 3000 个，控制运行时长；
  2. 第一轮：请求 http://httpbin.org/ip 验活，超时 5 秒；
  3. 第二轮：对第一轮最快的一批再请求 https://api.ipify.org 复检，
     只有 HTTPS 也通的才留（现在网站基本都是 HTTPS，通不了等于没用）；
  4. 最终只保留最快的：http 200 个、socks5 200 个、socks4 100 个。
安全阀：某类最终少于 MIN_KEEP 个时不覆盖旧文件，避免检测目标临时故障清空池子。
"""
import concurrent.futures
import json
import re
import time
from datetime import datetime, timezone

import requests

HTTP_TEST = "http://httpbin.org/ip"
HTTPS_TEST = "https://api.ipify.org"
TIMEOUT = 5
WORKERS = 120
MIN_KEEP = 10
CANDIDATE_CAP = 3000
KEEP = {"http": 200, "socks5": 200, "socks4": 100}

# 已预验活的源排前面（抓取顺序决定候选上限内优先保留谁）
SOURCES = {
    "http": [
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    ],
    "socks4": [
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000&country=all",
    ],
    "socks5": [
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
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
    ordered, seen = [], set()
    def add(line):
        if valid(line) and line not in seen and len(ordered) < CANDIDATE_CAP:
            seen.add(line); ordered.append(line)
    for url in SOURCES[protocol]:
        try:
            for l in requests.get(url, timeout=30).text.splitlines():
                add(l.strip())
            print(f"[{protocol}] source ok: {url[:60]}...")
        except Exception as e:
            print(f"[{protocol}] source FAILED {url[:60]}...: {e}")
    # 仓库现有的节点排最后复检（能活到现在的老节点值得再测一次）
    try:
        with open(f"{protocol}.txt") as f:
            for l in f:
                add(l.strip())
    except FileNotFoundError:
        pass
    return ordered


def _test(args, url, needle=None):
    protocol, proxy = args
    u = f"{protocol}://{proxy}"
    start = time.time()
    try:
        r = requests.get(url, proxies={"http": u, "https": u}, timeout=TIMEOUT)
        if r.status_code == 200 and (needle is None or needle in r.text):
            return proxy, round(time.time() - start, 2)
    except Exception:
        pass
    return None


def run_round(protocol, proxies, url, needle=None):
    ok = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for res in ex.map(lambda a: _test(a, url, needle), [(protocol, p) for p in proxies]):
            if res:
                ok.append(res)
    ok.sort(key=lambda x: x[1])
    return ok


def verify(protocol: str, candidates: list) -> list:
    r1 = run_round(protocol, candidates, HTTP_TEST, needle="origin")
    print(f"[{protocol}] round1 http alive: {len(r1)}/{len(candidates)}")
    # 第二轮只测第一轮最快的 3 倍于保留量的节点，控制时长
    shortlist = [p for p, _ in r1[: KEEP[protocol] * 3]]
    if not shortlist:
        return []
    r2 = run_round(protocol, shortlist, HTTPS_TEST)
    print(f"[{protocol}] round2 https alive: {len(r2)}/{len(shortlist)}")
    return r2[: KEEP[protocol]]


def main():
    result, status = {}, []
    for protocol in ("http", "socks4", "socks5"):
        candidates = fetch_candidates(protocol)
        alive = verify(protocol, candidates)
        if len(alive) >= MIN_KEEP:
            with open(f"{protocol}.txt", "w") as f:
                f.write("\n".join(p for p, _ in alive) + "\n")
            result[protocol] = [p for p, _ in alive]
            status.append(f"| {protocol} | {len(candidates)} | {len(alive)} | updated (严选上限 {KEEP[protocol]}) |")
        else:
            try:
                old = [l.strip() for l in open(f"{protocol}.txt") if l.strip()]
            except FileNotFoundError:
                old = []
            result[protocol] = old
            status.append(f"| {protocol} | {len(candidates)} | {len(alive)} | kept old ({len(old)}), below safety threshold |")
            print(f"[{protocol}] SAFETY: only {len(alive)} passed, keeping old file")

    with open("all_proxies.txt", "w") as f:
        for protocol in ("http", "socks4", "socks5"):
            f.write("\n".join(f"{protocol}://{p}" for p in result[protocol]) + "\n")
    with open("proxies.json", "w") as f:
        json.dump(result, f, indent=2)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open("STATUS.md", "w") as f:
        f.write(f"# 最近一次自动验活（严选版）\n\n时间：{now}（GitHub Actions 每 6 小时运行一次）\n\n")
        f.write("| 协议 | 抓取候选 | 两轮验活后保留 | 结果 |\n|---|---|---|---|\n")
        f.write("\n".join(status) + "\n\n")
        f.write("标准：先测 HTTP 再测 HTTPS，两轮都通且最快的一批才保留，http/socks5 各最多 200 个、socks4 最多 100 个，按速度排序。\n")
    print("done")


if __name__ == "__main__":
    main()
