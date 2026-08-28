"""
Bucket-switch consensus analysis.

Parses CANDIDATE log lines from bot.log and answers:
  - How often does the "best bucket" (highest fair_prob) flip between
    consecutive 30-min scans for the same city/date?
  - Given a flip to bucket Y, how long does Y hold before reverting to X?
  - How many false switches would N=3 / N=5 / N=10 fire?
  - What is the mu-delta distribution when a flip occurs?

Usage:
    python3 analytics/bucket_switch_analysis.py [logfile]
Default logfile: logs/bot.log
"""
import re
import sys
from collections import defaultdict
from datetime import datetime

LOG_PATH = sys.argv[1] if len(sys.argv) > 1 else "logs/bot.log"

# Match lines like:
# 2026-05-21 07:28:19,811 [INFO] strategy.weather_arb: [WA] CANDIDATE Paris 2026-05-22
#   poly=0.035 fair=0.305 edge=0.271 mu=26.70°C sigma=1.00°C bucket=[26.0,26.0] ...
CAND_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[INFO\] strategy\.weather_arb: "
    r"\[WA\] CANDIDATE (\S.*?) (\d{4}-\d{2}-\d{2}) "
    r"poly=([\d.]+) fair=([\d.]+) edge=([\d.]+) "
    r"mu=([\d.]+)°C sigma=([\d.]+)°C "
    r"bucket=\[([^\]]+)\]"
)

# ── Parse ──────────────────────────────────────────────────────────────────────
# Records keyed by (city, date), each scan = list of candidates
# scan_ts → sorted list of (fair_prob, bucket_repr, mu, poly)
scans_by_city_date: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))

with open(LOG_PATH) as f:
    for line in f:
        m = CAND_RE.search(line)
        if not m:
            continue
        ts_str, city, date_, poly, fair, edge, mu, sigma, bucket = m.groups()
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        # Round to nearest 30-min slot to group scans robustly
        slot_min = (ts.hour * 60 + ts.minute) // 30 * 30
        slot = ts.strftime("%Y-%m-%d ") + f"{slot_min // 60:02d}:{slot_min % 60:02d}"
        scans_by_city_date[(city, date_)][slot].append({
            "fair": float(fair),
            "bucket": bucket,
            "mu": float(mu),
            "poly": float(poly),
        })

# ── Build per-city-date scan sequence ─────────────────────────────────────────
# For each (city, date): sorted list of (slot, best_bucket, best_fair, mu)

print("=" * 72)
print("BEST-BUCKET STABILITY ACROSS CONSECUTIVE 30-MIN SCANS")
print("=" * 72)

all_transitions = []          # (city, date, slot_idx, old_bucket, new_bucket, mu_delta)
all_streak_lengths = []       # lengths of "stable streaks" (same best bucket)
mu_deltas_at_flip = []        # |mu[i] - mu[i-1]| when best bucket flips

summary_rows = []

for (city, date_), slot_dict in sorted(scans_by_city_date.items()):
    slots = sorted(slot_dict.keys())
    seq = []  # (slot, best_bucket, best_fair, mu)
    for slot in slots:
        candidates = slot_dict[slot]
        best = max(candidates, key=lambda c: c["fair"])
        seq.append((slot, best["bucket"], best["fair"], best["mu"]))

    if len(seq) < 2:
        continue

    # Count flips
    n_flips = 0
    streak = 1
    streaks = []
    for i in range(1, len(seq)):
        prev_bucket = seq[i-1][1]
        curr_bucket = seq[i][1]
        mu_prev = seq[i-1][3]
        mu_curr = seq[i][3]
        if curr_bucket != prev_bucket:
            n_flips += 1
            mu_delta = abs(mu_curr - mu_prev)
            mu_deltas_at_flip.append(mu_delta)
            all_transitions.append((city, date_, i, prev_bucket, curr_bucket, mu_delta, mu_prev, mu_curr))
            streaks.append(streak)
            streak = 1
        else:
            streak += 1
    streaks.append(streak)  # final streak
    all_streak_lengths.extend(streaks)

    flip_rate = n_flips / (len(seq) - 1)
    summary_rows.append({
        "city": city, "date": date_,
        "n_scans": len(seq), "n_flips": n_flips,
        "flip_rate": flip_rate,
        "streaks": streaks,
        "seq": seq,
    })

    # Per-city table
    print(f"\n{city} / {date_}  ({len(seq)} scans, {n_flips} flip(s), rate={flip_rate:.1%})")
    for slot, bucket, fair, mu in seq:
        print(f"  {slot}  best=[{bucket}]  fair={fair:.3f}  mu={mu:.2f}°C")

# ── Aggregate statistics ───────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("AGGREGATE")
print("=" * 72)

total_pairs = sum(r["n_scans"] - 1 for r in summary_rows)
total_flips = sum(r["n_flips"] for r in summary_rows)
print(f"City/date pairs with ≥2 scans : {len(summary_rows)}")
print(f"Total consecutive-scan pairs  : {total_pairs}")
print(f"Total best-bucket flips       : {total_flips}")
print(f"Overall flip rate             : {total_flips/total_pairs:.1%}" if total_pairs else "N/A")

if all_streak_lengths:
    from collections import Counter
    c = Counter(all_streak_lengths)
    print(f"\nStreak-length distribution (how many scans same bucket held before flip/end):")
    for length in sorted(c.keys()):
        print(f"  streak={length:2d}: {c[length]:3d} occurrences")

if mu_deltas_at_flip:
    print(f"\nMu-delta at flip (|mu_new - mu_prev|):")
    buckets = [0, 0.1, 0.3, 0.5, 1.0, 2.0, float("inf")]
    labels  = ["<0.1", "0.1-0.3", "0.3-0.5", "0.5-1.0", "1.0-2.0", "≥2.0"]
    counts = [0] * len(labels)
    for d in mu_deltas_at_flip:
        for i, (lo, hi) in enumerate(zip(buckets[:-1], buckets[1:])):
            if lo <= d < hi:
                counts[i] += 1
                break
    for label, count in zip(labels, counts):
        print(f"  {label:10s}: {count}")

# ── Simulate N-consensus thresholds ───────────────────────────────────────────
print("\n" + "=" * 72)
print("N-CONSENSUS SIMULATION  (how many switches would fire at N=3/5/10)")
print("Scenario: entered bucket X at scan 0. Subsequent scans evaluate Y.")
print("Switch fires when N consecutive scans prefer Y AND mu_delta ≥ 0.5°C.")
print("'False positive' = within 3 scans after switch, model reverts to X.")
print("=" * 72)

MU_THRESH = 0.5

for N in [2, 3, 5, 10]:
    switches = 0
    false_positives = 0
    suppressed_mu = 0
    for row in summary_rows:
        seq = row["seq"]
        if len(seq) < 2:
            continue
        held_bucket = seq[0][1]
        held_mu     = seq[0][3]
        streak_y    = 0
        for i in range(1, len(seq)):
            curr_bucket = seq[i][1]
            curr_mu     = seq[i][3]
            if curr_bucket != held_bucket:
                streak_y += 1
                if streak_y == N:
                    mu_delta = abs(curr_mu - held_mu)
                    if mu_delta < MU_THRESH:
                        suppressed_mu += 1
                        streak_y = 0  # suppressed — reset
                        continue
                    switches += 1
                    # check if the next 3 scans after this revert
                    revert = False
                    for j in range(i+1, min(i+4, len(seq))):
                        if seq[j][1] == held_bucket:
                            revert = True
                            break
                    if revert:
                        false_positives += 1
                    # now "held" is the new bucket
                    held_bucket = curr_bucket
                    held_mu = curr_mu
                    streak_y = 0
            else:
                streak_y = 0  # reverted to held

    print(f"N={N:2d}: switches={switches}  false_positives={false_positives}"
          f"  suppressed_by_mu={suppressed_mu}")

print("\nDone.")
