import { useState, type FormEvent } from 'react';
import { api, type AuthorType, type Comment } from '../api';
import { errMsg, fmtDate } from '../util';
import { Markdown } from './Markdown';

interface Props {
  ticketId: number;
  comments: Comment[];
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
}

const AUTHOR_TYPES: AuthorType[] = ['kay', 'human', 'hermes', 'agent'];

export function Comments({ ticketId, comments, onError, onChanged }: Props) {
  const [authorType, setAuthorType] = useState<AuthorType>('kay');
  const [authorName, setAuthorName] = useState('Kay');
  const [body, setBody] = useState('');
  const [digestible, setDigestible] = useState(true);
  const [busy, setBusy] = useState(false);

  const sorted = [...comments].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!body.trim()) {
      return;
    }
    setBusy(true);
    try {
      await api.createComment(ticketId, {
        author_type: authorType,
        author_name: authorName.trim() || authorType,
        body_md: body,
        is_digestible: digestible,
      });
      setBody('');
      await onChanged();
    } catch (e2) {
      onError(errMsg(e2));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="subpanel">
      <h3>Comments ({sorted.length})</h3>
      <ul className="comment-list">
        {sorted.map((c) => (
          <li key={c.id} className="comment">
            <div className="comment-meta">
              <strong>{c.author_name}</strong>
              <span className={`badge badge-author badge-${c.author_type}`}>
                {c.author_type}
              </span>
              <span className="muted small">{fmtDate(c.created_at)}</span>
              {!c.is_digestible && (
                <span className="tag" title="not digestible">
                  no-digest
                </span>
              )}
            </div>
            <Markdown source={c.body_md} />
            {c.body_latex_raw && (
              <pre className="latex-block" title="body_latex_raw">
                {c.body_latex_raw}
              </pre>
            )}
          </li>
        ))}
        {sorted.length === 0 && <li className="muted">No comments yet.</li>}
      </ul>

      <form className="comment-add" onSubmit={add}>
        <div className="row">
          <select
            value={authorType}
            onChange={(e) => setAuthorType(e.target.value as AuthorType)}
          >
            {AUTHOR_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="author name"
            value={authorName}
            onChange={(e) => setAuthorName(e.target.value)}
          />
          <label className="digest-toggle">
            <input
              type="checkbox"
              checked={digestible}
              onChange={(e) => setDigestible(e.target.checked)}
            />
            digestible
          </label>
        </div>
        <textarea
          placeholder="Comment (Markdown, $LaTeX$ preserved)"
          value={body}
          rows={3}
          onChange={(e) => setBody(e.target.value)}
        />
        <button className="btn" type="submit" disabled={busy}>
          Add comment
        </button>
      </form>
    </section>
  );
}
