/**
 * Статус-трекер (этап 6): расписка ИФНС и регистрация компании.
 *
 * - ClientRegistrationPanel — клиент загружает PDF расписки из письма ИФНС
 *   (сканы не принимаем — решение владельца 13.10.2026): сервер читает из него
 *   дату регистрации, название, номер, инспекцию; клиент проверяет дату и
 *   отправляет. От этой даты строится прогноз и напоминание площадке.
 * - ReceiptSummary — что известно из расписки: собственнику (по ней он
 *   отслеживает регистрацию и подтверждает компанию для ФНС) и админу.
 */
import { CheckCircle2, FileText, Loader2, Upload } from "lucide-react";
import { FormEvent, useState } from "react";
import { api } from "../api";
import { trackerDate } from "../applications/progress";
import type { ClientApplication, IfnsReceiptData, RegistrationTrackerFields } from "../types";

const DOCUMENTS_ISSUED = new Set(["ready_for_client", "completed"]);

/** Блок регистрации у клиента: только когда документы выданы. */
export function showsRegistrationPanel(application: { status: string }): boolean {
  return DOCUMENTS_ISSUED.has(application.status);
}

/** Сводка по расписке: компания, вх. номер, инспекция, даты. */
export function ReceiptSummary({ tracker }: { tracker: RegistrationTrackerFields }) {
  const receipt = tracker.ifns_receipt;
  if (!tracker.ifns_receipt_uploaded_at && !tracker.registration_confirmed_at) return null;
  return (
    <div className="receipt-summary">
      {tracker.registration_confirmed_at ? (
        <span className="receipt-summary__done">
          <CheckCircle2 size={14} /> Регистрация подтверждена {trackerDate(tracker.registration_confirmed_at)}
          {tracker.registration_inn ? ` · ИНН ${tracker.registration_inn}` : ""}
        </span>
      ) : null}
      {tracker.ifns_receipt_uploaded_at ? (
        <dl className="receipt-summary__kv">
          {receipt?.company_name ? <div><dt>Компания</dt><dd>{receipt.company_name}</dd></div> : null}
          {receipt?.ifns ? <div><dt>Инспекция</dt><dd>{receipt.ifns}</dd></div> : null}
          {receipt?.number ? <div><dt>Вх. №</dt><dd>{receipt.number}{receipt.form ? ` · ${receipt.form}` : ""}</dd></div> : null}
          {receipt?.submitted_on ? <div><dt>Подано</dt><dd>{trackerDate(receipt.submitted_on)}</dd></div> : null}
          {tracker.registration_expected_on ? (
            <div><dt>Регистрация</dt><dd>{trackerDate(tracker.registration_expected_on)}</dd></div>
          ) : null}
        </dl>
      ) : null}
    </div>
  );
}

export function ClientRegistrationPanel({
  application,
  onSaved
}: {
  application: ClientApplication;
  onSaved: () => void;
}) {
  const hasReceipt = Boolean(application.ifns_receipt_uploaded_at);
  const [editing, setEditing] = useState(!hasReceipt);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<IfnsReceiptData | null>(null);
  const [expectedOn, setExpectedOn] = useState("");
  const [busy, setBusy] = useState<"preview" | "upload" | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (application.registration_confirmed_at) {
    return (
      <div className="registration-panel">
        <strong>Регистрация компании</strong>
        <ReceiptSummary tracker={application} />
      </div>
    );
  }

  async function pick(next: File | null) {
    setFile(next);
    setPreview(null);
    setError(null);
    if (!next) return;
    setBusy("preview");
    try {
      const found = await api.previewIfnsReceipt(application.id, next);
      setPreview(found);
      setExpectedOn(found.expected_on || "");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !expectedOn) return;
    setBusy("upload");
    setError(null);
    try {
      await api.uploadIfnsReceipt(application.id, file, expectedOn);
      setEditing(false);
      setFile(null);
      setPreview(null);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="registration-panel">
      <strong>Регистрация компании</strong>
      {hasReceipt && !editing ? (
        <>
          <ReceiptSummary tracker={application} />
          <span className="registration-panel__muted">
            Площадка сверит регистрацию с ЕГРЮЛ после этой даты — от вас больше ничего не нужно.
          </span>
          <button className="text-action" onClick={() => setEditing(true)} type="button">
            Загрузить другую расписку
          </button>
        </>
      ) : (
        <form className="registration-panel__form" onSubmit={submit}>
          <span className="registration-panel__muted">
            Подали документы в ИФНС? Загрузите PDF расписки о приёме документов — его налоговая
            присылает на почту. Именно этот файл, не скан и не фото: из него мы возьмём дату
            регистрации, а собственник адреса по нему отследит регистрацию.
          </span>
          <label className="registration-panel__file">
            <Upload size={15} />
            <span>{file ? file.name : "Выбрать PDF из письма ИФНС"}</span>
            <input
              accept="application/pdf,.pdf"
              onChange={(event) => void pick(event.target.files?.[0] || null)}
              type="file"
            />
          </label>
          {busy === "preview" ? (
            <span className="registration-panel__muted">
              <Loader2 className="spin" size={14} /> Читаем расписку…
            </span>
          ) : null}
          {preview ? (
            <div className="registration-panel__preview">
              <span>
                <FileText size={14} /> {preview.looks_like_receipt ? "Расписка ИФНС" : "Файл прочитан, но на расписку не похож — проверьте, тот ли это файл"}
              </span>
              {preview.company_name ? <span>Компания: {preview.company_name}</span> : null}
              {preview.number ? <span>Вх. № {preview.number}{preview.ifns ? ` · ${preview.ifns}` : ""}</span> : null}
              <label className="field">
                <span>
                  Дата регистрации из расписки
                  {preview.expected_on ? " (нашли в файле — проверьте)" : " — в файле не нашли, укажите сами"}
                </span>
                <input
                  max={new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10)}
                  onChange={(event) => setExpectedOn(event.target.value)}
                  required
                  type="date"
                  value={expectedOn}
                />
              </label>
              <div className="registration-panel__actions">
                <button className="cab-btn cab-btn--primary cab-btn--sm" disabled={busy !== null || !expectedOn} type="submit">
                  {busy === "upload" ? <Loader2 className="spin" size={15} /> : null} Отправить расписку
                </button>
                {hasReceipt ? (
                  <button className="text-action" onClick={() => setEditing(false)} type="button">
                    Отмена
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
          {error ? <p className="payout-error" role="alert">{error}</p> : null}
        </form>
      )}
    </div>
  );
}
