import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
// Самохостинг шрифтов дизайн-системы (Inter + JetBrains Mono) — регистрируют
// семейства «Inter» / «JetBrains Mono» из design/tokens.css. Без внешних CDN:
// быстрее и надёжнее для RU-аудитории, дружелюбно к CSP.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/inter/800.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
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
