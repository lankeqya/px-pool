#!/usr/bin/env python3
"""
代理可用性检测脚本（在你本地运行）
用法:
  pip install requests PySocks
  python check_proxies.py http.txt --limit 500 --output verified_http.txt
  python check_proxies.py socks5.txt --protocol socks5 --limit 300
原理: 逐个用代理请求 http://httpbin.org/ip ，200 即存活，按延迟排序输出。
免费代理存活率通常只有 5%-15%，且寿命以小时计，入池前先跑一遍这个脚本。
"""
import argparse, concurrent.futures, time, requests

def test(args):
    proxy, protocol = args
    url = f"{protocol}://{proxy}"
    try:
        r = requests.get("http://httpbin.org/ip",
                         proxies={"http": url, "https": url}, timeout=7)
        if r.status_code == 200:
            return proxy, r.elapsed.total_seconds()
    except Exception:
        pass
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--protocol", default="http", choices=["http", "socks4", "socks5"])
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--workers", type=int, default=50)
    ap.add_argument("--output", default="verified.txt")
    a = ap.parse_args()

    proxies = [l.strip() for l in open(a.file) if l.strip()][:a.limit]
    print(f"检测 {len(proxies)} 个 {a.protocol} 代理...")
    ok, start = [], time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(test, [(p, a.protocol) for p in proxies]):
            if res:
                ok.append(res)
                print(f"  OK {res[0]}  {res[1]:.2f}s")
    ok.sort(key=lambda x: x[1])
    with open(a.output, "w") as f:
        f.write("\n".join(p for p, _ in ok) + ("\n" if ok else ""))
    print(f"完成: {len(ok)}/{len(proxies)} 存活，用时 {time.time()-start:.0f}s -> {a.output}")

if __name__ == "__main__":
    main()
