import { useState } from 'react';
import { api } from '../api';
import { errMsg } from '../util';

interface Props {
  ticketId: number;
  status: string;
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
}

export function ReviewPanel({ ticketId, status, onError, onChanged }: Props) {
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  const isReviewing = status === 'Reviewing';

  async function decide(satisfied: boolean) {
    if (!satisfied && !comment.trim()) {
      onError('A review comment is required when requesting a rerun.');
      return;
    }
    setBusy(true);
    try {
      await api.review(ticketId, {
        satisfied,
        actor: 'Kay',
        comment_md: satisfied ? undefined : comment,
      });
      setComment('');
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`subpanel review ${isReviewing ? '' : 'review-idle'}`}>
      <h3>Review</h3>
      {!isReviewing ? (
        <p className="muted">
          Review actions become available when the ticket is in{' '}
          <strong>Reviewing</strong>. Current status: <strong>{status}</strong>.
        </p>
      ) : (
        <>
          <button
            className="btn btn-success"
            disabled={busy}
            onClick={() => void decide(true)}
          >
            Satisfied / Complete
          </button>
          <textarea
            placeholder="Why is it not satisfied? (Markdown) — fed into the rerun prompt"
            value={comment}
            rows={3}
            onChange={(e) => setComment(e.target.value)}
          />
          <button
            className="btn btn-danger"
            disabled={busy}
            onClick={() => void decide(false)}
          >
            Not satisfied / Rerun
          </button>
        </>
      )}
    </section>
  );
}
