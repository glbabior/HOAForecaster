/** Light or dark screens – light unless dark was chosen in this browser. The choice is a
 * convenience kept in the browser, never in a project, and a browser that keeps nothing
 * simply opens light. Once there are users, this is the one place to make it a per-user
 * setting. */
export type Theme = "light" | "dark";

const KEY = "hoa-theme";

export function savedTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** Show the screens in `theme`, and remember it for the next visit when the browser lets us. */
export function applyTheme(theme: Theme, remember = true): void {
  document.documentElement.dataset.theme = theme;
  if (!remember) return;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // storage refused (a private window) – this visit still changes
  }
}
