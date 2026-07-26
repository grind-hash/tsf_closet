/**
 * useSSE hook - handles Server-Sent Events for real-time updates.
 * Supports both GET (EventSource) and POST (fetch API) methods.
 */

import { useCallback, useRef } from "react";
import type {
  AnlasBalance,
  SSEAchievementData,
  SSECriticalData,
  SSEEndingData,
  SSEStatsData,
} from "../types";

export interface UseSSEOptions {
  onText?: (chunk: string) => void;
  onImage?: (imageBase64: string, historyId: string, seed?: number) => void;
  onSurroundingsImage?: (
    imageBase64: string,
    historyId: string,
    seed?: number,
  ) => void;
  onStats?: (stats: SSEStatsData) => void;
  onCritical?: (data: SSECriticalData) => void;
  onEnding?: (data: SSEEndingData) => void;
  onAchievement?: (data: SSEAchievementData) => void;
  onComplete?: (historyId: string | null, transformationCount: number) => void;
  onCost?: (cost: number) => void;
  onAnlas?: (balance: AnlasBalance) => void;
  onRealityAttributeAdded?: (data: {
    attribute_id: string;
    attribute_text: string;
  }) => void;
  onError?: (message: string) => void;
}

export interface UseSSEReturn {
  startStream: (url: string) => void;
  startPostStream: (url: string, body: Record<string, unknown>) => void;
  stopStream: () => void;
  isStreaming: boolean;
}

export function useSSE(options: UseSSEOptions): UseSSEReturn {
  const eventSourceRef = useRef<EventSource | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isStreamingRef = useRef(false);
  const errorHandledRef = useRef(false);

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    isStreamingRef.current = false;
    errorHandledRef.current = false;
  }, []);

  // Process a single SSE event line
  const processEvent = useCallback(
    (eventType: string, eventData: string) => {
      try {
        const data = JSON.parse(eventData);

        switch (eventType) {
          case "text":
            if (data.chunk && options.onText) {
              options.onText(data.chunk);
            }
            break;
          case "image":
            if (options.onImage) {
              options.onImage(data.image, data.history_id, data.seed);
            }
            break;
          case "surroundings_image":
            if (options.onSurroundingsImage) {
              options.onSurroundingsImage(
                data.image,
                data.history_id,
                data.seed,
              );
            }
            break;
          case "stats":
            if (options.onStats) {
              options.onStats({
                bloom: data.bloom,
                shame: data.shame,
                adaptation: data.adaptation,
              });
            }
            break;
          case "critical":
            if (options.onCritical) {
              options.onCritical(data);
            }
            break;
          case "ending":
            if (options.onEnding) {
              options.onEnding(data);
            }
            break;
          case "achievement":
            if (options.onAchievement) {
              options.onAchievement(data);
            }
            break;
          case "complete":
            if (data.play_memory_update === "failed" && options.onError) {
              options.onError("プレイメモの自動更新に失敗しました");
            }
            if (options.onComplete) {
              options.onComplete(
                data.history_id ?? null,
                data.transformation_count,
              );
            }
            break;
          case "cost":
            if (options.onCost) {
              options.onCost(data.cost_usd);
            }
            break;
          case "anlas":
            if (options.onAnlas) {
              if (
                typeof data.fixed_anlas === "number" &&
                typeof data.purchased_anlas === "number" &&
                typeof data.total_anlas === "number"
              ) {
                options.onAnlas({
                  fixedAnlas: data.fixed_anlas,
                  purchasedAnlas: data.purchased_anlas,
                  totalAnlas: data.total_anlas,
                });
              }
            }
            break;
          case "reality_attribute_added":
            if (options.onRealityAttributeAdded) {
              options.onRealityAttributeAdded(data);
            }
            break;
          case "error":
            errorHandledRef.current = true;
            if (options.onError) {
              options.onError(data.message || "エラーが発生しました");
            }
            break;
        }
      } catch (e) {
        console.error(`Failed to parse ${eventType} event:`, e);
      }
    },
    [options],
  );

  // POST対応: fetch APIを使用してSSEストリームを取得
  const startPostStream = useCallback(
    async (url: string, body: Record<string, unknown>) => {
      stopStream();
      errorHandledRef.current = false;
      isStreamingRef.current = true;

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!response.ok) {
          const errorText = await response.text();
          errorHandledRef.current = true;
          if (options.onError) {
            options.onError(`HTTP ${response.status}: ${errorText}`);
          }
          stopStream();
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          if (options.onError) {
            options.onError("ストリームを開始できませんでした");
          }
          stopStream();
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";
        let currentEvent = "";
        let currentData = "";

        const flushEvent = (): boolean => {
          if (currentEvent && currentData) {
            processEvent(currentEvent, currentData);
            const wasComplete =
              currentEvent === "complete" || currentEvent === "error";
            currentEvent = "";
            currentData = "";
            return wasComplete;
          }
          return false;
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            // Flush any remaining event when stream ends
            flushEvent();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // Keep incomplete line in buffer

          for (const line of lines) {
            // Skip comment lines (start with :)
            if (line.startsWith(":")) {
              continue;
            }

            if (line.startsWith("event:")) {
              // Flush previous event before starting new one
              if (flushEvent()) {
                stopStream();
                return;
              }
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              currentData = line.slice(5).trim();
            } else if (line === "") {
              // Empty line marks end of event
              if (flushEvent()) {
                stopStream();
                return;
              }
            }
          }
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          if (!errorHandledRef.current && options.onError) {
            options.onError("接続が切断されました");
          }
        }
      } finally {
        stopStream();
      }
    },
    [options, stopStream, processEvent],
  );

  // GET対応: 従来のEventSourceを使用
  const startStream = useCallback(
    (url: string) => {
      // Close any existing stream
      stopStream();
      errorHandledRef.current = false;

      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;
      isStreamingRef.current = true;

      eventSource.addEventListener("text", (event) => {
        processEvent("text", event.data);
      });

      eventSource.addEventListener("image", (event) => {
        processEvent("image", event.data);
      });

      eventSource.addEventListener("stats", (event) => {
        processEvent("stats", event.data);
      });

      eventSource.addEventListener("critical", (event) => {
        processEvent("critical", event.data);
      });

      eventSource.addEventListener("ending", (event) => {
        processEvent("ending", event.data);
      });

      eventSource.addEventListener("complete", (event) => {
        processEvent("complete", event.data);
        stopStream();
      });

      eventSource.addEventListener("cost", (event) => {
        processEvent("cost", event.data);
      });

      eventSource.addEventListener("error", (event) => {
        if (event instanceof MessageEvent) {
          processEvent("error", event.data);
        } else if (!errorHandledRef.current && options.onError) {
          options.onError("接続が切断されました");
        }
        stopStream();
      });

      eventSource.onerror = () => {
        if (!errorHandledRef.current && options.onError) {
          options.onError("接続が切断されました");
        }
        stopStream();
      };
    },
    [options, stopStream, processEvent],
  );

  return {
    startStream,
    startPostStream,
    stopStream,
    isStreaming: isStreamingRef.current,
  };
}
