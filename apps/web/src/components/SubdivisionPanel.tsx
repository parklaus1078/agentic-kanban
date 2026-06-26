import { useEffect, useState } from 'react';
import { api, type SubdivisionProposal } from '../api';
import { errMsg } from '../util';

/** Recursive subdivision (§8): propose child tickets, then approve/reject. */
export function SubdivisionPanel({
  ticketId,
  parentTicketId,
  onError,
  onChanged,
}: {
  ticketId: number;
  parentTicketId: number | null;
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
}) {
  const [proposal, setProposal] = useState<SubdivisionProposal | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getSubdivision(ticketId)
      .then((p) => {
        if (!cancelled) setProposal(p);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [ticketId]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      onError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="subpanel">
      <h3>Subdivision</h3>
      {parentTicketId != null && (
        <p className="muted small">Child of ticket #{parentTicketId}.</p>
      )}
      <button
        className="btn btn-secondary"
        disabled={busy}
        onClick={() => void run(async () => setProposal(await api.subdivide(ticketId)))}
      >
        Propose subdivision
      </button>

      {proposal && (
        <div className="subdiv">
          <div className="muted small">
            proposal #{proposal.id} · {proposal.status}
          </div>
          <ul className="subdiv-list">
            {proposal.proposed_children_json.map((c, i) => (
              <li key={i}>{c.title}</li>
            ))}
          </ul>
          {proposal.status === 'proposed' && (
            <div className="row">
              <button
                className="btn btn-sm"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await api.approveSubdivision(proposal.id);
                    setProposal({ ...proposal, status: 'approved' });
                    await onChanged();
                  })
                }
              >
                Approve → create children
              </button>
              <button
                className="btn btn-sm btn-secondary"
                disabled={busy}
                onClick={() =>
                  void run(async () => setProposal(await api.rejectSubdivision(proposal.id)))
                }
              >
                Reject
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
