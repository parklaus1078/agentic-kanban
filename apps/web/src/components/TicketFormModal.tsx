import { useState, type FormEvent } from 'react';
import { api, type Persona, type Ticket } from '../api';
import { errMsg } from '../util';

interface Props {
  boardId: number;
  personas: Persona[];
  onError: (msg: string) => void;
  onClose: () => void;
  onCreated: (ticket: Ticket) => void | Promise<void>;
}

export function TicketFormModal({
  boardId,
  personas,
  onError,
  onClose,
  onCreated,
}: Props) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [acceptance, setAcceptance] = useState('');
  const [persona, setPersona] = useState('');
  const [priority, setPriority] = useState(3);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      onError('Title is required.');
      return;
    }
    setBusy(true);
    try {
      const ticket = await api.createTicket({
        board_id: boardId,
        title: title.trim(),
        description_md: description,
        acceptance_criteria_md: acceptance,
        assignee_persona: persona || null,
        priority,
      });
      await onCreated(ticket);
      onClose();
    } catch (e2) {
      onError(errMsg(e2));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>New Ticket</h2>
          <button className="btn btn-sm" onClick={onClose}>
            ✕
          </button>
        </div>
        <form className="ticket-form" onSubmit={submit}>
          <label className="block-label">
            Title
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
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
          <div className="modal-foot">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
            >
              Cancel
            </button>
            <button type="submit" className="btn" disabled={busy}>
              Create ticket
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
