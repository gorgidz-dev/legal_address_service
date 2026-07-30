/**
 * Блок «О нас» — цель ссылки #about в верхнем меню.
 *
 * Две задачи сразу: коротко объяснить, что это за сервис, и дать реквизиты
 * оператора. Реквизиты на сайте нужны не для красоты — по ним клиент проверяет,
 * с кем заключает договор, и они должны совпадать с разделом 10 оферты.
 *
 * Про границы услуги сказано прямо: сервис не подаёт документы в ФНС и не
 * заключает договор аренды за собственника. Это не самокритика, а то же, что
 * написано в оферте (п. 2) — расхождение сайта с офертой дороже, чем обтекаемая
 * формулировка на первом экране.
 */
import { Building2, FileText, Mail, ShieldCheck } from "lucide-react";
import type { LegalDoc } from "../router";
import { OPERATOR } from "./operator";

type Fact = {
  icon: typeof Building2;
  title: string;
  text: string;
};

const FACTS: Fact[] = [
  {
    icon: Building2,
    title: "Что мы делаем",
    text: "Сводим тех, кому нужен юридический адрес, с собственниками нежилых помещений. В каталоге — адреса с гарантийным письмом и выпиской ЕГРН, под регистрацию новой компании или смену адреса действующей.",
  },
  {
    icon: ShieldCheck,
    title: "Что проверяем",
    text: "Собственник и документы на объект проходят проверку до публикации карточки. Фотографии модерируются вручную, выписка ЕГРН прикладывается к адресу — её дату видно в карточке.",
  },
  {
    icon: FileText,
    title: "Как оформляется",
    text: "Заявка, переписка с собственником, счёт и статусы — в личном кабинете. Работаем по публичной оферте: она определяет состав услуги, порядок оплаты и условия возврата.",
  },
  {
    icon: Mail,
    title: "Границы услуги",
    text: "Сервис не является регистрирующим органом и не подаёт документы в ФНС — это делает клиент. Договор аренды заключается напрямую с собственником, на условиях сторон.",
  },
];

export function HomeAbout({ onOpenLegal }: { onOpenLegal: (doc: LegalDoc) => void }) {
  return (
    <section className="ds-about" id="about" aria-label="О нас">
      <div className="ds-about__inner">
        <header className="ds-about__head">
          <span className="ds-about__eyebrow">О нас</span>
          <h2 className="ds-about__title">Маркетплейс юридических адресов</h2>
        </header>

        <ul className="ds-about__facts">
          {FACTS.map((fact) => {
            const Icon = fact.icon;
            return (
              <li className="ds-about__fact" key={fact.title}>
                <span className="ds-about__fact-icon" aria-hidden="true">
                  <Icon size={20} strokeWidth={1.8} />
                </span>
                <h3>{fact.title}</h3>
                <p>{fact.text}</p>
              </li>
            );
          })}
        </ul>

        <div className="ds-about__requisites">
          <h3 className="ds-about__requisites-title">Реквизиты</h3>
          <dl className="ds-about__req-list">
            <div>
              <dt>Оператор</dt>
              <dd>{OPERATOR.name}</dd>
            </div>
            <div>
              <dt>ИНН</dt>
              <dd>{OPERATOR.inn}</dd>
            </div>
            <div>
              <dt>ОГРНИП</dt>
              <dd>{OPERATOR.ogrnip}</dd>
            </div>
            <div>
              <dt>Адрес</dt>
              <dd>{OPERATOR.address}</dd>
            </div>
            <div>
              <dt>Почта</dt>
              <dd>
                <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
              </dd>
            </div>
          </dl>
          <p className="ds-about__req-note">
            Полные условия — в{" "}
            <button className="ds-about__link" onClick={() => onOpenLegal("offer")} type="button">
              публичной оферте
            </button>
            .
          </p>
        </div>
      </div>
    </section>
  );
}
