#!/usr/bin/env bash
#
# run_tests.sh - Comprehensive test runner for Python projects
#
# Usage:
#   ./run_tests.sh           # Run all quality checks
#   ./run_tests.sh --quick   # Run only tests (skip linting/type checking)
#   ./run_tests.sh --help    # Show help
#
# Configuration (can be overridden via environment variables):
#   VENV_DIR             - Virtual environment directory (default: .venv)
#   MIN_COVERAGE         - Minimum coverage percentage (default: 80)
#   REQUIREMENTS_FILE    - Dev requirements file (default: requirements-dev.txt)
#   TEST_DIR             - Test directory (default: tests/)
#   MAIN_MODULE          - Main module to type check (default: auto-detect *.py in root)
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (with environment variable overrides)
VENV_DIR="${VENV_DIR:-.venv}"
MIN_COVERAGE="${MIN_COVERAGE:-80}"
TEST_DIR="${TEST_DIR:-tests/}"
MAIN_MODULE="${MAIN_MODULE:-trello2beads}"  # Package to type check

# Parse arguments
QUICK_MODE=false
HELP_MODE=false

for arg in "$@"; do
    case $arg in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --help|-h)
            HELP_MODE=true
            shift
            ;;
        *)
            # Unknown option
            ;;
    esac
done

# Show help
if [ "$HELP_MODE" = true ]; then
    echo "Python Project Test Runner"
    echo ""
    echo "Usage:"
    echo "  ./run_tests.sh           Run all quality checks (tests, linting, types)"
    echo "  ./run_tests.sh --quick   Run only tests (skip linting/type checking)"
    echo "  ./run_tests.sh --help    Show this help message"
    echo ""
    echo "Quality checks performed:"
    echo "  1. Python tests (pytest) with coverage"
    echo "  2. Code linting (ruff) - unless --quick"
    echo "  3. Type checking (mypy) - unless --quick"
    echo ""
    echo "Configuration (environment variables):"
    echo "  VENV_DIR=${VENV_DIR}"
    echo "  MIN_COVERAGE=${MIN_COVERAGE}%"
    echo "  TEST_DIR=${TEST_DIR}"
    echo "  MAIN_MODULE=${MAIN_MODULE}"
    exit 0
fi

# Detect project name from directory
PROJECT_NAME=$(basename "$(pwd)")

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  ${PROJECT_NAME} Test Runner${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""

# Step 1: Check if virtual environment exists, create if needed
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment found${NC}"
fi

# Step 2: Activate virtual environment
source "$VENV_DIR/bin/activate"

# Step 3: Ensure package is installed in editable mode
echo ""
echo -e "${BLUE}📦 Checking dependencies...${NC}"
if [ -f "pyproject.toml" ]; then
    pip install -q --upgrade pip
    pip install -q -e ".[dev]"
    echo -e "${GREEN}✓ Package installed in editable mode with dev dependencies${NC}"
else
    echo -e "${YELLOW}⚠️  pyproject.toml not found, skipping package install${NC}"
fi

# Step 4: Run tests with coverage
echo ""
echo -e "${BLUE}🧪 Running tests...${NC}"
echo ""

# Run pytest and capture exit code
set +e  # Temporarily disable exit on error
pytest "$TEST_DIR" -v --cov=. --cov-report=term --cov-report=html --cov-report=xml
PYTEST_EXIT=$?
set -e

if [ $PYTEST_EXIT -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo ""
    echo -e "${RED}❌ Tests failed (exit code: $PYTEST_EXIT)${NC}"
    exit $PYTEST_EXIT
fi

# Extract coverage percentage from .coverage if coverage.py is available
if command -v coverage &> /dev/null; then
    COVERAGE_PCT=$(coverage report | grep "TOTAL" | awk '{print $NF}' | sed 's/%//')

    if [ -n "$COVERAGE_PCT" ]; then
        # Compare coverage to minimum (using bc for float comparison)
        if command -v bc &> /dev/null; then
            COVERAGE_OK=$(echo "$COVERAGE_PCT >= $MIN_COVERAGE" | bc -l)

            if [ "$COVERAGE_OK" -eq 1 ]; then
                echo -e "${GREEN}✓ Coverage: ${COVERAGE_PCT}% (target: ${MIN_COVERAGE}%)${NC}"
            else
                echo -e "${YELLOW}⚠️  Coverage: ${COVERAGE_PCT}% (below target: ${MIN_COVERAGE}%)${NC}"
            fi
        else
            echo -e "${BLUE}ℹ️  Coverage: ${COVERAGE_PCT}%${NC}"
        fi
    fi
fi

# Skip linting and type checking in quick mode
if [ "$QUICK_MODE" = true ]; then
    echo ""
    echo -e "${BLUE}⚡ Quick mode: Skipping linting and type checking${NC}"
    echo ""
    echo -e "${GREEN}=======================================${NC}"
    echo -e "${GREEN}  ✅ Quick tests passed!${NC}"
    echo -e "${GREEN}=======================================${NC}"
    exit 0
fi

# Step 5: Run linting with ruff
echo ""
echo -e "${BLUE}🔍 Running code linting (ruff)...${NC}"
echo ""

set +e
ruff check . --exclude .venv --exclude htmlcov
RUFF_EXIT=$?
set -e

if [ $RUFF_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓ No linting issues${NC}"
else
    echo -e "${YELLOW}⚠️  Linting issues found (exit code: $RUFF_EXIT)${NC}"
    echo -e "${YELLOW}   Run 'ruff check --fix' to auto-fix some issues${NC}"
fi

# Step 6: Run type checking with mypy
echo ""
echo -e "${BLUE}🔎 Running type checking (mypy)...${NC}"
echo ""

# Check if package directory exists
if [ ! -d "$MAIN_MODULE" ]; then
    echo -e "${YELLOW}⚠️  Package directory '${MAIN_MODULE}' not found, skipping type checking${NC}"
    MYPY_EXIT=0
else
    set +e
    mypy "$MAIN_MODULE"
    MYPY_EXIT=$?
    set -e

    if [ $MYPY_EXIT -eq 0 ]; then
        echo -e "${GREEN}✓ No type issues${NC}"
    else
        echo -e "${YELLOW}⚠️  Type checking issues found (exit code: $MYPY_EXIT)${NC}"
    fi
fi

# Final summary
echo ""
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Summary${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""

TOTAL_ISSUES=0

if [ $PYTEST_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓ Tests: PASSED${NC}"
else
    echo -e "${RED}✗ Tests: FAILED${NC}"
    TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
fi

if [ $RUFF_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓ Linting: PASSED${NC}"
else
    echo -e "${YELLOW}⚠ Linting: ISSUES FOUND${NC}"
    TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
fi

if [ $MYPY_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓ Type checking: PASSED${NC}"
else
    echo -e "${YELLOW}⚠ Type checking: ISSUES FOUND${NC}"
    TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
fi

echo ""

if [ $TOTAL_ISSUES -eq 0 ]; then
    echo -e "${GREEN}=======================================${NC}"
    echo -e "${GREEN}  ✅ All quality checks passed!${NC}"
    echo -e "${GREEN}=======================================${NC}"
    exit 0
else
    echo -e "${YELLOW}=======================================${NC}"
    echo -e "${YELLOW}  ⚠️  ${TOTAL_ISSUES} quality check(s) had issues${NC}"
    echo -e "${YELLOW}=======================================${NC}"

    # Only fail CI if tests failed (not linting/types)
    if [ $PYTEST_EXIT -ne 0 ]; then
        exit 1
    else
        exit 0  # Warnings but tests passed
    fi
fi
