mexc-ws-proxy
=================

Tiny proxy that connects to MEXC WebSocket, decodes protobuf PushDataV3ApiWrapper -> PublicAggreDealsV3Api messages, and exposes JSON via an HTTP SSE endpoint.

Why use this
- Keep protobuf decoding on the server-side and deliver simple JSON to browser clients
- Useful if you can't connect from the browser or want to centralize parsing

Quick start

1. Open a terminal in the repo root and change into the proxy folder:

```powershell
cd tools\mexc_ws_proxy
```

2. Install dependencies:

```powershell
npm install
```

3. Run the proxy (port defaults to 3000):

```powershell
node server.js
# or
npm start
```

4. Open the SSE stream in a browser or curl:

- Browser: visit http://localhost:3000/stream (use an EventSource client)
- Poll last message: GET http://localhost:3000/last

Environment variables
- PORT: HTTP server port (default 3000)
- TOPIC: subscription topic (default spot@public.aggre.deals.v3.api.pb@100ms@BTCUSDT)
- MEXC_WS: websocket URL (default wss://wbs-api.mexc.com/ws)

Notes
- This proxy uses a simple delimiter-based split: messages are expected to include an ASCII channel string, a 0x1A separator, then the protobuf payload. This matches observed messages from MEXC.
- If the payload is gzipped, the proxy will attempt to gunzip it before decoding.
- For production, consider supervising the process (pm2/systemd) and handling backpressure/flow control more thoroughly.
