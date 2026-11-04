import "./styles/fonts";
import "./styles/tokens.css";
import "./styles/base.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import { createAppRouter } from "./router";

const container = document.getElementById("root");
if (!container) throw new Error("Falta el elemento #root en index.html");

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={createAppRouter()} />
  </StrictMode>,
);
