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
  CalendarCheck2,
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
            Сдайте свой адрес <br />в каталог
          </h2>
          <p className="ds-owners__sub">
            Только целевые заявки: клиент уже выбрал ваш адрес и готов арендовать.
            Фильтрацию, проверку и юридическое сопровождение берём на себя — вы
            подтверждаете бронь и передаёте документы.
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
              {/*
                Размер комиссии («от 10%») и срок выплаты («в течение 24 часов»)
                из замечаний здесь не пишем: ни расчёта комиссии, ни выплат в
                сервисе пока нет — оплата и расчёты идут вручную. Обещанный срок
                выплаты стал бы основанием для претензии в первый же месяц.
              */}
              <p>
                Фиксированный процент с каждой сделки — комиссия удерживается
                только при успешной сделке, а не за публикацию или продвижение.
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
                Принимайте только те заявки, которые подходят вам по срокам и
                условиям. Адрес можно поставить на паузу — за день до отпуска
                или ремонта.
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
                приёма-передачи. Спорные ситуации с ФНС помогаем урегулировать:
                консультация и подготовка документов.
              </p>
            </div>
          </li>
          <li className="ds-owners__perk">
            <span className="ds-owners__perk-icon">
              <Megaphone size={20} strokeWidth={1.8} />
            </span>
            <div>
              <h3>Поток клиентов</h3>
              {/*
                Про «реферальную сеть бухгалтерских сервисов» здесь было
                написано авансом — такой сети нет. Оставляем то, что делает сам
                каталог.
              */}
              <p>
                Адрес попадает в поисковую выдачу и показывается в релевантных
                подборках каталога.
              </p>
            </div>
          </li>
        </ul>
      </div>
    </section>
  );
}
