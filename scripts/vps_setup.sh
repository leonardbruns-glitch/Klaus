#!/bin/bash
# Klaus VPS Setup Script
# Run once on fresh QuantVPS Dublin instance (Ubuntu 22.04)
# Usage: bash vps_setup.sh

set -e

echo "=== Klaus VPS Setup ==="

# 1. System deps
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv git curl screen cron

# 2. Install Claude Code CLI
curl -fsSL https://claude.ai/install.sh | bash
echo "Claude Code installed: $(claude --version)"

# 3. Clone repo
cd /root
git clone https://github.com/leonardbruns-glitch/Klaus.git
cd Klaus
git checkout claude/investigate-zero-entry-price-lWxej

# 4. Python deps
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

# 5. Create .env (fill in values after running)
cat > .env << 'EOF'
# Fill these in before starting
POLYMARKET_API_KEY=
POLYMARKET_SECRET=
POLYMARKET_PASSPHRASE=
POLYMARKET_ADDRESS=
ANTHROPIC_API_KEY=
DRY_RUN=false
EOF
echo ">>> EDIT /root/Klaus/.env with your keys before proceeding <<<"

# 6. Cron jobs
# Bot: runs 24/7, restarts if it crashes
# Diagnosis: runs daily at 16:00 UTC (after active windows close)
(crontab -l 2>/dev/null; cat << 'CRON'
# Klaus bot — keep alive, restart every hour if not running
* * * * * pgrep -f "python3 main.py" > /dev/null || (cd /root/Klaus && git pull -q && source venv/bin/activate && screen -dmS klaus python3 main.py)

# Klaus diagnosis — daily at 16:00 UTC
0 16 * * * cd /root/Klaus && source venv/bin/activate && claude --dangerously-skip-permissions -p "$(cat .claude_prompt)" >> logs/claude_diagnosis.log 2>&1
CRON
) | crontab -

echo "Cron installed:"
crontab -l

# 7. Create the daily diagnosis prompt
cat > /root/Klaus/.claude_prompt << 'EOF'
Read STATUS.md first. Then run the data primacy protocol from CLAUDE.md:
1. Read logs/trades.jsonl — count n_live, confirm DRY_RUN=false trades only
2. Compute WR, profit factor, avg_win, avg_loss, fee_bleed_ratio
3. Compute WR by hour UTC and by asset
4. Check kill switches — halt if any triggered
5. Diagnose root cause of any losses
6. Implement fixes if data justifies (n>=20 for parameter changes)
7. Update STATUS.md with current stats
8. Commit and push all changes with data-cited commit message
EOF

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /root/Klaus/.env with your API keys"
echo "  2. Test: cd /root/Klaus && source venv/bin/activate && python3 main.py"
echo "  3. Start bot in screen: screen -S klaus python3 main.py"
echo "  4. Verify cron: crontab -l"
echo "  5. Watch logs: tail -f /root/Klaus/logs/bot.log"
