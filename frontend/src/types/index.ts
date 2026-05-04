/**
 * TypeScript type definitions for TSF Game.
 * Uses original parameter names (bloom, shame, adaptation).
 */

// Session statistics with original parameter names
export interface SessionStats {
  bloom: number; // 開花度
  shame: number; // 羞恥心
  adaptation: number; // 順応度
  passedCriticalPoints: number[];
  difficulty: string;
  nsfwMode: boolean; // NSFWモード
  enablePromptPreview: boolean; // プロンプト確認
}

// History item
export interface HistoryItem {
  id: string;
  instruction: string;
  imageUrl: string;
  feelingText: string;
  beforeDescription: string;
  afterDescription: string;
  timestamp: string;
  instructionType?: string;
  costumeCategory?: string;
  exposureLevel?: string; // exposure_level を維持
  ageImpression?: string;
  relatedMessageId?: string; // 007: 関連するチャットメッセージID
  seed?: number;
  surroundingsImageUrl?: string;
}

// Character
export interface Character {
  id: string;
  name: string;
  thumbnail: string;
  description: string;
}

// Ending
export interface Ending {
  id: string;
  name: string;
  description: string;
  triggerCondition: string;
  badge: string;
  speech: string;
  summary?: string;
}

// Difficulty preset
export interface DifficultyPreset {
  id: string;
  name: string;
  description: string;
}

// NovelAI Subscription response from backend API
export interface NovelAISubscriptionResponse {
  tier: number; // 0: Free, 1: Tablet, 2: Scroll, 3: Opus
  active: boolean; // サブスクリプションがアクティブか
  expires_at?: string; // 有効期限 (ISO 8601)
}

// NovelAI Subscription state in frontend
export interface NovelAISubscriptionState {
  tier: number | null; // nullは未取得
  isOpus: boolean; // tier === 3
  warningDismissed: boolean; // 警告を無視して続行を選択
  checkFailed: boolean; // API呼び出し失敗
}

// NovelAI タグサジェスト (006-novelai-prompt-enhancement)
export interface TagSuggestion {
  tag: string; // タグ文字列 (例: tifa_lockhart)
  count?: number; // 関連度/出現数スコア (optional)
}

export interface TagSuggestResponse {
  tags: TagSuggestion[]; // タグ候補リスト
  query?: string; // 元のクエリ (デバッグ用)
}

// localStorage保存用のInpaintSettings (永続化対象フィールドのみ)
export interface StoredInpaintSettings {
  promptOverride: string; // 直接プロンプト
  negativePrompt: string; // ネガティブプロンプト
  i2iStrength: number; // i2i強度 (0.05-0.99)
  maskStrength: number; // マスク強度 (0.05-1.0)
  inpaintNoise: number; // ノイズ (0-0.5)
}

// SSE event types
export type SSEEventType =
  | "text"
  | "image"
  | "stats"
  | "critical"
  | "ending"
  | "complete"
  | "cost"
  | "error"
  | "surroundings_image"
  | "anlas";

// SSE stats data
export interface SSEStatsData {
  bloom: number;
  shame: number;
  adaptation: number;
}

// SSE ending data (バックエンドのフィールド名に合わせる)
export interface SSEEndingData {
  ending_id: string;
  title: string; // バックエンドはtitleを送信
  description: string;
  badge: string;
  final_speech: string; // バックエンドはfinal_speechを送信
  summary?: string;
  is_new?: boolean;
}

// SSE critical point data
export interface SSECriticalData {
  threshold: number;
  name: string;
  effect_type: string;
  speech: string;
}

// SSE achievement data (007-chat-interactive-ux)
export interface SSEAchievementData {
  achievement_id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
}

// API response types
export interface SessionResponse {
  session_id: string;
  character_id: string | null;
  current_image_url: string;
  transformation_count: number;
  history: HistoryItem[];
  stats: SessionStats | null;
  created_at: string;
  updated_at: string;
  // 復帰用データ
  attributes: SessionAttribute[];
  conversation_history: ConversationMessage[];
}

export interface CharactersResponse {
  characters: Character[];
}

export interface StartSessionRequest {
  character_id?: string;
  difficulty?: string;
  nsfw_mode?: boolean;
}

export interface StartCustomSessionRequest {
  image: string; // Base64 encoded image
  difficulty?: string;
  nsfw_mode?: boolean;
}

// Conversation message
export interface ConversationMessage {
  id: string;
  role: "user" | "character";
  content: string;
  createdAt: string;
  instruction_type?: string | null;
}

// Session attribute
export interface SessionAttribute {
  id: string;
  text: string;
}

// Session summary (for list view)
export interface SessionSummary {
  sessionId: string;
  characterId: string | null;
  characterName: string | null;
  thumbnailUrl: string | null;
  transformationCount: number;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  lastInstruction: string | null;
}

// Session list response
export interface SessionListResponse {
  sessions: SessionSummary[];
  totalCount: number;
}

// Mask info (NovelAI専用)
export interface MaskInfo {
  id: string;
  name: string;
  type: "system" | "history" | "preset";
  url: string;
  created_at?: string; // バックエンドの命名規則に合わせる
}

// Mask list response (NovelAI専用)
export interface MaskListResponse {
  system: MaskInfo[];
  history: MaskInfo[];
  presets: MaskInfo[];
}

// Mask preset (NovelAI専用)
export interface MaskPreset {
  id: string;
  name: string;
  type: "preset";
  url: string;
  created_at: string;
}

// Attribute preset (localStorage保存用)
export interface AttributePreset {
  id: string;
  name: string;
  attributes: string[];
  createdAt: string;
}

// Inpaint settings (モーダル内で管理)
export interface InpaintSettings {
  enabled: boolean; // インペイント有効
  brushSize: number; // ブラシサイズ (4-96)
  eraserMode: boolean; // 消しゴムモード
  i2iStrength: number; // i2i強度 (0.05-0.99)
  maskStrength: number; // マスク強度 (0.05-1.0)
  inpaintNoise: number; // ノイズ (0-0.5)
  invertMask: boolean; // マスク反転
  negativePrompt: string; // ネガティブプロンプト
  promptOverride: string; // 直接プロンプト
}

export interface InpaintMaskState {
  maskDataUrl: string | null;
  selectedMaskId: string | null;
}

export interface SurroundingsImageState {
  imageBase64: string;
  historyId: string;
  seed?: number;
}

// Default inpaint settings
export const DEFAULT_INPAINT_SETTINGS: InpaintSettings = {
  enabled: false,
  brushSize: 32,
  eraserMode: false,
  i2iStrength: 0.9,
  maskStrength: 1.0,
  inpaintNoise: 0.0,
  invertMask: false,
  negativePrompt: "",
  promptOverride: "",
};

export const DEFAULT_INPAINT_MASK_STATE: InpaintMaskState = {
  maskDataUrl: null,
  selectedMaskId: null,
};

// ========================================
// Change Scope Control Types
// ========================================

// Preserve element options
export type PreserveElement =
  | "background"
  | "hairstyle"
  | "pose"
  | "expression"
  | "accessories";

// Change scope options
export type ChangeScope = "full" | "upper" | "lower" | "accessories" | "shoes";

// Change settings for a session
export interface ChangeSettings {
  preserveElements: PreserveElement[];
  changeScope: ChangeScope;
  customPreserveText: string;
}

// Global preset for change settings
export interface GlobalPreset {
  id: string;
  name: string;
  settings: ChangeSettings;
  createdAt: string;
}

// Default change settings
export const DEFAULT_CHANGE_SETTINGS: ChangeSettings = {
  preserveElements: [],
  changeScope: "full",
  customPreserveText: "",
};

// =============================================================================
// 007-chat-interactive-ux: 新規型定義
// =============================================================================

/**
 * 指示タイプ (着せ替え/現実改変/会話)
 */
export type InstructionType =
  | "dress_up"
  | "reality_alter"
  | "conversation"
  | "action";

/**
 * 指示タイプのラベル (日本語)
 */
export const INSTRUCTION_TYPE_LABELS: Record<InstructionType, string> = {
  dress_up: "着せ替え",
  reality_alter: "現実改変",
  conversation: "会話",
  action: "行動",
};

/**
 * 実績定義
 */
export interface Achievement {
  id: string;
  name: string;
  description: string;
  category: string; // transform, crossdress, reality, collection
  icon: string;
  condition_type: string; // count, specific, threshold
  condition_target: string;
  condition_value: number;
  is_hidden: boolean;
  hint?: string | null; // 未開放時のヒントテキスト
}

/**
 * ユーザー実績達成状態
 */
export interface UserAchievementStatus {
  achievement_id: string;
  achieved_at: string | null; // 達成日時（ISO 8601）、未達成はnull
  progress: number; // 現在の進捗値
  is_achieved: boolean;
}

/**
 * ギャラリーアイテム
 * 履歴から派生したギャラリー表示用データ
 * バックエンドAPIに合わせてスネークケースを使用
 */
export interface GalleryItem {
  id: string;
  session_id: string;
  image_url: string;
  instruction: string;
  feeling_text: string | null;
  before_description: string | null;
  after_description: string | null;
  timestamp: string;
  costume_category: string | null;
  exposure_level: string | null;
}

/**
 * ギャラリーセッション
 * セッション毎にグループ化されたギャラリー表示用データ
 */
export interface GallerySession {
  session_id: string;
  character_name: string | null;
  thumbnail_url: string;
  item_count: number;
  first_timestamp: string;
  last_timestamp: string;
  self_mode?: boolean;
  has_summary?: boolean;
}

/**
 * ギャラリーの表示モード
 */
export type GalleryViewMode = "card" | "list";

/**
 * 精密参照画像の参照種類
 */
export type PreciseReferenceType = "character" | "style" | "character&style";

/**
 * 精密参照画像（NovelAI Character Reference）
 * セッション内の一時状態として管理され、永続化しない
 */
export interface PreciseReference {
  id: string;
  imageData: string;
  fileName: string;
  type: PreciseReferenceType;
  strength: number;
  fidelity: number;
  enabled: boolean;
}

/**
 * チャットメッセージ
 * フロントエンドでのチャット表示用データ
 */
export interface ChatMessage {
  id: string;
  sessionId: string;
  role: "user" | "system" | "character";
  content: string;
  createdAt: string;
  instructionType?: InstructionType;
  attachedImageUrl?: string;
  relatedHistoryId?: string;
  /** バックエンド会話レコードのID */
  conversationId?: string;
  pendingToken?: string;
  isStreaming?: boolean;
  /** 心境テキストメッセージかどうか */
  isFeelingText?: boolean;
  surroundingsImageUrl?: string;
  seed?: number;
}

export type PendingMessageStatus =
  | "pending"
  | "resolvable"
  | "resolved"
  | "failed";

export interface PendingMessageIdentity {
  tempToken: string;
  userMessageId: string;
  feelingMessageId: string | null;
  resolvedHistoryId: string | null;
  status: PendingMessageStatus;
}

// Anlas balance information
export interface AnlasBalance {
  fixedAnlas: number;
  purchasedAnlas: number;
  totalAnlas: number;
}

// Surroundings image SSE event data
export interface SurroundingsImageEvent {
  image: string;
  historyId: string;
}

// =============================================================================
// Multi-character persistence (spec 005)
// =============================================================================

export type CharacterPosition =
  | "left"
  | "center-left"
  | "center"
  | "center-right"
  | "right";

// Note: AGENTS.md naming exception - backend returns snake_case fields,
// so the frontend types follow snake_case as well for direct mapping.
export interface SessionCharacter {
  id: string;
  session_id: string;
  slot_index: number;
  name: string;
  appearance_natural: string;
  appearance_tags: string;
  position: CharacterPosition;
  source_preset_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CharacterPreset {
  id: string;
  name: string;
  appearance_natural: string;
  appearance_tags: string;
  default_position: CharacterPosition;
  created_at: string;
  updated_at: string;
}

export interface GenerateTagsItem {
  id: string;
  name: string;
  natural: string;
}

export interface GenerateTagsResultItem {
  id: string;
  tags: string;
}
