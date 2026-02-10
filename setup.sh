#!/bin/bash
# NeuralDrift — First-time setup
# Run: bash setup.sh

set -e

CYAN='\033[96m'
GREEN='\033[92m'
WHITE='\033[97m'
DIM='\033[2m'
BOLD='\033[1m'
RST='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}"
echo " ███╗   ██╗███████╗██╗   ██╗██████╗  █████╗ ██╗     "
echo " ████╗  ██║██╔════╝██║   ██║██╔══██╗██╔══██╗██║     "
echo " ██╔██╗ ██║█████╗  ██║   ██║██████╔╝███████║██║     "
echo " ██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██╔══██║██║     "
echo " ██║ ╚████║███████╗╚██████╔╝██║  ██║██║  ██║███████╗"
echo " ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝"
echo ""
echo "          ██████╗ ██████╗ ██╗███████╗████████╗"
echo "          ██╔══██╗██╔══██╗██║██╔════╝╚══██╔══╝"
echo "          ██║  ██║██████╔╝██║█████╗     ██║   "
echo "          ██║  ██║██╔══██╗██║██╔══╝     ██║   "
echo "          ██████╔╝██║  ██║██║██║        ██║   "
echo "          ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝        ╚═╝   "
echo -e "${RST}"
echo -e "  ${WHITE}Your knowledge has a temperature.${RST}"
echo -e "  ${DIM}─────────────────────────────────${RST}"
echo ""

# Determine install location
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Add to PYTHONPATH
SHELL_RC="${HOME}/.bashrc"
if [ -n "$ZSH_VERSION" ] || [ -f "${HOME}/.zshrc" ]; then
    SHELL_RC="${HOME}/.zshrc"
fi

if ! grep -q "neural-drift\|neuraldrift" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# NeuralDrift" >> "$SHELL_RC"
    echo "export PYTHONPATH=\"${INSTALL_DIR}:\$PYTHONPATH\"" >> "$SHELL_RC"
    echo -e "  ${GREEN}[+]${RST} Added to PYTHONPATH in ${SHELL_RC}"
else
    echo -e "  ${GREEN}[+]${RST} PYTHONPATH already configured"
fi

# Create data directory
DATA_DIR="${HOME}/.neuraldrift"
mkdir -p "$DATA_DIR"
echo -e "  ${GREEN}[+]${RST} Data directory: ${DATA_DIR}"

# Quick test
export PYTHONPATH="${INSTALL_DIR}:$PYTHONPATH"
python3 -c "
from neuraldrift.brain import Brain
from neuraldrift.human_brain import HumanBrain
b = Brain()
hb = HumanBrain()
print('  \033[92m[+]\033[0m AI Brain: OK')
print('  \033[92m[+]\033[0m Human Brain: OK')
" 2>/dev/null && echo "" && echo -e "  ${GREEN}${BOLD}Setup complete! Both brains are ready.${RST}" || echo -e "  \033[91m[-]\033[0m Setup failed — check Python 3.9+ is installed"

echo ""
echo -e "  ${WHITE}Next steps:${RST}"
echo -e "    ${CYAN}python3 -c \"from neuraldrift.brain import Brain; Brain().level()\"${RST}"
echo -e "    ${CYAN}python3 -c \"from neuraldrift.human_brain import HumanBrain; HumanBrain().introduce('your_name')\"${RST}"
echo ""
