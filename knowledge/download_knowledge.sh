#!/usr/bin/env bash
# ◑ Ephe — Knowledge Base Download & Indexer
# Downloads official German crisis guides (BBK, BfS, BSI, THW)
# and converts PDFs to searchable text for offline RAG.
#
# Usage: ./download_knowledge.sh
# Requirements: curl, pdftotext (poppler-utils)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_DIR="$SCRIPT_DIR"
PDF_DIR="$KB_DIR/pdfs"
INDEX_FILE="$KB_DIR/index.json"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[KB]${NC} $1"; }
warn() { echo -e "${YELLOW}[KB]${NC} $1"; }
err()  { echo -e "${RED}[KB]${NC} $1"; }

# ── Check dependencies ──────────────────────────────────────────────
check_deps() {
  local missing=0
  for cmd in curl pdftotext; do
    if ! command -v "$cmd" &>/dev/null; then
      err "Fehlt: $cmd"
      missing=1
    fi
  done
  if [ $missing -eq 1 ]; then
    echo ""
    echo "Installiere fehlende Abhängigkeiten:"
    echo "  Ubuntu/Debian: sudo apt install poppler-utils curl"
    echo "  Fedora:        sudo dnf install poppler-utils curl"
    echo "  macOS:         brew install poppler curl"
    exit 1
  fi
}

# ── Download PDFs ───────────────────────────────────────────────────
download_pdfs() {
  mkdir -p "$PDF_DIR"

  # Official German government sources (§ 5 UrhG — amtliche Werke, frei verwendbar)
  declare -A SOURCES=(
    # BBK (Bundesamt für Bevölkerungsschutz und Katastrophenhilfe)
    ["bbk_ratgeber_notfallvorsorge"]="https://www.bbk.bund.de/SharedDocs/Downloads/DE/Mediathek/Publikationen/Buergerinformationen/ratgeber-notfallvorsorge.pdf?__blob=publicationFile&v=15"
    ["bbk_kochen_ohne_strom"]="https://www.bbk.bund.de/SharedDocs/Downloads/DE/Mediathek/Publikationen/Buergerinformationen/kochen-ohne-strom.pdf?__blob=publicationFile&v=7"
    ["bbk_checkliste"]="https://www.bbk.bund.de/SharedDocs/Downloads/DE/Mediathek/Publikationen/Buergerinformationen/checkliste-notfallvorsorge.pdf?__blob=publicationFile&v=11"
    ["bbk_ratgeber_hochwasser"]="https://www.bbk.bund.de/SharedDocs/Downloads/DE/Mediathek/Publikationen/Buergerinformationen/ratgeber-hochwasser.pdf?__blob=publicationFile&v=6"
    # BfS (Bundesamt für Strahlenschutz)
    ["bfs_strahlenschutz"]="https://www.bfs.de/SharedDocs/Downloads/BfS/DE/broschueren/str-notfallvorsorge.pdf?__blob=publicationFile&v=6"
  )

  local downloaded=0
  local skipped=0

  for name in "${!SOURCES[@]}"; do
    local url="${SOURCES[$name]}"
    local filepath="$PDF_DIR/${name}.pdf"

    if [ -f "$filepath" ]; then
      log "✓ Bereits vorhanden: $name.pdf"
      ((skipped++))
      continue
    fi

    log "⬇ Lade herunter: $name ..."
    if curl -fsSL -o "$filepath" "$url" 2>/dev/null; then
      local size=$(du -h "$filepath" | cut -f1)
      log "  ✓ $name.pdf ($size)"
      ((downloaded++))
    else
      warn "  ✗ Download fehlgeschlagen: $name"
      rm -f "$filepath"
    fi
  done

  echo ""
  log "Download abgeschlossen: $downloaded neu, $skipped bereits vorhanden"
}

# ── Convert PDFs to Text ───────────────────────────────────────────
convert_pdfs() {
  log "Konvertiere PDFs zu Text..."
  local converted=0

  for pdf in "$PDF_DIR"/*.pdf; do
    [ -f "$pdf" ] || continue
    local name=$(basename "$pdf" .pdf)
    local domain="survival"  # Default domain

    # Route to correct domain based on filename
    case "$name" in
      *medic*|*erste*|*hilfe*|*drk*|*gesundheit*) domain="medical" ;;
      *solar*|*technik*|*reparatur*|*thw*|*engineer*) domain="engineering" ;;
      *nuklear*|*strahl*|*cbrn*|*bfs*) domain="cbrn" ;;
      *bsi*|*it*|*system*|*cyber*) domain="system" ;;
      *) domain="survival" ;;
    esac

    local outdir="$KB_DIR/$domain"
    local outfile="$outdir/${name}.md"
    mkdir -p "$outdir"

    if [ -f "$outfile" ] && [ "$outfile" -nt "$pdf" ]; then
      log "✓ Aktuell: $domain/$name.md"
      continue
    fi

    log "📄 Konvertiere: $name.pdf → $domain/$name.md"

    # Extract text with pdftotext (preserves layout)
    local rawtext
    rawtext=$(pdftotext -layout "$pdf" - 2>/dev/null || echo "")

    if [ -z "$rawtext" ]; then
      warn "  Kein Text extrahierbar (gescanntes PDF?): $name"
      continue
    fi

    # Write as Markdown with metadata header
    {
      echo "# $name"
      echo "## Quelle: Offizielles Dokument der Bundesregierung"
      echo "## Domäne: $domain"
      echo "## Lizenz: Amtliches Werk (§ 5 UrhG) — frei verwendbar"
      echo ""
      echo "---"
      echo ""
      echo "$rawtext"
    } > "$outfile"

    local lines=$(wc -l < "$outfile")
    log "  ✓ $domain/$name.md ($lines Zeilen)"
    ((converted++))
  done

  echo ""
  log "Konvertierung abgeschlossen: $converted Dateien verarbeitet"
}

# ── Update Index ───────────────────────────────────────────────────
update_index() {
  local total_files=$(find "$KB_DIR" -name "*.md" -not -path "*/README*" | wc -l)
  local total_pdfs=$(find "$PDF_DIR" -name "*.pdf" 2>/dev/null | wc -l)
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Update stats in index.json using python (available everywhere)
  python3 -c "
import json, sys
with open('$INDEX_FILE', 'r') as f:
    idx = json.load(f)
idx['lastIndexed'] = '$timestamp'
idx['stats']['totalFiles'] = $total_files
idx['stats']['totalPDFs'] = $total_pdfs
with open('$INDEX_FILE', 'w') as f:
    json.dump(idx, f, indent=2, ensure_ascii=False)
print(f'Index aktualisiert: {$total_files} MD-Dateien, {$total_pdfs} PDFs')
" 2>/dev/null || warn "Index-Update fehlgeschlagen"
}

# ── Summary ────────────────────────────────────────────────────────
summary() {
  echo ""
  echo "════════════════════════════════════════════════"
  echo " ◑ Ephe Knowledge Base — Status"
  echo "════════════════════════════════════════════════"
  echo ""

  for domain in medical engineering survival cbrn system; do
    local dir="$KB_DIR/$domain"
    if [ -d "$dir" ]; then
      local count=$(find "$dir" -name "*.md" | wc -l)
      local size=$(du -sh "$dir" 2>/dev/null | cut -f1)
      echo "  📁 $domain: $count Dateien ($size)"
    else
      echo "  📁 $domain: (leer)"
    fi
  done

  local pdf_count=$(find "$PDF_DIR" -name "*.pdf" 2>/dev/null | wc -l)
  local pdf_size=$(du -sh "$PDF_DIR" 2>/dev/null | cut -f1 || echo "0")
  echo ""
  echo "  📋 PDFs: $pdf_count Dateien ($pdf_size)"
  echo ""
  echo "════════════════════════════════════════════════"
}

# ── Main ───────────────────────────────────────────────────────────
main() {
  echo ""
  echo "◑ Ephe Knowledge Base Downloader"
  echo "  Offizielle deutsche Krisenratgeber (BBK, BfS, BSI)"
  echo ""

  check_deps
  download_pdfs
  convert_pdfs
  update_index
  summary

  echo ""
  log "Fertig! Wissensbasis ist bereit für Offline-RAG."
  echo ""
}

main "$@"
