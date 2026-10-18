// Finds a meeting's printed row on a PDF page from pdf.js text content, so the source panel can
// highlight it. Pure: it takes the page's text items and returns a box in PDF user space (y up).

/** The parts of a pdf.js `TextItem` this needs: transform[4] is x, transform[5] the baseline. */
export interface PdfTextItem {
  str: string;
  transform: number[];
  width: number;
  height: number;
}

/** A rectangle in PDF user space; `bottom` < `top` because PDF y grows upwards. */
export interface RowBox {
  left: number;
  bottom: number;
  right: number;
  top: number;
}

// Glyphs reach about this far below and above the baseline, as a share of the font size.
const DESCENT = 0.25;
const ASCENT = 0.85;

const x = (it: PdfTextItem) => it.transform[4];
const baseline = (it: PdfTextItem) => it.transform[5];
const size = (it: PdfTextItem) => it.height || Math.hypot(it.transform[2], it.transform[3]) || 10;
/** Items whose baselines differ by less than this sit on the same printed line. */
const tolerance = (it: PdfTextItem) => Math.max(2, size(it) * 0.4);

/** "Pixelmint Studios (PXMS)" -> "pixelmint studios pxms": case, accents and punctuation don't count. */
function normalize(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

interface Line {
  items: PdfTextItem[];
  /** The line's items' normalized text joined by single spaces. */
  text: string;
  /** Where each item's text starts in `text`. */
  starts: number[];
}

/** The page's text as printed lines, top to bottom, each left to right. */
function linesOf(items: PdfTextItem[]): Line[] {
  const sorted = items
    .filter((it) => it.str.trim())
    .sort((a, b) => baseline(b) - baseline(a) || x(a) - x(b));
  const groups: PdfTextItem[][] = [];
  for (const it of sorted) {
    const last = groups[groups.length - 1];
    if (last && Math.abs(baseline(last[0]) - baseline(it)) <= tolerance(last[0])) last.push(it);
    else groups.push([it]);
  }
  return groups.map((group) => {
    const row = [...group].sort((a, b) => x(a) - x(b));
    const starts: number[] = [];
    let text = "";
    for (const it of row) {
      const part = normalize(it.str);
      if (!part) {
        starts.push(text.length);
        continue;
      }
      if (text) text += " ";
      starts.push(text.length);
      text += part;
    }
    return { items: row, text, starts };
  });
}

/** The item whose text holds character `at` of the line. */
function itemAt(line: Line, at: number): PdfTextItem {
  let index = 0;
  line.starts.forEach((start, i) => {
    if (start <= at) index = i;
  });
  return line.items[index];
}

/** A whole-word match of `needle` in the line, or -1. */
function wordIndex(text: string, needle: string): number {
  const at = ` ${text} `.indexOf(` ${needle} `);
  return at < 0 ? -1 : at;
}

/** The first item that prints the company, or else the ticker as a word of its own. */
function matchedItem(lines: Line[], company: string, ticker: string | null): PdfTextItem | null {
  const name = normalize(company);
  if (name) {
    for (const line of lines) {
      const at = wordIndex(line.text, name);
      if (at >= 0) return itemAt(line, at);
    }
    // Some PDFs split words across text items ("Pixel" "mint"); compare without spaces for longer names.
    const compact = name.replace(/ /g, "");
    if (compact.length >= 6) {
      for (const line of lines) {
        const flat = line.text.replace(/ /g, "");
        const at = flat.indexOf(compact);
        if (at < 0) continue;
        let seen = 0;
        for (let i = 0; i < line.text.length; i++) {
          if (line.text[i] === " ") continue;
          if (seen === at) return itemAt(line, i);
          seen += 1;
        }
      }
    }
  }
  const symbol = ticker?.trim().toUpperCase();
  if (symbol) {
    for (const line of lines) {
      for (const it of line.items) {
        if (it.str.split(/[^\p{L}\p{N}.]+/u).some((word) => word.replace(/\.$/, "") === symbol)) return it;
      }
    }
  }
  return null;
}

/**
 * The box around the printed row for a meeting: the first line that prints the company (or, failing
 * that, the ticker), widened to every text item on the matched item's baseline. Null when the page
 * prints neither.
 */
export function findRowBox(items: PdfTextItem[], company: string, ticker: string | null): RowBox | null {
  const hit = matchedItem(linesOf(items), company, ticker);
  if (!hit) return null;
  const row = items.filter((it) => it.str.trim() && Math.abs(baseline(it) - baseline(hit)) <= tolerance(hit));
  return {
    left: Math.min(...row.map(x)),
    right: Math.max(...row.map((it) => x(it) + it.width)),
    bottom: Math.min(...row.map((it) => baseline(it) - size(it) * DESCENT)),
    top: Math.max(...row.map((it) => baseline(it) + size(it) * ASCENT)),
  };
}

/**
 * The font size (PDF points) most of the page's text is set in: the median over its text items, so a
 * large title or a footnote doesn't move it. 10pt for a page without text. The viewer zooms to make
 * this readable on screen.
 */
export function bodyTextSize(items: PdfTextItem[]): number {
  const sizes = items
    .filter((it) => it.str.trim())
    .map(size)
    .sort((a, b) => a - b);
  return sizes.length ? sizes[Math.floor((sizes.length - 1) / 2)] : 10;
}
