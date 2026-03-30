"""
Klaus Trading Dashboard
=======================
Run:  streamlit run dashboard.py
Open: http://localhost:8501

Reads logs/trades.jsonl, logs/bankroll.json, logs/session.jsonl,
logs/market_ticks.jsonl — all written by the live bot.
Auto-refreshes every 15 seconds via browser JS.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
TRADES_FILE   = ROOT / "logs" / "trades.jsonl"
BANKROLL_FILE = ROOT / "logs" / "bankroll.json"
SESSION_FILE  = ROOT / "logs" / "session.jsonl"
TICKS_FILE    = ROOT / "logs" / "market_ticks.jsonl"

REFRESH_S = 15

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Klaus · Scalper",
    page_icon="⚡",
    layout="wide",
)

# Inject dark theme tweaks + auto-refresh
components.html(
    f"""
    <script>
    setTimeout(function() {{ window.parent.location.reload(); }}, {REFRESH_S * 1000});
    </script>
    """,
    height=0,
)
st.markdown(
    """
    <style>
    .block-container{padding-top:1rem}
    div[data-testid="stMetric"]{background:#1e2130;border-radius:8px;padding:12px}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Colours ───────────────────────────────────────────────────────────────────
C_GREEN  = "#00d4aa"
C_RED    = "#ff4b4b"
C_YELLOW = "#ffd700"
C_BLUE   = "#4b7bff"
C_BG     = "#0e1117"
C_CARD   = "#1e2130"

ASSET_COLOR = {"BTC": "#f7931a", "ETH": "#627eea", "SOL": "#9945ff"}
EXIT_COLOR  = {
    "PROFIT_2":        C_GREEN,
    "PROFIT_1":        "#00b894",
    "EXIT_WINDOW_END": C_YELLOW,
    "HARD_EXIT":       "#fd9644",
    "STOP_LOSS":       C_RED,
    "MANUAL_SELL":     "#a0a0a0",
    "MANUAL":          "#a0a0a0",
}

_LAYOUT = dict(
    paper_bgcolor=C_BG, plot_bgcolor=C_BG,
    font=dict(color="#ccc", size=12),
    margin=dict(l=10, r=10, t=10, b=30),
    xaxis=dict(gridcolor="#2a2a2a"),
    yaxis=dict(gridcolor="#2a2a2a"),
)


# ── Loaders ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=REFRESH_S)
def load_trades() -> pd.DataFrame:
    if not TRADES_FILE.exists():
        return pd.DataFrame()
    rows = []
    with open(TRADES_FILE) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["win"] = df["net_pnl"] > 0
    df["trade_num"] = range(1, len(df) + 1)
    # Timestamp columns — handle 0 values from reconstructed trades
    for col in ("ts_open", "ts_close"):
        df[col] = pd.to_datetime(
            df[col].where(df[col] > 0, other=pd.NaT), unit="s", utc=True
        )
    return df


@st.cache_data(ttl=REFRESH_S)
def load_bankroll() -> dict:
    if not BANKROLL_FILE.exists():
        return {}
    with open(BANKROLL_FILE) as fh:
        return json.load(fh)


@st.cache_data(ttl=REFRESH_S)
def load_latest_session() -> dict:
    if not SESSION_FILE.exists():
        return {}
    last: dict = {}
    with open(SESSION_FILE) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    last = json.loads(line)
                except Exception:
                    pass
    return last


@st.cache_data(ttl=5)
def load_ticks(n: int = 300) -> pd.DataFrame:
    if not TICKS_FILE.exists():
        return pd.DataFrame()
    with open(TICKS_FILE) as fh:
        lines = fh.readlines()
    rows = []
    for line in lines[-n:]:
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df


# ── Load ──────────────────────────────────────────────────────────────────────
df        = load_trades()
bankroll  = load_bankroll()
session   = load_latest_session()
ticks     = load_ticks()

live = df[df.get("is_live", pd.Series(True, index=df.index)) == True] if not df.empty else df
wins   = live[live["win"]] if not live.empty else pd.DataFrame()
losses = live[~live["win"]] if not live.empty else pd.DataFrame()

capital      = bankroll.get("capital", 0.0)
daily_start  = bankroll.get("daily_start_capital", capital)
daily_pnl    = capital - daily_start
consec_wins  = bankroll.get("consecutive_wins", 0)

win_rate      = len(wins) / len(live) * 100 if len(live) > 0 else 0.0
gross_wins    = wins["net_pnl"].sum()   if not wins.empty   else 0.0
gross_losses  = abs(losses["net_pnl"].sum()) if not losses.empty else 0.0
profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")
net_pnl_all   = live["net_pnl"].sum() if not live.empty else 0.0
fees_all      = live["fee_paid"].sum() if not live.empty else 0.0

alerts = session.get("diagnostics", {}).get("alerts", []) if session else []

now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    f"<h2 style='margin-bottom:0'>⚡ Klaus Scalper</h2>"
    f"<p style='color:#666;margin-top:0;font-size:13px'>"
    f"Polymarket CLOB · auto-refresh {REFRESH_S}s · {now_str}</p>",
    unsafe_allow_html=True,
)

# ── Alerts ────────────────────────────────────────────────────────────────────
for alert in alerts:
    st.warning(f"⚠  {alert}", icon=None)

# ── Top KPI row ───────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

def _delta_color(val: float) -> str:
    return C_GREEN if val >= 0 else C_RED

with c1:
    st.metric("Capital", f"${capital:.2f}",
              f"{'+' if daily_pnl >= 0 else ''}{daily_pnl:.2f} today")
with c2:
    wr_color = C_GREEN if win_rate >= 50 else (C_YELLOW if win_rate >= 35 else C_RED)
    st.metric("Win Rate", f"{win_rate:.1f}%", f"{len(wins)}W / {len(losses)}L")
with c3:
    pf_str = f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞"
    st.metric("Profit Factor", pf_str, "target ≥ 1.3")
with c4:
    net_str = f"{'+' if net_pnl_all >= 0 else ''}{net_pnl_all:.2f}"
    st.metric("Net P&L", f"${net_str}", f"fees ${fees_all:.2f}")
with c5:
    st.metric("Trades", str(len(live)), f"{len(live[live['market_type']=='updown']) if not live.empty else 0} updown")
with c6:
    st.metric("Win Streak", str(consec_wins), "heat-check at 2")
with c7:
    kill_pct = ((capital - daily_start) / daily_start * 100) if daily_start > 0 else 0
    st.metric("DD from day start", f"{kill_pct:+.1f}%", "kill at −25%")

st.divider()

# ── Row 1: Capital curve + Asset P&L ─────────────────────────────────────────
col_a, col_b = st.columns([2, 1])

with col_a:
    st.subheader("Capital Curve")
    cap_df = live[live["capital_after"] > 0].copy() if not live.empty else pd.DataFrame()

    if not cap_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=cap_df["trade_num"], y=cap_df["capital_after"],
            mode="lines+markers", name="Capital",
            line=dict(color=C_BLUE, width=2),
            marker=dict(color=[C_GREEN if w else C_RED for w in cap_df["win"]], size=9),
            hovertemplate="Trade #%{x}<br>$%{y:.2f}<extra></extra>",
        ))
        if daily_start > 0:
            fig.add_hline(y=daily_start, line_dash="dash", line_color="#555",
                          annotation_text="Day start", annotation_font_color="#888")
            fig.add_hline(y=daily_start * 0.75, line_dash="dot", line_color=C_RED,
                          annotation_text="Kill −25%", annotation_font_color=C_RED)
        fig.update_layout(**_LAYOUT, height=300, showlegend=False,
                          yaxis=dict(gridcolor="#2a2a2a", tickprefix="$"))
        st.plotly_chart(fig, use_container_width=True)
    elif not live.empty:
        # Fallback: cumulative PnL
        cum = live["net_pnl"].cumsum()
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=live["trade_num"], y=cum,
            fill="tozeroy", fillcolor="rgba(75,123,255,0.12)",
            line=dict(color=C_BLUE, width=2),
            hovertemplate="Trade #%{x}<br>Cum P&L: $%{y:.2f}<extra></extra>",
        ))
        fig.add_hline(y=0, line_color="#555", line_width=1)
        fig.update_layout(**_LAYOUT, height=300,
                          yaxis=dict(gridcolor="#2a2a2a", tickprefix="$",
                                     title="Cumulative P&L"))
        st.caption("Capital tracking sparse — showing cumulative P&L instead")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No trade data yet.")

with col_b:
    st.subheader("Asset P&L")
    if not live.empty:
        ag = live.groupby("asset").agg(
            pnl=("net_pnl", "sum"),
            n=("net_pnl", "count"),
            w=("win", "sum"),
        ).reset_index()
        ag["wr"] = (ag["w"] / ag["n"] * 100).round(1)
        fig = go.Figure(go.Bar(
            x=ag["asset"], y=ag["pnl"],
            marker_color=[ASSET_COLOR.get(a, "#888") for a in ag["asset"]],
            text=[f"${p:.2f}<br>{w}% WR" for p, w in zip(ag["pnl"], ag["wr"])],
            textposition="outside",
            hovertemplate="%{x}: $%{y:.2f}<extra></extra>",
        ))
        fig.add_hline(y=0, line_color="#555", line_width=1)
        fig.update_layout(**_LAYOUT, height=300, showlegend=False,
                          yaxis=dict(gridcolor="#2a2a2a", tickprefix="$"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data")

st.divider()

# ── Row 2: Signal bars + Exit pie + Rolling win rate ─────────────────────────
col_a, col_b, col_c = st.columns([1.4, 1, 1.4])

with col_a:
    st.subheader("Signal: Wins vs Losses")
    scored = live[live["composite_score"] > 0] if not live.empty else pd.DataFrame()
    if not scored.empty:
        cats = ["Breakout", "Trend", "Volume", "OB", "IWD"]
        cols = ["breakout_score", "trend_score", "volume_score", "ob_score", "intrawindow_score"]
        sw = scored[scored["win"]]
        sl = scored[~scored["win"]]
        w_avg = [sw[c].mean() if not sw.empty else 0 for c in cols]
        l_avg = [sl[c].mean() if not sl.empty else 0 for c in cols]
        w_avg = [v if v == v else 0 for v in w_avg]  # NaN → 0
        l_avg = [v if v == v else 0 for v in l_avg]
        fig = go.Figure([
            go.Bar(name="Win",  x=cats, y=w_avg, marker_color=C_GREEN),
            go.Bar(name="Loss", x=cats, y=l_avg, marker_color=C_RED),
        ])
        fig.update_layout(**_LAYOUT, height=260, barmode="group",
                          legend=dict(orientation="h", y=1.1),
                          yaxis=dict(gridcolor="#2a2a2a", range=[0, 1]))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"n={len(scored)} scored trades (0.0 scores = reconstructed, excluded)")
    else:
        st.info("No scored trades yet")

with col_b:
    st.subheader("Exit Reasons")
    if not live.empty:
        ec = live["exit_reason"].value_counts()
        fig = go.Figure(go.Pie(
            labels=ec.index, values=ec.values,
            marker_colors=[EXIT_COLOR.get(r, "#888") for r in ec.index],
            hole=0.52, textinfo="label+percent", textfont_size=11,
        ))
        fig.update_layout(paper_bgcolor=C_BG, font=dict(color="#ccc"),
                          height=260, margin=dict(l=0, r=0, t=0, b=0),
                          showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data")

with col_c:
    st.subheader("Rolling Win Rate (10-trade window)")
    if len(live) >= 3:
        rwr = live["win"].rolling(10, min_periods=1).mean() * 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=live["trade_num"], y=rwr,
            fill="tozeroy", fillcolor="rgba(0,212,170,0.08)",
            line=dict(color=C_GREEN, width=2),
            hovertemplate="Trade #%{x}<br>WR: %{y:.1f}%<extra></extra>",
        ))
        fig.add_hline(y=52, line_dash="dash", line_color=C_GREEN,
                      annotation_text="Target 52%", annotation_font_color=C_GREEN)
        fig.add_hline(y=30, line_dash="dot", line_color=C_RED,
                      annotation_text="Kill 30%", annotation_font_color=C_RED)
        fig.update_layout(**_LAYOUT, height=260,
                          xaxis=dict(gridcolor="#2a2a2a", title="Trade #"),
                          yaxis=dict(gridcolor="#2a2a2a", range=[0, 105],
                                     ticksuffix="%"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Need 3+ trades")

st.divider()

# ── Row 3: IWD scatter + Hold time histogram ──────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("King Signal — Intrawindow Delta vs P&L")
    if not live.empty:
        fig = go.Figure()
        for is_win, color, label in [(True, C_GREEN, "Win"), (False, C_RED, "Loss")]:
            sub = live[live["win"] == is_win]
            if not sub.empty:
                fig.add_trace(go.Scatter(
                    x=sub["intrawindow_score"], y=sub["net_pnl"],
                    mode="markers", name=label,
                    marker=dict(color=color, size=11, opacity=0.8,
                                line=dict(color="#111", width=1)),
                    hovertemplate=(
                        f"<b>{label}</b><br>IWD: %{{x:.2f}}"
                        "<br>P&L: $%{y:.3f}<extra></extra>"
                    ),
                ))
        fig.add_vline(x=0.60, line_dash="dash", line_color=C_YELLOW,
                      annotation_text="Strong ≥0.60", annotation_font_color=C_YELLOW)
        fig.add_hline(y=0, line_color="#555", line_width=1)
        fig.update_layout(**_LAYOUT, height=260,
                          legend=dict(orientation="h", y=1.1),
                          xaxis=dict(gridcolor="#2a2a2a", title="IWD Score", range=[-0.05, 1.05]),
                          yaxis=dict(gridcolor="#2a2a2a", title="Net P&L", tickprefix="$"))
        st.plotly_chart(fig, use_container_width=True)

with col_b:
    st.subheader("Hold Time Distribution")
    if not live.empty:
        fig = go.Figure()
        for is_win, color, label in [(True, C_GREEN, "Win"), (False, C_RED, "Loss")]:
            sub = live[live["win"] == is_win]["hold_seconds"]
            if not sub.empty:
                fig.add_trace(go.Histogram(
                    x=sub, name=label, marker_color=color,
                    opacity=0.7, nbinsx=18,
                ))
        fig.add_vline(x=180, line_dash="dash", line_color=C_YELLOW,
                      annotation_text="Hard exit 180s", annotation_font_color=C_YELLOW)
        fig.update_layout(**_LAYOUT, height=260, barmode="overlay",
                          legend=dict(orientation="h", y=1.1),
                          xaxis=dict(gridcolor="#2a2a2a", title="Hold (seconds)"),
                          yaxis=dict(gridcolor="#2a2a2a", title="Count"))
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Row 4: Live market ticks ──────────────────────────────────────────────────
if not ticks.empty:
    st.subheader("Live Signal Feed (last 300 ticks)")
    col_a, col_b = st.columns([2, 1])

    with col_a:
        fig = go.Figure()
        for asset, color in ASSET_COLOR.items():
            sub = ticks[ticks["asset"] == asset]
            if not sub.empty:
                fig.add_trace(go.Scatter(
                    x=sub["ts"], y=sub["score"],
                    mode="lines", name=asset,
                    line=dict(color=color, width=1.5),
                    hovertemplate=f"{asset}<br>%{{x}}<br>score=%{{y:.3f}}<extra></extra>",
                ))
        fig.add_hline(y=0.44, line_dash="dash", line_color="#888",
                      annotation_text="min_score=0.44", annotation_font_color="#888")
        fig.update_layout(**_LAYOUT, height=220,
                          legend=dict(orientation="h", y=1.1),
                          yaxis=dict(gridcolor="#2a2a2a", range=[0, 1], title="Score"))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("**Top signals right now**")
        actionable = ticks[ticks["direction"].isin(["BUY_YES", "BUY_NO"])]
        if not actionable.empty:
            top = (
                actionable.nlargest(8, "score")
                [["asset", "side", "score", "price", "direction"]]
                .copy()
            )
            top["score"] = top["score"].round(3)
            top["price"] = top["price"].round(4)
            top.columns = ["Asset", "Side", "Score", "Price", "Dir"]
            st.dataframe(top, use_container_width=True, hide_index=True)
        else:
            st.info("No actionable signals in last 300 ticks")
    st.divider()

# ── Row 5: Recent trades table ────────────────────────────────────────────────
st.subheader("Recent Trades (last 20)")
if not live.empty:
    display = [
        "trade_id", "asset", "direction", "entry_price", "exit_price",
        "net_pnl", "exit_reason", "hold_seconds",
        "composite_score", "intrawindow_score", "fee_zone",
    ]
    cols = [c for c in display if c in live.columns]
    recent = live[cols].tail(20).copy().iloc[::-1]

    def _fmt(df: pd.DataFrame) -> pd.DataFrame:
        for col, fmt in [
            ("net_pnl",          lambda x: f"+${x:.3f}" if x >= 0 else f"-${abs(x):.3f}"),
            ("entry_price",      lambda x: f"{x:.4f}"),
            ("exit_price",       lambda x: f"{x:.4f}"),
            ("composite_score",  lambda x: f"{x:.3f}"),
            ("intrawindow_score",lambda x: f"{x:.2f}"),
            ("hold_seconds",     lambda x: f"{int(x)}s"),
        ]:
            if col in df.columns:
                df[col] = df[col].map(fmt)
        return df

    st.dataframe(_fmt(recent), use_container_width=True, hide_index=True)
else:
    st.info("No trades yet.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(
    f"<p style='color:#444;font-size:11px;text-align:right'>"
    f"Klaus dashboard · refreshes every {REFRESH_S}s · {now_str}</p>",
    unsafe_allow_html=True,
)
