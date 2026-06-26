import { useState } from 'react';
import { api, type StatusBlock, type Ticket } from '../api';
import { errMsg } from '../util';

interface Props {
  tickets: Ticket[];
  blocks: StatusBlock[];
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
  onSelectTicket: (ticketId: number) => void;
}

export function KanbanBoard({
  tickets,
  blocks,
  onError,
  onChanged,
  onSelectTicket,
}: Props) {
  const [dragId, setDragId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const columns = [...blocks].sort((a, b) => a.order_index - b.order_index);
  const statusNames = columns.map((b) => b.name);

  // Tickets whose status no longer matches any block (e.g. deleted block).
  const orphanTickets = tickets.filter((t) => !statusNames.includes(t.status));

  async function moveTicket(ticket: Ticket, toStatus: string) {
    if (toStatus === ticket.status) {
      return;
    }
    try {
      await api.transition(ticket.id, { to_status: toStatus, actor: 'Kay' });
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    }
  }

  function onDrop(toStatus: string) {
    const id = dragId;
    setDragId(null);
    setDropTarget(null);
    if (id == null) {
      return;
    }
    const ticket = tickets.find((t) => t.id === id);
    if (ticket) {
      void moveTicket(ticket, toStatus);
    }
  }

  function renderCard(t: Ticket) {
    return (
      <div
        key={t.id}
        className="card"
        draggable
        onDragStart={() => setDragId(t.id)}
        onDragEnd={() => {
          setDragId(null);
          setDropTarget(null);
        }}
        onClick={() => onSelectTicket(t.id)}
      >
        <div className="card-head">
          <span className="ticket-number">{t.ticket_number}</span>
          <span className="prio" title="priority">
            P{t.priority}
          </span>
        </div>
        <div className="card-title">{t.title}</div>
        <div className="card-foot">
          <span className="persona">
            {t.assignee_persona ?? 'unassigned'}
          </span>
        </div>
        <select
          className="card-status"
          value={statusNames.includes(t.status) ? t.status : ''}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => void moveTicket(t, e.target.value)}
        >
          {!statusNames.includes(t.status) && (
            <option value="">{t.status}</option>
          )}
          {statusNames.map((s) => (
            <option key={s} value={s}>
              → {s}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className="board">
      {columns.map((col) => {
        const colTickets = tickets.filter((t) => t.status === col.name);
        return (
          <div
            key={col.id}
            className={`column ${dropTarget === col.name ? 'drop-target' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              if (dropTarget !== col.name) {
                setDropTarget(col.name);
              }
            }}
            onDragLeave={() => {
              if (dropTarget === col.name) {
                setDropTarget(null);
              }
            }}
            onDrop={() => onDrop(col.name)}
          >
            <div className="column-head" style={{ borderTopColor: col.color }}>
              <span className="column-name">{col.name}</span>
              <span className="column-count">{colTickets.length}</span>
              {col.is_agent_digestible && (
                <span className="tag tag-digest" title="is_agent_digestible">
                  digest
                </span>
              )}
            </div>
            <div className="column-body">
              {colTickets.map(renderCard)}
              {colTickets.length === 0 && (
                <div className="muted small empty-col">drop here</div>
              )}
            </div>
          </div>
        );
      })}

      {orphanTickets.length > 0 && (
        <div className="column column-orphan">
          <div className="column-head">
            <span className="column-name">Unmapped status</span>
            <span className="column-count">{orphanTickets.length}</span>
          </div>
          <div className="column-body">{orphanTickets.map(renderCard)}</div>
        </div>
      )}
    </div>
  );
}
