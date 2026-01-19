import asyncio
from aiohttp import web

async def handle_fast(request):
    return web.Response(text='{"data": "fast"}', content_type='application/json', headers={"Cache-Control": "max-age=60"})

async def handle_slow(request):
    await asyncio.sleep(1)
    return web.Response(text='{"data": "slow"}', content_type='application/json', headers={"Cache-Control": "max-age=60"})

async def handle_flaky(request):
    return web.Response(status=500, text="Internal Server Error") # Always error

async def init_func():
    app = web.Application()
    app.add_routes([
        web.get('/fast', handle_fast),
        web.get('/slow', handle_slow),
        web.get('/flaky', handle_flaky),
    ])
    return app

if __name__ == '__main__':
    web.run_app(init_func(), port=8082)
