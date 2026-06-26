import { api, type QueueItem, type QueueState } from '../api';
import { errMsg, fmtShort } from '../util';

interface Props {
  queue: QueueItem[];
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
  onSelectTicket: (ticketId: number) => void;
}

const STATE_LABEL: Record<QueueState, string> = {
  queued: 'queued',
  running: 'active',
  done: 'done',
  canceled: 'canceled',
};

export function QueuePanel({ queue, onError, onChanged, onSelectTicket }: Props) {
  const sorted = [...queue].sort((a, b) => a.order_index - b.order_index);

  async function reorder(from: number, to: number) {
    if (to < 0 || to >= sorted.length) {
      return;
    }
    const ids = sorted.map((q) => q.id);
    const moved = ids[from];
    ids.splice(from, 1);
    ids.splice(to, 0, moved);
    try {
      await api.reorderQueue({ ordered_ids: ids });
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    }
  }

  async function cancel(item: QueueItem) {
    try {
      await api.cancelQueueItem(item.id);
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    }
  }

  const counts = {
    active: sorted.filter((q) => q.state === 'running').length,
    queued: sorted.filter((q) => q.state === 'queued').length,
    done: sorted.filter((q) => q.state === 'done').length,
    canceled: sorted.filter((q) => q.state === 'canceled').length,
  };

  return (
    <section className="panel">
      <h2>
        Queue{' '}
        <span className="muted small">
          active {counts.active} · queued {counts.queued} · done {counts.done} ·
          canceled {counts.canceled}
        </span>
      </h2>
      <ul className="queue-list">
        {sorted.map((q, i) => (
          <li key={q.id} className={`queue-row state-${q.state}`}>
            <span className="queue-order">{q.order_index}</span>
            <span className={`badge badge-${q.state}`}>
              {STATE_LABEL[q.state]}
            </span>
            <button
              className="link"
              onClick={() => onSelectTicket(q.ticket_id)}
              title={q.ticket_title}
            >
              {q.ticket_number}
            </button>
            <span className="queue-title" title={q.ticket_title}>
              {q.ticket_title}
            </span>
            {q.cancel_requested && (
              <span className="tag tag-cancel">cancel req</span>
            )}
            {q.locked_by && (
              <span className="muted small">lock: {q.locked_by}</span>
            )}
            <span className="muted small">{fmtShort(q.queued_at)}</span>
            <span className="queue-actions">
              <button
                className="btn btn-sm"
                disabled={i === 0}
                onClick={() => void reorder(i, i - 1)}
                title="move up"
              >
                ↑
              </button>
              <button
                className="btn btn-sm"
                disabled={i === sorted.length - 1}
                onClick={() => void reorder(i, i + 1)}
                title="move down"
              >
                ↓
              </button>
              <button
                className="btn btn-danger btn-sm"
                disabled={q.state === 'canceled' || q.state === 'done'}
                onClick={() => void cancel(q)}
              >
                cancel
              </button>
            </span>
          </li>
        ))}
        {sorted.length === 0 && <li className="muted">Queue is empty.</li>}
      </ul>
    </section>
  );
}
