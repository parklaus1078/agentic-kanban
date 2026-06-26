import { useState } from 'react';
import {
  api,
  type AgentName,
  type NavigatorDecision,
  type NavigatorOverride,
  type Persona,
  type Skill,
} from '../api';
import { errMsg } from '../util';

interface Props {
  ticketId: number;
  decision: NavigatorDecision | null;
  personas: Persona[];
  skills: Skill[];
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
}

export function NavigatorPanel({
  ticketId,
  decision,
  personas,
  skills,
  onError,
  onChanged,
}: Props) {
  const [showOverride, setShowOverride] = useState(false);
  const [persona, setPersona] = useState('');
  const [agent, setAgent] = useState<'' | AgentName>('');
  const [model, setModel] = useState('');
  const [overrideSkills, setOverrideSkills] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function recommend(override?: NavigatorOverride) {
    setBusy(true);
    try {
      await api.recommend(ticketId, override ? { override } : {});
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  function runOverride() {
    const o: NavigatorOverride = {};
    if (persona) o.persona = persona;
    if (agent) o.agent = agent;
    if (model.trim()) o.model = model.trim();
    if (overrideSkills.length > 0) o.skills = overrideSkills;
    void recommend(Object.keys(o).length > 0 ? o : undefined);
  }

  function toggleSkill(name: string) {
    setOverrideSkills((prev) =>
      prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name],
    );
  }

  return (
    <section className="subpanel">
      <h3>Navigator</h3>
      <div className="row">
        <button
          className="btn"
          disabled={busy}
          onClick={() => void recommend()}
        >
          Recommend
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => setShowOverride((v) => !v)}
        >
          {showOverride ? 'Hide override' : 'Override…'}
        </button>
      </div>

      {decision ? (
        <div className="nav-decision">
          <div className="kv">
            <span className="k">persona</span>
            <span className="v">{decision.persona}</span>
          </div>
          <div className="kv">
            <span className="k">agent</span>
            <span className="v">{decision.agent}</span>
          </div>
          <div className="kv">
            <span className="k">model</span>
            <span className="v">{decision.model}</span>
          </div>
          <div className="kv">
            <span className="k">confidence</span>
            <span className="v">{(decision.confidence * 100).toFixed(0)}%</span>
          </div>
          <div className="kv">
            <span className="k">skills</span>
            <span className="v">
              {decision.skills.length > 0
                ? decision.skills.map((s) => (
                    <span key={s} className="tag tag-skill">
                      {s}
                    </span>
                  ))
                : '—'}
            </span>
          </div>
          <div className="kv">
            <span className="k">reason</span>
            <span className="v">{decision.reason}</span>
          </div>
          <div className="kv">
            <span className="k">alternatives</span>
            <span className="v">
              {decision.alternatives.length > 0 ? (
                <ul className="alt-list">
                  {decision.alternatives.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              ) : (
                '—'
              )}
            </span>
          </div>
          {decision.manual_override && (
            <span className="tag tag-override">manual override</span>
          )}
        </div>
      ) : (
        <p className="muted">
          No navigator decision yet. Click “Recommend”.
        </p>
      )}

      {showOverride && (
        <div className="override-box">
          <div className="row">
            <label>
              persona
              <select
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
              >
                <option value="">(navigator picks)</option>
                {personas.map((p) => (
                  <option key={p.id} value={p.persona_name}>
                    {p.persona_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              agent
              <select
                value={agent}
                onChange={(e) => setAgent(e.target.value as '' | AgentName)}
              >
                <option value="">(default)</option>
                <option value="codex">codex</option>
                <option value="claude">claude</option>
              </select>
            </label>
          </div>
          <label className="block-label">
            model
            <input
              type="text"
              placeholder="e.g. Claude CLI Sonnet 4.6"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </label>
          <div className="skills-pick">
            <span className="muted small">skills override</span>
            <div className="skills-grid">
              {skills.map((s) => (
                <label key={s.id} className="skill-check">
                  <input
                    type="checkbox"
                    checked={overrideSkills.includes(s.name)}
                    onChange={() => toggleSkill(s.name)}
                  />
                  {s.name}
                </label>
              ))}
              {skills.length === 0 && (
                <span className="muted small">no skills loaded</span>
              )}
            </div>
          </div>
          <button className="btn" disabled={busy} onClick={runOverride}>
            Re-run with override
          </button>
        </div>
      )}
    </section>
  );
}
