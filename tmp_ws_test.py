import asyncio, json
import websockets

async def main():
    uri = 'ws://127.0.0.1:8000/ws/opportunities'
    try:
        async with websockets.connect(uri) as ws:
            msg = await ws.recv()
            print('RECV:', msg)
    except Exception as e:
        print('ERR', e)

if __name__ == '__main__':
    asyncio.run(main())
