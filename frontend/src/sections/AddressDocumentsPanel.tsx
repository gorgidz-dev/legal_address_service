/**
 * Правоустанавливающие документы адреса — модалка в кабинете собственника.
 *
 * Срок действия здесь не украшение: по нему собственнику уходит напоминание,
 * что документ пора обновить. Поэтому просроченные и истекающие подсвечены, а
 * бессрочные подписаны словом «бессрочно», а не пустым местом — иначе не
 * отличить «срока нет» от «забыли заполнить».
 */
import { AlertTriangle, Download, FileText, Loader2, Trash2, Upload, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, apiDownloadUrl } from "../api";
import type { AddressDocument, AddressDocumentKind } from "../types";
import { ListEmpty, ListError, ListLoading } from "../ui/ListState";

const KIND_OPTIONS: { value: AddressDocumentKind; label: string }[] = [
  { value: "ownership_certificate", label: "Документ о праве собственности" },
  { value: "lease_agreement", label: "Договор с владельцем здания" },
  { value: "power_of_attorney", label: "Доверенность" },
  { value: "other", label: "Иной документ" }
];

function expiryText(doc: AddressDocument): string {
  if (doc.expiry_state === "none") return "бессрочно";
  const days = doc.days_until_expiry ?? 0;
  if (days < 0) {
    const overdue = -days;
    return overdue === 1 ? "истёк вчера" : `истёк ${overdue} дн. назад`;
  }
  if (days === 0) return "истекает сегодня";
  if (days === 1) return "истекает завтра";
  return `ещё ${days} дн.`;
}

function expiryClass(doc: AddressDocument): string {
  if (doc.expiry_state === "expired") return "addr-doc__expiry addr-doc__expiry--expired";
  if (doc.expiry_state === "soon") return "addr-doc__expiry addr-doc__expiry--soon";
  return "addr-doc__expiry";
}

export function AddressDocumentsPanel({
  addressId,
  addressLabel,
  onClose
}: {
  addressId: string;
  addressLabel: string;
  onClose: () => void;
}) {
  const [documents, setDocuments] = useState<AddressDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [kind, setKind] = useState<AddressDocumentKind>("ownership_certificate");
  const [title, setTitle] = useState("");
  const [issuedOn, setIssuedOn] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [file, setFile] = useState<File | null>(null);

  function reload() {
    setError(null);
    api
      .addressDocuments(addressId)
      .then(setDocuments)
      .catch((err) => setError((err as Error).message));
  }

  useEffect(reload, [addressId]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Выберите файл документа");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      form.append("title", title);
      if (issuedOn) form.append("issued_on", issuedOn);
      if (expiresAt) form.append("expires_at", expiresAt);
      await api.uploadAddressDocument(addressId, form);
      setTitle("");
      setIssuedOn("");
      setExpiresAt("");
      setFile(null);
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(documentId: string) {
    setBusy(true);
    try {
      await api.deleteAddressDocument(addressId, documentId);
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel addr-docs" onClick={(e) => e.stopPropagation()}>
        <header>
          <div>
            <span className="eyebrow">Документы адреса</span>
            <h2>{addressLabel}</h2>
          </div>
          <button className="text-action" onClick={onClose} type="button">
            <X size={16} /> Закрыть
          </button>
        </header>

        {error ? <ListError message={error} /> : null}

        <form className="addr-docs__form" onSubmit={submit}>
          <label className="field">
            <span>Тип документа</span>
            <select onChange={(e) => setKind(e.target.value as AddressDocumentKind)} value={kind}>
              {KIND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Название</span>
            <input
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Свидетельство 77-АБ 123456"
              value={title}
            />
          </label>
          <label className="field">
            <span>Выдан</span>
            <input onChange={(e) => setIssuedOn(e.target.value)} type="date" value={issuedOn} />
          </label>
          <label className="field">
            <span>Действует до</span>
            <input onChange={(e) => setExpiresAt(e.target.value)} type="date" value={expiresAt} />
            <small>Пусто — документ бессрочный</small>
          </label>
          <label className="field addr-docs__file">
            <span>Файл</span>
            <input onChange={(e) => setFile(e.target.files?.[0] || null)} type="file" />
          </label>
          <button className="cab-btn cab-btn--primary" disabled={busy} type="submit">
            {busy ? <Loader2 className="spin" size={15} /> : <Upload size={15} />} Загрузить
          </button>
        </form>

        {documents === null ? (
          <ListLoading rows={2} />
        ) : documents.length === 0 ? (
          <ListEmpty
            title="Документов пока нет"
            text="Загрузите документы, подтверждающие право на помещение."
          />
        ) : (
          <ul className="addr-docs__list">
            {documents.map((doc) => (
              <li className="addr-doc" key={doc.id}>
                <span className="addr-doc__icon" aria-hidden="true">
                  {doc.expiry_state === "expired" ? (
                    <AlertTriangle size={17} />
                  ) : (
                    <FileText size={17} />
                  )}
                </span>
                <div className="addr-doc__main">
                  <strong>{doc.title}</strong>
                  <span className="addr-doc__meta">
                    {doc.kind_label}
                    {doc.issued_on ? ` · выдан ${doc.issued_on}` : ""}
                  </span>
                </div>
                <span className={expiryClass(doc)}>{expiryText(doc)}</span>
                <div className="addr-doc__actions">
                  <a
                    className="text-action"
                    href={apiDownloadUrl(doc.download_url)}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <Download size={15} />
                  </a>
                  <button
                    className="text-action"
                    disabled={busy}
                    onClick={() => remove(doc.id)}
                    type="button"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
