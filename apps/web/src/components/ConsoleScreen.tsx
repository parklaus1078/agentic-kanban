import { useEffect, useState, type FormEvent } from 'react';
import {
  api,
  type GeneratedSkill,
  type MemoryHit,
  type ModelsForBrain,
  type PermissionPreset,
  type PermissionProfile,
} from '../api';
import { errMsg } from '../util';

/**
 * Operator console: the model registry (§12), per-agent permission scope (§11),
 * RAG memory search (§7), and self-evolution skill proposals (§8) in one place.
 */
export function ConsoleScreen({
  onError,
  onNotice,
}: {
  onError: (msg: string) => void;
  onNotice: (msg: string) => void;
}) {
  const [models, setModels] = useState<Record<string, ModelsForBrain>>({});
  const [presets, setPresets] = useState<PermissionPreset[]>([]);
  const [perms, setPerms] = useState<Record<string, PermissionProfile>>({});
  const [skills, setSkills] = useState<GeneratedSkill[]>([]);
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<MemoryHit[]>([]);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [cm, xm, pp, cp, xp, gs] = await Promise.all([
        api.listModels('claude'),
        api.listModels('codex'),
        api.listPermissionPresets(),
        api.getAgentPermissions('claude'),
        api.getAgentPermissions('codex'),
        api.listGeneratedSkills(),
      ]);
      setModels({ claude: cm, codex: xm });
      setPresets(pp.presets);
      setPerms({ claude: cp, codex: xp });
      setSkills(gs);
    } catch (e) {
      onError(errMsg(e));
    }
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function setPreset(brain: string, preset: string) {
    setBusy(true);
    try {
      const p = await api.setAgentPermissions(brain, { preset });
      setPerms((cur) => ({ ...cur, [brain]: p }));
    } catch (e) {
      onError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    try {
      setHits(await api.memorySearch(q.trim()));
    } catch (err) {
      onError(errMsg(err));
    }
  }

  async function reindex() {
    setBusy(true);
    try {
      const r = await api.reindexMemory();
      onNotice(`Indexed ${r.indexed_chunks} wiki chunks.`);
    } catch (e) {
      onError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  async function skillAction(id: number, act: 'accept' | 'reject') {
    try {
      if (act === 'accept') await api.acceptGeneratedSkill(id);
      else await api.rejectGeneratedSkill(id);
      setSkills(await api.listGeneratedSkills());
    } catch (e) {
      onError(errMsg(e));
    }
  }

  return (
    <div className="console-screen">
      <section className="console-block">
        <p className="proj-eyebrow">Agents</p>
        <h2 className="console-h">Models &amp; permissions</h2>
        <div className="console-grid">
          {(['claude', 'codex'] as const).map((brain) => (
            <div key={brain} className="console-card">
              <div className="console-card-head">
                <span className="mono">{brain}</span>
                <span className="muted small">default {models[brain]?.default}</span>
              </div>
              <div className="model-chips">
                {models[brain]?.models.map((m) => (
                  <span
                    key={m.id}
                    className={`chip${m.default ? ' chip-on' : ''}`}
                    title={m.id}
                  >
                    {m.display}
                    {m.latest && <span className="chip-tag">latest</span>}
                  </span>
                ))}
              </div>
              <label className="console-label">Permission preset</label>
              <div className="preset-row">
                {presets.map((p) => (
                  <button
                    key={p.key}
                    className={`preset-btn${perms[brain]?.preset === p.key ? ' on' : ''}`}
                    disabled={busy}
                    title={p.label}
                    onClick={() => void setPreset(brain, p.key)}
                  >
                    {p.key}
                  </button>
                ))}
              </div>
              {perms[brain] && (
                <code className="flags mono">{perms[brain].flags.join(' ')}</code>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="console-block">
        <p className="proj-eyebrow">Long-term memory</p>
        <h2 className="console-h">RAG over the LLM Wiki</h2>
        <form className="proj-new" onSubmit={search}>
          <input
            className="proj-new-name"
            placeholder="Search prior knowledge…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button className="btn">Search</button>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void reindex()}>
            Reindex wiki
          </button>
        </form>
        <ul className="hit-list">
          {hits.map((h, i) => (
            <li key={i} className="hit">
              <div className="hit-head">
                <span className="mono small">{h.wiki_path.split('/').slice(-2).join('/')}</span>
                <span className="hit-score">{h.score.toFixed(2)}</span>
                {h.outcome && <span className="chip-tag">{h.outcome}</span>}
              </div>
              <div className="hit-chunk">{h.chunk.slice(0, 240)}</div>
            </li>
          ))}
          {hits.length === 0 && <li className="muted small">No results yet.</li>}
        </ul>
      </section>

      <section className="console-block">
        <p className="proj-eyebrow">Self-evolution</p>
        <h2 className="console-h">Generated skills</h2>
        <ul className="skill-list">
          {skills.map((s) => (
            <li key={s.id} className="skill-row">
              <div className="skill-main">
                <span className="mono">{s.slug}</span>
                <span className={`chip-tag kind-${s.kind}`}>
                  {s.kind === 'install_existing' ? `install ${s.suggested_ref}` : 'new skill'}
                </span>
                <span className={`badge badge-${s.status}`}>{s.status}</span>
              </div>
              {s.status === 'proposed' && (
                <div className="skill-actions">
                  <button className="btn btn-sm" onClick={() => void skillAction(s.id, 'accept')}>
                    Accept
                  </button>
                  <button className="btn btn-sm btn-secondary" onClick={() => void skillAction(s.id, 'reject')}>
                    Reject
                  </button>
                </div>
              )}
            </li>
          ))}
          {skills.length === 0 && (
            <li className="muted small">
              No skill proposals yet — they appear as the system learns from reviews.
            </li>
          )}
        </ul>
      </section>
    </div>
  );
}
