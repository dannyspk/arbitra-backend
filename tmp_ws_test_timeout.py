import asyncio, json
import websockets

async def main():
    uri = 'ws://127.0.0.1:8000/ws/opportunities'
    try:
        async with websockets.connect(uri) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                print('RECV:', msg)
            except asyncio.TimeoutError:
                print('TIMEOUT: no message within 5s')
    except Exception as e:
        print('ERR', repr(e))

if __name__ == '__main__':
    asyncio.run(main())
