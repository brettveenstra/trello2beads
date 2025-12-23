#!/usr/bin/env bash
#
# install.sh - Installation script for trello2beads
#
# Usage:
#   ./install.sh              # Interactive install with virtual environment
#   ./install.sh --no-venv    # Install without virtual environment
#   ./install.sh --check      # Health check only (verify installation)
#   ./install.sh --help       # Show this help
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MIN_PYTHON_VERSION="3.8"
VENV_DIR=".venv"
USE_VENV=true
CHECK_ONLY=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --no-venv)
            USE_VENV=false
            shift
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        --help|-h)
            echo "trello2beads Installation Script"
            echo ""
            echo "Usage:"
            echo "  ./install.sh              Interactive install with virtual environment"
            echo "  ./install.sh --no-venv    Install without virtual environment"
            echo "  ./install.sh --check      Health check only (verify installation)"
            echo "  ./install.sh --help       Show this help"
            echo ""
            exit 0
            ;;
        *)
            # Unknown option
            ;;
    esac
done

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  trello2beads Installation${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ============================================================================
# ENVIRONMENT CHECKS
# ============================================================================

echo -e "${BLUE}📋 Step 1: Environment Checks${NC}"
echo ""

# Check Python version
echo -n "Checking Python version... "
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ FAILED${NC}"
    echo ""
    echo -e "${RED}Python 3 is not installed.${NC}"
    echo "Please install Python 3.8 or higher:"
    echo "  - Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  - macOS: brew install python3"
    echo "  - Windows: Download from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo -e "${RED}✗ FAILED${NC}"
    echo ""
    echo -e "${RED}Python $PYTHON_VERSION is too old.${NC}"
    echo "trello2beads requires Python 3.8 or higher."
    echo "Current version: Python $PYTHON_VERSION"
    exit 1
fi

echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"

# Check pip
echo -n "Checking pip availability... "
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${RED}✗ FAILED${NC}"
    echo ""
    echo -e "${RED}pip is not available.${NC}"
    echo "Please install pip:"
    echo "  - Ubuntu/Debian: sudo apt install python3-pip"
    echo "  - macOS: python3 -m ensurepip"
    exit 1
fi
echo -e "${GREEN}✓ pip available${NC}"

# Check beads CLI
echo -n "Checking beads CLI... "
if ! command -v bd &> /dev/null; then
    echo -e "${YELLOW}⚠ NOT FOUND${NC}"
    echo ""
    echo -e "${YELLOW}beads CLI is not installed.${NC}"
    echo "trello2beads requires beads for issue tracking."
    echo ""
    echo "Install beads:"
    echo "  pip install beads-project"
    echo "  # or"
    echo "  pip install --user beads-project"
    echo ""
    echo -n "Continue anyway? [y/N] "
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 1
    fi
else
    BD_VERSION=$(bd --version 2>&1 | head -1 || echo "unknown")
    echo -e "${GREEN}✓ $BD_VERSION${NC}"
fi

echo ""

# Exit here if check-only mode
if [ "$CHECK_ONLY" = true ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ✅ Environment check passed${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Run ./install.sh to complete installation"
    echo "  2. Configure Trello credentials in .env"
    echo "  3. Run: python3 trello2beads.py --help"
    exit 0
fi

# ============================================================================
# VIRTUAL ENVIRONMENT
# ============================================================================

if [ "$USE_VENV" = true ]; then
    echo -e "${BLUE}📦 Step 2: Virtual Environment${NC}"
    echo ""

    if [ -d "$VENV_DIR" ]; then
        echo -e "${GREEN}✓ Virtual environment already exists${NC}"
    else
        echo -n "Creating virtual environment... "
        python3 -m venv "$VENV_DIR"
        echo -e "${GREEN}✓ Created${NC}"
    fi

    echo -n "Activating virtual environment... "
    source "$VENV_DIR/bin/activate"
    echo -e "${GREEN}✓ Activated${NC}"

    echo ""
else
    echo -e "${BLUE}📦 Step 2: Virtual Environment${NC}"
    echo ""
    echo -e "${YELLOW}⚠ Skipping virtual environment (--no-venv flag)${NC}"
    echo ""
fi

# ============================================================================
# DEPENDENCIES
# ============================================================================

echo -e "${BLUE}📚 Step 3: Installing Dependencies${NC}"
echo ""

# Upgrade pip
echo -n "Upgrading pip... "
python3 -m pip install --upgrade pip --quiet
echo -e "${GREEN}✓ Done${NC}"

# Install runtime dependencies
echo -n "Installing runtime dependencies... "
if [ -f "requirements.txt" ]; then
    python3 -m pip install -r requirements.txt --quiet
    echo -e "${GREEN}✓ Installed from requirements.txt${NC}"
else
    echo -e "${YELLOW}⚠ requirements.txt not found${NC}"
fi

# Ask about dev dependencies
if [ -f "requirements-dev.txt" ]; then
    echo ""
    echo -n "Install development dependencies (testing, linting)? [y/N] "
    read -r install_dev
    if [[ "$install_dev" =~ ^[Yy]$ ]]; then
        echo -n "Installing dev dependencies... "
        python3 -m pip install -r requirements-dev.txt --quiet
        echo -e "${GREEN}✓ Installed${NC}"
    fi
fi

echo ""

# ============================================================================
# CREDENTIAL SETUP
# ============================================================================

echo -e "${BLUE}🔑 Step 4: Trello Credentials Setup${NC}"
echo ""

if [ -f ".env" ]; then
    echo -e "${GREEN}✓ .env file already exists${NC}"
    echo ""
    echo -n "Overwrite existing .env file? [y/N] "
    read -r overwrite_env
    if [[ ! "$overwrite_env" =~ ^[Yy]$ ]]; then
        echo "Keeping existing .env file"
        SKIP_ENV_SETUP=true
    else
        SKIP_ENV_SETUP=false
    fi
else
    SKIP_ENV_SETUP=false
fi

if [ "$SKIP_ENV_SETUP" = false ]; then
    echo ""
    echo "To use trello2beads, you need Trello API credentials."
    echo ""
    echo "Get your credentials:"
    echo "  1. Visit: https://trello.com/power-ups/admin"
    echo "  2. Create a new Power-Up (or use existing)"
    echo "  3. Copy your API Key"
    echo "  4. Generate a Token (click 'Token' link)"
    echo ""
    echo -n "Set up credentials now? [Y/n] "
    read -r setup_creds

    if [[ "$setup_creds" =~ ^[Nn]$ ]]; then
        echo ""
        echo -e "${YELLOW}⚠ Skipping credential setup${NC}"
        echo "You'll need to create .env manually later."
        echo ""
        echo "Example .env file:"
        echo "  TRELLO_API_KEY=your-api-key-here"
        echo "  TRELLO_TOKEN=your-token-here"
        echo "  TRELLO_BOARD_ID=your-board-id"
    else
        echo ""
        echo -n "Trello API Key: "
        read -r api_key

        echo -n "Trello Token: "
        read -r token

        echo -n "Trello Board ID (optional, press Enter to skip): "
        read -r board_id

        # Create .env file
        cat > .env << EOF
# Trello API Credentials
# Get these from: https://trello.com/power-ups/admin

TRELLO_API_KEY=$api_key
TRELLO_TOKEN=$token
EOF

        if [ -n "$board_id" ]; then
            echo "TRELLO_BOARD_ID=$board_id" >> .env
        else
            echo "# TRELLO_BOARD_ID=your-board-id-here" >> .env
        fi

        echo ""
        echo -e "${GREEN}✓ Created .env file${NC}"

        # Test API connection
        echo ""
        echo -n "Test Trello API connection? [Y/n] "
        read -r test_api
        if [[ ! "$test_api" =~ ^[Nn]$ ]]; then
            echo ""
            echo "Testing API connection..."

            # Simple curl test to verify credentials
            if command -v curl &> /dev/null; then
                response=$(curl -s -o /dev/null -w "%{http_code}" \
                    "https://api.trello.com/1/members/me?key=$api_key&token=$token")

                if [ "$response" = "200" ]; then
                    echo -e "${GREEN}✓ API connection successful!${NC}"
                else
                    echo -e "${YELLOW}⚠ API connection failed (HTTP $response)${NC}"
                    echo "Please verify your credentials are correct."
                fi
            else
                echo -e "${YELLOW}⚠ curl not available, skipping API test${NC}"
            fi
        fi
    fi
fi

echo ""

# ============================================================================
# VALIDATION
# ============================================================================

echo -e "${BLUE}✅ Step 5: Installation Validation${NC}"
echo ""

# Check if main script exists
if [ -f "trello2beads.py" ]; then
    echo -e "${GREEN}✓ trello2beads.py found${NC}"
else
    echo -e "${RED}✗ trello2beads.py not found${NC}"
    echo "  Make sure you're running this script from the trello2beads directory"
fi

# Check Python can import requests
echo -n "Checking Python dependencies... "
if python3 -c "import requests" 2>/dev/null; then
    echo -e "${GREEN}✓ All imports successful${NC}"
else
    echo -e "${RED}✗ Missing dependencies${NC}"
    echo "  Try: pip install -r requirements.txt"
fi

# Run tests if available
if [ -f "run_tests.sh" ] && [ -d "tests" ]; then
    echo ""
    echo -n "Run tests to verify installation? [y/N] "
    read -r run_tests
    if [[ "$run_tests" =~ ^[Yy]$ ]]; then
        echo ""
        ./run_tests.sh --quick
    fi
fi

echo ""

# ============================================================================
# SUCCESS
# ============================================================================

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Installation complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "📖 Quick Start:"
echo ""
if [ "$USE_VENV" = true ]; then
    echo "  1. Activate virtual environment:"
    echo "       source $VENV_DIR/bin/activate"
    echo ""
fi
echo "  2. Initialize beads database:"
echo "       mkdir my-project && cd my-project"
echo "       bd init --prefix myproject"
echo ""
echo "  3. Run conversion:"
echo "       cd .."
echo "       python3 trello2beads.py"
echo ""
echo "  4. Preview without creating issues:"
echo "       python3 trello2beads.py --dry-run"
echo ""
echo "📚 Documentation:"
echo "  - README.md for full documentation"
echo "  - python3 trello2beads.py --help"
echo ""
echo "🧪 Run tests:"
echo "  ./run_tests.sh --quick"
echo ""
