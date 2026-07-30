/**
 * Страница правовых документов: политика, оферта, согласие.
 *
 * Сам компонент — только отрисовка. Тексты лежат в legalDocuments.ts и
 * перенесены из .docx владельца скриптом; менять их здесь нельзя.
 *
 * До 29.07.2026 здесь лежал рабочий каркас, написанный без юриста, с
 * пометкой «должен вычитать юрист». Каркас заменён на переданную редакцию,
 * поэтому предупреждения о незаполненных реквизитах больше нет — реквизиты
 * оператора теперь внутри самих документов.
 */
import { ChevronLeft, Home } from "lucide-react";
import type { LegalDoc } from "../router";
import { LEGAL_DOCUMENTS } from "./legalDocuments";

export const LEGAL_TITLES: Record<LegalDoc, string> = {
  privacy: LEGAL_DOCUMENTS.privacy.title,
  offer: LEGAL_DOCUMENTS.offer.title,
  consent: LEGAL_DOCUMENTS.consent.title,
};

export function LegalPage({
  doc,
  onHome,
  onBack,
  canGoBack,
}: {
  doc: LegalDoc;
  onHome: () => void;
  onBack: () => void;
  canGoBack: boolean;
}) {
  const document = LEGAL_DOCUMENTS[doc];

  return (
    <main className="ds-legal">
      <div className="ds-legal__inner">
        <nav className="ds-legal__nav">
          {canGoBack ? (
            <button className="text-action" onClick={onBack} type="button">
              <ChevronLeft size={15} /> Назад
            </button>
          ) : null}
          <button className="text-action" onClick={onHome} type="button">
            <Home size={15} /> На главную
          </button>
        </nav>

        <h1 className="ds-legal__title">{document.title}</h1>
        <p className="ds-legal__updated">Редакция от {document.updated}</p>

        <p className="ds-legal__intro">{document.intro}</p>

        {document.sections.map((section, index) => (
          <section className="ds-legal__section" key={section.heading || index}>
            {section.heading ? <h2>{section.heading}</h2> : null}
            {section.blocks.map((block, i) =>
              block.kind === "p" ? (
                <p key={i}>{block.text}</p>
              ) : (
                <ul className="ds-legal__list" key={i}>
                  {block.items.map((item, j) => (
                    <li key={j}>{item}</li>
                  ))}
                </ul>
              ),
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
