/**
 * Блок «Для собственников помещений».
 *
 * Цель: дать понять владельцу нежилых помещений, что он может монетизировать
 * объект через каталог. Заявка уходит в admin-очередь
 * (provider-connection-requests), уже работает.
 */
import {
  ArrowRight,
  BadgeCheck,
  Banknote,
  CalendarCheck2,
  Headphones,
  Megaphone,
  ShieldCheck,
} from "lucide-react";

export function HomeForOwners({ onCTAClick }: { onCTAClick: () => void }) {
  return (
    <section className="ds-owners" id="owners" aria-label="Для собственников">
      <div className="ds-owners__inner">
        <div className="ds-owners__intro">
          <span className="ds-owners__eyebrow">Для собственников</span>
          <h2 className="ds-owners__title">
            Сдай свой адрес <br />в каталог
          </h2>
          <p className="ds-owners__sub">
            Заявки приходят от клиентов, которые уже знают зачем им твой адрес.
            Никаких холодных звонков, мы фильтруем и страхуем риски — ты только
            принимаешь заявку и выдаёшь документы.
          </p>
          <button
            type="button"
            className="ds-btn ds-btn--primary ds-btn--lg"
            onClick={onCTAClick}
          >
            Отправить заявку
            <ArrowRight size={14} />
          </button>
        </div>

        <ul className="ds-owners__perks">
          <li className="ds-owners__perk">
            <span className="ds-owners__perk-icon">
              <BadgeCheck size={20} strokeWidth={1.8} />
            </span>
            <div>
              <h3>Прозрачная комиссия</h3>
              <p>
                Фиксированный процент с каждой сделки. Никаких скрытых платежей за
                публикацию или продвижение.
              </p>
            </div>
          </li>
          <li className="ds-owners__perk">
            <span className="ds-owners__perk-icon">
              <CalendarCheck2 size={20} strokeWidth={1.8} />
            </span>
            <div>
              <h3>Гибкий график</h3>
              <p>
                Принимаешь только удобные заявки. Можно поставить адрес на паузу —
                за день до отпуска или ремонта.
              </p>
            </div>
          </li>
          <li className="ds-owners__perk">
            <span className="ds-owners__perk-icon">
              <ShieldCheck size={20} strokeWidth={1.8} />
            </span>
            <div>
              <h3>Юр-сопровождение</h3>
              <p>
                Помогаем с шаблонами договоров, гарантийных писем и порядком
                приёма-передачи. Спорные ситуации с ФНС закрываем мы.
              </p>
            </div>
          </li>
          <li className="ds-owners__perk">
            <span className="ds-owners__perk-icon">
              <Megaphone size={20} strokeWidth={1.8} />
            </span>
            <div>
              <h3>Поток клиентов</h3>
              <p>
                Каталог индексируется в поиске. Часть клиентов приходит из
                реферальной сети бухгалтерских сервисов.
              </p>
            </div>
          </li>
          <li className="ds-owners__perk">
            <span className="ds-owners__perk-icon">
              <Banknote size={20} strokeWidth={1.8} />
            </span>
            <div>
              <h3>Безопасные расчёты</h3>
              <p>
                Деньги клиента поступают на счёт после подтверждения получения
                документов — без зависших платежей и долгих ожиданий.
              </p>
            </div>
          </li>
          <li className="ds-owners__perk">
            <span className="ds-owners__perk-icon">
              <Headphones size={20} strokeWidth={1.8} />
            </span>
            <div>
              <h3>Поддержка 24/7</h3>
              <p>
                Менеджер на связи в чате, помогает с документами и спорными
                вопросами — отвечаем в течение часа в рабочее время.
              </p>
            </div>
          </li>
        </ul>
      </div>
    </section>
  );
}
