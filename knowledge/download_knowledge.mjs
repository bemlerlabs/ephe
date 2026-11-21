/**
 * ◑ Ephe — Offizieller Knowledge-Base Crawler & Indexer
 * 
 * Crawlt offizielle deutsche Krisenratgeber-Seiten (BBK, THW, DRK, BfS)
 * und speichert sie als durchsuchbares Markdown für den Offline-RAG.
 * 
 * Keine PDFs nötig — crawlt direkt den Volltext der offiziellen Webseiten.
 * Alle Quellen sind amtliche Werke (§ 5 UrhG) und frei verwendbar.
 * 
 * Usage: node download_knowledge.mjs
 */

import { writeFileSync, mkdirSync, existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const KB_DIR = __dirname;

/**
 * All official German sources to crawl.
 * These are publicly available government resources (§ 5 UrhG).
 */
const SOURCES = [
  // ── BBK Vorsorge-Ratgeber ──────────────────────────────────────
  {
    id: 'bbk_vorsorge_essen_trinken',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Essen-und-Trinken/essen-und-trinken_node.html',
    domain: 'survival',
    title: 'BBK — Essen und Trinken bei Notfallvorsorge',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },
  {
    id: 'bbk_vorsorge_hausapotheke',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Hausapotheke/hausapotheke_node.html',
    domain: 'medical',
    title: 'BBK — Hausapotheke',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },
  {
    id: 'bbk_vorsorge_notgepaeck',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Notgepaeck/notgepaeck_node.html',
    domain: 'survival',
    title: 'BBK — Notgepäck',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },
  {
    id: 'bbk_vorsorge_dokumente',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Dokumente/dokumente_node.html',
    domain: 'survival',
    title: 'BBK — Wichtige Dokumente sichern',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },

  // ── BBK Verhalten bei Notsituationen ──────────────────────────
  {
    id: 'bbk_verhalten_stromausfall',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Stromausfall/stromausfall_node.html',
    domain: 'engineering',
    title: 'BBK — Verhalten bei Stromausfall',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },
  {
    id: 'bbk_verhalten_hochwasser',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Hochwasser/hochwasser_node.html',
    domain: 'survival',
    title: 'BBK — Verhalten bei Hochwasser',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },
  {
    id: 'bbk_verhalten_unwetter',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Unwetter/unwetter_node.html',
    domain: 'survival',
    title: 'BBK — Verhalten bei Unwetter',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },
  {
    id: 'bbk_verhalten_erdbeben',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Erdbeben/erdbeben_node.html',
    domain: 'survival',
    title: 'BBK — Verhalten bei Erdbeben',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },
  {
    id: 'bbk_verhalten_feuer',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Vorsorge/Feuer/feuer_node.html',
    domain: 'survival',
    title: 'BBK — Verhalten bei Feuer',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },
  {
    id: 'bbk_gefahrenschutz',
    url: 'https://www.bbk.bund.de/DE/Themen/CBRN-Schutz/cbrn-schutz_node.html',
    domain: 'life-skills',
    title: 'BBK — Schutz bei gefährlichen Stoffen (Chemie, Bio, Radioaktiv)',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },

  // ── BBK Warnung ──────────────────────────────────────────────
  {
    id: 'bbk_warnung',
    url: 'https://www.bbk.bund.de/DE/Warnung-Vorsorge/Warnung-in-Deutschland/warnung-in-deutschland_node.html',
    domain: 'survival',
    title: 'BBK — Warnung in Deutschland (Sirenen, NINA, Cell-Broadcast)',
    source: 'Bundesamt für Bevölkerungsschutz und Katastrophenhilfe'
  },

  // ── DRK Erste Hilfe ──────────────────────────────────────────
  {
    id: 'drk_erste_hilfe_uebersicht',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-tipps-und-massnahmen/',
    domain: 'medical',
    title: 'DRK — Erste Hilfe: Tipps und Maßnahmen',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_stabile_seitenlage',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/stabile-seitenlage/',
    domain: 'medical',
    title: 'DRK — Stabile Seitenlage',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_herzinfarkt',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/herzinfarkt/',
    domain: 'medical',
    title: 'DRK — Herzinfarkt erkennen und handeln',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_schlaganfall',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/schlaganfall/',
    domain: 'medical',
    title: 'DRK — Schlaganfall erkennen und handeln',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_wiederbelebung',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/wiederbelebung/',
    domain: 'medical',
    title: 'DRK — Herz-Lungen-Wiederbelebung',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_verbrennungen',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/verbrennungen/',
    domain: 'medical',
    title: 'DRK — Verbrennungen',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_knochenbruch',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/knochenbrueche/',
    domain: 'medical',
    title: 'DRK — Knochenbrüche',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_vergiftungen',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/vergiftungen/',
    domain: 'medical',
    title: 'DRK — Vergiftungen',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_unterkuehlung',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/unterkuehlung/',
    domain: 'medical',
    title: 'DRK — Unterkühlung',
    source: 'Deutsches Rotes Kreuz'
  },
  {
    id: 'drk_sonnenstich',
    url: 'https://www.drk.de/hilfe-in-deutschland/erste-hilfe/erste-hilfe-a-z/sonnenstich-hitzschlag/',
    domain: 'medical',
    title: 'DRK — Sonnenstich und Hitzschlag',
    source: 'Deutsches Rotes Kreuz'
  },

  // ── BfS Strahlenschutz ──────────────────────────────────────
  {
    id: 'bfs_nuklearer_notfall',
    url: 'https://www.bfs.de/DE/themen/ion/notfallschutz/notfall/notfall_node.html',
    domain: 'life-skills',
    title: 'BfS — Verhalten bei einem nuklearen Notfall',
    source: 'Bundesamt für Strahlenschutz'
  },
  {
    id: 'bfs_jodtabletten',
    url: 'https://www.bfs.de/DE/themen/ion/notfallschutz/jod/jod_node.html',
    domain: 'life-skills',
    title: 'BfS — Jodtabletten bei nuklearem Notfall',
    source: 'Bundesamt für Strahlenschutz'
  },
];

/** Elements whose content is dropped together with the tag. */
const DROPPED_ELEMENTS = new Set([
  'script', 'style', 'noscript', 'template', 'iframe', 'svg', 'canvas',
  'nav', 'footer', 'header', 'form',
]);

/** Elements that never take a closing tag. */
const VOID_ELEMENTS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
  'param', 'source', 'track', 'wbr',
]);

/** Elements that put a line break around their text. */
const BLOCK_ELEMENTS = new Set([
  'p', 'div', 'section', 'article', 'aside', 'main', 'ul', 'ol', 'li', 'dl',
  'dt', 'dd', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'blockquote',
  'pre', 'figure', 'figcaption', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
]);

const NAMED_ENTITIES = {
  nbsp: ' ', amp: '&', lt: '<', gt: '>', quot: '"', apos: "'",
  auml: 'ä', ouml: 'ö', uuml: 'ü', szlig: 'ß',
  Auml: 'Ä', Ouml: 'Ö', Uuml: 'Ü',
  euro: '€', hellip: '…', mdash: '—', ndash: '–',
};

/**
 * Minimal HTML-to-text converter (no dependencies).
 *
 * The markup is walked by a scanner, not stripped by a chain of regexes. A
 * regex cannot tell an attribute's `>` from the end of a tag (`[^>]*` breaks
 * on `<a title=">">`) and matches `</script>` but not `</script >`, so both
 * `<script ...>` and friends could survive the filter. Here the tag end is
 * found with attribute quoting honoured, a dropped element takes its whole
 * subtree with it, and each character reference is decoded exactly once — a
 * second unescape would hand back the `<` of `&amp;lt;` that was meant to stay
 * text.
 */

/** Index of the `>` that ends the tag opened at `start`, or -1. Quoted
 *  attribute values are skipped so `title=">"` does not end the tag. */
function tagEnd(html, start) {
  let quote = '';
  for (let i = start; i < html.length; i += 1) {
    const ch = html[i];
    if (quote) {
      if (ch === quote) quote = '';
    } else if (ch === '"' || ch === "'") {
      quote = ch;
    } else if (ch === '>') {
      return i;
    }
  }
  return -1;
}

/** One pass over the references, so `&amp;lt;` stays `&lt;` and never `<`. */
function decodeEntities(text) {
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/g, (whole, body) => {
    if (body[0] === '#') {
      const hex = body[1] === 'x' || body[1] === 'X';
      const code = Number.parseInt(hex ? body.slice(2) : body.slice(1), hex ? 16 : 10);
      if (Number.isFinite(code) && code > 0 && code <= 0x10ffff) {
        return String.fromCodePoint(code);
      }
      return whole;
    }
    const named = NAMED_ENTITIES[body];
    return named === undefined ? whole : named;
  });
}

function htmlToText(html) {
  const out = [];
  let i = 0;
  let dropped = '';
  let depth = 0;
  while (i < html.length) {
    const lt = html.indexOf('<', i);
    if (lt === -1) {
      if (!dropped) out.push(html.slice(i));
      break;
    }
    if (lt > i && !dropped) out.push(html.slice(i, lt));
    if (html.startsWith('<!--', lt)) {
      const close = html.indexOf('-->', lt + 4);
      i = close === -1 ? html.length : close + 3;
      continue;
    }
    if (html.startsWith('<!', lt) || html.startsWith('<?', lt)) {
      const close = html.indexOf('>', lt);
      i = close === -1 ? html.length : close + 1;
      continue;
    }
    const end = tagEnd(html, lt + 1);
    if (end === -1) {
      if (!dropped) out.push(html.slice(lt));
      break;
    }
    const raw = html.slice(lt + 1, end);
    const closing = raw.startsWith('/');
    const named = /^\/?([a-zA-Z][a-zA-Z0-9-]*)/.exec(raw);
    const name = named ? named[1].toLowerCase() : '';

    if (!name) {
      // A `<` that opens no tag (HTML's invalid first character) is text.
      if (!dropped) out.push('<');
      i = lt + 1;
      continue;
    }

    const selfClosing = !closing && (raw.endsWith('/') || VOID_ELEMENTS.has(name));
    i = end + 1;

    if (dropped) {
      if (name !== dropped) continue;
      if (closing) {
        depth -= 1;
        if (depth <= 0) dropped = '';
      } else if (!selfClosing) {
        depth += 1;
      }
      continue;
    }
    if (closing || selfClosing) {
      if (name === 'br' || name === 'hr' || (BLOCK_ELEMENTS.has(name) && name !== 'li')) {
        out.push('\n');
      }
      continue;
    }
    if (DROPPED_ELEMENTS.has(name)) {
      dropped = name;
      depth = 1;
      continue;
    }
    const heading = /^h([1-6])$/.exec(name);
    if (heading) out.push(`\n${'#'.repeat(Number(heading[1]))} `);
    else if (name === 'li') out.push('\n- ');
    else if (BLOCK_ELEMENTS.has(name)) out.push('\n');
  }
  return decodeEntities(out.join(''))
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Download a source and convert to Markdown
 */
async function crawlSource(source) {
  console.log(`  ⬇ ${source.id}...`);
  
  try {
    const res = await fetch(source.url, {
      headers: {
        'User-Agent': 'Ephe-KnowledgeBot/2.0 (Offline-Krisen-KI; Gemeinwohl)',
        'Accept': 'text/html',
        'Accept-Language': 'de-DE,de;q=0.9',
      },
      signal: AbortSignal.timeout(15000),
    });
    
    if (!res.ok) {
      console.log(`  ✗ HTTP ${res.status}: ${source.url}`);
      return null;
    }
    
    const html = await res.text();
    
    // Extract main content (skip nav, footer, etc.)
    const mainMatch = html.match(/<main[^>]*>([\s\S]*?)<\/main>/i)
      || html.match(/<article[^>]*>([\s\S]*?)<\/article>/i)
      || html.match(/<div[^>]*class="[^"]*content[^"]*"[^>]*>([\s\S]*?)<\/div>/i);
    
    const content = mainMatch ? mainMatch[1] : html;
    const text = htmlToText(content);
    
    if (text.length < 100) {
      console.log(`  ✗ Zu wenig Text (${text.length} Zeichen): ${source.id}`);
      return null;
    }
    
    // Create markdown with metadata
    const md = [
      `# ${source.title}`,
      ``,
      `> **Quelle:** ${source.source}`,
      `> **URL:** ${source.url}`,
      `> **Lizenz:** Amtliches Werk (§ 5 UrhG) — frei verwendbar`,
      `> **Domäne:** ${source.domain}`,
      `> **Crawl-Datum:** ${new Date().toISOString().split('T')[0]}`,
      ``,
      `---`,
      ``,
      text,
    ].join('\n');
    
    console.log(`  ✓ ${source.id} (${text.length} Zeichen)`);
    return { ...source, content: md, charCount: text.length };
    
  } catch (err) {
    console.log(`  ✗ Fehler: ${source.id} — ${err.message}`);
    return null;
  }
}

/**
 * Main: crawl all sources and save
 */
async function main() {
  console.log('');
  console.log('◑ Ephe Knowledge-Base Crawler v2.0');
  console.log('  Offizielle deutsche Krisenratgeber (BBK, DRK, BfS)');
  console.log(`  ${SOURCES.length} Quellen konfiguriert`);
  console.log('');
  
  const results = [];
  
  // Crawl all sources (sequential to be polite to servers)
  for (const source of SOURCES) {
    const result = await crawlSource(source);
    if (result) {
      results.push(result);
    }
    // Be polite: 500ms pause between requests
    await new Promise(r => setTimeout(r, 500));
  }
  
  // Save results to knowledge base
  console.log('');
  console.log('📁 Speichere Ergebnisse...');
  
  for (const result of results) {
    const dir = join(KB_DIR, result.domain);
    mkdirSync(dir, { recursive: true });
    
    const filepath = join(dir, `${result.id}.md`);
    writeFileSync(filepath, result.content, 'utf-8');
    console.log(`  ✓ ${result.domain}/${result.id}.md`);
  }
  
  // Update index.json
  const indexPath = join(KB_DIR, 'index.json');
  const index = JSON.parse(readFileSync(indexPath, 'utf-8'));
  index.lastIndexed = new Date().toISOString();
  index.stats.totalFiles = results.length + (index.stats.totalFiles || 0);
  index.stats.crawledSources = results.length;
  index.stats.totalCharacters = results.reduce((s, r) => s + r.charCount, 0);
  writeFileSync(indexPath, JSON.stringify(index, null, 2), 'utf-8');
  
  // Summary
  console.log('');
  console.log('════════════════════════════════════════════════');
  console.log(' ◑ Ephe Knowledge Base — Ergebnis');
  console.log('════════════════════════════════════════════════');
  console.log(`  ✓ ${results.length}/${SOURCES.length} Quellen erfolgreich gecrawlt`);
  console.log(`  📊 ${(results.reduce((s, r) => s + r.charCount, 0) / 1000).toFixed(0)}k Zeichen Wissen`);
  
  const domains = {};
  for (const r of results) {
    domains[r.domain] = (domains[r.domain] || 0) + 1;
  }
  for (const [d, c] of Object.entries(domains)) {
    console.log(`  📁 ${d}: ${c} Dateien`);
  }
  console.log('════════════════════════════════════════════════');
  console.log('');
}

main().catch(err => {
  console.error('Fataler Fehler:', err);
  process.exit(1);
});
