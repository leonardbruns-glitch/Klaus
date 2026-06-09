"""M9 — Reflexive Information Propagation Arbitrage (RIPA).

Hypothesis
----------
Polymarket lags Binance trade-flow information, and the lag is *state-dependent*:
it is largest during **reflexive** information-propagation regimes (one-sided
aggressive flow, informed VPIN, slow LP updates, extreme OB imbalance).  RIPA
identifies those regimes and trades the Binance-implied mispricing **before
propagation completes**, exiting on convergence.

    ExpectedEdge_t = |Gap_t| · P(reflexive_t) · FlowExcitation_t      (Step 5)

and trades only the top-decile score that also clears the toxicity-aware cost.

Pipeline (matches the spec)
---------------------------
1. **Binance-implied fair** — P_fair(up) = Φ(r / (σ·√T_left)) from the causal
   intrawindow lead r and a realized-vol σ (martingale-drift form; the spec's
   μT/(σ√T) with μ taken from the lead).
2. **Gap** = P_fair − P_book (YES mid).
3. **4-state Gaussian HMM**, fit UNSUPERVISED, NO manual labels.  The reflexive
   state is the one whose occupancy precedes the largest realized *gap
   convergence* (measured on causal price movement in warmup — no resolution
   labels).
4. **Flow excitation H_t** — Hawkes-style self-excitation, here the spec's
   sanctioned **burst-intensity proxy**: H_t = squash( z(|binance velocity|) +
   z(|ΔOBI|) + z(VPIN) ), normalized to [0,1].
5. **Opportunity score** = |Gap|·P(reflexive)·H_t.
6. **Entry** — top-decile score (q90 from warmup): Gap>0 ⇒ BUY_YES, Gap<0 ⇒ BUY_NO.
7. **Toxicity filter** — require |Gap| > Cost_t + margin, Cost = fee + ½·spread +
   k·VPIN.
8. **Exit** — convergence |Gap|<ε, OR 80% of the entry-time remaining window
   elapsed, OR reflexive→efficient state change, OR VPIN toxicity spike.

DATA CAVEAT (honest): of the Step-3 feature set, only VPIN, OB-imbalance,
spread, quote-age exist as CONTINUOUS Tier-1 series.  Liquidation pressure,
funding, and Coinbase divergence exist only as point snapshots in trades.jsonl
(data blueprint §7), not as streams on_step can read — so they are OMITTED from
the live feature vector and the excitation proxy.  Re-add them only after a
continuous backfill exists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.schema import MarketTimelineRow, WindowPanel
from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy
from .s2_hmm_regime import GaussianHMM

_EPS = 1e-12


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass
class RipaParams(StrategyParams):
    n_states: int = 4              # Efficient / Lagging / Reflexive / Toxic
    conv_horizon: int = 8          # steps ahead to measure gap convergence (warmup)
    score_q: float = 0.90          # top-decile opportunity-score gate
    margin: float = 0.02           # extra cushion over toxicity cost
    vpin_cost_k: float = 0.05      # VPIN -> cost scaling
    eps_converge: float = 0.02     # |Gap| below this -> exit on convergence
    vpin_spike: float = 0.85       # VPIN above this -> toxicity-spike exit
    time_decay_frac: float = 0.80  # exit after this frac of entry-remaining elapsed
    min_secs_left: float = 30.0
    max_secs_left: float = 285.0
    vol_floor_persec: float = 2e-5
    hist_steps: int = 30           # causal step-feature window for the filter
    warmup_fit_rows: int = 30000   # cap rows used to FIT the HMM
    warmup_eval_panels: int = 200  # cap panels used for reflexive-state + q90
    max_position_frac: float = 0.10
    per_window_budget_frac: float = 0.20
    edge_min: float = 0.0          # gating is via score/cost, not edge_min


@register_strategy("ripa")
class RipaStrategy(Strategy):
    params_cls = RipaParams

    def __init__(self, params: Optional[RipaParams] = None) -> None:
        super().__init__(params)
        self.params: RipaParams
        self._models: Dict[str, GaussianHMM] = {}
        self._reflexive: Dict[str, int] = {}
        self._q90: Dict[str, float] = {}
        # excitation z-score stats per asset: means/stds of [ |vel|, |dOBI|, vpin ]
        self._exc_mu: Dict[str, np.ndarray] = {}
        self._exc_sd: Dict[str, np.ndarray] = {}
        # per-held-token: entry seconds_to_resolution (for time-decay exit)
        self._entry_sl: Dict[str, float] = {}
        self._acted: set = set()

    # ================= feature builders (causal) =======================
    @staticmethod
    def _f_vec(r: MarketTimelineRow) -> Optional[List[float]]:
        """Per-step HMM feature: [VPIN, |OBI|, spread_bps, quote_age_s]."""
        if r.spread_bps is None and r.vpin_score is None:
            return None
        return [
            float(r.vpin_score) if r.vpin_score is not None else 0.0,
            abs(float(r.ob_imb_top3)) if r.ob_imb_top3 is not None else 0.0,
            float(r.spread_bps) if r.spread_bps is not None else 0.0,
            float(r.ob_quote_age_ms) / 1000.0 if r.ob_quote_age_ms is not None else 0.0,
        ]

    def _seq(self, rows: Sequence[MarketTimelineRow]) -> np.ndarray:
        out = [v for v in (self._f_vec(r) for r in rows) if v is not None]
        return np.array(out, dtype=float) if out else np.empty((0, 4))

    def _fair_up(self, rows: Sequence[MarketTimelineRow], secs_left: float) -> Optional[float]:
        spots = [r.binance_spot for r in rows if r.binance_spot is not None]
        if len(spots) < 3 or spots[0] <= 0 or spots[-1] <= 0:
            return None
        arr = np.asarray(spots, dtype=float)
        r = math.log(arr[-1] / arr[0])
        steps = np.diff(np.log(np.clip(arr, _EPS, None)))
        persec = max(self.params.vol_floor_persec, float(np.std(steps)))
        sigma_rem = persec * math.sqrt(max(1.0, secs_left))
        if sigma_rem <= 0:
            return None
        return _phi(r / sigma_rem)

    def _fair_series(self, rows: Sequence[MarketTimelineRow]) -> List[Optional[float]]:
        """Causal P_fair per row in ONE pass (O(n)); carries forward last value.

        Equivalent to calling _fair_up(rows[:i+1]) for every i but without the
        O(n^2) re-scan — used in warmup.
        """
        out: List[Optional[float]] = []
        logs: List[float] = []          # log spots seen so far
        s1 = 0.0                        # running sum of step diffs
        s2 = 0.0                        # running sum of squared step diffs
        last: Optional[float] = None
        first_log: Optional[float] = None
        for r in rows:
            sp = r.binance_spot
            if sp is not None and sp > 0:
                lg = math.log(sp)
                if logs:
                    d = lg - logs[-1]
                    s1 += d
                    s2 += d * d
                else:
                    first_log = lg
                logs.append(lg)
                n = len(logs)
                if n >= 3 and first_log is not None:
                    nd = n - 1
                    mean = s1 / nd
                    var = max(0.0, s2 / nd - mean * mean)
                    persec = max(self.params.vol_floor_persec, math.sqrt(var))
                    sl = r.seconds_to_resolution or 0.0
                    sigma_rem = persec * math.sqrt(max(1.0, sl))
                    last = _phi((lg - first_log) / sigma_rem) if sigma_rem > 0 else last
            out.append(last)
        return out

    def _exc_raw(self, rows: Sequence[MarketTimelineRow]) -> Optional[np.ndarray]:
        """Raw excitation components [ |binance_vel_5s|, |dOBI|, VPIN ] at last step."""
        if not rows:
            return None
        last = rows[-1]
        vel = abs(float(last.binance_vel_5s_pct)) if last.binance_vel_5s_pct is not None else 0.0
        # ΔOBI over the last two available OBI readings
        obis = [r.ob_imb_top3 for r in rows if r.ob_imb_top3 is not None]
        d_obi = abs(float(obis[-1] - obis[-2])) if len(obis) >= 2 else 0.0
        vpin = float(last.vpin_score) if last.vpin_score is not None else 0.0
        return np.array([vel, d_obi, vpin], dtype=float)

    def _excitation(self, asset: str, rows: Sequence[MarketTimelineRow]) -> float:
        raw = self._exc_raw(rows)
        mu = self._exc_mu.get(asset)
        sd = self._exc_sd.get(asset)
        if raw is None or mu is None or sd is None:
            return 0.0
        z = (raw - mu) / np.clip(sd, _EPS, None)
        h = float(np.mean(z))
        return 1.0 / (1.0 + math.exp(-h))  # squash to (0,1)

    # ================= warmup ==========================================
    def warmup(self, panels: Sequence[WindowPanel]) -> None:
        p = self.params
        by_asset: Dict[str, List[WindowPanel]] = {}
        for panel in panels:
            if panel.is_up_token and panel.timeline:
                by_asset.setdefault(panel.asset, []).append(panel)

        for asset, ups in by_asset.items():
            # ---- collect step features to FIT the HMM (capped) ----
            feat_rows: List[List[float]] = []
            exc_rows: List[np.ndarray] = []
            for panel in ups:
                for r in panel.timeline:
                    v = self._f_vec(r)
                    if v is not None:
                        feat_rows.append(v)
                    er = self._exc_raw([r])
                    if er is not None:
                        exc_rows.append(er)
                if len(feat_rows) >= p.warmup_fit_rows:
                    break
            if len(feat_rows) < p.n_states + 5:
                continue
            X = np.array(feat_rows, dtype=float)
            m = GaussianHMM(n_states=p.n_states, seed=abs(hash(asset)) % 99999)
            m.fit(X)
            self._models[asset] = m
            # excitation z-score stats
            E = np.array(exc_rows, dtype=float)
            self._exc_mu[asset] = E.mean(axis=0)
            self._exc_sd[asset] = E.std(axis=0) + _EPS

            # ---- identify reflexive state + q90 on a panel subsample ----
            conv_by_state = {k: [] for k in range(p.n_states)}
            # store (abs_gap, posterior_vec, excitation) so the q90 can use the
            # TRUE reflexive posterior once it is identified after the loop.
            score_parts: List[Tuple[float, np.ndarray, float]] = []
            for panel in ups[: p.warmup_eval_panels]:
                rows = panel.timeline
                seq = self._seq(rows)
                if seq.shape[0] < 2:
                    continue
                alpha, _ = m.filter(seq)            # (T,K) causal posteriors
                states = alpha.argmax(axis=1)
                # per-step gap series (causal fair vs mid) — single O(n) pass
                fair_s = self._fair_series(rows)
                gaps: List[Optional[float]] = [
                    (fair_s[i] - rows[i].mid)
                    if (fair_s[i] is not None and rows[i].mid is not None) else None
                    for i in range(len(rows))
                ]
                # align states (built on filtered seq length) to rows by tail
                off = len(rows) - seq.shape[0]
                for t in range(seq.shape[0] - p.conv_horizon):
                    ri = off + t
                    g0 = gaps[ri] if ri < len(gaps) else None
                    g1 = gaps[ri + p.conv_horizon] if ri + p.conv_horizon < len(gaps) else None
                    if g0 is None or g1 is None:
                        continue
                    conv = abs(g0) - abs(g1)        # positive => gap closed
                    conv_by_state[int(states[t])].append(conv)
                    exc = self._excitation(asset, rows[max(0, ri - 4): ri + 1])
                    score_parts.append((abs(g0), alpha[t].copy(), exc))
            means = {k: (np.mean(v) if v else -1e9) for k, v in conv_by_state.items()}
            reflex = int(max(means, key=means.get))
            self._reflexive[asset] = reflex
            scores = [ag * float(post[reflex]) * exc for (ag, post, exc) in score_parts]
            self._q90[asset] = float(np.quantile(scores, p.score_q)) if scores else 0.0

    # ================= live ============================================
    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        asset = ctx.asset
        tok = ctx.token_id
        model = self._models.get(asset)
        if model is None:
            return []

        rows = list(ctx.history)

        def _p_reflex() -> float:
            seq = self._seq(rows[-p.hist_steps:])
            if seq.shape[0] < 1:
                return 0.0
            alpha, _ = model.filter(seq)
            return float(alpha[-1][self._reflexive.get(asset, 0)])

        # ---- manage an open leg: multi-condition exit ----
        if ctx.open_shares > 0:
            sl = ctx.seconds_to_resolution or 0.0
            fair = self._fair_up(rows, sl) if sl > 0 else None
            mid = ctx.mid
            gap = (fair - mid) if (fair is not None and mid is not None) else None
            entry_sl = self._entry_sl.get(tok)
            vpin = rows[-1].vpin_score if rows and rows[-1].vpin_score is not None else 0.0
            reasons = []
            if gap is not None and abs(gap) < p.eps_converge:
                reasons.append("converged")
            if entry_sl is not None and sl < (1.0 - p.time_decay_frac) * entry_sl:
                reasons.append("time_decay")
            if _p_reflex() < 0.30:
                reasons.append("state_change")
            if float(vpin) > p.vpin_spike:
                reasons.append("toxicity_spike")
            if reasons:
                return [Signal(side="FLAT", meta={"reason": ",".join(reasons)})]
            return []

        # ---- entry (UP panel only; NO routes to peer) ----  [cheap gates first]
        if (ctx.outcome_dir or "").lower() != "up":
            return []
        sl = ctx.seconds_to_resolution
        if sl is None or sl < p.min_secs_left or sl > p.max_secs_left:
            return []
        akey = (tok, ctx.window_end_ts)
        if akey in self._acted:
            return []
        fair = self._fair_up(rows, sl)
        mid = ctx.mid
        if fair is None or mid is None or not (0 < mid < 1):
            return []
        gap = fair - mid
        exc = self._excitation(asset, rows[-5:])
        p_reflex = _p_reflex()
        score = abs(gap) * p_reflex * exc
        if score < self._q90.get(asset, 1e9):
            return []

        # toxicity cost filter
        fee_fn = ctx.extras.get("fee_fn")
        exp_fill = ctx.extras["expected_fill_price"]
        spread = (ctx.best_ask - ctx.best_bid) if (ctx.best_ask and ctx.best_bid) else 0.0
        vpin = rows[-1].vpin_score if rows and rows[-1].vpin_score is not None else 0.0
        ref_price = ctx.best_ask if (gap > 0 and ctx.best_ask) else mid
        cost = (fee_fn(ref_price, 1.0) if fee_fn else 0.0) + 0.5 * spread + p.vpin_cost_k * float(vpin)
        if abs(gap) <= cost + p.margin:
            return []

        if gap > 0:  # fair above book -> YES underpriced
            ask = ctx.best_ask
            if ask is not None and 0 < ask < 1:
                f = exp_fill("buy", ask)
                self._acted.add(akey)
                self._entry_sl[tok] = sl
                return [Signal(side="BUY_YES", size_fraction=self._size(abs(gap) - cost),
                               price_limit=min(1.0, ask + 2 * abs(f - ask) + 0.02),
                               meta={"note": "ripa_yes", "gap": round(gap, 4),
                                     "p_reflex": round(p_reflex, 3), "exc": round(exc, 3),
                                     "score": round(score, 4)})]
        else:        # fair below book -> YES overpriced -> NO
            peer = ctx.peer
            no_ask = peer.get("best_ask") if peer else None
            if no_ask is not None and 0 < no_ask < 1:
                f = exp_fill("buy", no_ask)
                self._acted.add(akey)
                self._entry_sl[tok] = sl
                return [Signal(side="BUY_NO", size_fraction=self._size(abs(gap) - cost),
                               price_limit=min(1.0, no_ask + 2 * abs(f - no_ask) + 0.02),
                               meta={"note": "ripa_no", "gap": round(gap, 4),
                                     "p_reflex": round(p_reflex, 3), "exc": round(exc, 3),
                                     "score": round(score, 4)})]
        return []

    def _size(self, net_edge: float) -> float:
        return float(min(1.0, max(0.0, 0.2 + 3.0 * max(0.0, net_edge))))

    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        self._acted.discard((panel.token_id, int(panel.window_end_ts)))
        self._entry_sl.pop(panel.token_id, None)


__all__ = ["RipaParams", "RipaStrategy"]
