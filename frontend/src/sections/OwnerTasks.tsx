/**
 * Поручения в кабинете собственника.
 *
 * Открытые сверху, закрытые ниже и приглушённо: список задач нужен, чтобы
 * увидеть, что осталось, а не чтобы любоваться сделанным. Совсем прятать
 * закрытые тоже нельзя — иначе непонятно, зачем приходило уведомление.
 */
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { OwnerTask } from "../types";
import { ListEmpty, ListError, ListLoading } from "../ui/ListState";

function dueText(task: OwnerTask): string | null {
  if (task.days_until_due === null) return null;
  const days = task.days_until_due;
  if (days < 0) {
    const overdue = -days;
    return overdue === 1 ? "просрочено на день" : `просрочено на ${overdue} дн.`;
  }
  if (days === 0) return "сегодня";
  if (days === 1) return "завтра";
  return `через ${days} дн.`;
}

export function OwnerTasks({ onChanged }: { onChanged?: () => void }) {
  const [tasks, setTasks] = useState<OwnerTask[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function reload() {
    setError(null);
    api
      .ownerTasks()
      .then(setTasks)
      .catch((err) => setError((err as Error).message));
  }

  useEffect(reload, []);

  async function complete(taskId: string) {
    setBusyId(taskId);
    try {
      await api.completeOwnerTask(taskId);
      reload();
      onChanged?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ListError message={error} onRetry={reload} />;
  if (tasks === null) return <ListLoading rows={3} />;
  if (tasks.length === 0) {
    return (
      <ListEmpty
        title="Поручений нет"
        text="Здесь появятся задачи от площадки — например, обновить фото или выписку."
      />
    );
  }

  return (
    <ul className="owner-tasks">
      {tasks.map((task) => {
        const closed = task.status !== "open";
        const due = dueText(task);
        const overdue = (task.days_until_due ?? 0) < 0;
        return (
          <li className={closed ? "owner-task is-closed" : "owner-task"} key={task.id}>
            <span className="owner-task__mark" aria-hidden="true">
              {task.status === "done" ? (
                <CheckCircle2 size={18} />
              ) : task.status === "cancelled" ? (
                <XCircle size={18} />
              ) : (
                <Circle size={18} />
              )}
            </span>

            <div className="owner-task__main">
              <strong>{task.title}</strong>
              {task.description ? <p>{task.description}</p> : null}
              <span className="owner-task__meta">
                {task.address_label || "По организации"}
                {task.status === "cancelled" ? " · отменено площадкой" : ""}
              </span>
            </div>

            {due ? (
              <span className={overdue ? "owner-task__due is-overdue" : "owner-task__due"}>
                {due}
              </span>
            ) : null}

            {!closed ? (
              <button
                className="cab-btn cab-btn--sm"
                disabled={busyId === task.id}
                onClick={() => complete(task.id)}
                type="button"
              >
                {busyId === task.id ? <Loader2 className="spin" size={14} /> : null} Готово
              </button>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
