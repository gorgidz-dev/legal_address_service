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

const STEPS: Step[] = [
  {
    icon: MapPin,
    title: "Подбираешь адрес",
    text: "Фильтруешь каталог по региону, ИФНС и цене. В карточке — фото помещения, состав услуг, отзывы и рейтинг собственника.",
  },
  {
    icon: Send,
    title: "Оставляешь заявку",
    text: "Указываешь компанию и срок аренды. Собственник видит заявку в своём кабинете и подтверждает готовность выдать документы.",
  },
  {
    icon: ReceiptText,
    title: "Оплачиваешь",
    text: "После подтверждения приходит счёт: СБП или безналичный платёж для юрлица. Статус оплаты виден в личном кабинете.",
  },
  {
    icon: FileCheck2,
    title: "Получаешь комплект",
    text: "Гарантийное письмо, выписка ЕГРН, договор аренды и фото помещения — в кабинете, в DOCX и PDF. С ними идёшь в ФНС.",
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
      </div>
    </section>
  );
}
