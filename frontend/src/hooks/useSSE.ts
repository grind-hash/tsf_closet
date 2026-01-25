import { useCallback, useRef } from 'react';

export interface UseSSEOptions {
  onText?: (chunk: string) => void;
  onImage?: (image: string, historyId: string) => void;
  onStats?: (stats: {
    excitement: number;
    immersion: number;
    challenge: number;
    excitementDelta: number;
    immersionDelta: number;
    challengeDelta: number;
  }) => void;
  onCritical?: (data: {
    threshold: number;
    name: string;
    effectType: string;
    speech: string;
  }) => void;
  onEnding?: (data: {
    endingId: string;
    title: string;
    finalSpeech: string;
    summary: string;
    isNew: boolean;
  }) => void;
  onComplete?: (sessionId: string, transformationCount: number) => void;
  onError?: (message: string) => void;
}

export interface UseSSEReturn {
  startStream: (url: string) => void;
  stopStream: () => void;
  isStreaming: boolean;
}

export function useSSE(options: UseSSEOptions): UseSSEReturn {
  const eventSourceRef = useRef<EventSource | null>(null);
  const isStreamingRef = useRef(false);

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    isStreamingRef.current = false;
  }, []);

  const startStream = useCallback((url: string) => {
    stopStream();

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;
    isStreamingRef.current = true;

    eventSource.addEventListener('text', (event) => {
      try {
        const data = JSON.parse(event.data);
        options.onText?.(data.chunk);
      } catch (e) {
        console.error('Failed to parse text event:', e);
      }
    });

    eventSource.addEventListener('image', (event) => {
      try {
        const data = JSON.parse(event.data);
        options.onImage?.(data.image, data.history_id);
      } catch (e) {
        console.error('Failed to parse image event:', e);
      }
    });

    eventSource.addEventListener('stats', (event) => {
      try {
        const data = JSON.parse(event.data);
        options.onStats?.({
          excitement: data.excitement,
          immersion: data.immersion,
          challenge: data.challenge,
          excitementDelta: data.excitement_delta,
          immersionDelta: data.immersion_delta,
          challengeDelta: data.challenge_delta,
        });
      } catch (e) {
        console.error('Failed to parse stats event:', e);
      }
    });

    eventSource.addEventListener('critical', (event) => {
      try {
        const data = JSON.parse(event.data);
        options.onCritical?.({
          threshold: data.threshold,
          name: data.name,
          effectType: data.effect_type,
          speech: data.speech,
        });
      } catch (e) {
        console.error('Failed to parse critical event:', e);
      }
    });

    eventSource.addEventListener('ending', (event) => {
      try {
        const data = JSON.parse(event.data);
        options.onEnding?.({
          endingId: data.ending_id,
          title: data.title,
          finalSpeech: data.final_speech,
          summary: data.summary,
          isNew: data.is_new,
        });
      } catch (e) {
        console.error('Failed to parse ending event:', e);
      }
    });

    eventSource.addEventListener('complete', (event) => {
      try {
        const data = JSON.parse(event.data);
        options.onComplete?.(data.session_id, data.transformation_count);
      } catch (e) {
        console.error('Failed to parse complete event:', e);
      }
      stopStream();
    });

    // エラーイベント処理済みフラグ
    let errorHandled = false;

    eventSource.addEventListener('error', (event) => {
      if (event instanceof MessageEvent) {
        try {
          const data = JSON.parse(event.data);
          options.onError?.(data.message);
          errorHandled = true;
        } catch {
          options.onError?.('ストリームエラーが発生しました');
          errorHandled = true;
        }
      }
      stopStream();
    });

    eventSource.onerror = () => {
      // エラーイベントで既に処理済みの場合は無視
      if (!errorHandled) {
        options.onError?.('接続が切断されました');
      }
      stopStream();
    };
  }, [options, stopStream]);

  return {
    startStream,
    stopStream,
    isStreaming: isStreamingRef.current,
  };
}
