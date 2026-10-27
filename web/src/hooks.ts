import { useCallback, useEffect, useRef, useState } from "react";
import { useBlocker } from "react-router-dom";

/** A value that settles `delay` ms after its last change. */
export function useDebounced<T>(value: T, delay: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

/** Ask before leaving a screen with unsaved changes – in the app or by closing the tab.
 * `allowNextNavigation` lets the app's own move after a save or delete through. */
export function useUnsavedGuard(dirty: boolean, sameForm?: (pathname: string) => boolean) {
  const allowed = useRef(false);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (allowed.current) return false;
    // a move between screens of the same form keeps the edits on screen – nothing is left
    if (sameForm?.(currentLocation.pathname) && sameForm(nextLocation.pathname)) return false;
    return dirty && currentLocation.pathname !== nextLocation.pathname;
  });
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = ""; // older browsers need this as well
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const allowNextNavigation = useCallback(() => {
    allowed.current = true;
  }, []);
  return { blocker, allowNextNavigation };
}

export type SaveStatus =
  | { state: "saved" }
  | { state: "saving" }
  | { state: "waiting" } // an entry is not yet usable – saved once it is
  | { state: "failed"; error: unknown };

export interface Autosave {
  status: SaveStatus;
  /** the value differs from the one last saved */
  dirty: boolean;
  /** save now, without waiting for typing to stop – true once everything is saved */
  flushNow: () => Promise<boolean>;
}

/** Save `value` by itself, `delay` ms after it stops changing (spec 7.2) – never while `ready`
 * is false, one save at a time, and the latest value after a save in flight. Anything still
 * unsaved is sent when the screen closes, and closing the tab first asks. `initial` is the
 * value as last saved. */
export function useAutosave<T>(
  value: T,
  initial: T,
  ready: boolean,
  save: (value: T) => Promise<void>,
  delay = 600,
): Autosave {
  const [status, setStatus] = useState<SaveStatus>({ state: "saved" });
  const [savedText, setSavedText] = useState(() => JSON.stringify(initial));
  const saved = useRef(savedText);
  const running = useRef<Promise<boolean> | null>(null);
  const latest = useRef({ value, ready, save });
  useEffect(() => {
    latest.current = { value, ready, save }; // before the effects below read it
  });
  const text = JSON.stringify(value);
  const dirty = text !== savedText;
  // a value becoming usable waits for typing to stop too – "Plan" on the way to "Plan B"
  const settled = useDebounced(`${ready}:${text}`, delay);

  const flush = useCallback((): Promise<boolean> => {
    // the save in flight picks up the latest value when it ends
    if (running.current) return running.current;
    const loop = async () => {
      for (;;) {
        const { value: next, ready: ok, save: send } = latest.current;
        const nextText = JSON.stringify(next);
        if (nextText === saved.current) {
          setStatus({ state: "saved" });
          return true;
        }
        if (!ok) {
          setStatus({ state: "waiting" });
          return false;
        }
        setStatus({ state: "saving" });
        try {
          await send(next);
        } catch (e) {
          setStatus({ state: "failed", error: e });
          return false;
        }
        saved.current = nextText;
        setSavedText(nextText);
      }
    };
    running.current = loop().finally(() => {
      running.current = null;
    });
    return running.current;
  }, []);

  const flushNow = useCallback(async () => {
    await running.current;
    return flush();
  }, [flush]);

  useEffect(() => {
    void flush();
  }, [settled, flush]);

  // closing the tab before the last edit is saved asks first
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = ""; // older browsers need this as well
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // whatever is still unsaved goes when the screen closes – a save in flight takes it itself
  useEffect(
    () => () => {
      const { value: next, ready: ok, save: send } = latest.current;
      if (ok && !running.current && JSON.stringify(next) !== saved.current)
        void send(next).catch(() => undefined);
    },
    [],
  );
  return { status, dirty, flushNow };
}
