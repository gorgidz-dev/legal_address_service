/**
 * Документы платежа по счёту (manual_invoice).
 *
 * Роли:
 * - client: скачать счёт; «я оплатил» — загрузить платёжное поручение.
 * - owner:  загрузить счёт; скачать платёжку; «Подтвердить поступление средств».
 * - staff:  только просмотр/скачивание.
 *
 * Момент оплаты — подтверждение собственником (confirm-receipt), не загрузка
 * платёжки клиентом.
 */
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Download, FileText, Upload } from "lucide-react";
import { api, ApiError, paymentDocumentDownloadUrl } from "../api";
import type {
  Payment,
  PaymentAttachment,
  PaymentAttachmentKind,
} from "../types";

type Props = {
  paymentId: string;
  viewerRole: "client" | "owner" | "staff";
  /** Текущий статус платежа — нужен, чтобы скрыть кнопку подтверждения после оплаты. */
  paymentStatus: string;
  /** Колбэк после успешного подтверждения собственником. */
  onConfirmed?: () => void;
};

export function PaymentAttachmentsPanel({
  paymentId,
  viewerRole,
  paymentStatus,
  onConfirmed,
}: Props) {
  const [items, setItems] = useState<PaymentAttachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function reload() {
    setLoading(true);
    api
      .listPaymentAttachments(paymentId)
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }

  useEffect(reload, [paymentId]);

  const invoice = items.find((a) => a.kind === "invoice") || null;
  const paymentOrder = items.find((a) => a.kind === "payment_order") || null;
  const paid = paymentStatus === "succeeded";

  async function upload(kind: PaymentAttachmentKind, file: File) {
    setBusy(true);
    setError(null);
    try {
      await api.uploadPaymentAttachment(paymentId, kind, file);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить файл.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!window.confirm("Подтвердить поступление средств по счёту?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.confirmPaymentReceipt(paymentId);
      onConfirmed?.();
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось подтвердить оплату.");
    } finally {
      setBusy(false);
    }
  }

  function pickFile(kind: PaymentAttachmentKind) {
    const input = fileInputRef.current;
    if (!input) return;
    input.onchange = () => {
      const f = input.files?.[0];
      if (f) void upload(kind, f);
      input.value = "";
    };
    input.click();
  }

  if (loading) {
    return <div className="ds-payatt__loading">Загружаем документы платежа…</div>;
  }

  return (
    <div className="ds-payatt">
      <input ref={fileInputRef} type="file" hidden accept=".pdf,.jpg,.jpeg,.png" />

      {/* Счёт */}
      <div className="ds-payatt__row">
        <FileText size={16} className="ds-payatt__icon" />
        <div className="ds-payatt__body">
          <span className="ds-payatt__label">Счёт на оплату</span>
          {invoice ? (
            <a
              className="ds-payatt__file"
              href={paymentDocumentDownloadUrl(invoice.download_url)}
              target="_blank"
              rel="noreferrer"
            >
              <Download size={13} /> {invoice.original_filename}
            </a>
          ) : (
            <span className="ds-payatt__muted">
              {viewerRole === "owner"
                ? "Загрузите счёт — клиент оплатит по нему."
                : "Ожидаем счёт от собственника."}
            </span>
          )}
        </div>
        {viewerRole === "owner" && (
          <button
            type="button"
            className="ds-btn ds-btn--ghost ds-btn--sm"
            onClick={() => pickFile("invoice")}
            disabled={busy}
          >
            <Upload size={13} /> {invoice ? "Заменить" : "Загрузить счёт"}
          </button>
        )}
      </div>

      {/* Платёжное поручение */}
      <div className="ds-payatt__row">
        <FileText size={16} className="ds-payatt__icon" />
        <div className="ds-payatt__body">
          <span className="ds-payatt__label">Платёжное поручение</span>
          {paymentOrder ? (
            <a
              className="ds-payatt__file"
              href={paymentDocumentDownloadUrl(paymentOrder.download_url)}
              target="_blank"
              rel="noreferrer"
            >
              <Download size={13} /> {paymentOrder.original_filename}
            </a>
          ) : (
            <span className="ds-payatt__muted">
              {viewerRole === "client"
                ? invoice
                  ? "Оплатите счёт в банке и приложите платёжку."
                  : "Платёжку можно приложить после получения счёта."
                : "Клиент ещё не приложил платёжное поручение."}
            </span>
          )}
        </div>
        {viewerRole === "client" && invoice && !paid && (
          <button
            type="button"
            className="ds-btn ds-btn--primary ds-btn--sm"
            onClick={() => pickFile("payment_order")}
            disabled={busy}
          >
            <Upload size={13} /> {paymentOrder ? "Заменить" : "Я оплатил"}
          </button>
        )}
      </div>

      {error && <div className="ds-payatt__error">{error}</div>}

      {/* Подтверждение собственником */}
      {viewerRole === "owner" && paymentOrder && !paid && (
        <button
          type="button"
          className="ds-btn ds-btn--primary ds-btn--md"
          onClick={confirm}
          disabled={busy}
        >
          <CheckCircle2 size={14} /> Подтвердить поступление средств
        </button>
      )}
      {paid && (
        <div className="ds-payatt__paid">
          <CheckCircle2 size={14} /> Оплата подтверждена.
        </div>
      )}
    </div>
  );
}

/**
 * Обёртка для кабинета собственника: сам подтягивает платёж по заявке
 * и показывает панель документов, если оплата идёт по счёту (manual_invoice).
 */
export function OwnerPaymentSection({
  applicationId,
  onConfirmed,
}: {
  applicationId: string;
  onConfirmed?: () => void;
}) {
  const [payment, setPayment] = useState<Payment | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .getPaymentByApplication(applicationId)
      .then((p) => alive && setPayment(p))
      .catch(() => alive && setPayment(null))
      .finally(() => alive && setLoaded(true));
    return () => {
      alive = false;
    };
  }, [applicationId]);

  if (!loaded) return null;
  if (!payment || payment.provider !== "manual_invoice") return null;

  return (
    <div className="ds-payatt-card">
      <h4 className="ds-payatt-card__title">Оплата по счёту</h4>
      <PaymentAttachmentsPanel
        paymentId={payment.id}
        viewerRole="owner"
        paymentStatus={payment.status}
        onConfirmed={onConfirmed}
      />
    </div>
  );
}
