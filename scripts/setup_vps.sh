#!/bin/bash
# Klaus VPS Bootstrap Script
# Run once on a fresh Ubuntu/Debian VPS (TradoxVPS Dublin)
# Usage: bash scripts/setup_vps.sh

set -e

REPO_URL="https://github.com/leonardbruns-glitch/Klaus.git"
BRANCH="claude/investigate-zero-entry-price-lWxej"
INSTALL_DIR="$HOME/Klaus"
SERVICE_NAME="klaus"
PYTHON_MIN="3.10"

echo "============================================"
echo "  Klaus VPS Setup — TradoxVPS Dublin"
echo "============================================"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/7] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git curl wget screen tmux \
    build-essential libssl-dev libffi-dev \
    python3-dev

# ── 2. Check Python version ───────────────────────────────────────────────────
echo "[2/7] Checking Python version..."
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python $PYTHON_VERSION found"
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
    echo "  ✓ Python version OK"
else
    echo "  ERROR: Python 3.10+ required, found $PYTHON_VERSION"
    exit 1
fi

# ── 3. Clone or update repo ───────────────────────────────────────────────────
echo "[3/7] Setting up repository..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Repo exists — pulling latest..."
    cd "$INSTALL_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    echo "  Cloning repo..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    git checkout "$BRANCH"
fi
echo "  ✓ Branch: $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)"

# ── 4. Python venv + dependencies ────────────────────────────────────────────
echo "[4/7] Setting up Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✓ Dependencies installed"

# ── 5. Create .env if missing ─────────────────────────────────────────────────
echo "[5/7] Checking .env..."
if [ -f "$INSTALL_DIR/.env" ]; then
    echo "  .env already exists — skipping"
else
    echo "  Creating .env from template..."
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo "  ┌─────────────────────────────────────────────────┐"
    echo "  │  IMPORTANT: Edit .env before starting the bot   │"
    echo "  │  nano $INSTALL_DIR/.env                         │"
    echo "  │                                                  │"
    echo "  │  Required fields:                                │"
    echo "  │    PRIVATE_KEY=0x...                             │"
    echo "  │    FUNDER_ADDRESS=0x...                          │"
    echo "  │    ANTHROPIC_API_KEY=sk-ant-...                  │"
    echo "  │    DRY_RUN=false                                 │"
    echo "  └─────────────────────────────────────────────────┘"
    echo ""
fi

# ── 6. Create logs directory ──────────────────────────────────────────────────
echo "[6/7] Creating directories..."
mkdir -p "$INSTALL_DIR/logs"
echo "  ✓ logs/ ready"

# ── 7. Systemd service for auto-restart ──────────────────────────────────────
echo "[7/7] Installing systemd service..."
VENV_PYTHON="$INSTALL_DIR/venv/bin/python3"

sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=Klaus Polymarket Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_PYTHON main.py
Restart=always
RestartSec=10
StartLimitIntervalSec=60
StartLimitBurst=5

# Environment
EnvironmentFile=$INSTALL_DIR/.env

# Logging — journalctl -u klaus -f to watch
StandardOutput=append:$INSTALL_DIR/logs/bot.log
StandardError=append:$INSTALL_DIR/logs/bot.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
echo "  ✓ Systemd service installed and enabled"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "  1. Fill in your credentials:"
echo "     nano $INSTALL_DIR/.env"
echo ""
echo "  2. Verify Polymarket geo-block (Ireland must be allowed):"
echo "     curl https://polymarket.com/api/geoblock"
echo ""
echo "  3. Test with dry-run first:"
echo "     cd $INSTALL_DIR && source venv/bin/activate"
echo "     DRY_RUN=true python3 main.py"
echo ""
echo "  4. Start live bot (after confirming dry-run works):"
echo "     sudo systemctl start $SERVICE_NAME"
echo ""
echo "  5. Monitor:"
echo "     sudo journalctl -u $SERVICE_NAME -f"
echo "     tail -f $INSTALL_DIR/logs/bot.log"
echo "     tail -f $INSTALL_DIR/logs/trades.jsonl"
echo ""
echo "  6. Stop / restart:"
echo "     sudo systemctl stop $SERVICE_NAME"
echo "     sudo systemctl restart $SERVICE_NAME"
echo ""
echo "  7. Reconcile trades vs Polymarket history:"
echo "     cd $INSTALL_DIR && source venv/bin/activate"
echo "     python3 scripts/reconcile_polymarket.py"
echo ""
