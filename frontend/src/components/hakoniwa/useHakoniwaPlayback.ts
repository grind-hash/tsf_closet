import { useCallback, useEffect, useRef, useState } from "react";
import type { HakoniwaEvent, HakoniwaLine } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";

/** 再生に使う部屋ステージの操作 */
export interface PlaybackStage {
  focusGroup: (ids: string[]) => Promise<boolean>;
  releaseFocus: () => void;
  setInvolved: (ids: string[]) => void;
}

export interface HakoniwaPlayback {
  event: HakoniwaEvent | null;
  /** 今出している台詞(地の文だけの幕では null) */
  line: HakoniwaLine | null;
  /** 何件目の出来事か(1 から)と、まとめて再生する件数 */
  position: number;
  total: number;
  advance: () => void;
  skipAll: () => void;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    tag === "BUTTON" ||
    target.isContentEditable
  );
}

/**
 * 待ち行列の先頭の出来事を部屋で再生する。自動では進まず、クリック・Enter・Space で
 * 1幕ずつ送る(最初の幕は地の文、続いて台詞を1つずつ)。Esc とスキップで残りをすべて飛ばす。
 */
export function useHakoniwaPlayback(
  stage: PlaybackStage | null,
): HakoniwaPlayback {
  const { playbackQueue, finishPlayback, clearPlayback } = useHakoniwa();
  const event = playbackQueue[0] ?? null;
  const [cursor, setCursor] = useState<{ id: string | null; step: number }>({
    id: null,
    step: 0,
  });
  const step = cursor.id === event?.id ? cursor.step : 0;
  const [total, setTotal] = useState(0);
  const previousLength = useRef(0);

  // まとめて積まれた件数を数え、空になったら数え直す
  useEffect(() => {
    const length = playbackQueue.length;
    if (length === 0) {
      setTotal(0);
    } else if (length > previousLength.current) {
      const added = length - previousLength.current;
      setTotal((current) => current + added);
    }
    previousLength.current = length;
  }, [playbackQueue.length]);

  const eventId = event?.id ?? null;
  const participantsKey = event?.participants.join(",") ?? "";
  useEffect(() => {
    if (!stage || !eventId) return;
    const ids = participantsKey ? participantsKey.split(",") : [];
    stage.setInvolved(ids);
    void stage.focusGroup(ids);
  }, [stage, eventId, participantsKey]);

  const release = useCallback(() => {
    stage?.releaseFocus();
    stage?.setInvolved([]);
  }, [stage]);

  const advance = useCallback(() => {
    if (!event) return;
    if (step < event.lines.length) {
      setCursor({ id: event.id, step: step + 1 });
      return;
    }
    release();
    finishPlayback();
  }, [event, finishPlayback, release, step]);

  const skipAll = useCallback(() => {
    release();
    clearPlayback();
  }, [clearPlayback, release]);

  useEffect(() => {
    if (!event) return;
    const onKeyDown = (keyEvent: KeyboardEvent) => {
      if (keyEvent.key === "Escape") {
        keyEvent.preventDefault();
        skipAll();
        return;
      }
      if (
        (keyEvent.key === "Enter" || keyEvent.key === " ") &&
        !isTypingTarget(keyEvent.target)
      ) {
        keyEvent.preventDefault();
        advance();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [advance, event, skipAll]);

  const line = event && step > 0 ? (event.lines[step - 1] ?? null) : null;
  const position = event ? Math.max(1, total - playbackQueue.length + 1) : 0;
  return {
    event,
    line,
    position,
    total: Math.max(total, playbackQueue.length),
    advance,
    skipAll,
  };
}
