import { requestJson } from "../utils/http";

/**
 * GET /health の応答。API_BASE の外（ルート直下）にある互換エンドポイントで、
 * 起動時にプロバイダー構成を知るためだけに使う。
 */
export interface HealthStatus {
  status?: string;
  image_provider?: string;
  image_description_provider?: string;
  feeling_provider?: string;
  /** 従量課金の外部 API を使う構成か。未定義なら旧サーバーなのでプロバイダー名から推定する */
  cost_tracking?: boolean;
  judge?: {
    enabled?: boolean;
    transport?: string | null;
    model?: string | null;
  };
  services?: Record<string, unknown>;
}

/**
 * 料金表示を出す構成かどうか。サーバーの判定 (cost_tracking) を優先し、
 * それを返さない旧サーバーではプロバイダー名から推定する。
 * 判定専用モデル (Jev) は生成プロバイダーに現れないため、サーバー側の値が要る。
 */
export function shouldShowCost(health: HealthStatus): boolean {
  return (
    health.cost_tracking ??
    (health.image_provider === "openrouter" ||
      health.image_description_provider === "openrouter" ||
      health.feeling_provider === "openrouter")
  );
}

export async function fetchHealth(): Promise<HealthStatus> {
  return requestJson<HealthStatus>("/health");
}
