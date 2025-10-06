'use strict';

const WebSocket = require('ws');
const express = require('express');
const protobuf = require('protobufjs');
const zlib = require('zlib');

const PORT = process.env.PORT || 3000;
const TOPIC = process.env.TOPIC || 'spot@public.aggre.deals.v3.api.pb@100ms@BTCUSDT';
// HOTCOINS: comma-separated symbols (e.g. BTCUSDT,ETHUSDT) or HOTCOINS_FILE path to JSON array
const HOTCOINS_ENV = process.env.HOTCOINS || null;
const HOTCOINS_FILE = process.env.HOTCOINS_FILE || null;
const MEXC_WS = process.env.MEXC_WS || 'wss://wbs-api.mexc.com/ws';
const BACKEND_WS = process.env.BACKEND_WS || 'ws://127.0.0.1:8000/ws/hotcoins';

// minimal proto definitions needed to decode PushDataV3ApiWrapper -> PublicAggreDealsV3Api
const protoText = `
syntax = "proto3";

message PublicAggreDealsV3ApiItem { string price = 1; string quantity = 2; int32 tradeType = 3; int64 time = 4; }
message PublicAggreDealsV3Api { repeated PublicAggreDealsV3ApiItem deals = 1; string eventType = 2; }
message PushDataV3ApiWrapper {
  string channel = 1;
  oneof body { PublicAggreDealsV3Api publicAggreDeals = 314; }
  optional string symbol = 3;
  optional string symbolId = 4;
  optional int64 createTime = 5;
  optional int64 sendTime = 6;
}
`;

const root = protobuf.parse(protoText).root;
const Wrapper = root.lookupType('PushDataV3ApiWrapper');

let sseClients = new Set();
let lastMessage = null;
let wsClient = null;
let reconnectTimer = null;
let hotcoins = null; // Set of symbols to track (uppercase, like BTCUSDT)
let prices = {}; // mapping symbol -> numeric price or null
let backendWs = null;
let backendReconnect = null;
let currentSubscribed = new Set(); // symbols currently subscribed at MEXC-level (uppercase no slash)
let pendingHotcoinsSet = null;
let pendingHotcoinsTimer = null;
const BACKEND_DEBOUNCE_MS = parseInt(process.env.BACKEND_SUB_DEBOUNCE_MS || '500', 10);

function prettySymbol(sym) {
  if (!sym) return sym;
  sym = String(sym).toUpperCase();
  const knownQuotes = ['USDT','USDC','USD','BTC','ETH','BNB','USDS','TUSD','BUSD'];
  for (const q of knownQuotes) {
    if (sym.endsWith(q) && sym.length > q.length) {
      return sym.slice(0, sym.length - q.length) + '/' + q;
    }
  }
  // fallback: try split last 4 chars
  if (sym.length > 6) return sym.slice(0, sym.length - 4) + '/' + sym.slice(sym.length - 4);
  return sym;
}

function broadcast(obj){
  lastMessage = obj;
  const payload = JSON.stringify(obj);
  for (const res of sseClients) {
    try {
      res.write(`data: ${payload}\n\n`);
    } catch (e) {
      // ignore client write errors
    }
  }
}

function connectWs(){
  if (wsClient) {
    try { wsClient.terminate(); } catch(_){}
    wsClient = null;
  }

  console.log('connecting to', MEXC_WS);
  wsClient = new WebSocket(MEXC_WS);

  wsClient.on('open', () => {
    console.log('ws open');

    // Determine hotcoins from env or file (lazy init)
    if (!hotcoins) {
      try {
        if (HOTCOINS_ENV) {
          hotcoins = new Set(HOTCOINS_ENV.split(',').map(s => s.trim().toUpperCase()).filter(Boolean));
        } else if (HOTCOINS_FILE) {
          const fs = require('fs');
          const txt = fs.readFileSync(HOTCOINS_FILE, 'utf8');
          const arr = JSON.parse(txt);
          hotcoins = new Set((arr || []).map(s => String(s).trim().toUpperCase()).filter(Boolean));
        }
      } catch (e) {
        console.error('error loading HOTCOINS config', e);
        hotcoins = null;
      }

      if (hotcoins && hotcoins.size) {
        // init prices map with pretty keys (BASE/QUOTE)
        for (const s of hotcoins) prices[prettySymbol(s)] = null;
      }
    }

    if (hotcoins && hotcoins.size) {
      // subscribe to all hotcoin topics
      const topics = Array.from(hotcoins).map(sym => `spot@public.aggre.deals.v3.api.pb@100ms@${sym}`);
      console.log('ws open, subscribing to hotcoin topics count=', topics.length);
      sendSubscribeTopics(topics);
    } else {
      console.log('ws open, subscribing to', TOPIC);
      sendSubscribeTopics([TOPIC]);
    }
  });

  wsClient.on('message', (data) => {
    try {
      // Normalize to Buffer
      const buf = Buffer.isBuffer(data) ? data : Buffer.from(data);

      // Quick detect: some messages arrive as text frames but as Buffer; try parsing as JSON first
      if (buf.length && (buf[0] === 0x7b || buf[0] === 0x5b)) { // '{' or '['
        const s = buf.toString('utf8');
        try {
          const t = JSON.parse(s);
          if (t && t.msg) console.log('ack:', t.msg);
          return;
        } catch (e) {
          // not JSON, continue
        }
      }

      // helper: try decode wrapper from a slice and return object or null
      function tryDecodeSlice(slice) {
        try {
          // attempt gunzip if needed
          let p = slice;
          if (p.length >= 2 && p[0] === 0x1f && p[1] === 0x8b) {
            try { p = zlib.gunzipSync(p); } catch(e) { return { err: e }; }
          }
          const decoded = Wrapper.decode(p);
          const obj = Wrapper.toObject(decoded, { longs: String, enums: String, bytes: String });
          return { obj };
        } catch (err) {
          return { err };
        }
      }

      // find delimiter 0x1A between ascii channel and protobuf bytes
      const delimByte = 0x1A;
      const idx = buf.indexOf(delimByte);
      if (idx === -1) {
        // Not found: maybe the provider sent a plain protobuf without delimiter or different framing
        // Try direct decode attempts with several heuristics below
      }

      const attempts = [];

      // If delim found, try after it
      if (idx !== -1) attempts.push({name: 'after_delim', slice: buf.slice(idx + 1)});

      // 1) direct whole buffer
      attempts.push({name: 'direct', slice: buf});

      // 2) skip varint length prefix (read varint)
      function readVarint(b) {
        let result = 0n;
        let shift = 0n;
        for (let i = 0; i < b.length; i++) {
          const byte = BigInt(b[i]);
          result |= (byte & 0x7fn) << shift;
          if ((b[i] & 0x80) === 0) return { value: result, bytes: i + 1 };
          shift += 7n;
          if (shift > 64n) break;
        }
        return null;
      }

      const v = readVarint(buf);
      if (v && v.bytes < buf.length) attempts.push({name: 'skip_varint', slice: buf.slice(v.bytes)});

      // 3) try gRPC 5-byte prefix skip
      if (buf.length > 5) attempts.push({name: 'skip_grpc5', slice: buf.slice(5)});

      // 4) if delim found, also try skipping some extra bytes after delim (in case of extra length prefix)
      if (idx !== -1) {
        for (let extra = 1; extra <= 5; extra++) {
          if (idx + 1 + extra < buf.length) attempts.push({name: `after_delim+skip${extra}`, slice: buf.slice(idx + 1 + extra)});
        }
      }

      // 5) scan for 0x0a in first 128 bytes and try decode from there
      const scanLen = Math.min(128, buf.length);
      for (let i = 0; i < scanLen; i++) {
        if (buf[i] === 0x0a) attempts.push({name: `scan_0a_at_${i}`, slice: buf.slice(i)});
      }

      // Deduplicate attempts by slice length+first8 bytes
      const seen = new Set();
      const unique = [];
      for (const a of attempts) {
        const key = a.slice.length + '-' + a.slice.slice(0,8).toString('hex');
        if (!seen.has(key)) { seen.add(key); unique.push(a); }
      }

      let success = false;
      for (const a of unique) {
        const res = tryDecodeSlice(a.slice);
        if (res && res.obj) {
          const obj = res.obj;
          if (obj.publicAggreDeals && obj.publicAggreDeals.deals) {
            const deals = obj.publicAggreDeals.deals.map(d => ({ price: d.price, quantity: d.quantity, tradeType: d.tradeType, time: (d.time ? Number(d.time) : null) }));
            // try to determine symbol
            let sym = (obj.symbol || null);
            if (!sym && obj.channel) {
              // channel often like 'spot@public.aggre.deals.v3.api.pb@100ms@BTCUSDT'
              const parts = String(obj.channel).split('@');
              sym = parts[parts.length - 1] || null;
            }
            if (sym) sym = String(sym).toUpperCase();

            // choose last deal price as latest
            let latestPrice = null;
            if (deals && deals.length) {
              const lp = deals[deals.length - 1].price;
              const n = Number(lp);
              latestPrice = Number.isFinite(n) ? n : (lp ? parseFloat(String(lp)) : null);
            }

            if (hotcoins && sym && hotcoins.has(sym)) {
              // update prices map using pretty symbol key and broadcast minimal mapping only
              const key = prettySymbol(sym);
              prices[key] = latestPrice;
              console.log('hotcoin update', sym, '->', key, 'price=', prices[key]);
              broadcastPrices();
            } else {
              // non-hotcoin, keep old behavior for debugging
              const out = { channel: obj.channel || null, symbol: obj.symbol || null, createTime: obj.createTime ? Number(obj.createTime) : null, sendTime: obj.sendTime ? Number(obj.sendTime) : null, deals };
              console.log('decoded (method=', a.name, ') deals count=', deals.length, 'sample=', deals[0]);
              broadcast(out);
            }
            success = true;
            break;
          } else {
            // generic wrapper
            console.log('decoded wrapper (method=', a.name, ')');
            broadcast({ channel: obj.channel || null, body: obj });
            success = true;
            break;
          }
        }
        // else continue trying
      }

      if (!success) {
        console.error('protobuf decode failed for all attempts; hex preview:', buf.slice(0,128).toString('hex'));
      }

    } catch (err) {
      console.error('message handler error', err);
    }
  });

  wsClient.on('close', (code, reason) => {
    console.log('ws closed', code, reason && reason.toString ? reason.toString() : reason);
    scheduleReconnect();
  });
  wsClient.on('error', (err) => {
    console.error('ws error', err);
    // will trigger close as well
  });
}

function sendSubscribeTopics(topics) {
  if (!wsClient || wsClient.readyState !== WebSocket.OPEN) return;
  try {
    wsClient.send(JSON.stringify({ method: 'SUBSCRIPTION', params: topics, id: Date.now() }));
    // mark currentSubscribed for topic symbols when topics are in the hotcoin format
    for (const t of topics) {
      const parts = String(t).split('@');
      const sym = parts[parts.length - 1] || null;
      if (sym) currentSubscribed.add(String(sym).toUpperCase());
    }
  } catch (e) {
    console.error('sendSubscribeTopics error', e);
  }
}

function sendUnsubscribeTopics(topics) {
  if (!wsClient || wsClient.readyState !== WebSocket.OPEN) return;
  try {
    wsClient.send(JSON.stringify({ method: 'UNSUBSCRIPTION', params: topics, id: Date.now() }));
    for (const t of topics) {
      const parts = String(t).split('@');
      const sym = parts[parts.length - 1] || null;
      if (sym) currentSubscribed.delete(String(sym).toUpperCase());
    }
  } catch (e) {
    console.error('sendUnsubscribeTopics error', e);
  }
}

// Connect to backend websocket to receive hotcoins broadcasts
function connectBackendHotcoins(){
  try {
    if (backendWs) {
      try { backendWs.terminate(); } catch(_){}
      backendWs = null;
    }
    console.log('connecting to backend hotcoins ws', BACKEND_WS);
    backendWs = new WebSocket(BACKEND_WS);

    backendWs.on('open', () => {
      console.log('backend hotcoins ws open');
      if (backendReconnect) { clearTimeout(backendReconnect); backendReconnect = null; }
    });

    backendWs.on('message', (data) => {
      try {
        const s = (typeof data === 'string') ? data : Buffer.isBuffer(data) ? data.toString('utf8') : null;
        if (!s) return;
        let parsed = null;
        try { parsed = JSON.parse(s); } catch(e) { return; }
        // Expecting parsed to be a list of hotcoin items
        let newSet = new Set();
        if (Array.isArray(parsed)) {
          for (const it of parsed) {
            try {
              const symRaw = (it && (it.symbol || (it.base && it.quote && `${it.base}/${it.quote}`))) || null;
              if (!symRaw) continue;
              // normalize to MEXC symbol (no separators)
              const norm = String(symRaw).replace(/[^A-Za-z0-9]/g, '').toUpperCase();
              if (norm) newSet.add(norm);
            } catch(e) { continue; }
          }
        }
        // update hotcoins set and subscriptions
        updateHotcoinsFromBackend(newSet);
      } catch (e) {
        console.error('backend message handler error', e);
      }
    });

    backendWs.on('close', (code, reason) => {
      console.log('backend ws closed', code, reason && reason.toString ? reason.toString() : reason);
      scheduleBackendReconnect();
    });
    backendWs.on('error', (err) => {
      console.error('backend ws error', err);
      // will trigger close
    });
  } catch (e) {
    console.error('connectBackendHotcoins failed', e);
    scheduleBackendReconnect();
  }
}

function scheduleBackendReconnect(){
  if (backendReconnect) return;
  backendReconnect = setTimeout(() => { backendReconnect = null; connectBackendHotcoins(); }, 2000);
}

function updateHotcoinsFromBackend(newSet) {
  // Schedule a debounced apply: collect rapid updates and apply after BACKEND_DEBOUNCE_MS
  pendingHotcoinsSet = new Set(newSet);
  if (pendingHotcoinsTimer) {
    clearTimeout(pendingHotcoinsTimer);
  }
  pendingHotcoinsTimer = setTimeout(() => { applyPendingHotcoins(); }, BACKEND_DEBOUNCE_MS);
}

function applyPendingHotcoins() {
  pendingHotcoinsTimer = null;
  if (!pendingHotcoinsSet) return;

  const newHot = new Set(pendingHotcoinsSet);
  pendingHotcoinsSet = null;

  // prepare pretty-price keys and preserve previous values if possible
  const newPrices = {};
  for (const s of newHot) {
    const key = prettySymbol(s);
    newPrices[key] = prices[key] ?? null;
  }
  prices = newPrices;

  // compute subscribe/unsubscribe diffs using raw symbol names
  const desiredRaw = new Set(Array.from(newHot));
  const added = [];
  const removed = [];
  for (const s of desiredRaw) if (!currentSubscribed.has(s)) added.push(s);
  for (const s of Array.from(currentSubscribed)) if (!desiredRaw.has(s)) removed.push(s);

  if (added.length) {
    const topics = added.map(sym => `spot@public.aggre.deals.v3.api.pb@100ms@${sym}`);
    console.log('subscribing new topics', topics);
    sendSubscribeTopics(topics);
  }
  if (removed.length) {
    const topics = removed.map(sym => `spot@public.aggre.deals.v3.api.pb@100ms@${sym}`);
    console.log('unsubscribing topics', topics);
    sendUnsubscribeTopics(topics);
  }

  // update hotcoins set and push updated prices map to SSE clients
  hotcoins = newHot;
  broadcastPrices();
}

// start backend hotcoins watcher
connectBackendHotcoins();

function broadcastPrices(){
  // lastMessage remains for non-hotcoin messages; for hotcoins we want to push only minimal mapping
  const payload = JSON.stringify(prices);
  for (const res of sseClients) {
    try {
      res.write(`data: ${payload}\n\n`);
    } catch (e) {
      // ignore
    }
  }
}

function scheduleReconnect(){
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connectWs(); }, 2000);
}

// start WS
connectWs();

// HTTP + SSE server
const app = express();
app.use((req,res,next)=>{ res.setHeader('Access-Control-Allow-Origin','*'); next(); });

app.get('/health', (req,res)=> res.json({ ok: true }));
app.get('/last', (req,res)=> {
  if (hotcoins && Object.keys(prices).length) return res.json(prices);
  return res.json(lastMessage || {});
});

// Always-available JSON endpoint with the minimal prices mapping (quick front-end fetch)
app.get('/prices', (req, res) => {
  res.setHeader('Content-Type', 'application/json');
  return res.json(prices || {});
});

app.get('/stream', (req,res)=>{
  res.setHeader('Content-Type','text/event-stream');
  res.setHeader('Cache-Control','no-cache');
  res.setHeader('Connection','keep-alive');
  res.flushHeaders && res.flushHeaders();

  // send initial comment
  res.write(': connected\n\n');
  if (lastMessage) res.write(`data: ${JSON.stringify(lastMessage)}\n\n`);

  sseClients.add(res);
  console.log('sse client connected, total=', sseClients.size);

  req.on('close', () => {
    sseClients.delete(res);
    try { res.end(); } catch(e){}
    console.log('sse client disconnected, total=', sseClients.size);
  });
});

app.listen(PORT, () => console.log(`server listening ${PORT}. SSE: /stream  last: /last`));
