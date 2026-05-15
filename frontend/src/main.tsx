import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./design/legacy-tokens.css";
import "./styles.css";
import "./design/tokens.css";
import "./design/components.css";
import "./design/catalog.css";
import "./design/app-shell.css";
import "./design/sections.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
