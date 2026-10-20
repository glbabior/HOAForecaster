import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { fromPercent, parseDecimal, toPercent } from "../decimal";

export function Problems({ title, items }: { title?: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="problems" role="alert">
      {title && <strong>{title}</strong>}
      <ul>
        {items.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </div>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  const problems =
    typeof error === "object" && error !== null && "problems" in error
      ? ((error as { problems: string[] }).problems ?? [])
      : [];
  return <Problems title={capitalise(message)} items={problems} />;
}

export const capitalise = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

// ---------------------------------------------------------------- entries that are not numbers

type Report = (field: string, invalid: boolean) => void;
const InvalidFields = createContext<Report | null>(null);

/** Collects the fields whose text is not yet a usable value, so a form can refuse to save
 * and say which ones – a field never quietly keeps its last good value. */
export function useInvalidFields(): {
  invalid: string[];
  Provider: (p: { children: ReactNode }) => ReactNode;
} {
  const [fields, setFields] = useState<Record<string, boolean>>({});
  const report = useCallback<Report>((field, invalid) => {
    setFields((current) => {
      if (Boolean(current[field]) === invalid) return current;
      const next = Object.fromEntries(Object.entries(current).filter(([f]) => f !== field));
      if (invalid) next[field] = true;
      return next;
    });
  }, []);
  const Provider = useMemo(
    () =>
      function InvalidFieldsProvider({ children }: { children: ReactNode }) {
        return <InvalidFields.Provider value={report}>{children}</InvalidFields.Provider>;
      },
    [report],
  );
  return { invalid: Object.keys(fields), Provider };
}

function useReportValidity(field: string, invalid: boolean): void {
  const report = useContext(InvalidFields);
  useEffect(() => {
    report?.(field, invalid);
  }, [report, field, invalid]);
  useEffect(() => () => report?.(field, false), [report, field]); // forget it when removed
}

// ---------------------------------------------------------------- fields

interface FieldProps {
  label: string;
  hint?: string;
  error?: string | null;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}

export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`field${error ? " field-error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children(id, describedBy)}
      {hint && (
        <small id={hintId} className="hint">
          {hint}
        </small>
      )}
      {error && (
        <small id={errorId} className="error">
          {error}
        </small>
      )}
    </div>
  );
}

const MAX_PLACES = 10; // more decimal places than any amount or rate needs

/** A decimal typed as text. `onChange` receives the exact decimal string; while the text is
 * not a number the field is marked and reported to the form, which will not save. `percent`
 * shows and takes percentages for stored fractions. `name` says which field it is in the
 * form's list of problems. */
export function DecimalInput({
  id,
  value,
  onChange,
  name,
  percent = false,
  describedBy,
  allowBlank = false,
  label,
}: {
  id?: string;
  value: string | null;
  onChange: (value: string | null) => void;
  name: string;
  percent?: boolean;
  describedBy?: string;
  allowBlank?: boolean;
  label?: string;
}) {
  const shown = value === null ? "" : percent ? toPercent(value) : value;
  const [text, setText] = useState(shown);
  const [invalid, setInvalid] = useState(false);
  const [seen, setSeen] = useState(value);
  useReportValidity(name, invalid);
  if (value !== seen) {
    // follow outside changes (restoring a draft, pasting into a table) but not our own typing
    setSeen(value);
    setText(shown);
    setInvalid(false);
  }
  return (
    <span className={percent ? "with-unit" : undefined}>
      <input
        id={id}
        aria-label={label}
        inputMode="decimal"
        value={text}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        onChange={(e) => {
          const next = e.target.value;
          setText(next);
          if (allowBlank && next.trim() === "") {
            setInvalid(false);
            setSeen(null);
            onChange(null);
            return;
          }
          const parsed = percent ? fromPercent(next) : parseDecimal(next);
          const tooFine = parsed !== null && (parsed.split(".")[1] ?? "").length > MAX_PLACES;
          setInvalid(parsed === null || tooFine);
          if (parsed !== null && !tooFine) {
            setSeen(parsed);
            onChange(parsed);
          }
        }}
      />
      {percent && <span aria-hidden="true">%</span>}
    </span>
  );
}

/** A whole number – a year, a count. Text that is not one is kept on screen, marked, and
 * reported to the form; it never becomes year 0 or 2030.5. */
export function YearInput({
  id,
  value,
  onChange,
  name,
  describedBy,
  label,
}: {
  id?: string;
  value: number;
  onChange: (value: number) => void;
  name: string;
  describedBy?: string;
  label?: string;
}) {
  const [text, setText] = useState(String(value));
  const [seen, setSeen] = useState(value);
  const invalid = !/^\d{1,4}$/.test(text.trim());
  useReportValidity(name, invalid);
  if (value !== seen) {
    setSeen(value);
    setText(String(value));
  }
  return (
    <input
      id={id}
      aria-label={label}
      inputMode="numeric"
      value={text}
      aria-invalid={invalid || undefined}
      aria-describedby={describedBy}
      onChange={(e) => {
        setText(e.target.value);
        if (/^\d{1,4}$/.test(e.target.value.trim())) {
          const n = Number(e.target.value.trim());
          setSeen(n);
          onChange(n);
        }
      }}
    />
  );
}

/** A modal question with a yes and a no. */
export function Confirm({
  open,
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal?.();
    if (!open && dialog.open) dialog.close?.();
  }, [open]);
  if (!open) return null;
  return (
    <dialog ref={ref} className="confirm" aria-labelledby="confirm-title" onCancel={onCancel} open>
      <h2 id="confirm-title">{title}</h2>
      <div>{children}</div>
      <div className="actions">
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="primary" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

/** "Fix the text in …" above a form's save buttons. */
export function InvalidNotice({ fields }: { fields: string[] }) {
  if (fields.length === 0) return null;
  return (
    <Problems
      title="These entries are not usable numbers or years – fix them before saving"
      items={fields}
    />
  );
}
