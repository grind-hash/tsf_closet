import { useEffect, useRef } from "react";
import type { AdventureRun } from "../apis/adventure";
import {
  partnerLines,
  stripStageDirections,
  stripTalkHeader,
} from "../utils/adventureDialogue";
import {
  linesToVoiceSegments,
  textToVoiceSegments,
  turnVoiceKey,
} from "../utils/adventureVoiceSegments";
import {
  type UseAdventureVoiceOptions,
  type UseAdventureVoiceResult,
  useAdventureVoice,
} from "./useAdventureVoice";

interface UseAdventureNarrationOptions extends UseAdventureVoiceOptions {
  activeRun: AdventureRun | null;
  streamingNarrative: string;
  narrativeSettled: boolean;
  pendingUserInput: string | null;
  /** 3D モデル表示中など、本文の確定行を先読みしてよい状況か */
  earlyVoiceAllowed: boolean;
}

/**
 * セリフ読み上げ（AivisSpeech）と、いつ何を読むかの判断。
 *
 * - 読み上げ(0): 先読みが許される場面では、本文ストリーム中の確定行を逐次読む
 * - 読み上げ(1): 新しい手番が届いたら攻略対象のセリフを読む（先読み済みは読まない）
 * - 読み上げ(2): トークの返答が確定したらその返答を読む
 */
export function useAdventureNarration({
  activeRun,
  streamingNarrative,
  narrativeSettled,
  pendingUserInput,
  earlyVoiceAllowed,
  ...voiceOptions
}: UseAdventureNarrationOptions): UseAdventureVoiceResult {
  const voice = useAdventureVoice(voiceOptions);
  const {
    canSpeak: voiceCanSpeak,
    speakSegments: voiceSpeakSegments,
    appendSegments: voiceAppendSegments,
  } = voice;

  // 読み上げ(0)で先読みした手番の控え。turn 到着時の読み上げ(1)が同じ手番を
  // 読み直さないための識別に使う(turn id は先読み時点で未確定なので手番番号)
  const earlySpokenRef = useRef<{ runId: string; turnNumber: number } | null>(
    null,
  );

  // 読み上げ(1): 新しい手番が届いたら攻略対象のセリフだけを読む。
  // 初回ロード・run 切替では読まない(その時点の最新手番を控えるだけ)
  const spokenTurnRef = useRef<{ runId: string; turnId: string | null } | null>(
    null,
  );
  useEffect(() => {
    if (!activeRun) return;
    const latest = activeRun.turns.at(-1) ?? null;
    const previous = spokenTurnRef.current;
    spokenTurnRef.current = { runId: activeRun.id, turnId: latest?.id ?? null };
    if (!previous || previous.runId !== activeRun.id) return;
    if (!latest || previous.turnId === latest.id) return;
    if (activeRun.preset !== "romance" || !voiceCanSpeak) return;
    const early = earlySpokenRef.current;
    if (
      early &&
      early.runId === activeRun.id &&
      early.turnNumber === latest.turn_number
    ) {
      return;
    }
    const name = activeRun.sim?.partner_name?.trim() ?? "";
    const groupKey = turnVoiceKey(activeRun.id, latest.turn_number);
    const segments = linesToVoiceSegments(
      partnerLines(latest.narrative, name),
      groupKey,
    );
    if (segments.length > 0) voiceSpeakSegments(segments, groupKey);
  }, [activeRun, voiceCanSpeak, voiceSpeakSegments]);

  // 読み上げ(2): トークの返答が確定したら、その返答を読む
  const spokenTalkRef = useRef<{
    runId: string;
    entryId: string | null;
  } | null>(null);
  useEffect(() => {
    if (!activeRun) return;
    const lastPartner =
      [...(activeRun.talk_log ?? [])]
        .reverse()
        .find((entry) => entry.role === "partner") ?? null;
    const previous = spokenTalkRef.current;
    spokenTalkRef.current = {
      runId: activeRun.id,
      entryId: lastPartner?.id ?? null,
    };
    if (!previous || previous.runId !== activeRun.id) return;
    if (!lastPartner || previous.entryId === lastPartner.id) return;
    if (!voiceCanSpeak) return;
    const text = stripStageDirections(stripTalkHeader(lastPartner.text));
    if (!text) return;
    const groupKey = `talk:${lastPartner.id}`;
    const segments = textToVoiceSegments(text, groupKey);
    if (segments.length > 0) voiceSpeakSegments(segments, groupKey);
  }, [activeRun, voiceCanSpeak, voiceSpeakSegments]);

  // 読み上げ(0): 本文のストリーム中から確定済みの行を逐次給餌して読み始める
  // (行は後続の改行が来た時点で内容確定、narrative_done で全文確定)。
  // 同じ確定行を毎チャンク渡しても appendSegments の重複判定で一度だけ読まれる。
  // 判定と保存を待たずに喋り始めるため、turn 到着時の読み上げ(1)は控えを見て
  // 同じ手番を読まない。控えはストリーム終了(pendingUserInput=null)で必ず消す
  // (巻き戻し後に同じ番号の手番を作り直しても読めるようにする)
  const earlyVoice = earlyVoiceAllowed && voiceCanSpeak;
  useEffect(() => {
    if (pendingUserInput === null) {
      earlySpokenRef.current = null;
      return;
    }
    if (!activeRun || !earlyVoice) return;
    const settledText = narrativeSettled
      ? streamingNarrative
      : streamingNarrative.slice(0, streamingNarrative.lastIndexOf("\n") + 1);
    if (!settledText) return;
    const name = activeRun.sim?.partner_name?.trim() ?? "";
    const lines = partnerLines(settledText, name);
    if (lines.length === 0) return;
    const turnNumber = activeRun.turn_count + 1;
    const groupKey = turnVoiceKey(activeRun.id, turnNumber);
    earlySpokenRef.current = { runId: activeRun.id, turnNumber };
    voiceAppendSegments(linesToVoiceSegments(lines, groupKey), groupKey);
  }, [
    narrativeSettled,
    streamingNarrative,
    pendingUserInput,
    activeRun,
    earlyVoice,
    voiceAppendSegments,
  ]);

  return voice;
}
