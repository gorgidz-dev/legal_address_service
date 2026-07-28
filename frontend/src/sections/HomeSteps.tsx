/**
 * Блок «Как это работает» — цель ссылки #how в верхнем меню.
 *
 * Раньше пункт меню вёл в никуда: элемента с id="how" в проекте не было,
 * клик просто дописывал мусорный хеш в адрес.
 *
 * Шаги описывают реальный маршрут заявки в сервисе: подбор в каталоге →
 * заявка и проверка собственником → счёт и оплата → выдача комплекта.
 */
import { FileCheck2, MapPin, ReceiptText, Send } from "lucide-react";

type Step = {
  icon: typeof MapPin;
  title: string;
  text: string;
};

/**
 * Расшифровка комплекта: документ → зачем он нужен.
 *
 * Стоит отдельной полосой под шагами, а не внутри четвёртого шага: карточки
 * шагов лежат в grid и тянутся по самой высокой, поэтому список внутри одной
 * из них оставлял в трёх соседних по 156 px пустоты.
 */
const DOCS: { name: string; purpose: string }[] = [
  { name: "Гарантийное письмо", purpose: "подтверждает согласие собственника" },
  { name: "Выписка ЕГРН", purpose: "подтверждает право собственности" },
  { name: "Договор аренды", purpose: "основание для регистрации по адресу" },
];

const STEPS: Step[] = [
  {
    icon: MapPin,
    title: "Выберите адрес",
    text: "Отфильтруйте каталог по региону, ИФНС и цене. В карточке — фото помещения, состав услуг, отзывы и рейтинг собственника.",
  },
  {
    icon: Send,
    title: "Отправьте заявку",
    text: "Укажите компанию и срок аренды. Собственник получит уведомление и подтвердит готовность выдать документы — статус заявки виден в личном кабинете.",
  },
  {
    icon: ReceiptText,
    title: "Оплатите счёт",
    text: "После подтверждения приходит счёт: СБП или безналичный платёж для юрлица. Статус оплаты отображается в личном кабинете.",
  },
  {
    icon: FileCheck2,
    title: "Получите документы",
    // Про доставку на email в макете было сказано, но её нет: почта в сервисе
    // отправляет только подтверждение адреса, сообщения чата и отзывы —
    // комплект нигде не прикладывается к письму. Пишем то, что есть.
    text: "Комплект появляется в личном кабинете после подтверждения оплаты — в DOCX и PDF. С ним вы подаёте документы в ФНС.",
  },
];

export function HomeSteps() {
  return (
    <section className="ds-steps" id="how" aria-label="Как это работает">
      <div className="ds-steps__inner">
        <div className="ds-steps__intro">
          <span className="ds-steps__eyebrow">Как это работает</span>
          <h2 className="ds-steps__title">Четыре шага до юридического адреса</h2>
          <p className="ds-steps__sub">
            Весь путь проходит внутри сервиса: переписка с собственником, оплата и
            выдача документов — без выездов и бумажной пересылки.
          </p>
        </div>

        <ol className="ds-steps__list">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            return (
              <li className="ds-steps__item" key={step.title}>
                <span className="ds-steps__num" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="ds-steps__icon" aria-hidden="true">
                  <Icon size={20} strokeWidth={1.8} />
                </span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </li>
            );
          })}
        </ol>

        <div className="ds-steps__docs">
          <span className="ds-steps__docs-label">Что в комплекте</span>
          <ul className="ds-steps__docs-list">
            {DOCS.map((doc) => (
              <li key={doc.name}>
                <b>{doc.name}</b> — {doc.purpose}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
