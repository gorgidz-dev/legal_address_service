/**
 * Маленькая кнопка-тоггл Web Push, ставится в topbar кабинета.
 *
 * Состояния:
 * - "unsupported" / "disabled-server" → не показываем.
 * - "denied" → текст "Push заблокирован браузером" (надо в настройки).
 * - "default" / "granted-not-subscribed" → кнопка "Включить push".
 * - "subscribed" → кнопка "Отключить push".
 */
import { useEffect, useState } from "react";
import { Bell, BellOff, Loader2 } from "lucide-react";
import { detectPushStatus, ensureSubscribed, unsubscribe, type PushStatus } from "./webPush";

export function PushToggle() {
  const [status, setStatus] = useState<PushStatus | "loading">("loading");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    detectPushStatus().then((s) => {
      if (alive) setStatus(s);
    });
    return () => {
      alive = false;
    };
  }, []);

  if (status === "loading") {
    return null;
  }
  if (status === "unsupported" || status === "disabled-server") {
    return null;
  }
  if (status === "denied") {
    return (
      <button
        type="button"
        className="ds-btn ds-btn--ghost ds-btn--sm"
        disabled
        title="Push заблокирован в настройках браузера"
      >
        <BellOff size={14} /> Push заблокирован
      </button>
    );
  }

  const isOn = status === "subscribed";
  return (
    <button
      type="button"
      className="ds-btn ds-btn--ghost ds-btn--sm"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          if (isOn) {
            await unsubscribe();
            setStatus("granted-not-subscribed");
          } else {
            const next = await ensureSubscribed();
            setStatus(next);
          }
        } finally {
          setBusy(false);
        }
      }}
      title={isOn ? "Отключить push-уведомления" : "Получать push-уведомления"}
    >
      {busy ? <Loader2 size={14} className="spin" /> : isOn ? <Bell size={14} /> : <BellOff size={14} />}
      {isOn ? "Push включён" : "Включить push"}
    </button>
  );
}
