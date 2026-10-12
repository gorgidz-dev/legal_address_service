/**
 * Выплаты собственникам — интерфейс всех трёх ролей.
 *
 * Модель денег (CLAUDE.md, «Как устроены деньги»): если клиент платит площадке,
 * площадка перечисляет собственнику цену за вычетом комиссии — только после
 * того, как админ сверил с ЕГРЮЛ, что компания клиента зарегистрирована по
 * адресу. Переводы ручные: система ведёт реестр, админ платит в банке и
 * отмечает выплату здесь. Правила — app/services/owner_payouts.py.
 *
 * - AdminPayoutsView — реестр оператора: проверка регистрации, отметка, отмена;
 * - ProviderPayoutSettingsModal — процент и реквизиты собственника (только админ);
 * - OwnerPayoutsView — выплаты собственника, только чтение;
 * - RegistrationInnPanel — клиент сообщает ИНН зарегистрированной компании.
 */
import { AlertTriangle, CheckCircle2, Loader2, ReceiptText, ShieldCheck, Wallet, XCircle } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type {
  AdminPayout,
  ClientApplication,
  OwnerPayout,
  PayoutStatus,
  Provider,
  RegistrationCheck
} from "../types";
import { Badge } from "../ui/Badge";
import { ListEmpty, ListError, ListLoading } from "../ui/ListState";
import { useModalDismiss } from "../useModalDismiss";

const STATUS_META: Record<PayoutStatus, { label: string; tone: "warning" | "brand" | "success" | "neutral" }> = {
  awaiting_registration: { label: "Ждёт регистрации", tone: "warning" },
  due: { label: "К выплате", tone: "brand" },
  paid: { label: "Выплачено", tone: "success" },
  cancelled: { label: "Отменена", tone: "neutral" }
};

const TAB_ORDER: PayoutStatus[] = ["due", "awaiting_registration", "paid", "cancelled"];

/** Документы выданы — можно подтверждать регистрацию (owner_payouts.REGISTRATION_ALLOWED). */
const DOCUMENTS_ISSUED = new Set(["ready_for_client", "completed"]);

function rub(kopeks: number | null | undefined): string {
  if (kopeks === null || kopeks === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB" }).format(kopeks / 100);
}

/**
 * «2026-10-12» → «12.10.2026» как есть (дата без времени: платёжка, регистрация);
 * отметка времени из базы (в UTC) → дата по Москве, иначе оплата в 01:15 МСК
 * показывалась бы вчерашним числом.
 */
function day(value: string | null | undefined): string {
  if (!value) return "—";
  if (value.length <= 10) {
    const [y, m, d] = value.split("-");
    return d && m && y ? `${d}.${m}.${y}` : value;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("ru-RU", { timeZone: "Europe/Moscow" });
}

/** Сегодня по местному времени в формате поля <input type="date">. */
function todayLocal(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function percent(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Number(value).toLocaleString("ru-RU")}%`;
}

function Money({ payout }: { payout: OwnerPayout }) {
  return (
    <dl className="payout-money">
      <div>
        <dt>Оплата клиента</dt>
        <dd>{rub(payout.gross_kopeks)}</dd>
      </div>
      <div>
        <dt>Комиссия площадки</dt>
        <dd>
          {payout.commission_percent === null
            ? "процент не задан"
            : `${percent(payout.commission_percent)} · ${rub(payout.commission_kopeks)}`}
        </dd>
      </div>
      <div className="payout-money__total">
        <dt>Собственнику</dt>
        <dd>{rub(payout.payout_kopeks)}</dd>
      </div>
    </dl>
  );
}

function ModalShell({
  eyebrow,
  title,
  onClose,
  children
}: {
  eyebrow: string;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useModalDismiss(true, onClose);
  return (
    <div className="modal-backdrop">
      <div className="modal-panel payout-modal" role="dialog" aria-modal="true" aria-label={title}>
        <header>
          <div>
            <span className="eyebrow">{eyebrow}</span>
            <h2>{title}</h2>
          </div>
          <button className="text-action" onClick={onClose} type="button">
            Закрыть
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

function ErrorLine({ message }: { message: string | null }) {
  return message ? <p className="payout-error" role="alert">{message}</p> : null;
}

// ============================================================
// Админ: реестр
// ============================================================

export function AdminPayoutsView() {
  const [payouts, setPayouts] = useState<AdminPayout[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<PayoutStatus | null>(null);
  const [registering, setRegistering] = useState<AdminPayout | null>(null);
  const [paying, setPaying] = useState<AdminPayout | null>(null);
  const [cancelling, setCancelling] = useState<AdminPayout | null>(null);

  function reload() {
    setError(null);
    api
      .adminPayouts()
      .then(setPayouts)
      .catch((err: Error) => setError(err.message));
  }

  useEffect(reload, []);

  const counts = useMemo(() => {
    const result: Record<PayoutStatus, number> = { awaiting_registration: 0, due: 0, paid: 0, cancelled: 0 };
    for (const payout of payouts || []) result[payout.status] += 1;
    return result;
  }, [payouts]);

  // Открываем ту вкладку, где есть работа: сначала «к выплате», потом «ждут регистрации».
  const activeTab: PayoutStatus = tab ?? (counts.due ? "due" : "awaiting_registration");
  const visible = (payouts || []).filter((payout) => payout.status === activeTab);
  const dueTotal = (payouts || [])
    .filter((payout) => payout.status === "due")
    .reduce((sum, payout) => sum + (payout.payout_kopeks || 0), 0);

  function replace(updated: AdminPayout) {
    setPayouts((current) => (current || []).map((p) => (p.id === updated.id ? updated : p)));
  }

  if (error) return <ListError message={error} onRetry={reload} />;
  if (!payouts) return <ListLoading />;

  return (
    <div className="payouts">
      <p className="payouts__intro">
        Собственник получает деньги, только когда компания клиента зарегистрирована по адресу.
        Переводите в банке по реквизитам из карточки и отмечайте выплату здесь.
      </p>
      {counts.due ? (
        <div className="payouts__summary">
          <Wallet size={16} /> К перечислению: {counts.due} на {rub(dueTotal)}
        </div>
      ) : null}

      <div className="cab-tabs payouts__tabs" role="tablist">
        {TAB_ORDER.map((status) => (
          <button
            aria-selected={activeTab === status}
            className={`cab-tab${activeTab === status ? " is-active" : ""}`}
            key={status}
            onClick={() => setTab(status)}
            role="tab"
            type="button"
          >
            {STATUS_META[status].label}
            <span className="cab-tab__count">{counts[status]}</span>
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <ListEmpty
          title="Здесь пусто"
          text={
            activeTab === "awaiting_registration"
              ? "Выплата появляется, когда клиент оплачивает заявку через площадку."
              : "Выплат в этом статусе нет."
          }
        />
      ) : (
        <ul className="payouts__list">
          {visible.map((payout) => (
            <AdminPayoutCard
              key={payout.id}
              onCancel={() => setCancelling(payout)}
              onPay={() => setPaying(payout)}
              onRegister={() => setRegistering(payout)}
              payout={payout}
            />
          ))}
        </ul>
      )}

      {registering ? (
        <RegistrationModal
          onClose={() => setRegistering(null)}
          onDone={(updated) => {
            replace(updated);
            setRegistering(null);
          }}
          payout={registering}
        />
      ) : null}
      {paying ? (
        <MarkPaidModal
          onClose={() => setPaying(null)}
          onDone={(updated) => {
            replace(updated);
            setPaying(null);
          }}
          payout={paying}
        />
      ) : null}
      {cancelling ? (
        <CancelModal
          onClose={() => setCancelling(null)}
          onDone={(updated) => {
            replace(updated);
            setCancelling(null);
          }}
          payout={cancelling}
        />
      ) : null}
    </div>
  );
}

function AdminPayoutCard({
  payout,
  onRegister,
  onPay,
  onCancel
}: {
  payout: AdminPayout;
  onRegister: () => void;
  onPay: () => void;
  onCancel: () => void;
}) {
  const meta = STATUS_META[payout.status];
  const live = payout.status === "awaiting_registration" || payout.status === "due";
  const blocked = payout.blockers.length > 0;
  const check = payout.registration_check;
  const missingRequisites = !payout.payee.settlement_account || !payout.payee.bik;
  // Подтверждать регистрацию можно после выдачи документов — раньше сервер всё
  // равно ответит 409, успев дважды сходить в ЕГРЮЛ.
  const documentsIssued = DOCUMENTS_ISSUED.has(payout.application_status);

  return (
    <li className="payout-card">
      <div className="payout-card__head">
        <div>
          <strong>{payout.application_label}</strong>
          <span className="payout-card__sub">
            {payout.provider_name}
            {payout.address ? ` · ${payout.address}` : ""}
          </span>
        </div>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>

      <Money payout={payout} />

      <div className="payout-card__facts">
        {payout.registration_confirmed_at && check ? (
          <span>
            <ShieldCheck size={14} /> Регистрация подтверждена {day(payout.registration_confirmed_at)}:{" "}
            {check.full_name || "компания"}, ИНН {check.inn}
            {check.ogrn ? `, ОГРН ${check.ogrn}` : ""}
            {check.accepted_address_mismatch ? " · адрес сверен вручную" : ""}
          </span>
        ) : payout.registration_inn_submitted_at ? (
          <span>Клиент сообщил ИНН {payout.registration_inn} ({day(payout.registration_inn_submitted_at)})</span>
        ) : payout.status === "awaiting_registration" ? (
          <span className="payout-card__muted">
            {payout.suggested_inn
              ? `ИНН компании из заявки: ${payout.suggested_inn}`
              : "Клиент ещё не сообщил ИНН зарегистрированной компании"}
          </span>
        ) : null}

        {payout.status === "paid" ? (
          <span>
            <CheckCircle2 size={14} /> Платёжное поручение № {payout.bank_reference} от {day(payout.paid_on)}
            {payout.payee.settlement_account ? ` · р/с ${payout.payee.settlement_account}` : ""}
            {payout.comment ? ` · ${payout.comment}` : ""}
          </span>
        ) : null}
        {payout.status === "cancelled" ? (
          <span>
            <XCircle size={14} /> Отменена {day(payout.cancelled_at)}: {payout.cancel_reason}
          </span>
        ) : null}
        {payout.status === "due" ? (
          missingRequisites ? (
            <span className="payout-card__warn">
              <AlertTriangle size={14} /> У собственника нет реквизитов — внесите их в разделе «Собственники».
            </span>
          ) : (
            <span>
              {payout.payee.full_name}, ИНН {payout.payee.inn || "—"} · {payout.payee.bank_name || "банк не указан"},
              БИК {payout.payee.bik}, р/с {payout.payee.settlement_account}
            </span>
          )
        ) : null}
      </div>

      {blocked ? (
        <ul className="payout-card__blockers">
          {payout.blockers.map((reason) => (
            <li key={reason}>
              <AlertTriangle size={14} /> {reason}
            </li>
          ))}
        </ul>
      ) : null}

      {live ? (
        <div className="payout-card__actions">
          {payout.status === "awaiting_registration" ? (
            <>
              <button
                className="cab-btn cab-btn--primary cab-btn--sm"
                disabled={blocked || !documentsIssued}
                onClick={onRegister}
                type="button"
              >
                <ShieldCheck size={15} /> Проверить регистрацию
              </button>
              {!documentsIssued && !blocked ? (
                <span className="payout-card__muted payout-card__hint">После выдачи документов клиенту</span>
              ) : null}
            </>
          ) : (
            <button
              className="cab-btn cab-btn--primary cab-btn--sm"
              disabled={blocked || missingRequisites}
              onClick={onPay}
              type="button"
            >
              <ReceiptText size={15} /> Отметить выплату
            </button>
          )}
          <button className="cab-btn cab-btn--danger cab-btn--sm" onClick={onCancel} type="button">
            <XCircle size={15} /> Отменить
          </button>
        </div>
      ) : null}
    </li>
  );
}

function RegistrationModal({
  payout,
  onClose,
  onDone
}: {
  payout: AdminPayout;
  onClose: () => void;
  onDone: (updated: AdminPayout) => void;
}) {
  const [inn, setInn] = useState(payout.suggested_inn || "");
  const [check, setCheck] = useState<RegistrationCheck | null>(null);
  const [manual, setManual] = useState(false);
  const [busy, setBusy] = useState<"check" | "confirm" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cleanInn = inn.replace(/\D/g, "");
  const checkIsCurrent = check !== null && check.inn === cleanInn;
  const canConfirm =
    checkIsCurrent && check.found && (check.address_matches === true || manual) && busy === null;

  async function runCheck(event: FormEvent) {
    event.preventDefault();
    setBusy("check");
    setError(null);
    setManual(false);
    try {
      setCheck(await api.checkRegistration(payout.application_id, cleanInn));
    } catch (err) {
      setCheck(null);
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function confirm() {
    setBusy("confirm");
    setError(null);
    try {
      onDone(await api.confirmRegistration(payout.application_id, cleanInn, manual));
    } catch (err) {
      setError((err as Error).message);
      setBusy(null);
    }
  }

  return (
    <ModalShell eyebrow="Регистрация компании" onClose={onClose} title={payout.application_label}>
      <p className="payout-modal__text">
        Введите ИНН компании, зарегистрированной по адресу заявки, и сверьте данные из ЕГРЮЛ.
        После подтверждения собственнику уйдёт уведомление, а выплата встанет «к перечислению».
      </p>
      <form className="payout-modal__row" onSubmit={runCheck}>
        <label className="field">
          <span>ИНН компании</span>
          <input
            autoFocus
            inputMode="numeric"
            maxLength={12}
            onChange={(event) => setInn(event.target.value)}
            placeholder="10 цифр"
            value={inn}
          />
        </label>
        <button className="cab-btn cab-btn--sm" disabled={cleanInn.length !== 10 || busy !== null} type="submit">
          {busy === "check" ? <Loader2 className="spin" size={15} /> : <ShieldCheck size={15} />} Проверить в ЕГРЮЛ
        </button>
      </form>

      {checkIsCurrent ? (
        <div className="payout-check">
          {check.found ? (
            <dl className="payout-check__kv">
              <div><dt>Компания</dt><dd>{check.full_name}</dd></div>
              <div><dt>ОГРН</dt><dd>{check.ogrn || "—"}</dd></div>
              <div><dt>Зарегистрирована</dt><dd>{day(check.registration_date)}</dd></div>
              <div><dt>Статус</dt><dd>{check.egrul_status || "—"}</dd></div>
              <div><dt>Юрадрес в ЕГРЮЛ</dt><dd>{check.legal_address || "—"}</dd></div>
              <div><dt>Адрес заявки</dt><dd>{check.our_address || payout.address || "—"}</dd></div>
            </dl>
          ) : null}
          <div className={`payout-check__verdict payout-check__verdict--${check.address_matches ? "ok" : "warn"}`}>
            {check.address_matches ? (
              <><CheckCircle2 size={15} /> Адрес совпадает</>
            ) : (
              <><AlertTriangle size={15} /> {check.found ? "Адрес не совпал — сравните вручную" : "Компания не найдена"}</>
            )}
          </div>
          {check.warnings.length ? (
            <ul className="payout-card__blockers">
              {check.warnings.map((warning) => (
                <li key={warning}><AlertTriangle size={14} /> {warning}</li>
              ))}
            </ul>
          ) : null}
          {check.found && check.address_matches !== true ? (
            <label className="payout-check__manual">
              <input checked={manual} onChange={(event) => setManual(event.target.checked)} type="checkbox" />
              Я сверил адрес вручную — это тот же адрес
            </label>
          ) : null}
        </div>
      ) : null}

      <ErrorLine message={error} />
      <div className="payout-modal__actions">
        <button className="cab-btn cab-btn--primary" disabled={!canConfirm} onClick={confirm} type="button">
          {busy === "confirm" ? <Loader2 className="spin" size={15} /> : <CheckCircle2 size={15} />} Подтвердить регистрацию
        </button>
      </div>
    </ModalShell>
  );
}

function MarkPaidModal({
  payout,
  onClose,
  onDone
}: {
  payout: AdminPayout;
  onClose: () => void;
  onDone: (updated: AdminPayout) => void;
}) {
  const [paidOn, setPaidOn] = useState(todayLocal());
  const [reference, setReference] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(
        await api.markPayoutPaid(payout.id, {
          paid_on: paidOn,
          bank_reference: reference.trim(),
          comment: comment.trim() || null
        })
      );
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const payee = payout.payee;
  return (
    <ModalShell eyebrow="Выплата собственнику" onClose={onClose} title={rub(payout.payout_kopeks)}>
      <dl className="payout-check__kv">
        <div><dt>Получатель</dt><dd>{payee.full_name || payout.provider_name}</dd></div>
        <div><dt>ИНН / КПП</dt><dd>{payee.inn || "—"}{payee.kpp ? ` / ${payee.kpp}` : ""}</dd></div>
        <div><dt>Банк</dt><dd>{payee.bank_name || "—"}</dd></div>
        <div><dt>БИК</dt><dd>{payee.bik || "—"}</dd></div>
        <div><dt>Расчётный счёт</dt><dd>{payee.settlement_account || "—"}</dd></div>
        <div><dt>Корр. счёт</dt><dd>{payee.corr_account || "—"}</dd></div>
        <div><dt>За что</dt><dd>{payout.application_label}</dd></div>
      </dl>
      <form className="payout-modal__form" onSubmit={submit}>
        <label className="field">
          <span>Дата платёжного поручения</span>
          <input max={todayLocal()} onChange={(event) => setPaidOn(event.target.value)} required type="date" value={paidOn} />
        </label>
        <label className="field">
          <span>Номер платёжного поручения</span>
          <input maxLength={100} onChange={(event) => setReference(event.target.value)} required value={reference} />
        </label>
        <label className="field payout-modal__wide">
          <span>Комментарий (необязательно)</span>
          <input maxLength={1000} onChange={(event) => setComment(event.target.value)} value={comment} />
        </label>
        <ErrorLine message={error} />
        <div className="payout-modal__actions payout-modal__wide">
          <button className="cab-btn cab-btn--primary" disabled={busy || !reference.trim()} type="submit">
            {busy ? <Loader2 className="spin" size={15} /> : <CheckCircle2 size={15} />} Деньги отправлены
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function CancelModal({
  payout,
  onClose,
  onDone
}: {
  payout: AdminPayout;
  onClose: () => void;
  onDone: (updated: AdminPayout) => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await api.cancelPayout(payout.id, reason.trim()));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <ModalShell eyebrow="Отмена выплаты" onClose={onClose} title={payout.application_label}>
      <p className="payout-modal__text">
        Отменённую выплату нельзя вернуть: если деньги всё же положены собственнику, их придётся
        рассчитать вручную. Причину увидит собственник в разделе «Выплаты»
        {payout.status === "due" ? ", и ему уйдёт уведомление" : ""} — пишите её для него.
      </p>
      <form className="payout-modal__form" onSubmit={submit}>
        <label className="field payout-modal__wide">
          <span>Причина</span>
          <input
            autoFocus
            maxLength={500}
            minLength={3}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Например: возврат клиенту по отказу ИФНС"
            required
            value={reason}
          />
        </label>
        <ErrorLine message={error} />
        <div className="payout-modal__actions payout-modal__wide">
          <button className="cab-btn cab-btn--danger" disabled={busy || reason.trim().length < 3} type="submit">
            {busy ? <Loader2 className="spin" size={15} /> : <XCircle size={15} />} Отменить выплату
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ============================================================
// Админ: процент и реквизиты собственника
// ============================================================

export function ProviderPayoutSettingsModal({
  provider,
  onClose,
  onSaved
}: {
  provider: Provider;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    commission_percent: provider.commission_percent ?? "",
    bank_name: provider.bank_name ?? "",
    settlement_account: provider.settlement_account ?? "",
    corr_account: provider.corr_account ?? "",
    bik: provider.bik ?? ""
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const field = (key: keyof typeof form) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: event.target.value })
  });
  const orNull = (value: string) => value.trim() || null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.setProviderPayoutSettings(provider.id, {
        commission_percent: orNull(form.commission_percent.replace(",", ".")),
        bank_name: orNull(form.bank_name),
        settlement_account: orNull(form.settlement_account.replace(/\s/g, "")),
        corr_account: orNull(form.corr_account.replace(/\s/g, "")),
        bik: orNull(form.bik.replace(/\s/g, ""))
      });
      onSaved();
      onClose();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <ModalShell eyebrow="Выплаты собственнику" onClose={onClose} title={provider.short_name}>
      <p className="payout-modal__text">
        Процент применяется к новым оплатам — в уже заведённых выплатах он не меняется. Пустое поле —
        действует общий процент площадки.
      </p>
      <form className="payout-modal__form" onSubmit={submit}>
        <label className="field">
          <span>Комиссия площадки, %</span>
          <input inputMode="decimal" placeholder="общий" {...field("commission_percent")} />
        </label>
        <label className="field">
          <span>Банк</span>
          <input maxLength={300} {...field("bank_name")} />
        </label>
        <label className="field">
          <span>БИК</span>
          <input inputMode="numeric" maxLength={9} {...field("bik")} />
        </label>
        <label className="field">
          <span>Расчётный счёт</span>
          <input inputMode="numeric" maxLength={24} {...field("settlement_account")} />
        </label>
        <label className="field payout-modal__wide">
          <span>Корр. счёт</span>
          <input inputMode="numeric" maxLength={24} {...field("corr_account")} />
        </label>
        <ErrorLine message={error} />
        <div className="payout-modal__actions payout-modal__wide">
          <button className="cab-btn cab-btn--primary" disabled={busy} type="submit">
            {busy ? <Loader2 className="spin" size={15} /> : <CheckCircle2 size={15} />} Сохранить
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ============================================================
// Собственник: свои выплаты
// ============================================================

export function OwnerPayoutsView() {
  const [payouts, setPayouts] = useState<OwnerPayout[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setError(null);
    api
      .myPayouts()
      .then(setPayouts)
      .catch((err: Error) => setError(err.message));
  }

  useEffect(reload, []);

  if (error) return <ListError message={error} onRetry={reload} />;
  if (!payouts) return <ListLoading />;

  // Пока процент комиссии не задан, сумма выплаты неизвестна — не выдаём ноль за итог.
  const total = (status: PayoutStatus): string => {
    const group = payouts.filter((p) => p.status === status);
    if (group.some((p) => p.payout_kopeks === null)) return "уточняется";
    return rub(group.reduce((sum, p) => sum + (p.payout_kopeks || 0), 0));
  };

  return (
    <div className="payouts">
      <p className="payouts__intro">
        Когда клиент оплачивает регистрацию через площадку, деньги ждут, пока его компания не будет
        зарегистрирована по вашему адресу. После этого площадка перечисляет вам сумму за вычетом
        своей комиссии.
      </p>
      <div className="cab-stats payouts__stats">
        <div className="cab-stat">
          <span className="cab-stat__label">Ждут регистрации</span>
          <strong className="cab-stat__value">{total("awaiting_registration")}</strong>
        </div>
        <div className="cab-stat">
          <span className="cab-stat__label">К выплате</span>
          <strong className="cab-stat__value">{total("due")}</strong>
        </div>
        <div className="cab-stat">
          <span className="cab-stat__label">Выплачено</span>
          <strong className="cab-stat__value">{total("paid")}</strong>
        </div>
      </div>
      {payouts.length === 0 ? (
        <ListEmpty title="Выплат пока нет" text="Они появятся, когда клиенты оплатят заявки на ваши адреса." />
      ) : (
        <ul className="payouts__list">
          {payouts.map((payout) => {
            const meta = STATUS_META[payout.status];
            return (
              <li className="payout-card" key={payout.id}>
                <div className="payout-card__head">
                  <div>
                    <strong>{payout.application_label}</strong>
                    {payout.address ? <span className="payout-card__sub">{payout.address}</span> : null}
                  </div>
                  <Badge tone={meta.tone}>{meta.label}</Badge>
                </div>
                <Money payout={payout} />
                <div className="payout-card__facts">
                  {payout.status === "awaiting_registration" ? (
                    <span className="payout-card__muted">Оплачено {day(payout.created_at)} · ждём регистрации компании</span>
                  ) : null}
                  {payout.status === "due" ? <span>Регистрация подтверждена {day(payout.due_at)}</span> : null}
                  {payout.status === "paid" ? (
                    <span>
                      <CheckCircle2 size={14} /> Перечислено: п/п № {payout.bank_reference} от {day(payout.paid_on)}
                    </span>
                  ) : null}
                  {payout.status === "cancelled" ? <span>Отменена: {payout.cancel_reason}</span> : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ============================================================
// Клиент: ИНН зарегистрированной компании
// ============================================================

const REGISTRATION_STATUSES = new Set(["ready_for_client", "completed"]);

/** Показывать ли клиенту поле ИНН: документы выданы, компания новая. */
export function needsRegistrationInn(application: ClientApplication): boolean {
  return application.type === "initial_registration" && REGISTRATION_STATUSES.has(application.status);
}

export function RegistrationInnPanel({
  application,
  onSaved
}: {
  application: ClientApplication;
  onSaved: () => void;
}) {
  const [inn, setInn] = useState(application.registration_inn || "");
  const [editing, setEditing] = useState(!application.registration_inn);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (application.registration_confirmed_at) {
    return (
      <div className="registration-inn registration-inn--done">
        <CheckCircle2 size={16} /> Площадка подтвердила регистрацию компании по адресу (ИНН{" "}
        {application.registration_inn}).
      </div>
    );
  }

  const clean = inn.replace(/\D/g, "");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.submitRegistrationInn(application.id, clean);
      setEditing(false);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <div className="registration-inn">
        <span>
          Вы сообщили ИНН {application.registration_inn} — площадка сверит регистрацию с ЕГРЮЛ.
        </span>
        <button className="text-action" onClick={() => setEditing(true)} type="button">
          Исправить
        </button>
      </div>
    );
  }

  return (
    <form className="registration-inn" onSubmit={submit}>
      <span>Компания уже зарегистрирована? Сообщите её ИНН — мы сверим регистрацию по адресу с ЕГРЮЛ.</span>
      <div className="registration-inn__row">
        <input
          aria-label="ИНН компании"
          inputMode="numeric"
          maxLength={12}
          onChange={(event) => setInn(event.target.value)}
          placeholder="ИНН, 10 цифр"
          value={inn}
        />
        <button className="cab-btn cab-btn--primary cab-btn--sm" disabled={busy || clean.length !== 10} type="submit">
          {busy ? <Loader2 className="spin" size={15} /> : null} Отправить
        </button>
      </div>
      <ErrorLine message={error} />
    </form>
  );
}
