/**
 * Оболочка кабинета: сайдбар, шапка, полоса контента — одна на все три роли.
 *
 * До этого она была написана трижды (корневой return App(), ClientDashboardView,
 * OwnerDashboardView) и успела разъехаться: три разных названия в логотипе
 * («uradres.net» / «Личный кабинет» / «Кабинет»), три набора отступов в шапке,
 * PushToggle у клиента и собственника, но не у оператора, заголовок раздела в
 * одном месте в шапке, в другом — отдельной секцией под ней.
 *
 * Различается только конфигурация разделов (shell/navConfig.ts) и содержимое.
 */
import { ChevronLeft, ExternalLink, LogOut, MailWarning, MoreHorizontal, RefreshCw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { EmailVerificationBanner } from "../sections/EmailVerification";
import type { CurrentUser } from "../types";
import { navGroupsFor, ROLE_CAPTIONS, type NavGroup } from "./navConfig";

/** Счётчики у разделов: раздел → число. Раздел без записи показывается без цифры. */
export type SectionCounts = Record<string, number | undefined>;

export function AppShell({
  user,
  section,
  onSection,
  title,
  subtitle,
  crumb,
  counts,
  onOpenSite,
  onBack,
  canGoBack,
  onLogout,
  onRefresh,
  actions,
  banner,
  children
}: {
  user: CurrentUser;
  section: string;
  onSection: (id: string) => void;
  title: string;
  subtitle?: string;
  /** Крошка показывается только там, где есть вложенность (вкладки раздела). */
  crumb?: { parent: string; current: string } | null;
  counts?: SectionCounts;
  onOpenSite: () => void;
  onBack: () => void;
  canGoBack: boolean;
  onLogout: () => void;
  onRefresh: () => void;
  /** Уведомления и push-переключатель — они живут в App.tsx. */
  actions?: ReactNode;
  /** Ошибки и сообщения раздела: показываются над контентом. */
  banner?: ReactNode;
  children: ReactNode;
}) {
  const groups = navGroupsFor(user.role);
  const [verifyOpen, setVerifyOpen] = useState(false);
  // Плашку о неподтверждённом адресе видят только те, кто заводил аккаунт сам.
  // У сотрудников учётку создаёт администратор — просить их подтвердить почту
  // некому и незачем.
  const needsVerify =
    user.email_verified === false && (user.role === "client" || user.role === "owner");

  const initials = (user.full_name || user.email || "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");

  return (
    <div className="cab-shell">
      <aside className="cab-sidebar">
        <button className="cab-brand" onClick={onOpenSite} title="Открыть публичный сайт" type="button">
          <span className="cab-brand__mark">UR</span>
          <span>
            <strong className="cab-brand__name">uradres.net</strong>
            <span className="cab-brand__role">{ROLE_CAPTIONS[user.role] || "кабинет"}</span>
          </span>
        </button>

        <nav className="cab-nav">
          {groups.map((group) => (
            <NavGroupView
              counts={counts}
              group={group}
              key={group.title}
              onSection={onSection}
              section={section}
            />
          ))}
        </nav>

        <div className="cab-sidebar__footer">
          <div className="cab-user">
            <span className="cab-user__avatar">{initials || "—"}</span>
            <span style={{ minWidth: 0 }}>
              <strong className="cab-user__mail" title={user.email}>
                {user.email}
              </strong>
              <span className="cab-user__role">{ROLE_CAPTIONS[user.role] || user.role}</span>
            </span>
          </div>
          <button className="cab-btn cab-btn--sm cab-btn--block" onClick={onOpenSite} type="button">
            <ExternalLink size={14} /> Открыть сайт
          </button>
          <button className="cab-btn cab-btn--ghost cab-btn--sm cab-btn--block" onClick={onLogout} type="button">
            <LogOut size={14} /> Выйти
          </button>
        </div>
      </aside>

      <main className="cab-main">
        <header className="cab-topbar">
          <div className="cab-topbar__left">
            {/*
              В макете кнопки «Назад» нет — там ходят только по меню. Но в
              приложении есть вложенность и внешние ссылки (письмо, push), и до
              этой правки вернуться можно было только крошками, которые макет
              убирает. Кнопка осталась, но появляется, лишь когда внутри
              приложения действительно есть куда возвращаться.
            */}
            {canGoBack ? (
              <button
                aria-label="Назад"
                className="cab-iconbtn cab-iconbtn--sm"
                onClick={onBack}
                title="Назад"
                type="button"
              >
                <ChevronLeft size={16} />
              </button>
            ) : null}
            <div className="cab-topbar__heading">
              {crumb ? (
                <div className="cab-crumbs">
                  <span>{crumb.parent}</span>
                  <span>/</span>
                  <span className="cab-crumbs__current">{crumb.current}</span>
                </div>
              ) : null}
              <h1 className="cab-topbar__title">{title}</h1>
              {subtitle ? <span className="cab-topbar__sub">{subtitle}</span> : null}
            </div>
          </div>

          <div className="cab-topbar__actions">
            {needsVerify ? (
              <button
                aria-expanded={verifyOpen}
                className="cab-verify"
                onClick={() => setVerifyOpen((open) => !open)}
                type="button"
              >
                <MailWarning size={14} /> Подтвердите e-mail
              </button>
            ) : null}
            {actions}
            <button className="cab-btn cab-btn--sm" onClick={onRefresh} type="button">
              <RefreshCw size={14} /> Обновить
            </button>
          </div>
        </header>

        {/*
          Плашка раскрывается по клику: в макете это неинтерактивная подпись,
          но вместе с ней пропала бы кнопка «Отправить ссылку» — единственный
          способ получить письмо заново.
        */}
        {needsVerify && verifyOpen ? (
          <div className="cab-verify-panel">
            <EmailVerificationBanner email={user.email} />
          </div>
        ) : null}

        <div className="cab-content">
          {banner}
          {children}
        </div>

        <MobileTabbar groups={groups} onSection={onSection} section={section} />
      </main>
    </div>
  );
}

function NavGroupView({
  group,
  section,
  onSection,
  counts
}: {
  group: NavGroup;
  section: string;
  onSection: (id: string) => void;
  counts?: SectionCounts;
}) {
  return (
    <div className="cab-nav__group">
      <div className="cab-nav__group-title">{group.title}</div>
      {group.items.map((item) => {
        const Icon = item.icon;
        const count = counts?.[item.id];
        return (
          <button
            aria-current={section === item.id ? "page" : undefined}
            className={section === item.id ? "cab-nav__item is-active" : "cab-nav__item"}
            key={item.id}
            onClick={() => onSection(item.id)}
            type="button"
          >
            <Icon size={17} strokeWidth={1.8} />
            <span className="cab-nav__label">{item.label}</span>
            {typeof count === "number" && count > 0 ? (
              <span className="cab-nav__count">{count > 99 ? "99+" : count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Нижняя панель на телефоне. Разделов у оператора тринадцать, в панель влезает
 * пять — берём первые из каждой группы, остальное остаётся доступным по прямой
 * ссылке. Лучше пять достижимых кнопок, чем тринадцать нечитаемых.
 */
/** Сколько кнопок помещается в нижнюю панель телефона. */
const TABBAR_SLOTS = 5;

function MobileTabbar({
  groups,
  section,
  onSection
}: {
  groups: NavGroup[];
  section: string;
  onSection: (id: string) => void;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const flat = groups.flatMap((group) => group.items);
  // Не влезает — четыре кнопки и «Ещё» с остальными. Раньше лишние разделы
  // просто пропадали: у собственника с шестым пунктом в панели оставались
  // одни «Заявки», и до остальных разделов с телефона было не добраться.
  const overflow = flat.length > TABBAR_SLOTS;
  const primary = !overflow
    ? flat
    : groups.length > 1
      ? groups.map((group) => group.items[0]).slice(0, TABBAR_SLOTS - 1)
      : flat.slice(0, TABBAR_SLOTS - 1);
  const rest = flat.filter((item) => !primary.includes(item));
  const restActive = rest.some((item) => item.id === section);

  function go(id: string) {
    setMoreOpen(false);
    onSection(id);
  }

  return (
    <>
      {moreOpen ? (
        <div className="cab-tabbar__more" role="menu">
          {rest.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={section === item.id ? "cab-tabbar__more-item is-active" : "cab-tabbar__more-item"}
                key={item.id}
                onClick={() => go(item.id)}
                role="menuitem"
                type="button"
              >
                <Icon size={18} strokeWidth={1.8} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
      <nav className="cab-tabbar">
        {primary.map((item) => {
          const Icon = item.icon;
          return (
            <button
              aria-current={section === item.id ? "page" : undefined}
              className={section === item.id ? "cab-tabbar__item is-active" : "cab-tabbar__item"}
              key={item.id}
              onClick={() => go(item.id)}
              type="button"
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{item.shortLabel || item.label}</span>
            </button>
          );
        })}
        {overflow ? (
          <button
            aria-expanded={moreOpen}
            className={restActive || moreOpen ? "cab-tabbar__item is-active" : "cab-tabbar__item"}
            onClick={() => setMoreOpen((open) => !open)}
            type="button"
          >
            <MoreHorizontal size={18} strokeWidth={1.8} />
            <span>Ещё</span>
          </button>
        ) : null}
      </nav>
    </>
  );
}
