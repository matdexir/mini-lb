from backend_pool import BackendPool
from core import MetricsCollector
from aiohttp import web, ClientSession
import argparse
import asyncio
import logging
import time


def setup_logging(log_level: str, log_file: str | None):
    level = getattr(logging, log_level.upper())
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    return logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--metrics-port", type=int, default=9090, help="Port for metrics server"
    )
    parser.add_argument(
        "--enable-metrics",
        type=bool,
        default=True,
        help="Enable metrics collection",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--log-file", default=None, help="Optional file path for logging"
    )
    args, _ = parser.parse_known_args()

    logger = setup_logging(args.log_level, args.log_file)
    asyncio.run(run_app(args.port, args.metrics_port, args.enable_metrics, logger))


async def run_app(port: int, metrics_port: int, enable_metrics: bool, logger):
    metrics = MetricsCollector() if enable_metrics else None
    backend_pool = BackendPool(metrics=metrics)
    await backend_pool.start_health_checks()
    await backend_pool.start_stats_cleanup()
    client_session = ClientSession()
    shutdown_event = asyncio.Event()
    metrics_runner = None

    try:

        async def proxy_handler(request):
            start_time = time.time()
            backend = await backend_pool.select_backend()

            if not backend:
                return web.Response(text="No backends", status=503)

            try:
                async with client_session.request(
                    method=request.method,
                    url=f"{backend.url}{request.rel_url}",
                    headers=request.headers,
                    data=await request.read(),
                ) as resp:
                    body = await resp.read()
                    await backend_pool.record_request(backend.url)

                    duration = (time.time() - start_time) * 1000

                    if metrics:
                        await metrics.increment_counter(
                            "backend.requests.total",
                            {
                                "backend": backend.url,
                                "method": request.method,
                                "status": str(resp.status),
                            },
                        )
                        await metrics.record_histogram(
                            "backend.latency.ms", duration, {"backend": backend.url}
                        )

                    logger.info(
                        f"{request.method} {request.path} -> {backend.url} ({resp.status}) - {duration:.2f}ms"
                    )

                    return web.Response(
                        body=body, status=resp.status, headers=resp.headers
                    )

            except Exception as e:
                logger.error(f"Proxy error for {backend.url}: {e}")

                if metrics:
                    await metrics.increment_counter(
                        "backend.errors.total", {"backend": backend.url}
                    )
                    await metrics.increment_counter(
                        "backend.requests.total",
                        {
                            "backend": backend.url,
                            "method": request.method,
                            "status": "error",
                        },
                    )

                return web.Response(text=str(e), status=502)

            finally:
                await backend_pool.release(backend)

        async def add_backend(request):
            data = await request.json()
            url = data["url"]
            await backend_pool.add(url, data.get("weight", 1))
            logger.info(f"Backend added: {url}")
            return web.json_response({"status": "added"})

        async def remove_backend(request):
            data = await request.json()
            url = data["url"]
            await backend_pool.remove(url)
            logger.info(f"Backend removed: {url}")
            return web.json_response({"status": "removed"})

        async def set_algorithm(request):
            data = await request.json()
            algo = data["algorithm"]
            await backend_pool.set_scheduler(algo)
            logger.info(f"Scheduler algorithm changed to: {algo}")
            return web.json_response({"status": "scheduler_updated"})

        async def list_backends(request):
            return web.json_response(await backend_pool.show())

        async def get_stats(request):
            periods_param = request.query.get("periods", "5m,30m,1h,6h,24h,all")
            periods = [p.strip() for p in periods_param.split(",")]
            return web.json_response(await backend_pool.get_stats(periods))

        app = web.Application()

        app.router.add_post("/_control/add", add_backend)
        app.router.add_post("/_control/remove", remove_backend)
        app.router.add_post("/_control/scheduler", set_algorithm)
        app.router.add_get("/_control/list", list_backends)
        app.router.add_get("/_control/stats", get_stats)

        app.router.add_route("*", "/{path:.*}", proxy_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()

        logger.info(f"Load balancer running on http://127.0.0.1:{port}")

        if metrics:
            metrics_app = web.Application()

            async def metrics_handler(request):
                accept = request.headers.get("Accept", "")
                if "application/json" in accept or "/json" in accept:
                    return web.json_response(await metrics.get_metrics())
                return web.Response(
                    text=await metrics.export_prometheus(), content_type="text/plain"
                )

            metrics_app.router.add_get("/metrics", metrics_handler)
            metrics_app.router.add_get("/metrics/json", metrics_handler)

            metrics_runner = web.AppRunner(metrics_app)
            await metrics_runner.setup()
            metrics_site = web.TCPSite(metrics_runner, "127.0.0.1", metrics_port)
            await metrics_site.start()
            logger.info(
                f"Metrics server running on http://127.0.0.1:{metrics_port}/metrics"
            )

        await shutdown_event.wait()

    finally:
        shutdown_event.set()
        await backend_pool.stop_health_checks()
        await backend_pool.stop_stats_cleanup()
        await client_session.close()
        if metrics_runner:
            await metrics_runner.cleanup()


if __name__ == "__main__":
    main()
