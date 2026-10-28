import { useRef, useState } from "react";

import type { Scenario } from "../types";
import { useModal } from "./ui";

/** Choose the scenarios to copy something into (spec 7.2) – a box for each, and one for all.
 * Adopted plans are listed but cannot be chosen; they are read-only. */
export function CopyDialog({
  what,
  others,
  onCopy,
  onClose,
}: {
  /** what is being copied, as a phrase – "the starting reserve balance" */
  what: string;
  /** every other scenario of the project */
  others: Scenario[];
  onCopy: (names: string[]) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const open = others.filter((s) => !s.adoption);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const all = open.length > 0 && open.every((s) => chosen.has(s.name));
  useModal(ref);

  function toggle(name: string) {
    const next = new Set(chosen);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setChosen(next);
  }

  return (
    <dialog
      ref={ref}
      className="confirm"
      aria-labelledby="copy-title"
      onCancel={(e) => {
        e.preventDefault(); // Escape – closed by the page's own state, like Cancel
        onClose();
      }}
    >
      <h2 id="copy-title">Copy {what} to…</h2>
      {others.length === 0 ? (
        <p>This is the project's only scenario.</p>
      ) : (
        <fieldset className="plain copy-choices">
          <legend className="visually-hidden">Scenarios to copy into</legend>
          <label className="check all">
            <input
              type="checkbox"
              checked={all}
              disabled={open.length === 0}
              onChange={() => setChosen(all ? new Set() : new Set(open.map((s) => s.name)))}
            />{" "}
            All scenarios
          </label>
          {others.map((s) => (
            <label key={s.name} className="check">
              <input
                type="checkbox"
                checked={chosen.has(s.name)}
                disabled={Boolean(s.adoption)}
                onChange={() => toggle(s.name)}
              />{" "}
              {s.name}
              {s.adoption && <span className="hint"> – an adopted plan, read-only</span>}
            </label>
          ))}
        </fieldset>
      )}
      <p className="hint">It replaces what the chosen scenarios have now.</p>
      <div className="actions">
        <button type="button" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="primary"
          disabled={chosen.size === 0}
          onClick={() => onCopy(open.filter((s) => chosen.has(s.name)).map((s) => s.name))}
        >
          Copy
        </button>
      </div>
    </dialog>
  );
}
