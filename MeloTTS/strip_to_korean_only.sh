#!/bin/bash
#
# Script to strip MeloTTS down to Korean-only TTS
# This removes all other language modules, training files, and unnecessary components
# while keeping everything needed for Korean TTS to work at the same quality level.
#
# Usage: ./strip_to_korean_only.sh [--no-backup] [--remove-ui] [--remove-docs]
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
BACKUP=true
REMOVE_UI=false
REMOVE_DOCS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-backup)
            BACKUP=false
            shift
            ;;
        --remove-ui)
            REMOVE_UI=true
            shift
            ;;
        --remove-docs)
            REMOVE_DOCS=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--no-backup] [--remove-ui] [--remove-docs]"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MeloTTS Korean-Only Stripper${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Safety check
if [ ! -f "melo/text/korean.py" ]; then
    echo -e "${RED}Error: korean.py not found. Are you in the MeloTTS directory?${NC}"
    exit 1
fi

# Create backup if requested
if [ "$BACKUP" = true ]; then
    BACKUP_DIR="backup_before_strip_$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}Creating backup to: $BACKUP_DIR${NC}"
    mkdir -p "$BACKUP_DIR"
    
    # Backup essential directories
    cp -r melo "$BACKUP_DIR/" 2>/dev/null || true
    cp -r test "$BACKUP_DIR/" 2>/dev/null || true
    cp setup.py requirements.txt "$BACKUP_DIR/" 2>/dev/null || true
    
    echo -e "${GREEN}Backup created!${NC}"
    echo ""
fi

echo -e "${YELLOW}Starting removal process...${NC}"
echo ""

# Counter for removed items
REMOVED_COUNT=0

# Function to remove file/dir and count
remove_item() {
    if [ -e "$1" ]; then
        rm -rf "$1"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
        echo -e "  ${GREEN}✓${NC} Removed: $1"
    fi
}

# 1. Remove other language modules
echo -e "${BLUE}[1/8] Removing other language modules...${NC}"
remove_item "melo/text/chinese.py"
remove_item "melo/text/chinese_bert.py"
remove_item "melo/text/chinese_mix.py"
remove_item "melo/text/japanese.py"  # Keep japanese_bert.py!
remove_item "melo/text/english.py"
remove_item "melo/text/english_bert.py"
remove_item "melo/text/french.py"
remove_item "melo/text/french_bert.py"
remove_item "melo/text/spanish.py"
remove_item "melo/text/spanish_bert.py"
echo ""

# 2. Remove phonemizer directories
echo -e "${BLUE}[2/8] Removing phonemizer directories...${NC}"
remove_item "melo/text/es_phonemizer"
remove_item "melo/text/fr_phonemizer"
remove_item "melo/text/english_utils"
echo ""

# 3. Remove language-specific data files
echo -e "${BLUE}[3/8] Removing language-specific data files...${NC}"
remove_item "melo/text/cmudict_cache.pickle"
remove_item "melo/text/cmudict.rep"
remove_item "melo/text/opencpop-strict.txt"
remove_item "melo/text/tone_sandhi.py"
remove_item "melo/text/cleaner_multiling.py"
echo ""

# 4. Remove training files
echo -e "${BLUE}[4/8] Removing training files...${NC}"
remove_item "melo/train.py"
remove_item "melo/train.sh"
remove_item "melo/data_utils.py"
remove_item "melo/losses.py"
remove_item "melo/preprocess_text.py"
remove_item "melo/infer.py"
remove_item "melo/init_downloads.py"
echo ""

# 5. Remove UI/CLI (if requested)
if [ "$REMOVE_UI" = true ]; then
    echo -e "${BLUE}[5/8] Removing UI and CLI...${NC}"
    remove_item "melo/app.py"
    remove_item "melo/main.py"
else
    echo -e "${BLUE}[5/8] Keeping UI and CLI (use --remove-ui to remove)${NC}"
fi
echo ""

# 6. Remove test files (other languages)
echo -e "${BLUE}[6/8] Removing test files for other languages...${NC}"
remove_item "test/test_base_model_tts_package.py"
remove_item "test/test_base_model_tts_package_from_S3.py"
remove_item "test/basetts_test_resources/en_egs_text.txt"
remove_item "test/basetts_test_resources/es_egs_text.txt"
remove_item "test/basetts_test_resources/fr_egs_text.txt"
remove_item "test/basetts_test_resources/jp_egs_text.txt"
remove_item "test/basetts_test_resources/zh_mix_en_egs_text.txt"
# Keep: test/basetts_test_resources/kr_egs_text.txt
echo ""

# 7. Remove documentation (if requested)
if [ "$REMOVE_DOCS" = true ]; then
    echo -e "${BLUE}[7/8] Removing documentation...${NC}"
    remove_item "docs"
    remove_item "logo.png"
else
    echo -e "${BLUE}[7/8] Keeping documentation (use --remove-docs to remove)${NC}"
fi
echo ""

# 8. Remove build artifacts and cache
echo -e "${BLUE}[8/8] Cleaning build artifacts and cache...${NC}"
remove_item "melotts.egg-info"
find melo -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find melo -name "*.pyc" -delete 2>/dev/null || true
find melo -name "*.pyo" -delete 2>/dev/null || true
remove_item "*.wav"  # Generated test audio files
echo ""

# Remove Docker and CI (optional)
echo -e "${BLUE}[Extra] Removing Docker and CI files...${NC}"
remove_item "Dockerfile"
remove_item ".github"
echo ""

# Remove example data
echo -e "${BLUE}[Extra] Removing example data...${NC}"
remove_item "melo/data"
remove_item "melo/configs"  # Base config not needed if using MeloTTS-Korean config
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Removal Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Removed ${GREEN}$REMOVED_COUNT${NC} items"
echo ""

# Verify essential files still exist
echo -e "${BLUE}Verifying essential files...${NC}"
ESSENTIAL_FILES=(
    "melo/text/korean.py"
    "melo/text/ko_dictionary.py"
    "melo/text/japanese_bert.py"
    "melo/text/symbols.py"
    "melo/text/punctuation.py"
    "melo/text/cleaner.py"
    "melo/text/__init__.py"
    "melo/api.py"
    "melo/models.py"
    "melo/utils.py"
)

ALL_PRESENT=true
for file in "${ESSENTIAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "  ${GREEN}✓${NC} $file"
    else
        echo -e "  ${RED}✗${NC} $file ${RED}(MISSING!)${NC}"
        ALL_PRESENT=false
    fi
done

echo ""

if [ "$ALL_PRESENT" = true ]; then
    echo -e "${GREEN}✓ All essential files are present!${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Test the Korean TTS:"
    echo "     ${BLUE}source venv/bin/activate${NC}"
    echo "     ${BLUE}python test_korean_tts.py${NC}"
    echo ""
    echo "  2. If everything works, you can remove the backup:"
    if [ "$BACKUP" = true ]; then
        echo "     ${BLUE}rm -rf $BACKUP_DIR${NC}"
    fi
    echo ""
    echo -e "${GREEN}Korean-only TTS setup complete! 🎉${NC}"
else
    echo -e "${RED}⚠ Warning: Some essential files are missing!${NC}"
    echo -e "${YELLOW}You may need to restore from backup.${NC}"
    if [ "$BACKUP" = true ]; then
        echo -e "${YELLOW}Backup location: $BACKUP_DIR${NC}"
    fi
    exit 1
fi

