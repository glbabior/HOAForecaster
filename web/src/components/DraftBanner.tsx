import { date } from "../format";
import type { Draft } from "../types";

/** Offer unsaved edits found from an earlier session – restored after a crash (spec 8.2). */
export function DraftBanner({
  draft,
  revision,
  onRestore,
  onDiscard,
}: {
  draft: Draft;
  revision: number;
  onRestore: () => void;
  onDiscard: () => void;
}) {
  const stale = draft.base_revision !== revision;
  return (
    <div className="draft-banner" role="status">
      <p>
        Unsaved edits from {date(draft.saved)} were found.
        {stale &&
          " The project has been saved since they were made – restoring them replaces those later changes on this screen."}
      </p>
      <button type="button" className="primary" onClick={onRestore}>
        Restore them
      </button>
      <button type="button" onClick={onDiscard}>
        Discard them
      </button>
    </div>
  );
}

/** "Unsaved edits are kept as a draft" next to the save buttons. */
export function DraftStatus({ status }: { status: "idle" | "saved" | "failed" }) {
  const text = {
    idle: "",
    saved: "Unsaved edits are kept as a draft",
    failed: "The draft could not be kept",
  }[status];
  return (
    <span className="hint" role="status">
      {text}
    </span>
  );
}
