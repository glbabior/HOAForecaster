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
  type RefObject,
} from "react";

import { fromPercent, grouped, parseDecimal, toPercent } from "../decimal";

/** A download arrow for a toolbar action – decoration, so the action's words name it. */
export function DownloadIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M8 2v8m-3.5-3.5L8 10l3.5-3.5M2.5 13.5h11"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

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
  if (problems.length === 0)
    // an error with no list of problems is still shown – Problems alone would show nothing
    return (
      <div className="problems" role="alert">
        <strong>{capitalise(message)}</strong>
      </div>
    );
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
 * not a number the field is marked and reported to the form, which will not save. Text is
 * left as typed while typing and shown tidied on leaving the field – amounts with thousands
 * separators. `percent` shows and takes percentages for stored fractions. `name` says which
 * field it is in the form's list of problems. */
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
  const shown = value === null ? "" : percent ? toPercent(value) : grouped(value);
  const [text, setText] = useState(shown);
  const [invalid, setInvalid] = useState(false);
  const [seen, setSeen] = useState(value);
  useReportValidity(name, invalid);
  if (value !== seen) {
    // follow outside changes (pasting into a table, a copy) but not our own typing
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
        onBlur={() => !invalid && setText(shown)}
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

/** A year that may be left blank (null) – an expense's first or last year. Text that is
 * neither blank nor a year is kept on screen, marked, and reported to the form. */
export function OptionalYearInput({
  value,
  onChange,
  name,
  label,
  placeholder,
}: {
  value: number | null;
  onChange: (value: number | null) => void;
  name: string;
  label: string;
  placeholder?: string;
}) {
  const [text, setText] = useState(value === null ? "" : String(value));
  const [seen, setSeen] = useState(value);
  const trimmed = text.trim();
  const invalid = trimmed !== "" && !/^\d{1,4}$/.test(trimmed);
  useReportValidity(name, invalid);
  if (value !== seen) {
    setSeen(value);
    setText(value === null ? "" : String(value));
  }
  return (
    <input
      aria-label={label}
      inputMode="numeric"
      placeholder={placeholder}
      value={text}
      aria-invalid={invalid || undefined}
      onChange={(e) => {
        const next = e.target.value.trim();
        setText(e.target.value);
        if (next === "" || /^\d{1,4}$/.test(next)) {
          const n = next === "" ? null : Number(next);
          setSeen(n);
          onChange(n);
        }
      }}
    />
  );
}

/** Open a dialog as a modal while it is on the page – in the browser's top layer, centred
 * above everything, keeping the keyboard inside it and Escape for its cancel – and on closing
 * put the focus back where it was before the dialog rendered. Without showModal (the test
 * browser) it simply opens. showModal focuses the dialog's first control, so a dialog wanting
 * the focus elsewhere must move it after opening. */
export function useModal(ref: RefObject<HTMLDialogElement | null>): void {
  // taken while rendering – before anything in the dialog (an autoFocus box) has the focus
  const [before] = useState(() => document.activeElement);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    return () => {
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      if (before instanceof HTMLElement && before.isConnected) before.focus();
    };
  }, [ref, before]);
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
  if (!open) return null;
  return (
    <ConfirmDialog
      title={title}
      confirmLabel={confirmLabel}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      {children}
    </ConfirmDialog>
  );
}

function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useModal(ref);
  return (
    <dialog
      ref={ref}
      className="confirm"
      aria-labelledby="confirm-title"
      onCancel={(e) => {
        e.preventDefault(); // Escape – closed by the page's own state, like Cancel
        onCancel();
      }}
    >
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
