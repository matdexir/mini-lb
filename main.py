from backend_pool import BackendPool
from aiohttp import web, ClientSession
import argparse
import asyncio


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args, _ = parser.parse_known_args()
    asyncio.run(run_app(args.port))


async def run_app(port):
    backend_pool = BackendPool()
    await backend_pool.start_health_checks()
    await backend_pool.start_stats_cleanup()
    client_session = ClientSession()

    try:

        async def proxy_handler(request):
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

                    return web.Response(
                        body=body, status=resp.status, headers=resp.headers
                    )

            except Exception as e:
                return web.Response(text=str(e), status=502)

            finally:
                await backend_pool.release(backend)

        async def add_backend(request):
            data = await request.json()
            await backend_pool.add(data["url"], data.get("weight", 1))
            return web.json_response({"status": "added"})

        async def remove_backend(request):
            data = await request.json()
            await backend_pool.remove(data["url"])
            return web.json_response({"status": "removed"})

        async def set_algorithm(request):
            data = await request.json()
            await backend_pool.set_scheduler(data["algorithm"])
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

        print(f"Load balancer running on http://127.0.0.1:{port}")

        while True:
            await asyncio.sleep(3600)

    finally:
        await backend_pool.stop_health_checks()
        await backend_pool.stop_stats_cleanup()
        await client_session.close()


if __name__ == "__main__":
    main()
