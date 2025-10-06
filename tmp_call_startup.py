import asyncio, json
import arbitrage.web as w

async def run_start():
    await w._start_scanner()
    print('LOGS:', json.dumps(w.server_logs[-10:], indent=2))
    print('LATEST:', json.dumps(w.latest_opportunities))

if __name__ == '__main__':
    asyncio.run(run_start())
