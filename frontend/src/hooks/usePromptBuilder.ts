import { useCallback, useEffect, useMemo, useState } from "react";
import { readStorage, writeStorage } from "../utils/storage";

export const PROMPT_BUILDER_STORAGE_KEY = "prompt_builder";

export type PromptBuilderMode = "fields" | "textarea";

export interface PromptBuilderFields {
  who: string;
  location: string;
  outfit: string;
  target: string;
  action: string;
}

const EMPTY_FIELDS: PromptBuilderFields = {
  who: "",
  location: "",
  outfit: "",
  target: "",
  action: "",
};

/** 「誰が・どの衣装で・どこで・何を・どうする」を句読点で繋いだ指示文にする */
export function composePromptBuilderText(fields: PromptBuilderFields): string {
  const who = fields.who.trim();
  const outfit = fields.outfit.trim();
  const location = fields.location.trim();
  const target = fields.target.trim();
  const action = fields.action.trim();
  const parts: string[] = [];
  if (who) parts.push(who);
  if (outfit) parts.push(`${outfit}で`);
  if (location) parts.push(`${location}にて`);
  if (target) parts.push(`${target}を`);
  if (action) parts.push(action);
  return parts.join("、");
}

/**
 * 右パネルのプロンプトビルダー。入力欄の値と入力方式(項目 / 自由入力)を
 * localStorage `prompt_builder` に保存し、次回も同じ内容から始める。
 */
export function usePromptBuilder() {
  const saved = useMemo(() => {
    try {
      const raw = readStorage("local", PROMPT_BUILDER_STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }, []);
  const [mode, setMode] = useState<PromptBuilderMode>(
    saved.mode === "textarea" ? "textarea" : "fields",
  );
  const [fields, setFields] = useState<PromptBuilderFields>({
    who: saved.who ?? "",
    location: saved.location ?? "",
    outfit: saved.outfit ?? "",
    target: saved.target ?? "",
    action: saved.action ?? "",
  });
  const [freeform, setFreeform] = useState<string>(saved.freeform ?? "");

  // Save prompt builder state to localStorage
  useEffect(() => {
    try {
      writeStorage(
        "local",
        PROMPT_BUILDER_STORAGE_KEY,
        JSON.stringify({ mode, ...fields, freeform }),
      );
    } catch {
      /* ignore */
    }
  }, [mode, fields, freeform]);

  const setField = useCallback(
    (key: keyof PromptBuilderFields, value: string) => {
      setFields((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );
  const toggleMode = useCallback(() => {
    setMode((prev) => (prev === "fields" ? "textarea" : "fields"));
  }, []);
  const reset = useCallback(() => {
    setFields(EMPTY_FIELDS);
    setFreeform("");
  }, []);

  return { mode, toggleMode, fields, setField, freeform, setFreeform, reset };
}
