/**
 * Web Push: регистрация Service Worker + подписка через VAPID.
 *
 * Используется в кабинетах. Сначала спрашивает разрешение у пользователя.
 * При первом подключении сервер должен иметь VAPID_PUBLIC_KEY — иначе
 * 503 от /push/public-key, push выключен.
 */
import { api } from "./api";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const base64Std = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64Std);
  const buffer = new ArrayBuffer(raw.length);
  const arr = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i += 1) arr[i] = raw.charCodeAt(i);
  return arr;
}

export type PushStatus =
  | "unsupported"
  | "denied"
  | "default"
  | "granted-not-subscribed"
  | "subscribed"
  | "disabled-server";

export async function detectPushStatus(): Promise<PushStatus> {
  if (typeof window === "undefined") return "unsupported";
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return "unsupported";
  const perm = (typeof Notification !== "undefined" && Notification.permission) || "default";
  if (perm === "denied") return "denied";
  try {
    const info = await api.pushPublicKey();
    if (!info.enabled) return "disabled-server";
  } catch {
    return "disabled-server";
  }
  if (perm === "default") return "default";
  try {
    const registration = await navigator.serviceWorker.getRegistration("/sw.js");
    if (!registration) return "granted-not-subscribed";
    const existing = await registration.pushManager.getSubscription();
    return existing ? "subscribed" : "granted-not-subscribed";
  } catch {
    return "granted-not-subscribed";
  }
}

export async function ensureSubscribed(): Promise<PushStatus> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return "unsupported";

  const info = await api.pushPublicKey();
  if (!info.enabled || !info.public_key) return "disabled-server";

  // 1) запросить разрешение
  let perm = Notification.permission;
  if (perm === "default") {
    perm = await Notification.requestPermission();
  }
  if (perm === "denied") return "denied";

  // 2) зарегистрировать SW (если ещё нет)
  let registration = await navigator.serviceWorker.getRegistration("/sw.js");
  if (!registration) {
    registration = await navigator.serviceWorker.register("/sw.js");
  }
  await navigator.serviceWorker.ready;

  // 3) подписать
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(info.public_key) as BufferSource
    });
  }

  // 4) сохранить на сервере
  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    return "granted-not-subscribed";
  }
  await api.pushSubscribe({
    endpoint: json.endpoint,
    p256dh: json.keys.p256dh,
    auth: json.keys.auth
  });
  return "subscribed";
}

export async function unsubscribe(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  const registration = await navigator.serviceWorker.getRegistration("/sw.js");
  if (!registration) return;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;
  try {
    await api.pushUnsubscribe(subscription.endpoint);
  } catch {
    /* ignore */
  }
  await subscription.unsubscribe().catch(() => undefined);
}
