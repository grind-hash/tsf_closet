// @vitest-environment node
import { describe, expect, it } from "vitest";
import { readSseEvents, type SseEvent } from "./sse";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(chunks: string[]): Promise<SseEvent[]> {
  const events: SseEvent[] = [];
  for await (const event of readSseEvents(streamOf(chunks))) {
    events.push(event);
  }
  return events;
}

describe("readSseEvents", () => {
  it("parses event and data fields separated by blank lines", async () => {
    const events = await collect([
      'event: text\ndata: {"chunk":"a"}\n\nevent: done\ndata: {}\n\n',
    ]);
    expect(events).toEqual([
      { event: "text", data: '{"chunk":"a"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("uses message as the default event name", async () => {
    const events = await collect(['data: {"type":"text"}\n\n']);
    expect(events).toEqual([{ event: "message", data: '{"type":"text"}' }]);
  });

  it("reassembles lines split across chunks", async () => {
    const events = await collect([
      "event: te",
      'xt\ndata: {"chu',
      'nk":"a"}\n',
      "\n",
    ]);
    expect(events).toEqual([{ event: "text", data: '{"chunk":"a"}' }]);
  });

  it("joins multi-line data, accepts CRLF and skips comments", async () => {
    const events = await collect([
      ": keep-alive\r\nevent: x\r\ndata: line1\r\ndata: line2\r\n\r\n",
    ]);
    expect(events).toEqual([{ event: "x", data: "line1\nline2" }]);
  });

  it("flushes a trailing event without a terminating blank line", async () => {
    const events = await collect(["event: done\ndata: {}"]);
    expect(events).toEqual([{ event: "done", data: "{}" }]);
  });

  it("drops events that carry no data and resets the event name", async () => {
    const events = await collect(["event: empty\n\ndata: x\n\n"]);
    expect(events).toEqual([{ event: "message", data: "x" }]);
  });

  it("decodes multi-byte characters split across chunks", async () => {
    const bytes = new TextEncoder().encode('data: {"t":"あ"}\n\n');
    const cut = 10;
    const encoder = new TextDecoder();
    void encoder;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, cut));
        controller.enqueue(bytes.slice(cut));
        controller.close();
      },
    });
    const events: SseEvent[] = [];
    for await (const event of readSseEvents(stream)) events.push(event);
    expect(events).toEqual([{ event: "message", data: '{"t":"あ"}' }]);
  });
});
