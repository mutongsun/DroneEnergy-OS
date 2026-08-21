"""容器网络内 HTTP 探针：绕过 Windows Docker 端口代理，验证应用真实吞吐

仅依赖标准库（http.client 连接级 keep-alive），可直接在 backend 容器内运行：
    docker cp probe_http.py <backend>:/tmp/
    docker exec <backend> python /tmp/probe_http.py 40 20 /api/v1/sensor/history/1?minutes=10&limit=600
"""

import http.client
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HOST, PORT = "localhost", 8000  # 容器自身：backend:8000


def fetch_token() -> str:
    conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
    body = json.dumps({"username": "operator", "password": "operator123"})
    conn.request(
        "POST",
        "/api/v1/auth/login",
        body=body,
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    token = json.loads(resp.read())["access_token"]
    conn.close()
    return token


def worker(token: str, n: int, path: str, results: list[tuple[float, int]]) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    conn = http.client.HTTPConnection(HOST, PORT, timeout=30)
    try:
        for _ in range(n):
            t0 = time.perf_counter()
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            results.append(((time.perf_counter() - t0) * 1000, len(body)))
            if resp.status != 200:
                print(f"  !! HTTP {resp.status}")
    finally:
        conn.close()


def main() -> None:
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    per_worker = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    path = (
        sys.argv[3]
        if len(sys.argv) > 3
        else "/api/v1/sensor/history/1?minutes=10&limit=600"
    )

    token = fetch_token()
    results: list[tuple[float, int]] = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(worker, token, per_worker, path, results)
            for _ in range(concurrency)
        ]
        for f in futures:
            f.result()
    wall = time.perf_counter() - t0

    lat = sorted(r[0] for r in results)
    total = len(lat)
    avg_body = sum(r[1] for r in results) / total
    print(
        f"path={path}\n  concurrency={concurrency} reqs={total} wall={wall:.2f}s "
        f"RPS={total / wall:.1f} p50={lat[total // 2]:.1f}ms p95={lat[int(total * 0.95)]:.0f}ms "
        f"max={lat[-1]:.0f}ms avg_body={avg_body / 1024:.1f}KB"
    )


if __name__ == "__main__":
    main()
