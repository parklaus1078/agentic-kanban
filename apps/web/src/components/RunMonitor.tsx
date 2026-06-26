import { useState } from 'react';
import {
  api,
  type AgentRun,
  type AgentRunDetail,
  type AgentRunStatus,
} from '../api';
import { errMsg, fmtDate } from '../util';

interface Props {
  ticketId: number;
  runs: AgentRun[];
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
}

const RUN_STATE_CLASS: Record<AgentRunStatus, string> = {
  queued: 'badge-queued',
  running: 'badge-running',
  success: 'badge-success',
  failed: 'badge-failed',
  canceled: 'badge-canceled',
};

export function RunMonitor({ ticketId, runs, onError, onChanged }: Props) {
  const [openRunId, setOpenRunId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AgentRunDetail | null>(null);
  const [busy, setBusy] = useState(false);

  const sorted = [...runs].sort((a, b) => b.run_number - a.run_number);

  async function loadDetail(runId: number) {
    if (openRunId === runId) {
      setOpenRunId(null);
      setDetail(null);
      return;
    }
    setOpenRunId(runId);
    setDetail(null);
    try {
      const d = await api.getRun(runId);
      setDetail(d);
    } catch (e) {
      onError(errMsg(e));
    }
  }

  async function createRun() {
    setBusy(true);
    try {
      await api.createRun(ticketId, { use_navigator: true });
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  async function cancelRun(run: AgentRun) {
    try {
      await api.cancelRun(run.id);
      if (openRunId === run.id) {
        setDetail(await api.getRun(run.id));
      }
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    }
  }

  async function tick(kind: 'worker' | 'watcher') {
    setBusy(true);
    try {
      if (kind === 'worker') {
        await api.workerTick();
      } else {
        await api.watcherTick();
      }
      if (openRunId != null) {
        setDetail(await api.getRun(openRunId));
      }
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="subpanel">
      <h3>Agent Runs ({sorted.length})</h3>
      <div className="row">
        <button className="btn" disabled={busy} onClick={() => void createRun()}>
          Create Agent Run
        </button>
        <button
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => void tick('worker')}
          title="POST /admin/worker/tick"
        >
          Worker tick
        </button>
        <button
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => void tick('watcher')}
          title="POST /admin/watcher/tick"
        >
          Watcher tick
        </button>
      </div>

      <ul className="run-list">
        {sorted.map((r) => (
          <li key={r.id} className="run-row">
            <button className="run-summary" onClick={() => void loadDetail(r.id)}>
              <span className="run-num">#{r.run_number}</span>
              <span className={`badge ${RUN_STATE_CLASS[r.status]}`}>
                {r.status}
              </span>
              <span className="muted small">
                {r.agent} / {r.model}
              </span>
              <span className="muted small">{r.persona}</span>
              <span className="caret">{openRunId === r.id ? '▾' : '▸'}</span>
            </button>
            {(r.status === 'queued' || r.status === 'running') && (
              <button
                className="btn btn-danger btn-sm"
                onClick={() => void cancelRun(r)}
              >
                cancel
              </button>
            )}

            {openRunId === r.id && (
              <div className="run-detail">
                {!detail && <p className="muted">Loading…</p>}
                {detail && detail.id === r.id && (
                  <>
                    <div className="kv">
                      <span className="k">output_path</span>
                      <span className="v mono">{detail.output_path ?? '—'}</span>
                    </div>
                    <div className="kv">
                      <span className="k">process_id</span>
                      <span className="v mono">{detail.process_id ?? '—'}</span>
                    </div>
                    <div className="kv">
                      <span className="k">started</span>
                      <span className="v">{fmtDate(detail.started_at)}</span>
                    </div>
                    <div className="kv">
                      <span className="k">finished</span>
                      <span className="v">{fmtDate(detail.finished_at)}</span>
                    </div>
                    {detail.error && (
                      <div className="kv">
                        <span className="k">error</span>
                        <span className="v error-text">{detail.error}</span>
                      </div>
                    )}
                    {detail.skills.length > 0 && (
                      <div className="kv">
                        <span className="k">skills</span>
                        <span className="v">
                          {detail.skills.map((s) => (
                            <span key={s} className="tag tag-skill">
                              {s}
                            </span>
                          ))}
                        </span>
                      </div>
                    )}

                    <h4>Artifacts ({detail.artifacts.length})</h4>
                    {detail.artifacts.length === 0 && (
                      <p className="muted small">No artifacts.</p>
                    )}
                    <ul className="artifact-list">
                      {detail.artifacts.map((a) => (
                        <li key={a.id}>
                          <div className="mono small">{a.path}</div>
                          <div className="muted small">
                            {a.author_name} · {a.mime_type}
                          </div>
                          <div className="small">{a.summary}</div>
                        </li>
                      ))}
                    </ul>

                    <h4>Watcher Events ({detail.watcher_events.length})</h4>
                    {detail.watcher_events.length === 0 && (
                      <p className="muted small">No watcher events.</p>
                    )}
                    <ul className="event-list">
                      {detail.watcher_events.map((ev) => (
                        <li key={ev.id}>
                          <span className="badge badge-event">
                            {ev.event_type}
                          </span>
                          <span className="muted small">
                            {fmtDate(ev.observed_at)}
                          </span>
                          <pre className="payload">
                            {JSON.stringify(ev.payload, null, 2)}
                          </pre>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}
          </li>
        ))}
        {sorted.length === 0 && <li className="muted">No runs yet.</li>}
      </ul>
    </section>
  );
}
