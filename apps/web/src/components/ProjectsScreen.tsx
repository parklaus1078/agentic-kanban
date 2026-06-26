import { useEffect, useState, type FormEvent } from 'react';
import { api, type BoardTemplate, type Project } from '../api';
import { errMsg } from '../util';

/**
 * Workspace landing: pick or create a project. Each project owns one Kanban
 * board; opening a project hands its board to the rest of the console.
 */
export function ProjectsScreen({
  onOpen,
  onError,
}: {
  onOpen: (project: Project) => void;
  onError: (msg: string) => void;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [templates, setTemplates] = useState<BoardTemplate[]>([]);
  const [title, setTitle] = useState('');
  const [templateId, setTemplateId] = useState<number | ''>('');
  const [showArchived, setShowArchived] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [p, t] = await Promise.all([
        api.listProjects(),
        api.listBoardTemplates(),
      ]);
      setProjects(p);
      setTemplates(t);
      setTemplateId((cur) => (cur === '' && t.length ? t[0].id : cur));
    } catch (e) {
      onError(errMsg(e));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    try {
      const proj = await api.createProject({
        title: title.trim(),
        board_template_id: templateId === '' ? null : Number(templateId),
      });
      setTitle('');
      onOpen(proj);
    } catch (err) {
      onError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  async function archive(id: number) {
    setBusy(true);
    try {
      await api.archiveProject(id);
      await load();
    } catch (err) {
      onError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  const visible = projects.filter((p) => showArchived || p.status === 'active');

  return (
    <div className="proj-screen">
      <section className="proj-intro">
        <p className="proj-eyebrow">Workspace</p>
        <h1 className="proj-headline">Projects</h1>
        <p className="proj-sub">
          Each project runs its own Kanban board. Drag a ticket into{' '}
          <span className="mono">In&nbsp;Progress</span> and an agent picks it up.
        </p>
      </section>

      <form className="proj-new" onSubmit={create}>
        <input
          className="proj-new-name"
          placeholder="Name a new project…"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          aria-label="New project name"
        />
        <select
          value={templateId}
          onChange={(e) =>
            setTemplateId(e.target.value === '' ? '' : Number(e.target.value))
          }
          aria-label="Board template"
        >
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <button className="btn" disabled={busy || !title.trim()}>
          Create project
        </button>
      </form>

      <div className="proj-grid">
        {visible.map((p) => (
          <article
            key={p.id}
            className={`proj-card${p.status === 'archived' ? ' is-archived' : ''}`}
          >
            <button className="proj-card-open" onClick={() => onOpen(p)}>
              <span className="proj-card-slug mono">{p.slug}</span>
              <span className="proj-card-title">{p.title}</span>
              {p.description && (
                <span className="proj-card-desc">{p.description}</span>
              )}
              <span className="proj-card-enter">Open board →</span>
            </button>
            {p.status === 'active' && (
              <button
                className="proj-card-archive"
                onClick={() => archive(p.id)}
                disabled={busy}
              >
                Archive
              </button>
            )}
          </article>
        ))}
        {visible.length === 0 && (
          <p className="proj-empty muted">
            No projects yet — name one above to spin up its board.
          </p>
        )}
      </div>

      {projects.some((p) => p.status === 'archived') && (
        <label className="proj-archived-toggle">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Show archived
        </label>
      )}
    </div>
  );
}
