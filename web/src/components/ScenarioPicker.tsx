import { useEffect, useRef, useState } from "react";

/** A dropdown of scenarios with a checkbox each (spec 7.4) – default all. */
export function ScenarioPicker({
  names,
  selected,
  onChange,
}: {
  names: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const label =
    selected.length === names.length
      ? "All scenarios"
      : selected.length === 0
        ? "No scenarios"
        : `${selected.length} of ${names.length} scenarios`;

  function toggle(name: string) {
    // keep the project's order, whatever order the boxes are ticked in
    const next = selected.includes(name)
      ? selected.filter((n) => n !== name)
      : names.filter((n) => n === name || selected.includes(n));
    onChange(next);
  }

  return (
    <div className="picker" ref={ref}>
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
      >
        {label} ▾
      </button>
      {open && (
        <fieldset className="picker-menu" onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
          <legend className="visually-hidden">Scenarios to show</legend>
          <div className="picker-all">
            <button type="button" onClick={() => onChange(names)}>
              All
            </button>
            <button type="button" onClick={() => onChange([])}>
              None
            </button>
          </div>
          {names.map((name) => (
            <label key={name}>
              <input
                type="checkbox"
                checked={selected.includes(name)}
                onChange={() => toggle(name)}
              />{" "}
              {name}
            </label>
          ))}
        </fieldset>
      )}
    </div>
  );
}
