/**
 * Server-Sent Events の本文を読むための共通処理。
 *
 * `readSseEvents(response.body)` はイベント（`event:` + `data:` 行のまとまり）を
 * 1 件ずつ返す非同期イテレータ。chunk 境界で行が分断されても正しく組み立て、
 * 複数行の `data:` は改行で連結し、`:` で始まるコメント行は無視する。
 * ストリーム終端に空行が無い最後のイベントも返す。
 * `event:` が無いイベントは event = "message" になる。
 */

export interface SseEvent {
  event: string;
  data: string;
}

export async function* readSseEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent, void, undefined> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];

  const flush = (): SseEvent | null => {
    if (dataLines.length === 0) {
      eventName = "message";
      return null;
    }
    const event = { event: eventName, data: dataLines.join("\n") };
    eventName = "message";
    dataLines = [];
    return event;
  };

  const handleLine = (line: string): SseEvent | null => {
    if (line === "") return flush();
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") {
      eventName = value.trim() || "message";
    } else if (field === "data") {
      dataLines.push(value);
    }
    return null;
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split(/\r\n|\r|\n/);
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const event = handleLine(line);
        if (event) yield event;
      }
      if (done) break;
    }
    if (buffer) {
      const event = handleLine(buffer);
      if (event) yield event;
    }
    const tail = flush();
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}
