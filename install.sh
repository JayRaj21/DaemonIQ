#!/usr/bin/env bash
# DaemonIQ installer — silent, single command
#
# Recommended:
#   curl -fsSL https://raw.githubusercontent.com/JayRaj21/DaemonIQ/master/install.sh | bash
#
# Local install (files already downloaded):
#   bash install.sh
set -euo pipefail

PRODUCT="DaemonIQ"
CLI="daemoniq"
DAEMON_LABEL="daemoniq-demon"
BASE_URL="https://raw.githubusercontent.com/JayRaj21/DaemonIQ/master"

R='\033[0m'; BOLD='\033[1m'; DIM='\033[2m'
GREEN='\033[38;5;82m'; YELLOW='\033[38;5;220m'
RED='\033[38;5;196m';  CYAN='\033[38;5;51m'

ok()   { echo -e "  ${GREEN}✓${R} $*"; }
warn() { echo -e "  ${YELLOW}⚠${R} $*"; }
err()  { echo -e "  ${RED}✗${R} $*"; }
info() { echo -e "  ${DIM}$*${R}"; }
hdr()  { echo -e "\n${CYAN}${BOLD}── $* ${R}"; }

INSTALL_DIR="$HOME/.${DAEMON_LABEL}"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/${CLI}"

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${RED}${BOLD}"
echo '  ██████╗  █████╗ ███████╗███╗   ███╗ ██████╗ ███╗   ██╗██████╗ ██████╗  '
echo '  ██╔══██╗██╔══██╗██╔════╝████╗ ████║██╔═══██╗████╗  ██║╚═██╔═╝██╔═══██╗ '
echo '  ██║  ██║███████║█████╗  ██╔████╔██║██║   ██║██╔██╗ ██║  ██║  ██║   ██║ '
echo '  ██║  ██║██╔══██║██╔══╝  ██║╚██╔╝██║██║   ██║██║╚██╗██║  ██║  ██║▄▄ ██║ '
echo '  ██████╔╝██║  ██║███████╗██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██████╗╚██████╔╝ '
echo '  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═════╝ ╚══▀▀═╝ '
echo -e "${R}${DIM}  * Linux Troubleshooting Assistant *${R}"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# 1 — Python check
# ══════════════════════════════════════════════════════════════════════════════
hdr "Checking requirements"

if ! command -v python3 &>/dev/null; then
    err "Python 3 is not installed."
    echo ""
    echo "  Install it first:"
    echo "    sudo apt install python3     ← Ubuntu / Debian / Mint"
    echo "    sudo dnf install python3     ← Fedora"
    echo "    sudo pacman -S python        ← Arch"
    echo ""
    exit 1
fi

PYMAJ=$(python3 -c "import sys; print(sys.version_info.major)")
PYMIN=$(python3 -c "import sys; print(sys.version_info.minor)")
PYVER="${PYMAJ}.${PYMIN}"

if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 8 ]; }; then
    err "Python $PYVER found — ${PRODUCT} requires Python 3.8+."
    exit 1
fi
ok "Python $PYVER"

# ══════════════════════════════════════════════════════════════════════════════
# 2 — Download or copy scripts
# ══════════════════════════════════════════════════════════════════════════════
hdr "Installing ${PRODUCT}"

mkdir -p "$INSTALL_DIR" "$BIN_DIR"

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-install.sh}")" 2>/dev/null && pwd || echo ".")"
SCRIPTS=("daemoniq-imp.py" "daemoniq-sovereign.py")
INSTALLED=0

_download() {
    local file="$1" dest="$2"
    if command -v curl &>/dev/null; then
        curl -fsSL "$BASE_URL/$file" -o "$dest" 2>/dev/null
    elif command -v wget &>/dev/null; then
        wget -q "$BASE_URL/$file" -O "$dest" 2>/dev/null
    else
        return 1
    fi
}

for script in "${SCRIPTS[@]}"; do
    LOCAL=""
    for candidate in "$INSTALLER_DIR/$script" "./$script" "$HOME/Downloads/$script"; do
        if [ -f "$candidate" ]; then LOCAL="$candidate"; break; fi
    done

    if [ -n "$LOCAL" ]; then
        cp "$LOCAL" "$INSTALL_DIR/$script"
        chmod +x "$INSTALL_DIR/$script"
        ok "Installed $script"
        INSTALLED=$((INSTALLED + 1))
    elif _download "$script" "$INSTALL_DIR/$script"; then
        chmod +x "$INSTALL_DIR/$script"
        ok "Downloaded $script"
        INSTALLED=$((INSTALLED + 1))
    else
        warn "Could not get $script — skipping"
    fi
done

if [ "$INSTALLED" -eq 0 ]; then
    err "No scripts could be installed."
    echo "  Place the script files next to install.sh, or check your internet connection."
    exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
# 3 — Create the launcher
# ══════════════════════════════════════════════════════════════════════════════
cat > "$LAUNCHER" << LAUNCHER_EOF
#!/usr/bin/env bash
INSTALL_DIR="\$HOME/.${DAEMON_LABEL}"
CONFIG="\$INSTALL_DIR/config.json"

# First run — no config yet, launch setup wizard
if [ ! -f "\$CONFIG" ] && [[ "\${1:-}" != "setup" ]] && [[ "\${1:-}" != "_daemon_bg" ]] && [[ "\${1:-}" != "_daemon_fg" ]]; then
    exec python3 "\$INSTALL_DIR/daemoniq-imp.py" setup
fi

# Read active script from config
ACTIVE=\$(python3 -c "
import json
try:    print(json.load(open('\$CONFIG')).get('active_script','daemoniq-imp.py'))
except: print('daemoniq-imp.py')
" 2>/dev/null || echo "daemoniq-imp.py")

SCRIPT="\$INSTALL_DIR/\$ACTIVE"
[ ! -f "\$SCRIPT" ] && { echo "Error: \$SCRIPT not found. Run: ${CLI} setup"; exit 1; }

exec python3 "\$SCRIPT" "\$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"
ok "Created 'daemoniq' command"

# ══════════════════════════════════════════════════════════════════════════════
# 4 — PATH (silent — no prompt)
# ══════════════════════════════════════════════════════════════════════════════
hdr "Configuring PATH"

SHELL_RC=""
case "${SHELL:-}" in
    */zsh)  SHELL_RC="$HOME/.zshrc" ;;
    */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
    *)      SHELL_RC="$HOME/.bashrc" ;;
esac

if [[ ":${PATH}:" == *":${BIN_DIR}:"* ]]; then
    ok "Already in PATH"
else
    if [ -n "$SHELL_RC" ] && ! grep -q "local/bin" "$SHELL_RC" 2>/dev/null; then
        if [[ "${SHELL:-}" == */fish ]]; then
            echo 'fish_add_path $HOME/.local/bin' >> "$SHELL_RC"
        else
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        fi
    fi
    export PATH="$BIN_DIR:$PATH"
    ok "Added ~/.local/bin to PATH in ${SHELL_RC##*/}"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 5 — Auto-start on login (one optional question)
# ══════════════════════════════════════════════════════════════════════════════
if command -v systemctl &>/dev/null && [ "${EUID:-$(id -u)}" -ne 0 ]; then
    hdr "Auto-start on login (optional)"
    read -r -p "  Start DaemonIQ automatically when you log in? [y/n] " ans
    if [[ "${ans:-}" =~ ^[Yy]$ ]]; then
        SVCDIR="$HOME/.config/systemd/user"
        mkdir -p "$SVCDIR"
        {
            echo "[Unit]"
            echo "Description=${PRODUCT} Troubleshooting Daemon"
            echo "After=network.target"
            echo ""
            echo "[Service]"
            echo "Type=forking"
            echo "ExecStart=${LAUNCHER} _daemon_bg"
            echo "PIDFile=/tmp/${DAEMON_LABEL}.pid"
            echo "Restart=on-failure"
            echo "RestartSec=5"
            echo "EnvironmentFile=-%h/.${DAEMON_LABEL}/env"
            echo ""
            echo "[Install]"
            echo "WantedBy=default.target"
        } > "$SVCDIR/${DAEMON_LABEL}.service"
        systemctl --user daemon-reload
        systemctl --user enable "${DAEMON_LABEL}.service" 2>/dev/null || true
        ok "Auto-start enabled"
    else
        info "Skipped — DaemonIQ starts on demand when you run it."
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}${BOLD}  ✓ DaemonIQ installed!${R}"
echo ""

# Add to PATH for this session so we can run setup immediately
export PATH="$BIN_DIR:$PATH"

echo -e "  Starting setup wizard...${R}"
echo ""
python3 "$INSTALL_DIR/daemoniq-imp.py" setup

echo ""
echo -e "${GREEN}${BOLD}  Ready. Run ${CYAN}daemoniq${GREEN} in a new terminal to start.${R}"
echo ""
