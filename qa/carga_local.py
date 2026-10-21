"""Carga de humo local y limitada. Nunca ejecuta escrituras ni apunta a AWS.

Uso: python qa/carga_local.py --requests 30 --workers 3
"""
import argparse
import concurrent.futures
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def measure(url):
    opener = build_opener(NoRedirect)
    started = time.perf_counter()
    try:
        with opener.open(url, timeout=10) as response:
            status = response.status
    except HTTPError as exc:
        status = exc.code
    except (URLError, TimeoutError):
        status = 0
    return status, time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description="Prueba acotada GET en servidor local")
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.requests <= 100 or not 1 <= args.workers <= 5:
        parser.error("Máximo 100 solicitudes y 5 trabajadores")
    url = "http://127.0.0.1:8000/"
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(measure, [url] * args.requests))
    durations = sorted(duration for _, duration in results)
    n = len(durations)
    statuses = {s: sum(status == s for status, _ in results) for s in {s for s, _ in results}}
    seconds = time.perf_counter() - started
    print(f"URL local: {url}")
    print(f"Solicitudes: {n}; concurrentes: {args.workers}; códigos HTTP: {statuses}")
    print(f"Duración total: {seconds:.2f}s; solicitudes/seg: {n / seconds:.2f}")
    print(f"Latencia media: {statistics.mean(durations) * 1000:.1f}ms")
    print(f"Latencia p95: {durations[max(0, int(.95 * n) - 1)] * 1000:.1f}ms")
    print("Prueba de humo GET, NO equivale a pruebas de estrés completas del docente.")


if __name__ == "__main__":
    main()
