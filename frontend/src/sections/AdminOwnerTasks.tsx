/**
 * Поручения собственникам — сторона оператора.
 *
 * Живёт в разделе «Собственники»: задача всегда адресована организации, и
 * ставить её логично там же, где на эту организацию смотрят.
 *
 * Заготовки нужны не для красоты: «загрузить фото» и «обновить выписку» —
 * это 90% поручений, и набирать их руками каждый раз оператор перестанет
 * через неделю.
 */
import { Loader2, Plus, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { OwnerTask, OwnerTaskTemplate, Provider } from "../types";
import { ListEmpty, ListError, ListLoading } from "../ui/ListState";

export function AdminOwnerTasks({ providers }: { providers: Provider[] }) {
  const [tasks, setTasks] = useState<OwnerTask[] | null>(null);
  const [templates, setTemplates] = useState<OwnerTaskTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [providerId, setProviderId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueOn, setDueOn] = useState("");

  function reload() {
    setError(null);
    api
      .staffOwnerTasks()
      .then(setTasks)
      .catch((err) => setError((err as Error).message));
  }

  useEffect(() => {
    reload();
    api.ownerTaskTemplates().then(setTemplates).catch(() => {
      // Заготовки — удобство, а не условие работы: форму можно заполнить руками.
    });
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!providerId) {
      setError("Выберите собственника");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createOwnerTask({
        provider_id: providerId,
        title,
        description: description || null,
        due_on: dueOn || null
      });
      setTitle("");
      setDescription("");
      setDueOn("");
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function cancel(taskId: string) {
    setBusy(true);
    try {
      await api.cancelOwnerTask(taskId);
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const providerName = (id: string) =>
    providers.find((provider) => provider.id === id)?.short_name || "Собственник";

  return (
    <div className="admin-tasks">
      <div className="timeline-title">
        <Plus size={18} />
        <strong>Поручения собственникам</strong>
      </div>

      {error ? <ListError message={error} /> : null}

      <form className="admin-tasks__form" onSubmit={submit}>
        <label className="field">
          <span>Собственник</span>
          <select onChange={(e) => setProviderId(e.target.value)} value={providerId}>
            <option value="">— выберите —</option>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.short_name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Что нужно сделать</span>
          <input onChange={(e) => setTitle(e.target.value)} required value={title} />
        </label>
        <label className="field">
          <span>Срок</span>
          <input onChange={(e) => setDueOn(e.target.value)} type="date" value={dueOn} />
        </label>
        <label className="field admin-tasks__wide">
          <span>Пояснение</span>
          <textarea onChange={(e) => setDescription(e.target.value)} rows={2} value={description} />
        </label>

        {templates.length ? (
          <div className="admin-tasks__templates">
            {templates.map((template) => (
              <button
                className="cab-chip"
                key={template.title}
                onClick={() => {
                  setTitle(template.title);
                  setDescription(template.description);
                }}
                type="button"
              >
                {template.title}
              </button>
            ))}
          </div>
        ) : null}

        <button className="cab-btn cab-btn--primary" disabled={busy} type="submit">
          {busy ? <Loader2 className="spin" size={15} /> : <Plus size={15} />} Поставить
        </button>
      </form>

      {tasks === null ? (
        <ListLoading rows={2} />
      ) : tasks.length === 0 ? (
        <ListEmpty title="Поручений нет" text="Поставьте первое через форму выше." />
      ) : (
        <ul className="owner-tasks">
          {tasks.map((task) => (
            <li className={task.status === "open" ? "owner-task" : "owner-task is-closed"} key={task.id}>
              <div className="owner-task__main">
                <strong>{task.title}</strong>
                <span className="owner-task__meta">
                  {providerName(task.provider_id)}
                  {task.address_label ? ` · ${task.address_label}` : ""}
                  {task.status === "done" ? " · выполнено" : ""}
                  {task.status === "cancelled" ? " · отменено" : ""}
                </span>
              </div>
              {task.days_until_due !== null ? (
                <span
                  className={
                    task.days_until_due < 0 ? "owner-task__due is-overdue" : "owner-task__due"
                  }
                >
                  {task.days_until_due < 0
                    ? `просрочено на ${-task.days_until_due} дн.`
                    : `${task.days_until_due} дн.`}
                </span>
              ) : null}
              {task.status === "open" ? (
                <button
                  className="text-action"
                  disabled={busy}
                  onClick={() => cancel(task.id)}
                  type="button"
                >
                  <XCircle size={15} /> Отменить
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
