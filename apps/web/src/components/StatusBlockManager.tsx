import { useState, type FormEvent } from 'react';
import { api, type StatusBlock } from '../api';
import { errMsg } from '../util';

interface Props {
  boardId: number;
  blocks: StatusBlock[];
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
}

export function StatusBlockManager({
  boardId,
  blocks,
  onError,
  onChanged,
}: Props) {
  const [name, setName] = useState('');
  const [color, setColor] = useState('#cbd5e1');
  const [digestible, setDigestible] = useState(false);
  const [busy, setBusy] = useState(false);

  const sorted = [...blocks].sort((a, b) => a.order_index - b.order_index);

  async function addBlock(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      return;
    }
    setBusy(true);
    try {
      await api.createStatusBlock(boardId, {
        name: name.trim(),
        color,
        is_agent_digestible: digestible,
        order_index: sorted.length,
      });
      setName('');
      setDigestible(false);
      await onChanged();
    } catch (e2) {
      onError(errMsg(e2));
    } finally {
      setBusy(false);
    }
  }

  async function toggleDigest(block: StatusBlock) {
    try {
      await api.updateStatusBlock(block.id, {
        is_agent_digestible: !block.is_agent_digestible,
      });
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    }
  }

  async function remove(block: StatusBlock) {
    if (!confirm(`Delete status block "${block.name}"?`)) {
      return;
    }
    try {
      await api.deleteStatusBlock(block.id);
      await onChanged();
    } catch (e) {
      onError(errMsg(e));
    }
  }

  return (
    <section className="panel">
      <h2>Status Blocks</h2>
      <ul className="block-list">
        {sorted.map((b) => (
          <li key={b.id} className="block-row">
            <span
              className="swatch"
              style={{ background: b.color }}
              title={b.color}
            />
            <span className="block-name">{b.name}</span>
            <span className="muted">#{b.order_index}</span>
            {b.is_terminal && <span className="tag tag-terminal">terminal</span>}
            <label className="digest-toggle" title="is_agent_digestible">
              <input
                type="checkbox"
                checked={b.is_agent_digestible}
                onChange={() => void toggleDigest(b)}
              />
              digest
            </label>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => void remove(b)}
            >
              delete
            </button>
          </li>
        ))}
        {sorted.length === 0 && <li className="muted">No status blocks.</li>}
      </ul>

      <form className="block-add" onSubmit={addBlock}>
        <input
          type="text"
          placeholder="New status name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          type="color"
          value={color}
          onChange={(e) => setColor(e.target.value)}
          title="color"
        />
        <label className="digest-toggle">
          <input
            type="checkbox"
            checked={digestible}
            onChange={(e) => setDigestible(e.target.checked)}
          />
          digest
        </label>
        <button className="btn" type="submit" disabled={busy}>
          Add block
        </button>
      </form>
    </section>
  );
}
