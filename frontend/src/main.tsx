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
// Слой кабинета (.cab-*) идёт последним и ничего не перебивает: пересечений
// с остальными файлами у него нет. app-shell.css пока остаётся — вопреки плану
// миграции, в нём лежат не только стили оболочки, но и модалки, карточка адреса
// в каталоге, «Чаты», «Услуги адресов» и редактор адреса собственника. Его
// разбор — последний шаг, после того как разметка переедет на .cab-*.
import "./design/cabinet.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
