import { useCallback, useEffect, useRef, useState } from "react";
import { useBlocker } from "react-router-dom";

import { api } from "./api";
import type { Draft } from "./types";

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

export type DraftStatusValue = "idle" | "saved" | "failed";

/** Autosave one screen's unsaved edits as a draft on the server (spec 8.2), two seconds after
 * typing stops. When the edits go back to the saved state, the draft is dropped. */
export function useDraftAutosave(
  projectId: string,
  screen: string,
  revision: number,
  edits: Draft["edits"] | null,
): DraftStatusValue {
  const [status, setStatus] = useState<DraftStatusValue>("idle");
  const settled = useDebounced(edits, 2000);
  const kept = useRef(false);
  useEffect(() => {
    let cancelled = false;
    if (settled === null) {
      if (kept.current) {
        kept.current = false;
        api.discardDraft(projectId, screen).then(
          () => !cancelled && setStatus("idle"),
          () => undefined,
        );
      }
      return;
    }
    api.saveDraft(projectId, screen, settled, revision).then(
      () => {
        kept.current = true;
        if (!cancelled) setStatus("saved");
      },
      () => !cancelled && setStatus("failed"),
    );
    return () => {
      cancelled = true;
    };
  }, [projectId, screen, revision, settled]);
  return status;
}
