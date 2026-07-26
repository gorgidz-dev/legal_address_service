/**
 * Общее поведение для модальных окон: Escape закрывает, фон не прокручивается.
 *
 * До этого Escape обрабатывала только карта адреса, а фон под модалкой
 * прокручивался — на телефоне это выглядело как «страница уехала».
 */
import { useEffect, useRef } from "react";

/**
 * Стек открытых модалок. Escape должен закрывать только верхнюю: иначе одно
 * нажатие схлопывает и форму заявки, и карточку адреса под ней.
 */
const openModals: symbol[] = [];

/**
 * @param onClose null — только блокировка прокрутки, без Escape. Так сделано
 *   для модалок с формами: случайный Escape стёр бы заполненную заявку.
 */
export function useModalDismiss(open: boolean, onClose: (() => void) | null): void {
  // Через ref, чтобы новая ссылка на onClose при каждом рендере не переподписывала
  // слушатель и не ломала сохранённое значение overflow.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;

    const token = Symbol("modal");
    openModals.push(token);

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (openModals[openModals.length - 1] !== token) return;
      const close = closeRef.current;
      if (!close) return;
      event.stopPropagation();
      close();
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      const index = openModals.indexOf(token);
      if (index !== -1) openModals.splice(index, 1);
      // Скролл возвращаем только когда закрылась последняя модалка — иначе
      // закрытие вложенной разблокирует фон под всё ещё открытой родительской.
      if (openModals.length === 0) document.body.style.overflow = previousOverflow;
    };
  }, [open]);
}
