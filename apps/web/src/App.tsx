import { useCallback, useEffect, useState } from 'react';
import {
  API_BASE,
  api,
  type Board,
  type Persona,
  type Project,
  type QueueItem,
  type Skill,
  type Ticket,
} from './api';
import { errMsg } from './util';
import { ConsoleScreen } from './components/ConsoleScreen';
import { KanbanBoard } from './components/KanbanBoard';
import { ProjectsScreen } from './components/ProjectsScreen';
import { QueuePanel } from './components/QueuePanel';
import { StatusBlockManager } from './components/StatusBlockManager';
import { TicketFormModal } from './components/TicketFormModal';
import { TicketDrawer } from './components/TicketDrawer';

export default function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [showConsole, setShowConsole] = useState(false);
  const [boardId, setBoardId] = useState<number | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);

  const [selectedTicketId, setSelectedTicketId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleError = useCallback((msg: string) => setError(msg), []);

  const statusBlocks = board?.status_blocks ?? [];

  const loadCatalogs = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        api.listPersonas(),
        api.listSkills(),
      ]);
      setPersonas(p);
      setSkills(s);
    } catch (e) {
      handleError(errMsg(e));
    }
  }, [handleError]);

  const loadBoards = useCallback(
    async (preferId?: number) => {
      try {
        const list = await api.listBoards();
        setBoardId((current) => {
          if (preferId != null && list.some((b) => b.id === preferId)) {
            return preferId;
          }
          if (current != null && list.some((b) => b.id === current)) {
            return current;
          }
          return list.length > 0 ? list[0].id : null;
        });
      } catch (e) {
        handleError(errMsg(e));
      }
    },
    [handleError],
  );

  const refresh = useCallback(async () => {
    if (boardId == null) {
      setBoard(null);
      setTickets([]);
      setQueue([]);
      return;
    }
    try {
      const [b, t, q] = await Promise.all([
        api.getBoard(boardId),
        api.listTickets(boardId),
        api.getQueue(),
      ]);
      setBoard(b);
      setTickets(t);
      setQueue(q);
    } catch (e) {
      handleError(errMsg(e));
    }
  }, [boardId, handleError]);

  // Initial load.
  useEffect(() => {
    void loadCatalogs();
    void loadBoards();
  }, [loadCatalogs, loadBoards]);

  // Reload board-scoped data whenever the selected board changes.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function withBusy(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      handleError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  function doSeed() {
    void withBusy(async () => {
      const res = await api.seed();
      await loadCatalogs();
      await loadBoards(res.board.id);
    });
  }

  function doWorkerTick() {
    void withBusy(async () => {
      await api.workerTick();
      await refresh();
    });
  }

  function doWatcherTick() {
    void withBusy(async () => {
      await api.watcherTick();
      await refresh();
    });
  }

  function openProject(p: Project) {
    setProject(p);
    setBoardId(p.board_id ?? null);
    setSelectedTicketId(null);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          {project ? (
            <>
              <button className="brand-back" onClick={() => setProject(null)}>
                ← Projects
              </button>
              <span className="brand-proj" title={project.slug}>
                {project.title}
              </span>
            </>
          ) : (
            <>
              Agent System v2 <span className="muted">ops console</span>
            </>
          )}
        </div>
        <div className="topbar-actions">
          <button
            className="btn btn-secondary"
            onClick={() => setShowConsole((s) => !s)}
            title="Models, permissions, memory & skills"
          >
            {showConsole ? '← Board' : 'Console'}
          </button>
          <button className="btn btn-secondary" disabled={busy} onClick={doSeed}>
            Seed
          </button>
          <button
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Refresh
          </button>
          <button
            className="btn"
            disabled={busy || boardId == null}
            onClick={() => setShowCreate(true)}
          >
            + New Ticket
          </button>
          <span className="divider" />
          <button
            className="btn btn-secondary"
            disabled={busy}
            onClick={doWorkerTick}
            title="POST /admin/worker/tick"
          >
            Worker tick
          </button>
          <button
            className="btn btn-secondary"
            disabled={busy}
            onClick={doWatcherTick}
            title="POST /admin/watcher/tick"
          >
            Watcher tick
          </button>
          <span className="api-base muted small" title="VITE_API_BASE">
            {API_BASE}
          </span>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button className="btn btn-sm" onClick={() => setError(null)}>
            dismiss
          </button>
        </div>
      )}

      {showConsole ? (
        <ConsoleScreen onError={handleError} onNotice={handleError} />
      ) : project ? (
      <main className="layout">
        <section className="board-area">
          {board ? (
            <KanbanBoard
              tickets={tickets}
              blocks={statusBlocks}
              onError={handleError}
              onChanged={refresh}
              onSelectTicket={(id) => setSelectedTicketId(id)}
            />
          ) : (
            <div className="empty-state">
              <p>No board loaded.</p>
              <p className="muted">
                Click <strong>Seed</strong> to create the default board,
                personas and skills, or check that the API is running at{' '}
                <code>{API_BASE}</code>.
              </p>
              <button className="btn" disabled={busy} onClick={doSeed}>
                Seed default board
              </button>
            </div>
          )}
        </section>

        <aside className="sidebar">
          <QueuePanel
            queue={queue}
            onError={handleError}
            onChanged={refresh}
            onSelectTicket={(id) => setSelectedTicketId(id)}
          />
          {board && (
            <StatusBlockManager
              boardId={board.id}
              blocks={statusBlocks}
              onError={handleError}
              onChanged={refresh}
            />
          )}
        </aside>
      </main>
      ) : (
        <ProjectsScreen onOpen={openProject} onError={handleError} />
      )}

      {showCreate && boardId != null && (
        <TicketFormModal
          boardId={boardId}
          personas={personas}
          onError={handleError}
          onClose={() => setShowCreate(false)}
          onCreated={async (t) => {
            await refresh();
            setSelectedTicketId(t.id);
          }}
        />
      )}

      {selectedTicketId != null && (
        <TicketDrawer
          ticketId={selectedTicketId}
          personas={personas}
          skills={skills}
          statusBlocks={statusBlocks}
          onError={handleError}
          onClose={() => setSelectedTicketId(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
