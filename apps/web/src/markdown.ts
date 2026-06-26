/**
 * Markdown rendering for ticket descriptions, acceptance criteria and comments.
 *
 * Uses the `marked` package to convert Markdown -> HTML.
 *
 * LaTeX handling: we PRESERVE LaTeX math spans (`$...$` and `$$...$$`) exactly
 * as written. Math segments are pulled out before Markdown parsing (replaced by
 * an alphanumeric placeholder token that Markdown will not transform), then
 * re-inserted as HTML-escaped raw text inside `<span class="latex-raw">`. This
 * guarantees the raw `$...$` source is never stripped or corrupted by Markdown's
 * emphasis/underscore rules.
 *
 * BACKLOG: render the preserved math with KaTeX (drop-in: replace the restore
 * callback below with katex.renderToString). Kept as raw text for the MVP to
 * avoid pulling in the KaTeX dependency + stylesheet.
 */
import { marked } from 'marked';

marked.setOptions({
  gfm: true,
  breaks: true,
});

function escapeHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Alphanumeric token: Markdown leaves it untouched (no underscores / specials),
// and it does not depend on surrounding whitespace surviving the parser.
const TOKEN_OPEN = 'zZmathZz';
const TOKEN_CLOSE = 'zZendZz';

export function renderMarkdown(source: string | null | undefined): string {
  if (!source) {
    return '';
  }

  const math: string[] = [];
  const stash = (raw: string): string => {
    const index = math.push(raw) - 1;
    return `${TOKEN_OPEN}${index}${TOKEN_CLOSE}`;
  };

  // Protect block math first ($$...$$), then inline math ($...$).
  let protectedSource = source.replace(/\$\$([\s\S]+?)\$\$/g, (full) =>
    stash(full),
  );
  // Inline math must start and end with a non-space char so prose like
  // "$5 and $10" is not mistaken for math.
  protectedSource = protectedSource.replace(
    /\$([^\s$][^$\n]*?[^\s$]|[^\s$])\$/g,
    (full) => stash(full),
  );

  // marked.parse returns a string synchronously when async mode is not enabled.
  let html = marked.parse(protectedSource) as string;

  html = html.replace(
    new RegExp(`${TOKEN_OPEN}(\\d+)${TOKEN_CLOSE}`, 'g'),
    (_match, idx: string) => {
      const raw = math[Number(idx)] ?? '';
      return `<span class="latex-raw">${escapeHtml(raw)}</span>`;
    },
  );

  return html;
}
