"""UPDOWN-SNIPER live executor — owner-authorized 2026-07-13 ("can we start now").

Policy (v1, from tape calibration Jul5-7 + Jul11-13, state_log 10:35 UTC):
  Buy the decided side of a BTC updown window ONLY when ALL hold:
    t_left in [T_MIN, T_MAX[step]]
    |binance move vs window open| >= MOVE_FLOOR   (basis guard)
    p_model = Phi(move/(sigma1s*sqrt(t_left))) >= P_MIN
    best ask in [ASK_MIN, ASK_MAX[step]]          (market-confirmation gate)
    edge = p_model - ask - 0.07*ask*(1-ask) >= EDGE_MIN
    ask depth >= clip shares
  Taker limit_buy at ask (crosses, cancels on no-fill). Hold to redemption. Never sell.
Rails: $5 clips, max $15 open at cost, 60 fires/day, day-halt on realized <= -$6
  or 3 consecutive losses, kill file logs/UPDOWN_STOP, reserve $2.
Run: UPDOWN_LIVE=1 (default shadow-print only). systemd: klaus_updown_sniper.service
Log: logs/updown_sniper.jsonl  State: logs/updown_sniper_state.json
"""
import asyncio, json, math, os, sys, time
import aiohttp

sys.path.insert(0, "/root/Klaus")
from strategy.updown_shadow import Spot, gj, GAMMA, CLOB, HDR

LIVE = os.environ.get("UPDOWN_LIVE", "0") == "1"
LOG = "/root/Klaus/logs/updown_sniper.jsonl"
STATE = "/root/Klaus/logs/updown_sniper_state.json"
STOP_FILE = "/root/Klaus/logs/UPDOWN_STOP"

T_MAX = {900: 120, 300: 60}  # 5m 30->60s 2026-07-15: gate-sweep added slice 18/18 true-label;
                             # SIG_FLOOR forces >=6.5bp for p>=0.99 at t_left>30s, so no
                             # low-certainty cell opens (the p<0.99 & >30s combo cell lost)
T_MIN = 5.0
ASK_MIN = 0.90
ASK_MAX = {900: 0.97, 300: 0.99}
P_MIN = 0.99
MOVE_FLOOR = 0.0004          # 6->4 bps 2026-07-15: gate-sweep added slice 20/20 true-label;
                             # basis guard keeps 4x margin over observed <1bp Chainlink/
                             # Binance basis; certainty still gated by P_MIN + SIG_FLOOR
SIG_FLOOR = 0.00005          # 0.5bp/sqrt(s) floor on sigma1s: certainty built on a
                             # calmer estimate is sigma-junk (2026-07-13 15m loss:
                             # sig1s 0.195bp -> p 0.9996, then a 13bp reversal = 6z)
EDGE_MIN = 0.010
CLIP_USD = 2.0               # 5.0 -> 2.0 2026-07-14: gate-collection mode — extends
                             # runway to the n>=100 gate; wallet-truth realized since
                             # go-live is negative (-$5.48 incl. untracked 10:49 fill),
                             # so collect the gate at minimum size, not harvest size.
                             # NOTE 07-15: CLOB 5-share buy minimum means the true
                             # minimum fire is 5 shares = $4.50-4.95 at ask 0.90-0.99;
                             # $2 is unreachable. est_cost in signal_loop carries the
                             # real number into the depth + reserve gates.
RESERVE_USD = 20.0           # 2.0 -> 20.0 2026-07-14: owner floor waiver (07-13,
                             # equity $39.40) has no lower bound — this stops fires at
                             # wallet <$22 so one path cannot burn to ruin; $20 matches
                             # the owner's sprint-ladder hard cash reserve
MAX_OPEN_COST = 15.0
MAX_FIRES_DAY = 60
DAILY_STOP_LOSS = 4.5        # 6.0 -> 4.5 2026-07-15: true clip is $4.50-4.95 (5-share
                             # CLOB min), so one full-clip loss must end the day —
                             # $4.9 = 14% of $34.9 equity, the engine daily-loss rail
MAX_CONSEC_LOSS = 3

def log(rec):
    rec["ts"] = round(time.time(), 3)
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(rec, flush=True)

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"day": "", "fires": 0, "consec_loss": 0, "realized": 0.0, "open": {}}

def save_state(st):
    json.dump(st, open(STATE, "w"))

class Sniper:
    def __init__(self):
        self.spot = Spot()
        self.windows = {}
        self.done = set()
        self.st = load_state()
        self.om = None

    def day_roll(self):
        d = time.strftime("%Y%m%d", time.gmtime())
        if self.st["day"] != d:
            self.st.update({"day": d, "fires": 0, "consec_loss": 0, "realized": 0.0})
            save_state(self.st)

    def rails_ok(self):
        self.day_roll()
        if os.path.exists(STOP_FILE):
            return "stop_file"
        if self.st["fires"] >= MAX_FIRES_DAY:
            return "fires_cap"
        if self.st["realized"] <= -DAILY_STOP_LOSS:
            return "daily_stop"
        if self.st["consec_loss"] >= MAX_CONSEC_LOSS:
            return "consec_loss"
        if sum(p["cost"] for p in self.st["open"].values()) >= MAX_OPEN_COST:
            return "open_cap"
        return None

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
                                self.windows[slug] = {"slug": slug, "step": step,
                                    "w": w, "end": w + step, "tokens": toks,
                                    "outcomes": ocs, "open_px": None}
            await asyncio.sleep(20)

    async def book(self, sess, token):
        b = await gj(sess, f"{CLOB}/book?token_id={token}")
        try:
            asks = sorted((float(a["price"]), float(a["size"])) for a in b.get("asks") or [])
            return asks[0] if asks else (None, None)
        except Exception:
            return (None, None)

    async def fire(self, win, side_idx, side, ask, p_model, t_left):
        from execution.order_manager import Direction
        token = win["tokens"][side_idx]
        res = await self.om.limit_buy(token, ask, CLIP_USD, Direction.BUY_YES,
                                      price_ceiling=round(min(ask + 0.005,
                                                              ASK_MAX[win["step"]]), 3))
        status = str(getattr(res, "status", "")) if res else "None"
        filled = res is not None and "FILLED" in status
        shares = float(getattr(res, "total_size", 0.0) or 0.0)
        fpx = float(getattr(res, "avg_fill_price", 0.0) or ask)
        cost = shares * fpx
        log({"event": "FIRE", "slug": win["slug"], "side": side, "ask": ask,
             "p_model": round(p_model, 4), "t_left": round(t_left, 1),
             "status": status, "shares": shares, "fill_px": fpx,
             "cost": round(cost, 2)})
        if filled and shares > 0:
            self.st["fires"] += 1
            self.st["open"][win["slug"]] = {"side": side, "token": token,
                                            "shares": shares, "cost": round(cost, 2)}
            save_state(self.st)

    async def signal_loop(self, sess):
        while True:
            now = time.time()
            for win in list(self.windows.values()):
                t_left = win["end"] - now
                if win["w"] <= now < win["end"] and win["open_px"] is None:
                    win["open_px"] = self.spot.at(win["w"])
                if not (T_MIN <= t_left <= T_MAX[win["step"]]):
                    continue
                if win["slug"] in self.st["open"] or win["slug"] in self.done:
                    continue
                px, op, sig = self.spot.px, win["open_px"], self.spot.sigma1s()
                if not (px and op and sig and sig > 0):
                    continue
                sig = max(sig, SIG_FLOOR)
                move = px / op - 1.0
                if abs(move) < MOVE_FLOOR:
                    continue
                z = move / (sig * math.sqrt(max(t_left, 0.5)))
                p_up = 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
                side_idx, p_model = (0, p_up) if move > 0 else (1, 1.0 - p_up)
                if p_model < P_MIN:
                    continue
                side = win["outcomes"][side_idx]
                ask, sz = await self.book(sess, win["tokens"][side_idx])
                if ask is None or not (ASK_MIN <= ask <= ASK_MAX[win["step"]]):
                    continue
                edge = p_model - ask - 0.07 * ask * (1 - ask)
                # CLOB enforces a 5-share buy minimum: order_manager snaps a
                # CLIP_USD stake UP to 5 shares, so true cost = max(CLIP, 5*ask)
                # ($4.50-4.95 at ask 0.90-0.99). Gate depth and cash on that,
                # not on the nominal clip (07-15: every post-fix fill was 5.0 sh).
                est_cost = max(CLIP_USD, 5.0 * ask)
                if edge < EDGE_MIN or sz * ask < est_cost:
                    continue
                why = self.rails_ok()
                if why:
                    log({"event": "skip_rails", "why": why, "slug": win["slug"]})
                    continue
                bal = await asyncio.to_thread(self.om.fetch_usdc_balance) if LIVE else 99.0
                if bal is None or bal - est_cost < RESERVE_USD:
                    log({"event": "skip_cash", "balance": bal})
                    continue
                if LIVE:
                    await self.fire(win, side_idx, side, ask, p_model, t_left)
                else:
                    log({"event": "DRY_FIRE", "slug": win["slug"], "side": side,
                         "ask": ask, "p_model": round(p_model, 4),
                         "t_left": round(t_left, 1), "edge": round(edge, 4)})
                    self.st["open"][win["slug"]] = {"side": side, "token": "",
                                                    "shares": CLIP_USD / ask,
                                                    "cost": CLIP_USD, "dry": True}
                    save_state(self.st)
            await asyncio.sleep(0.7)

    async def resolve_loop(self, sess):
        while True:
            now = time.time()
            for slug, win in list(self.windows.items()):
                if now < win["end"] + 20:
                    continue
                evs = await gj(sess, f"{GAMMA}/events?slug={slug}")
                winner = None
                for ev in evs or []:
                    for m in ev.get("markets") or []:
                        try:
                            op = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                        except Exception:
                            op = []
                        # exact 1/0 only: pre-resolution live prices also sum to 1.0
                        # (2026-07-13 bug booked winner="Down" on 84/196 windows)
                        if sorted(op) == [0.0, 1.0]:
                            winner = win["outcomes"][0] if op[0] == 1.0 else win["outcomes"][1]
                if winner is None:
                    # never book a position off anything but a true resolution;
                    # positionless windows get cleaned up after 15 min
                    if slug not in self.st["open"] and now > win["end"] + 900:
                        self.done.add(slug)
                        self.windows.pop(slug, None)
                    continue
                pos = self.st["open"].pop(slug, None)
                if pos:
                    won = pos["side"] == winner
                    pnl = (pos["shares"] - pos["cost"]) if won else -pos["cost"]
                    if not pos.get("dry"):
                        self.st["realized"] = round(self.st["realized"] + pnl, 2)
                        self.st["consec_loss"] = 0 if won else self.st["consec_loss"] + 1
                    log({"event": "SETTLE", "slug": slug, "winner": winner,
                         "side": pos["side"], "won": won, "pnl": round(pnl, 2),
                         "dry": bool(pos.get("dry")),
                         "day_realized": self.st["realized"],
                         "consec_loss": self.st["consec_loss"]})
                    save_state(self.st)
                self.done.add(slug)
                self.windows.pop(slug, None)
            while len(self.done) > 3000:
                self.done.pop()
            await asyncio.sleep(10)

    async def main(self):
        if LIVE:
            from execution.order_manager import OrderManager
            self.om = OrderManager()
            try:
                await self.om.start()
            except Exception as e:
                log({"event": "om_start_warn", "err": str(e)[:200]})
        conn = aiohttp.TCPConnector(limit=8)
        async with aiohttp.ClientSession(connector=conn, headers=HDR,
                                         timeout=aiohttp.ClientTimeout(total=15)) as sess:
            log({"event": "start", "live": LIVE, "pid": os.getpid()})
            await asyncio.gather(self.spot.run(), self.discover(sess),
                                 self.signal_loop(sess), self.resolve_loop(sess))

if __name__ == "__main__":
    asyncio.run(Sniper().main())
