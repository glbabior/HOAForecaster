import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { router } from "./App";
import "./styles.css";
import { applyTheme, savedTheme } from "./theme";

applyTheme(savedTheme(), false); // before React renders, so no screen draws in the wrong theme

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
