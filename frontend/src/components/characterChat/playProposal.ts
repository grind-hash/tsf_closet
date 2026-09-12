import type {
  CharacterChatMessageMeta,
  CharacterChatPlayProposal,
  CharacterChatProposalInstructionType,
} from "../../apis/characterChat";

/** 提案の最初の指示に使える指示タイプ(画像のみは提案しない) */
const PROPOSAL_INSTRUCTION_TYPES: readonly CharacterChatProposalInstructionType[] =
  ["dress_up", "reality_alter", "action", "conversation"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function trimmedString(value: unknown): string | null {
  return typeof value === "string" ? value.trim() : null;
}

function isProposalInstructionType(
  value: unknown,
): value is CharacterChatProposalInstructionType {
  return (
    typeof value === "string" &&
    (PROPOSAL_INSTRUCTION_TYPES as readonly string[]).includes(value)
  );
}

/**
 * meta.play_proposal を表示できる提案へ正規化する。
 *
 * 種類が play 以外(後の版で増える adventure 等)のもの、必須項目が欠けたもの、
 * 型が違うものは null を返し、カードを出さない。理由(reason)だけは空でも通す。
 */
export function toPlayProposal(
  meta: CharacterChatMessageMeta | null | undefined,
): CharacterChatPlayProposal | null {
  const raw: unknown = meta?.play_proposal;
  if (!isRecord(raw) || raw.kind !== "play") return null;
  const { character, first_instruction: instruction } = raw;
  if (!isRecord(character) || !isRecord(instruction)) return null;
  if (typeof raw.self_mode !== "boolean") return null;
  const source = character.source;
  if (source !== "template" && source !== "custom") return null;
  const instructionType = instruction.instruction_type;
  if (!isProposalInstructionType(instructionType)) return null;

  const title = trimmedString(raw.title);
  const reason = trimmedString(raw.reason);
  const id = trimmedString(character.id);
  const name = trimmedString(character.name);
  const text = trimmedString(instruction.text);
  if (!title || reason === null || !id || !name || !text) return null;

  return {
    kind: "play",
    title,
    reason,
    character: { source, id, name },
    self_mode: raw.self_mode,
    first_instruction: { instruction_type: instructionType, text },
  };
}
