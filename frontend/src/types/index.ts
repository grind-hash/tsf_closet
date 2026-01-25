// アプリケーション全体の型定義

// セッション統計 (パラメータ)
export interface SessionStats {
  excitement: number;  // ワクワク度 (旧: bloom)
  immersion: number;   // なりきり度 (旧: shame)
  challenge: number;   // チャレンジ度 (旧: adaptation)
  passedCriticalPoints: number[];
  difficulty: string;
}

// 履歴アイテム
export interface HistoryItem {
  id: string;
  instruction: string;
  imageUrl: string;
  feelingText: string;
  beforeDescription: string;
  afterDescription: string;
  timestamp: string;
  costumeCategory?: string;
  sparkleLevel?: string;
  ageImpression?: string;
}

// セッションレスポンス
export interface SessionResponse {
  sessionId: string;
  characterId?: string;
  currentImageUrl: string;
  transformationCount: number;
  history: HistoryItem[];
  createdAt: string;
  updatedAt: string;
  stats?: SessionStats;
}

// キャラクター情報
export interface Character {
  id: string;
  name: string;
  thumbnail: string;
  description: string;
  gender: 'girl' | 'boy' | 'unknown';
}

// 変身カテゴリ
export type TransformationCategory = 
  | 'hero'        // ヒーロー・戦士
  | 'wizard'      // 魔法使い
  | 'adventure'   // 冒険家・探検家
  | 'ninja'       // 忍者
  | 'animal'      // 動物
  | 'sports'      // スポーツ選手
  | 'space'       // 宇宙飛行士
  | 'fantasy';    // その他ファンタジー

// エンディング
export interface Ending {
  endingId: string;
  title: string;
  finalSpeech: string;
  summary: string;
  isNew: boolean;
}

// 会話メッセージ
export interface ConversationMessage {
  id: string;
  role: 'user' | 'character';
  content: string;
  createdAt: string;
}

// アプリケーション状態
export interface AppState {
  screen: 'character-select' | 'game';
  sessionId: string | null;
  currentImageUrl: string | null;
  transformationCount: number;
  history: HistoryItem[];
  stats: SessionStats;
  isLoading: boolean;
  error: string | null;
}

// SSEイベント型
export interface SSETextEvent {
  chunk: string;
}

export interface SSEImageEvent {
  image: string;
  historyId: string;
}

export interface SSEStatsEvent {
  excitement: number;
  immersion: number;
  challenge: number;
  excitementDelta: number;
  immersionDelta: number;
  challengeDelta: number;
}

export interface SSEEndingEvent {
  endingId: string;
  title: string;
  finalSpeech: string;
  summary: string;
  isNew: boolean;
}

export interface SSECompleteEvent {
  sessionId: string;
  transformationCount: number;
}
