/**
 * ◑ Ephe — Knowledge Chunk Builder
 * knowledge/build_chunks.mjs
 *
 * Konvertiert alle Markdown-Dateien in chunks.json.
 * Chunks werden mit Priorität, Domain und Titel getaggt.
 *
 * TRIAGE-SYSTEM:
 *   SOFORT     — Lebensbedrohliche Info, Sofortmaßnahmen (<30 Sek lesbar)
 *   ANLEITUNG  — Schritt-für-Schritt Anleitung (1-10 Min)
 *   HINTERGRUND — Kontext, Details, Tabellen
 *
 * Usage: node knowledge/build_chunks.mjs
 * Output: knowledge/chunks.json (ins Repo committen!)
 */

import { readdirSync, readFileSync, writeFileSync, statSync } from 'node:fs';
import { join, dirname, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const KB_DIR = __dirname;
const OUTPUT = join(KB_DIR, 'chunks.json');

// ── Triage-Keyword-Definitionen ──────────────────────────────────────

const SOFORT_KEYWORDS = [
  'sofortmaßnahm', 'sofort ', 'lebensgefahr', 'lebensrettend', 'herzstill',
  'bewusstlos', 'nicht atmet', 'kein puls', 'anaphylax', 'atemnot',
  'starkstromb', 'vergiftung sofort', 'notruf', '112', 'erste-hilfe',
  'hlw', 'herzdruckmassage', 'wiederbelebung', 'schock',
  'nuklearer notfall', 'chemie-unfall', 'dekontamination sofort',
  'rettungsdecke', 'druckverband', 'tourniquet', 'abschnüren',
];

const ANLEITUNG_KEYWORDS = [
  'schritt', 'schritte', 'vorgehen', 'anleitung', 'methode', 'verfahren',
  '1.', '2.', '3.', 'zuerst', 'dann', 'danach', 'abschließend',
  'material', 'benötigt', 'vorbereitung', 'installation', 'einrichten',
  'reparatur', 'wartung', 'diagnose', 'prüfung', 'test',
];

/** Bestimmt die Triage-Priorität eines Text-Chunks */
function detectPriority(text, heading) {
  const combined = (text + ' ' + heading).toLowerCase();
  
  if (SOFORT_KEYWORDS.some(kw => combined.includes(kw))) return 'SOFORT';
  if (ANLEITUNG_KEYWORDS.some(kw => combined.includes(kw))) return 'ANLEITUNG';
  return 'HINTERGRUND';
}

// ── Domain-Konfiguration ─────────────────────────────────────────────

const DOMAINS = {
  medical:      { label: 'Gesundheit & Erste Hilfe',     agent: 'medic_agent' },
  engineering:  { label: 'Technik & Reparatur',           agent: 'engineer_agent' },
  survival:     { label: 'Alltag & Vorsorge',             agent: 'navigator_agent' },
  'life-skills': { label: 'Life Skills & Sicherheitswissen', agent: 'medic_agent' },
  navigation:   { label: 'Navigation & Orientierung',    agent: 'navigator_agent' },
  system:       { label: 'Energie & Infrastruktur',       agent: 'sensor_agent' },
};

// ── Markdown-Chunker ─────────────────────────────────────────────────

/**
 * Chunkt eine Markdown-Datei in sinnvolle Abschnitte.
 * Jede Überschrift (##, ###) startet einen neuen Chunk.
 * Max. Chunk-Größe: 800 Zeichen (konservativ für lokale Gemma-Modelle).
 */
function chunkMarkdown(content, domain, filename) {
  const lines = content.split('\n');
  const chunks = [];
  
  let currentHeading = '';
  let currentTopHeading = '';
  let currentLines = [];
  let inCodeBlock = false;
  
  function flushChunk() {
    const text = currentLines.join('\n').trim();
    if (text.length < 40) return; // Zu kurz, skip
    
    const priority = detectPriority(text, currentHeading);
    const title = currentTopHeading
      ? `${currentTopHeading} — ${currentHeading}`.replace(/^#+\s*/, '')
      : currentHeading.replace(/^#+\s*/, '');
    
    // Große Chunks aufteilen (max 800 Zeichen)
    if (text.length > 800) {
      const parts = splitLargeChunk(text, 800);
      parts.forEach((part, i) => {
        chunks.push({
          id: `${domain}/${filename}/${chunks.length}`,
          domain,
          source: filename,
          title: parts.length > 1 ? `${title} (${i + 1}/${parts.length})` : title,
          text: part,
          priority,
          agent: DOMAINS[domain]?.agent || 'medic_agent',
        });
      });
    } else {
      chunks.push({
        id: `${domain}/${filename}/${chunks.length}`,
        domain,
        source: filename,
        title,
        text,
        priority,
        agent: DOMAINS[domain]?.agent || 'medic_agent',
      });
    }
    
    currentLines = [];
  }
  
  for (const line of lines) {
    // Code-Block tracking (Code-Blöcke intakt halten)
    if (line.startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      currentLines.push(line);
      continue;
    }
    
    if (inCodeBlock) {
      currentLines.push(line);
      continue;
    }
    
    // Hauptüberschrift (# oder ##)
    if (line.match(/^#{1,2}\s/) && !inCodeBlock) {
      flushChunk();
      currentTopHeading = currentHeading = line;
      currentLines = [line];
      continue;
    }
    
    // Unterüberschrift (### oder ####) → neuer Chunk
    if (line.match(/^#{3,4}\s/) && !inCodeBlock) {
      flushChunk();
      currentHeading = line;
      currentLines = [line];
      continue;
    }
    
    currentLines.push(line);
  }
  
  flushChunk(); // letzter Chunk
  return chunks;
}

/** Teilt große Chunks an Absatzgrenzen auf */
function splitLargeChunk(text, maxChars) {
  if (text.length <= maxChars) return [text];
  
  const parts = [];
  const paragraphs = text.split('\n\n');
  let current = '';
  
  for (const para of paragraphs) {
    if ((current + para).length > maxChars && current.length > 0) {
      parts.push(current.trim());
      current = '';
    }
    current += para + '\n\n';
  }
  
  if (current.trim()) parts.push(current.trim());
  return parts;
}

// ── Main ──────────────────────────────────────────────────────────────

function build() {
  console.log('');
  console.log('◑ Ephe Knowledge Chunk Builder');
  console.log('  Triage-System: SOFORT / ANLEITUNG / HINTERGRUND');
  console.log('');
  
  const allChunks = [];
  
  for (const [domain, config] of Object.entries(DOMAINS)) {
    const domainDir = join(KB_DIR, domain);
    
    let files;
    try {
      files = readdirSync(domainDir).filter(f => extname(f) === '.md');
    } catch {
      console.log(`  ⚠ Verzeichnis nicht gefunden: ${domain}/`);
      continue;
    }
    
    console.log(`  📁 ${domain}: ${files.length} Dateien`);
    
    for (const file of files) {
      const filepath = join(domainDir, file);
      const content = readFileSync(filepath, 'utf-8');
      const chunks = chunkMarkdown(content, domain, file);
      allChunks.push(...chunks);
      
      const sofort = chunks.filter(c => c.priority === 'SOFORT').length;
      const anleit = chunks.filter(c => c.priority === 'ANLEITUNG').length;
      const hinter = chunks.filter(c => c.priority === 'HINTERGRUND').length;
      
      console.log(`    - ${file}: ${chunks.length} Chunks [🚨SOFORT:${sofort} 📋ANLEIT:${anleit} 📖HINTER:${hinter}]`);
    }
  }
  
  // Output schreiben
  writeFileSync(OUTPUT, JSON.stringify(allChunks, null, 2), 'utf-8');
  
  // Statistiken
  const byPriority = {
    SOFORT: allChunks.filter(c => c.priority === 'SOFORT').length,
    ANLEITUNG: allChunks.filter(c => c.priority === 'ANLEITUNG').length,
    HINTERGRUND: allChunks.filter(c => c.priority === 'HINTERGRUND').length,
  };
  const byDomain = {};
  for (const c of allChunks) byDomain[c.domain] = (byDomain[c.domain] || 0) + 1;
  const sizeKB = Math.round(JSON.stringify(allChunks).length / 1024);
  
  console.log('');
  console.log('════════════════════════════════════════════════');
  console.log(' ◑ chunks.json erstellt');
  console.log('════════════════════════════════════════════════');
  console.log(`  Chunks gesamt:  ${allChunks.length}`);
  console.log(`  🚨 SOFORT:      ${byPriority.SOFORT}`);
  console.log(`  📋 ANLEITUNG:   ${byPriority.ANLEITUNG}`);
  console.log(`  📖 HINTERGRUND: ${byPriority.HINTERGRUND}`);
  console.log(`  Dateigröße:     ${sizeKB}KB`);
  console.log('');
  console.log('  📦 Bitte ins Git-Repository committen:');
  console.log('     git add knowledge/chunks.json');
  console.log('     git commit -m "chore: update knowledge chunks"');
  console.log('════════════════════════════════════════════════');
  console.log('');
}

build();
