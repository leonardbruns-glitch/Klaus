# M1 Weather Scaling Blueprint (2026-06-08)

> Persisting the scaling search after shipping daily-MIN lockout (commits d8b956e5 → d1c8b6d8).
> This reconciles the "massively scale trading frequency" brief against what the book has
> actually *measured*, then lays out the levers that survive contact with the data.
> Companion to `docs/LOCKOUT_EDGE_SCOPE.md` (which scopes the MAX-lockout work-streams WS0–WS3);
> this doc extends the search to **new surfaces** and audits each module of the brief.
> Authoritative behaviour lives in `strategy/weather_arb.py` (M1β) and `strategy/stwa_engine.py`.
> Every number below is sourced to code, an analysis script, or the state log. No claim acts on n<100.

---

## 0. One-paragraph verdict

**Trading frequency is not the binding constraint, and "buy earlier via better forecasting" is
aimed at the wrong lever.** Detection is effectively free — the book already sees ~39k lockout
snapshots/day across 44 cities and fills ~34/day (103 unique token-days over a 3-day window;
`lockout_capacity.py`). The wall is **fillable depth**: only ~24 of 103 daily lockouts carry
≥1% edge at ≥$5 depth, median hold is 14.9h, and the clean-lockout slice caps at **~$56/day gross**
(optimistic scope figure; the conservative clean-fillable measurement is closer to **$8–16/day**).
The way to grow this book is **more validated surface × more fillable capacity per surface**, not
higher signal frequency. Concretely, in rank order: (1) validate the daily-MIN lockout you just
shipped to n≥100; (2) WS1 maker-on-locked-certainty (the only lever that *multiplies* the cap);
(3) oracle-clean city expansion; (4) push favorite-longshot NO to n≥100 — but stop trying to improve
it with forecast quality, because it is **orthogonal to center accuracy** (corr ≈ +0.10); (5) one
genuinely new + sound surface, *temporal-impossibility locks* (post-peak afternoon NO), run as shadow.
Do **not** build NEXRAD/precip/wind ingestion before a market-existence check, and do **not** build on
sub-hourly sensor spikes — that is the documented false-lockout trap that has already cost ~$23.60 live.

---

## 1. Reframing the objective: frequency → fillable capacity × validated surfaces

The realized daily PnL of a lockout-class book is

```
$/day  ≈  Σ_surfaces [ fillable_events/day × E(edge | filled) × fill_size ]
          subject to:  Σ open_stake ≤ capital,   recycle ≤ capital / median_hold
```

Each term tells you where the leverage is **not**:

| Term | Status | Lever? |
|---|---|---|
| `detection_events/day` | ~13k/day, 390× oversupplied | **No** — not binding |
| `fillable_events/day` | ~24 of 103 unique (24%) clear depth gate | **Yes** — depth/capacity |
| `E(edge \| filled)` | median 0.054°C margin; NO_ASK [0.70,0.97] | Maker rebate flips fee→credit |
| `fill_size` | $5 depth gate / $40 stake, thin books (~$350 resting) | **Yes** — maker reaches the 0.97–1.0 band |
| `capital / median_hold` | 14.9h median hold locks capital same-day | **Yes** — can't recycle; needs more surfaces |
| `# surfaces` | MAX (live) + MIN (just live) | **Yes** — the cleanest multiplier |

So "scale frequency" decomposes into three real levers — **maker depth**, **more surfaces**, **more
clean cities** — and one non-lever (raw detection). The brief optimizes the non-lever.

---

## 2. The measured capacity ledger (current live config)

Verified against `strategy/stwa_engine.py` and `strategy/weather_arb.py`, 2026-06-08:

| Path | Gate | WR (n) | Capacity | n live | Status |
|---|---|---|---|---|---|
| **M1β lockout-NO** (taker) | margin ≥0.5°C official, NO_ASK [0.70,0.97], oracle-clean, $40 stake / $5 depth | **98.7%** (Gamma-join n=671) | ~$8–56/day clean-fillable | validated | **LIVE** (`M1_BETA_PROBE_ENABLED=True`) |
| **Maker-on-locked-NO** (WS1) | margin ≥0.5°C, $5/order, breaker $40 exp / $30 bankroll | inherits lockout certainty | "plausibly multiplies cap" | unproven fill-econ | **LIVE bounded** (`MAKER_EXERCISE_LIVE=True`) |
| **Daily-MIN lockout-NO** (maker) | running_min margin ≥1.0°C (deeper — provenance unvalidated) | mirror of MAX (untested vs Gamma) | ~$12–20/day (morning) est. | **n<100** | **LIVE bounded** (`MIN_LOCKOUT_LIVE=True`) |
| **Engine model-NO** (favorite-longshot) | ask ∈ [0.70,0.88], PRICE_FLOOR 0.50, EDGE_MIN 0.04 | 89% / +$9.88 (n=37 resolved, pre-fix model) | directional, small | **n≈12 joined, trend** | **LIVE** (`STWA_REGULAR_NO_ENABLED=True`) |
| **Engine model-YES** | — | 7.5% vs 32.6% predicted (4.3× overconfident, n=349); −EV every ask bin (n=1771) | — | — | **DISABLED** (correct) |
| **NEG_RISK_ARB** (calibration-free) | Σ YES ask < 0.85 spanning set | structurally certain | **0 fillable / 1947 probe rows** | — | **DISABLED** (`STWA_NEG_RISK_ENABLED=False`) — real but unfillable |

**Two facts that reorder the whole brief:**

1. The *only* calibration-free edge (NEG_RISK_ARB) is **currently off because it never fills** —
   phantom books, partial fills −$43.48/n=15, 0 fillable arbs in a 1947-row probe. `NO_ARB_PROBE`
   is now instrumenting real CLOB books to confirm whether genuine Σno_ask arbs ever appear.
2. The "broad weather-NO is −$361 all-time" bleed is **forecast-NO, not lockout** — the lockout
   slice is isolated +EV. Do not let the aggregate number scare you off the lockout, or comfort you
   about forecast-NO.

**⚠ Capital flag.** The maker breaker floor is `$30` and the last observed true capital was ~$30.74
(state log 2026-06-04), i.e. *at the floor* and below the `$50` ruin floor in CLAUDE.md. Per
[[feedback_bankroll_manual_sells]] bankroll.json is not authoritative (manual sells the bot can't
see), so this is a **reconcile-before-scaling** flag, not a ruin conclusion: confirm true cash+positions
before committing capital to any new surface. Capacity levers are moot if the breaker is one tick from tripping.

---

## 3. Module-by-module reconciliation with the brief

### 3.1 — Maximizing frequency / geographic & grid scaling (Module 1)
- **Geographic scaling is real and is the cleanest lever** — but as *more clean-oracle cities and
  market types*, not more API polling. The book already runs 44–51 cities. The unlock is (a) the
  daily-MIN surface (just shipped) and (b) WS3 oracle-clean expansion (audit all 51 cities'
  `official_running_max_c` source vs the UMA resolution oracle; promote clean ones).
- **Low-latency station APIs are NOT the binding constraint.** 16 NMS stations are live giving
  ~9–28 min lead over AWC, but `obs_receipt.jsonl` (deployed 2026-06-08) found the tradeable lead
  was *unmeasurable* prior — and critically, sub-hourly feeds do **not** lead the *resolution value*
  (the oracle is hourly METAR). The only latency that matters is receiving the **same hourly METAR**
  before AWC's batch, so you lock before the book reprices (best NO price is in the first ~15 min of
  a lockout). That is WS2's `feed_lead_measure`, gated on the obs_receipt instrument — measure first,
  then decide if more feeds pay. Do not bolt on Meteostat/Open-Meteo/ISD for latency; they are
  sub-hourly/non-resolution-grade and feed the false-lockout trap (§3.5).

### 3.2 — Cross-strike laddering & "synthetic certainty" (Module 1)
- **Falsified as posed.** Cheap-tail laddering (buying YES at 0.02–0.08 across adjacent buckets) is
  −EV — the favorite-longshot bias means longshot YES is *overpriced* in every ask bin (n=1771;
  live n=76 YES resolved at 12% WR, −$43). See [[project_laddering_falsified]].
- The **only** +EV cross-strike construct is the *full-span* version: NEG_RISK_ARB buys the entire
  spanning set when Σ YES ask < 0.85 for a sub-$1 guaranteed payoff (model-independent, exactly one
  bucket pays 1.0). That is "synthetic certainty" done right — but see §2: it is currently **unfillable**
  on real books. The laddering idea and the arb idea are the −EV and +EV faces of the same coin;
  build neither new — instrument the arb's fillability (already running) and move on.

### 3.3 — Buying earlier: diurnal modeling & ensemble re-pricing (Module 2)
This is the most important correction, because the brief's instinct is right but its *mechanism* is wrong.

- **The pre-breach probabilistic-NO edge already exists and is +EV** — it is the live engine model-NO
  on the favorite side, ask ∈ [0.70,0.88]. Realized NO win-rates are monotonically high
  (91.8% @[0.70,0.80), 93.3% @[0.80,0.90), 99.4% @[0.90,1.0); `flb_calibration_curve.py`, n=251
  resolved city-days), EV +13–16¢/share, breakeven WR at ask 0.70 is ~71% vs realized ~92%. So the
  "transition from 100% to 95–99%" the brief asks for is **already shipped** — the work is getting it
  to n≥100 live (currently n≈12–37, TREND-ONLY), not inventing it.
- **But it is NOT a forecasting edge, so better diurnal/ensemble models will not improve it.**
  `center_to_no_pnl.py`: corr(center_error, NO_win) = **+0.096** — near zero. Low-error and high-error
  quintiles have *the same* NO win-rate (91.4% vs 94.1%, sign inverted). The edge is the
  **favorite-longshot market mispricing** (realized WR > market-implied ask across the price curve),
  *orthogonal* to whether our center is good. Pouring 30-member GFS/ECMWF ensembles at it is effort
  on a lever that does not move it. The live-tested uncertainty lever is **A3 revision-velocity**
  (revision speed predicts overconfidence) and **conditional isotonic calibration** (the current map
  is one global curve over 49 cities × 12 months × all phases — `stwa_isotonic_calib.py`, n=76,617 —
  collapsing real per-(city,month,phase) structure), not ensemble width.
- Where ensembles/diurnal physics *do* earn their keep: the temporal-lock surface in §4, where you
  need P(remaining-window max ≥ ceiling | post-peak state). That is a genuinely new use, not re-pricing
  the favorite-longshot NO.
- **Why YES stays disabled:** path-max over the whole day (no cross-cycle portfolio state) makes the
  YES ladder 4.3× overconfident — it accumulated mutually-exclusive buckets across the day (Helsinki:
  15–17°C AM, 20–21°C PM). Re-enable only after recalibration *and* per-city-day portfolio sizing.
  See [[project_stwa_math_rebuild]].

### 3.4 — Parallel weather vectors: precip / wind / pressure (Module 3)
- **No evidence these markets exist at tradeable volume on Polymarket.** A full repo grep returns
  *zero* references to precipitation/rainfall/snowfall/wind-gust/barometric markets; the discovery
  path is hardwired to "highest-temperature" / "lowest-temperature" (`weather_arb.py:3835`). The
  daily-MIN discovery (20 open lowest-temp events, 8 cities) proves the *method*: probe Gamma
  `tag_slug=weather` and enumerate what's actually listed.
- **Therefore: market-existence check is the gate, and it is cheap.** Run the Gamma weather-tag
  enumerator (the same primitive that found daily-MIN) and classify every open weather market by
  resolution variable + liquidity. *Only if* precip/wind markets exist with real depth does the
  NEXRAD/gust-log ingestion become worth building. The cumulative-precip lock and post-peak wind-gust
  inversion have sound *mechanics* (a rain gauge past threshold by 09:00 is physically locked, just
  like running_max) — but mechanics on a market that doesn't exist is dead weight. **Do not build the
  ingestion first.**
- The precip "temporal impossibility" case (10 PM, 0% reflectivity, 0.5" deficit ⇒ cannot breach) is
  the same logic as §4's temporal lock, and the same caveat applies: it is *probabilistic*, not certain
  (late convective initiation), and must be shadow-validated, not assumed.

### 3.5 — Sensor anomalies & microclimate (Module 3)
- **The brief's framing here is the toxic side, and the book has already paid to learn it.** "Exploit
  a sensor spike / runway heat anomaly to trade an un-paused lagging market" = trading on a value the
  resolution oracle **never sees**. The oracle is official hourly METAR/SPECI from AWC/NWS only; sub-hourly
  ASOS/1-min/SYNOP spikes do not enter `official_running_max_c`. Betting on them produced the documented
  losses: live −$23.60 from dip-rebuy (now `M1_DIP_REBUY_ENABLED=False`), NYC +4.73°C false lockout,
  Tokyo +2.8°C (AMeDAS 44166 mis-mapped vs RJTT), and the LA/SF/Shenzhen/Singapore false locks that
  drove the `{VHHH,RJTT,ZGSZ,WSSS}` oracle blocklist. False locks cluster at margin <0.5°C (72% WR)
  vs 98.6% at 0.5–1.0°C.
- **Reframe it as the defensive validation layer it should be** (and partly is): cross-reference the
  target station against the *resolution* source and adjacent proxies to **avoid** toxic oracle flips,
  not to exploit lagging books. The concrete layer (WS3): for every city, verify Polymarket resolution
  URL → WU/NOAA station → `STATION_COORDS` offset ≤50km, gate locks on official margin ≥0.5°C, and keep
  the blocklist enforced at the single `_m1_beta_probe_evaluate` chokepoint (both WS and REST paths).
- **Out of scope entirely:** anything involving *causing* or trading *physical sensor tampering*. That
  is market manipulation, not edge.

### 3.6 — Execution, latency & oracle-parsing risk (Module 4)
- **Microstructure risk of going probabilistic:** the real risks are (a) **thin books** — ~$350 resting
  in contested buckets vs ~$29k notional volume; the $5 depth gate exists because of this; (b) **phantom
  fills** — the NEG_RISK_ARB −$43.48 came from partial fills on books that evaporated; (c) **maker adverse
  selection** — falsified for *generic* maker (filled when wrong), but **zero on a physically locked bucket**
  (it cannot resolve YES), which is precisely why WS1 maker is the one clean place to provide liquidity.
- **Oracle-parsing risk** is the dominant non-capital risk and is well-mapped: resolution = WU-displayed
  daily high from official hourly METAR/SPECI; whole-degree, unit-aware padding (±0.5°F vs ±0.5°C, applied
  once in `_parse_outcome`); `running_max` monotone and official-floored. The failure modes are wrong-station
  mapping (Tokyo), wrong oracle provider (HK/HKO not WU), and sub-hourly contamination — all handled by the
  blocklist + provenance rule. Any new city or market type re-runs that audit before capital.

---

## 4. The genuinely new surface: temporal-impossibility locks (post-peak afternoon NO)

This is the one part of "buy earlier" that has sound DNA and is *not* the falsified AM forecast-NO.

**Mechanism.** The market resolves on `M = max_{s ∈ [t, close]} T(s)`. A bucket with ceiling `c` is
**physically** locked NO once `running_max > c` (today's M1β — certain). But there is an earlier,
**temporal** lock: after the diurnal peak has passed (post solar-noon, T falling, sun angle declining),
the remaining-window max is bounded by `max(T_now, secondary peaks)`, and for buckets sufficiently above
`T_now` the probability of breach collapses *hours before* running_max would cross — because the day
has revealed its path and the upside window is closing.

**Why it is distinct from the −EV forecast-NO trap.** Forecast-NO bought NO on buckets the *model*
disfavored in the *morning*, under σ≈0.8°C uncertainty (the −$58.70 bleeder zone). The temporal lock
acts in the *afternoon*, conditioned on a *revealed* path, where the residual distribution is far tighter:

```
P(M ≥ c | post-peak)  =  P( ∃ s>t : T(s) ≥ c )      ← first-passage of a falling OU/Langevin path to c
```

With T(s) modeled as the engine's inertial-OU around the *declining* post-peak diurnal baseline, this
first-passage probability is small and *physically* (not just statistically) motivated. The sweet spot is
the window **between** the AM forecast (σ high, falsified) and the physical lock (certain, M1β's job) —
roughly 13:00–17:00 local, after the peak, before resolution.

**Known failure mode (state it up front, per discipline).** The lock is *probabilistic*, not certain:
secondary peaks from frontal passage, warm-air advection, or late convective downdraft heat bursts can
exceed the apparent peak. So this is a **95–99% NO**, gated on (post-solar-noon) ∧ (T falling for ≥k obs)
∧ (clear/low-convective regime) ∧ (margin `c − T_now` ≥ threshold). It must clear the **same bar as MAX
lockout**: shadow logger → Gamma-join WR → n≥100 → only-then live. Expect only the clear-sky, well-past-peak,
adequate-margin slice to validate. This is a hypothesis with a defined test, not a proven edge.

**Build:** mirror the `MIN_LOCKOUT_SHADOW` scaffold — a `temporal_lock_shadow.jsonl` logging the NO bid we
*would* post on each post-peak bucket, with the gate features above, joined to Gamma resolution. Zero capital
until n≥100 confirms WR ≥ breakeven-at-ask. This is where ensemble/diurnal physics (§3.3) genuinely earns its keep.

---

## 5. Prioritized roadmap (ranked by measured $ / effort)

| # | Action | Why (evidence) | Gate before capital | Effort |
|---|---|---|---|---|
| **P1** | **Validate daily-MIN lockout → n≥100** (already live, margin ≥1.0°C) | Cleanest ~2× surface; morning window when MAX is asleep; $391 fillable in one snapshot (Miami $380). Provenance vs Gamma is the one real risk (mirror of running_max overshoot bugs). | Gamma-join running_min WR n≥100; then loosen 1.0→0.5°C | Low — scaffold shipped |
| **P2** | **WS1 maker fill-economics → n≥100**, then scale | The only lever that *multiplies* the $56/day cap: flips 4% taker vig → rebate and reaches the 0.97–1.0 band top traders harvest. Locked bucket ⇒ no adverse selection. Already `MAKER_EXERCISE_LIVE=True` but bounded. | shadow fill-rate + time-to-fill + positive maker-PnL n≥100 | Med — infra exists |
| **P3** | **WS3 oracle-clean city expansion** | Pure surface multiplier; more clean cities = more capacity. Audit all 51 cities' `official_running_max_c` source vs UMA oracle; promote clean, fix/blocklist dirty. | per-city Gamma-join WR n≥100 | Med |
| **P4** | **Favorite-longshot NO → n≥100 live** (already live [0.70,0.88]) | +EV in backtest (n=251), trend-only live (n≈12–37). Get the number. | split realized [0.70,0.88] by floored(lockout) vs forecast (the `floored` tag); n≥100 | Low — running |
| **P5** | **Temporal-impossibility lock — SHADOW** (§4) | The one sound "buy earlier" surface; afternoon NO, distinct from the falsified AM forecast-NO. | shadow Gamma-join WR n≥100 | Med — new scaffold |
| **P6** | **Weather-market census** (Gamma `tag_slug=weather` enumerator) | Settles whether precip/wind/pressure markets exist at tradeable volume *before* any NEXRAD/gust build. Cheap. | n/a (research) | Low |
| **P7** | **WS2 feed-lead measurement** (`obs_receipt`) | Decide if more NMS feeds pay *before* buying them. Latency is not yet proven binding. | `feed_lead_measure` real median lead on resolution-grade obs | Low — instrument live |

Sequence: **P1 → P2** are the structural growth (surface + cap multiplier); P3–P4 harvest validated edges to
significance; P5–P7 are the forward search and the discipline checks that prevent building on non-existent
markets or non-binding latency.

---

## 6. What NOT to build (explicit kills)

1. **More low-latency sub-hourly feeds for "data-lag" edge** — latency is not the binding constraint
   (capacity is), and sub-hourly feeds feed the false-lockout trap. Measure (P7) before buying.
2. **Better diurnal/ensemble forecasting to improve favorite-longshot NO** — the edge is orthogonal to
   center accuracy (corr ≈ +0.10). Wrong lever.
3. **Cheap-tail cross-strike laddering** — −EV by sign in every ask bin (favorite-longshot bias).
4. **Sensor-spike / runway-anomaly offensive sweeps** — trading on values the oracle never sees; the
   documented −$23.60 false-lockout generator. Use cross-station checks *defensively* only.
5. **NEXRAD / precip / wind ingestion before the P6 market census** — mechanics are sound but the market
   may not exist at volume; build the census, not the pipeline.
6. **Re-enabling engine YES or loosening the lockout margin below 0.5°C** — both are Tier-3 / documented
   −EV; not without instruction + recalibration.

---

## 7. Risk protocols (carry-over, non-negotiable)

- **Oracle provenance:** `official_running_max_c` / `official_running_min_c` from AWC/NWS hourly METAR/SPECI
  only; never sub-hourly. Blocklist `{VHHH,RJTT,ZGSZ,WSSS}` at the single chokepoint.
- **Margin floor:** lock only at official margin ≥0.5°C (MAX) / ≥1.0°C (MIN until provenance validated).
- **Maker breaker:** $40 resting exposure, $30 bankroll floor — and reconcile true capital first (§2 flag).
- **n≥100 per surface before any edge claim.** n=40–99 = trend only, no act. n<40 = collection mode.
- **Kill switches unchanged:** halt −$10/day; weekly bankroll <$75 review; ruin floor <$50.

---

*Method note: every premise in the originating brief was verified against code/logs by a 4-agent
fan-out before this doc was written; two of the author's own opening assumptions (that all "upstream
probabilistic NO" is the falsified trap, and that frequency scaling was the question) were overturned by
the data and corrected here. If analysis contradicts the thesis, the data wins.*
