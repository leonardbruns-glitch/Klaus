"""UPDOWN-SNIPER shadow recorder — NO ORDERS, public reads only.

Records, for every BTC 5m/15m updown window in its final minutes:
  - Binance spot (ws trade stream) vs window-open, trailing 1s sigma, z, p_model
  - real CLOB books (both tokens): best bid/ask + ask depth
  - resolution label once Gamma settles
Offline fit then selects (t_left, z*, ask_max) policy and simulates fills
conservatively (ask must persist across consecutive snapshots).

Run: python3 strategy/updown_shadow.py   (systemd: klaus_updown_shadow.service)
Logs: logs/shadow/updown_sniper/snap_YYYYMMDD.jsonl (snapshots + resolutions)
"""
import asyncio, collections, json, math, os, time
import aiohttp

LOG_DIR = "/root/Klaus/logs/shadow/updown_sniper"
HDR = {"User-Agent": "Mozilla/5.0"}
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@trade"
SAMPLE_WINDOW = {300: 300, 900: 240}      # sample when t_left <= this
CADENCE_FAR, CADENCE_NEAR = 2.0, 1.0      # s; near = t_left <= 60

os.makedirs(LOG_DIR, exist_ok=True)

def out(rec):
    rec["ts"] = round(time.time(), 3)
    path = f"{LOG_DIR}/snap_{time.strftime('%Y%m%d', time.gmtime())}.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")

class Spot:
    """Binance BTCUSDT via ws; keeps (ts, px) for sigma + window opens."""
    def __init__(self):
        self.px = None
        self.hist = collections.deque()          # (ts, px) ~1/s downsampled
        self._last_keep = 0.0

    async def run(self):
        while True:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.ws_connect(BINANCE_WS, heartbeat=20) as ws:
                        async for msg in ws:
                            if msg.type != aiohttp.WSMsgType.TEXT:
                                continue
                            d = json.loads(msg.data)
                            self.px = float(d["p"])
                            now = time.time()
                            if now - self._last_keep >= 1.0:
                                self.hist.append((now, self.px))
                                self._last_keep = now
                                while self.hist and now - self.hist[0][0] > 2100:
                                    self.hist.popleft()
            except Exception as e:
                out({"type": "err", "where": "binance_ws", "err": str(e)[:200]})
                await asyncio.sleep(3)

    def at(self, ts):
        best = None
        for t, p in self.hist:
            if t <= ts + 0.5:
                best = p
            else:
                break
        return best

    def sigma1s(self, lookback=900):
        now = time.time()
        pts = [(t, p) for t, p in self.hist if now - t <= lookback]
        if len(pts) < 60:
            return None
        rets = [math.log(pts[i][1] / pts[i-1][1]) /
                max(pts[i][0] - pts[i-1][0], 0.5) ** 0.5
                for i in range(1, len(pts)) if pts[i][1] > 0 and pts[i-1][1] > 0]
        if len(rets) < 30:
            return None
        m = sum(rets) / len(rets)
        return (sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5

async def gj(sess, url):
    try:
        async with sess.get(url) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None

class Runner:
    def __init__(self):
        self.spot = Spot()
        self.windows = {}        # slug -> dict
        self.done = set()

    async def discover(self, sess):
        while True:
            now = int(time.time())
            for step in (300, 900):
                for off in (0, step):
                    w = now - now % step + off
                    slug = f"btc-updown-{'5m' if step==300 else '15m'}-{w}"
                    if slug in self.windows or slug in self.done:
                        continue
                    evs = await gj(sess, f"{GAMMA}/events?slug={slug}")
                    for ev in evs or []:
                        for m in ev.get("markets") or []:
                            try:
                                toks = json.loads(m.get("clobTokenIds") or "[]")
                                ocs = json.loads(m.get("outcomes") or "[]")
                            except Exception:
                                continue
                            if len(toks) == 2 and m.get("acceptingOrders"):
                                self.windows[slug] = {
                                    "slug": slug, "step": step, "w": w,
                                    "end": w + step, "tokens": toks,
                                    "outcomes": ocs, "cid": m["conditionId"],
                                    "open_px": None}
            await asyncio.sleep(20)

    async def resolve(self, sess):
        while True:
            now = time.time()
            for slug, win in list(self.windows.items()):
                if now < win["end"] + 30:
                    continue
                evs = await gj(sess, f"{GAMMA}/events?slug={slug}")
                for ev in evs or []:
                    for m in ev.get("markets") or []:
                        try:
                            op = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                        except Exception:
                            op = []
                        # exact 1/0 only: pre-resolution live prices also sum to 1.0
                        # (2026-07-13 bug mislabeled winner on 84/196 windows)
                        if sorted(op) == [0.0, 1.0]:
                            winner = win["outcomes"][0] if op[0] == 1.0 else win["outcomes"][1]
                            out({"type": "res", "slug": slug, "winner": winner,
                                 "b_open": win["open_px"],
                                 "b_close": self.spot.at(win["end"])})
                            self.done.add(slug)
                            del self.windows[slug]
                if now > win["end"] + 900 and slug in self.windows:
                    out({"type": "res", "slug": slug, "winner": None})
                    self.done.add(slug); del self.windows[slug]
            while len(self.done) > 3000:
                self.done.pop()
            await asyncio.sleep(15)

    async def book(self, sess, token):
        b = await gj(sess, f"{CLOB}/book?token_id={token}")
        if not b:
            return None
        try:
            asks = sorted(((float(a["price"]), float(a["size"])) for a in b.get("asks") or []))
            bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids") or []), reverse=True)
            ba = asks[0] if asks else (None, None)
            bb = bids[0] if bids else (None, None)
            return {"ask": ba[0], "ask_sz": ba[1], "bid": bb[0], "bid_sz": bb[1]}
        except Exception:
            return None

    async def sample(self, sess):
        while True:
            now = time.time()
            active = []
            for win in self.windows.values():
                t_left = win["end"] - now
                in_win = win["w"] <= now < win["end"]
                if in_win and win["open_px"] is None:
                    win["open_px"] = self.spot.at(win["w"])
                if in_win and 0 < t_left <= SAMPLE_WINDOW[win["step"]]:
                    active.append((win, t_left))
            for win, t_left in active:
                px, op = self.spot.px, win["open_px"]
                sig = self.spot.sigma1s()
                move = z = p_up = None
                if px and op and sig and sig > 0:
                    move = px / op - 1.0
                    z = move / (sig * math.sqrt(max(t_left, 0.5)))
                    p_up = 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
                b0, b1 = await asyncio.gather(
                    self.book(sess, win["tokens"][0]),
                    self.book(sess, win["tokens"][1]))
                out({"type": "snap", "slug": win["slug"], "step": win["step"],
                     "t_left": round(t_left, 2), "b_px": px, "b_open": op,
                     "move": move, "sigma1s": sig, "z": z, "p_up": p_up,
                     "up": b0, "down": b1})
            near = any(t <= 60 for _, t in active)
            await asyncio.sleep(CADENCE_NEAR if near else CADENCE_FAR)

    async def main(self):
        conn = aiohttp.TCPConnector(limit=8)
        async with aiohttp.ClientSession(connector=conn, headers=HDR,
                                         timeout=aiohttp.ClientTimeout(total=15)) as sess:
            out({"type": "start", "pid": os.getpid()})
            await asyncio.gather(self.spot.run(), self.discover(sess),
                                 self.resolve(sess), self.sample(sess))

if __name__ == "__main__":
    asyncio.run(Runner().main())
