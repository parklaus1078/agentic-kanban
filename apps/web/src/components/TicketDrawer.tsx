import { useEffect, useState, type FormEvent } from 'react';
import {
  api,
  type Persona,
  type Skill,
  type StatusBlock,
  type TicketDetail,
} from '../api';
import { errMsg, fmtDate } from '../util';
import { Markdown } from './Markdown';
import { Comments } from './Comments';
import { NavigatorPanel } from './NavigatorPanel';
import { RunMonitor } from './RunMonitor';
import { ReviewPanel } from './ReviewPanel';
import { SubdivisionPanel } from './SubdivisionPanel';

interface Props {
  ticketId: number;
  personas: Persona[];
  skills: Skill[];
  statusBlocks: StatusBlock[];
  onError: (msg: string) => void;
  onClose: () => void;
  /** Refresh board-level data (tickets + queue) after a mutation. */
  onChanged: () => void | Promise<void>;
}

export function TicketDrawer({
  ticketId,
  personas,
  skills,
  statusBlocks,
  onError,
  onClose,
  onChanged,
}: Props) {
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);

  // Edit form (initialised only when switching tickets, never clobbered on reload).
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [acceptance, setAcceptance] = useState('');
  const [persona, setPersona] = useState('');
  const [priority, setPriority] = useState(3);
  const [saving, setSaving] = useState(false);

  const statusNames = [...statusBlocks]
    .sort((a, b) => a.order_index - b.order_index)
    .map((b) => b.name);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    api
      .getTicket(ticketId)
      .then((d) => {
        if (cancelled) {
          return;
        }
        setDetail(d);
        setTitle(d.title);
        setDescription(d.description_md);
        setAcceptance(d.acceptance_criteria_md);
        setPersona(d.assignee_persona ?? '');
        setPriority(d.priority);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          onError(errMsg(e));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [ticketId, onError]);

  async function reloadDetail() {
    try {
      const d = await api.getTicket(ticketId);
      setDetail(d);
    } catch (e) {
      onError(errMsg(e));
    }
  }

  /** Subpanels call this: refresh both this drawer and the board. */
  async function refreshAll() {
    await reloadDetail();
    await onChanged();
  }

  async function saveEdits(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.updateTicket(ticketId, {
        title: title.trim(),
        description_md: description,
        acceptance_criteria_md: acceptance,
        assignee_persona: persona || null,
        priority,
      });
      await refreshAll();
    } catch (e2) {
      onError(errMsg(e2));
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(toStatus: string) {
    if (!detail || toStatus === detail.status) {
      return;
    }
    try {
      await api.transition(ticketId, { to_status: toStatus, actor: 'Kay' });
      await refreshAll();
    } catch (e) {
      onError(errMsg(e));
    }
  }

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div>
            <span className="ticket-number">
              {detail?.ticket_number ?? `#${ticketId}`}
            </span>{' '}
            <span className="badge badge-status">{detail?.status ?? '…'}</span>
          </div>
          <button className="btn btn-sm" onClick={onClose}>
            ✕ close
          </button>
        </div>

        {loading && <p className="muted">Loading ticket…</p>}

        {detail && (
          <div className="drawer-body">
            {/* Status transition */}
            <section className="subpanel">
              <h3>Status</h3>
              <div className="row">
                <select
                  value={statusNames.includes(detail.status) ? detail.status : ''}
                  onChange={(e) => void changeStatus(e.target.value)}
                >
                  {!statusNames.includes(detail.status) && (
                    <option value="">{detail.status}</option>
                  )}
                  {statusNames.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <span className="muted small">
                  created {fmtDate(detail.created_at)}
                </span>
              </div>
            </section>

            {/* Edit form */}
            <form className="subpanel ticket-form" onSubmit={saveEdits}>
              <h3>Edit</h3>
              <label className="block-label">
                Title
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label className="block-label">
                Description (Markdown)
                <textarea
                  rows={5}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
              <label className="block-label">
                Acceptance criteria (Markdown)
                <textarea
                  rows={4}
                  value={acceptance}
                  onChange={(e) => setAcceptance(e.target.value)}
                />
              </label>
              <div className="row">
                <label className="block-label">
                  Assignee persona
                  <select
                    value={persona}
                    onChange={(e) => setPersona(e.target.value)}
                  >
                    <option value="">(unassigned)</option>
                    {personas.map((p) => (
                      <option key={p.id} value={p.persona_name}>
                        {p.persona_name} ({p.default_agent})
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block-label">
                  Priority
                  <select
                    value={priority}
                    onChange={(e) => setPriority(Number(e.target.value))}
                  >
                    {[1, 2, 3, 4, 5].map((p) => (
                      <option key={p} value={p}>
                        P{p}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button className="btn" type="submit" disabled={saving}>
                Save changes
              </button>
            </form>

            {/* Rendered previews */}
            <section className="subpanel">
              <h3>Description</h3>
              <Markdown source={detail.description_md} />
              <h3>Acceptance criteria</h3>
              <Markdown source={detail.acceptance_criteria_md} />
            </section>

            <NavigatorPanel
              ticketId={ticketId}
              decision={detail.navigator_decision}
              personas={personas}
              skills={skills}
              onError={onError}
              onChanged={refreshAll}
            />

            <SubdivisionPanel
              ticketId={ticketId}
              parentTicketId={detail.parent_ticket_id ?? null}
              onError={onError}
              onChanged={refreshAll}
            />

            <RunMonitor
              ticketId={ticketId}
              runs={detail.runs}
              onError={onError}
              onChanged={refreshAll}
            />

            <ReviewPanel
              ticketId={ticketId}
              status={detail.status}
              onError={onError}
              onChanged={refreshAll}
            />

            <Comments
              ticketId={ticketId}
              comments={detail.comments}
              onError={onError}
              onChanged={refreshAll}
            />

            {/* Status history */}
            <section className="subpanel">
              <h3>Status history ({detail.status_events.length})</h3>
              <ul className="event-list">
                {[...detail.status_events]
                  .sort(
                    (a, b) =>
                      new Date(a.created_at).getTime() -
                      new Date(b.created_at).getTime(),
                  )
                  .map((ev) => (
                    <li key={ev.id}>
                      <span className="small">
                        {ev.from_status ?? '∅'} → <strong>{ev.to_status}</strong>
                      </span>
                      <span className="muted small"> by {ev.actor}</span>
                      <span className="muted small"> · {fmtDate(ev.created_at)}</span>
                      {ev.wiki_raw_path && (
                        <div className="mono small wiki-path">
                          {ev.wiki_raw_path}
                        </div>
                      )}
                    </li>
                  ))}
                {detail.status_events.length === 0 && (
                  <li className="muted">No status events.</li>
                )}
              </ul>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}
