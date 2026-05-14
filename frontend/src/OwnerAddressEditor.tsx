/**
 * Модалка собственника: редактировать описание адреса + прайс доп.услуг.
 *
 * Использует owner-эндпоинты:
 * - PATCH /api/v1/owner/addresses/{id}/description
 * - GET/PUT/DELETE /api/v1/owner/addresses/{id}/services/{kind}
 */
import { FormEvent, useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { api } from "./api";
import type { AddressServiceAdmin } from "./types";

type Props = {
  addressId: string;
  addressLabel: string;
  initialDescription: string | null;
  onClose: () => void;
  onSaved?: () => void;
};

const SERVICE_CATALOG: Array<{ kind: string; label: string; group: "doc" | "extra" }> = [
  { kind: "guarantee_letter", label: "Гарантийное письмо", group: "doc" },
  { kind: "lease_agreement", label: "Договор аренды", group: "doc" },
  { kind: "owner_confirmation", label: "Подтверждение собственника", group: "doc" },
  { kind: "door_sign", label: "Табличка на входе", group: "extra" },
  { kind: "mail_reception", label: "Приём почты", group: "extra" },
  { kind: "fns_visit_photo", label: "Фотофиксация приёма ФНС", group: "extra" },
  { kind: "phone_answering", label: "Звонки", group: "extra" },
  { kind: "visitor_reception", label: "Приём посетителей", group: "extra" }
];

type Draft = { price: string; is_active: boolean; busy: boolean; err: string | null };

export function OwnerAddressEditor({
  addressId,
  addressLabel,
  initialDescription,
  onClose,
  onSaved
}: Props) {
  // --- Описание ---
  const [description, setDescription] = useState(initialDescription || "");
  const [descBusy, setDescBusy] = useState(false);
  const [descSaved, setDescSaved] = useState(false);
  const [descError, setDescError] = useState<string | null>(null);

  // --- Услуги ---
  const [services, setServices] = useState<AddressServiceAdmin[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [servicesLoading, setServicesLoading] = useState(true);
  const [servicesError, setServicesError] = useState<string | null>(null);

  useEffect(() => {
    setServicesLoading(true);
    setServicesError(null);
    api
      .ownerListAddressServices(addressId)
      .then((rows) => {
        setServices(rows);
        const next: Record<string, Draft> = {};
        for (const c of SERVICE_CATALOG) {
          const existing = rows.find((s) => s.kind === c.kind);
          next[c.kind] = {
            price: existing ? String(existing.price) : "",
            is_active: existing ? existing.is_active : false,
            busy: false,
            err: null
          };
        }
        setDrafts(next);
      })
      .catch((err: Error) => setServicesError(err.message))
      .finally(() => setServicesLoading(false));
  }, [addressId]);

  async function saveDescription(event: FormEvent) {
    event.preventDefault();
    setDescBusy(true);
    setDescError(null);
    setDescSaved(false);
    try {
      await api.ownerUpdateAddressDescription(addressId, description.trim() || null);
      setDescSaved(true);
      onSaved?.();
    } catch (err) {
      setDescError((err as Error).message);
    } finally {
      setDescBusy(false);
    }
  }

  async function saveService(kind: string) {
    const draft = drafts[kind];
    if (!draft) return;
    const priceNum = Number(draft.price);
    if (!Number.isFinite(priceNum) || priceNum < 0) {
      setDrafts((prev) => ({ ...prev, [kind]: { ...draft, err: "Цена должна быть числом ≥ 0" } }));
      return;
    }
    setDrafts((prev) => ({ ...prev, [kind]: { ...draft, busy: true, err: null } }));
    try {
      const updated = await api.ownerUpsertAddressService(addressId, kind, {
        price: priceNum.toFixed(2),
        is_active: draft.is_active
      });
      setServices((prev) => [...prev.filter((s) => s.kind !== kind), updated]);
      setDrafts((prev) => ({
        ...prev,
        [kind]: { price: String(updated.price), is_active: updated.is_active, busy: false, err: null }
      }));
    } catch (err) {
      setDrafts((prev) => ({ ...prev, [kind]: { ...draft, busy: false, err: (err as Error).message } }));
    }
  }

  async function removeService(kind: string) {
    if (!window.confirm("Убрать услугу с этого адреса?")) return;
    try {
      await api.ownerDeleteAddressService(addressId, kind);
      setServices((prev) => prev.filter((s) => s.kind !== kind));
      setDrafts((prev) => ({
        ...prev,
        [kind]: { price: "", is_active: false, busy: false, err: null }
      }));
    } catch (err) {
      setServicesError((err as Error).message);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-panel"
        style={{ maxWidth: 760, width: "100%" }}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <div>
            <span className="eyebrow">Адрес</span>
            <h2>{addressLabel}</h2>
          </div>
          <button className="text-action" type="button" onClick={onClose}>
            <X size={16} /> Закрыть
          </button>
        </header>

        <form onSubmit={saveDescription} className="owner-editor__section">
          <label className="field">
            <span>Описание адреса (видно клиентам)</span>
            <textarea
              rows={6}
              value={description}
              maxLength={4000}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Опишите БЦ, удобства, варианты прохода, услуги ресепшен…"
            />
          </label>
          {descError && <div className="ds-input-error-text">{descError}</div>}
          {descSaved && <div className="success-note">Описание сохранено</div>}
          <div className="row-actions" style={{ display: "flex", justifyContent: "flex-end" }}>
            <button type="submit" className="ds-btn ds-btn--primary ds-btn--sm" disabled={descBusy}>
              {descBusy ? <Loader2 size={14} className="spin" /> : null}
              Сохранить описание
            </button>
          </div>
        </form>

        <div className="owner-editor__section">
          <h3 style={{ margin: 0, fontSize: 14 }}>Доп. услуги и прайс</h3>
          {servicesError && <div className="ds-input-error-text">{servicesError}</div>}
          {servicesLoading ? (
            <div className="hint">Загружаем…</div>
          ) : (
            (["doc", "extra"] as const).map((group) => (
              <div key={group} className="owner-editor__group">
                <h4>{group === "doc" ? "Входит в стоимость" : "Дополнительные услуги"}</h4>
                <div className="owner-editor__rows">
                  {SERVICE_CATALOG.filter((c) => c.group === group).map((cat) => {
                    const draft = drafts[cat.kind];
                    if (!draft) return null;
                    const existing = services.find((s) => s.kind === cat.kind);
                    return (
                      <div key={cat.kind} className="owner-editor__row">
                        <div className="owner-editor__row-lbl">
                          <strong>{cat.label}</strong>
                          <span className="hint">{cat.kind}</span>
                        </div>
                        <label className="owner-editor__row-price">
                          <span>Цена, ₽</span>
                          <input
                            type="number"
                            min={0}
                            step={100}
                            value={draft.price}
                            placeholder={group === "doc" ? "0 (входит)" : "0"}
                            onChange={(e) =>
                              setDrafts((prev) => ({
                                ...prev,
                                [cat.kind]: { ...draft, price: e.target.value }
                              }))
                            }
                          />
                        </label>
                        <label className="owner-editor__row-active">
                          <input
                            type="checkbox"
                            checked={draft.is_active}
                            onChange={(e) =>
                              setDrafts((prev) => ({
                                ...prev,
                                [cat.kind]: { ...draft, is_active: e.target.checked }
                              }))
                            }
                          />
                          <span>Активна</span>
                        </label>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="ds-btn ds-btn--secondary ds-btn--sm"
                            disabled={draft.busy}
                            onClick={() => saveService(cat.kind)}
                          >
                            {draft.busy ? "…" : existing ? "Сохр." : "Добавить"}
                          </button>
                          {existing && (
                            <button
                              type="button"
                              className="ds-btn ds-btn--ghost ds-btn--sm"
                              onClick={() => removeService(cat.kind)}
                            >
                              Убрать
                            </button>
                          )}
                        </div>
                        {draft.err && (
                          <div className="ds-input-error-text" style={{ gridColumn: "1 / -1" }}>
                            {draft.err}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
