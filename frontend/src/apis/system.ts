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
  services?: Record<string, unknown>;
}

export async function fetchHealth(): Promise<HealthStatus> {
  return requestJson<HealthStatus>("/health");
}
