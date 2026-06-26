import { renderMarkdown } from '../markdown';

interface MarkdownProps {
  source: string | null | undefined;
  className?: string;
}

/**
 * Renders Markdown (with raw LaTeX preserved) into sanitised-enough HTML for an
 * internal operations console. Output comes from `marked`; this is an internal
 * MVP tool, not a public surface.
 */
export function Markdown({ source, className }: MarkdownProps) {
  const html = renderMarkdown(source);
  if (!html) {
    return <div className={`md md-empty ${className ?? ''}`}>—</div>;
  }
  return (
    <div
      className={`md ${className ?? ''}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
