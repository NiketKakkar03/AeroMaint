export type DecoderRequest =
  | {
      readonly type: "configure";
      readonly generation: number;
      readonly config: VideoDecoderConfig;
    }
  | {
      readonly type: "decode";
      readonly generation: number;
      readonly chunk: EncodedVideoChunkInit;
    }
  | { readonly type: "flush"; readonly generation: number }
  | { readonly type: "close" };

export type DecoderResponse =
  | { readonly type: "ready"; readonly generation: number }
  | {
      readonly type: "frame";
      readonly generation: number;
      readonly frame: VideoFrame;
    }
  | { readonly type: "flushed"; readonly generation: number }
  | {
      readonly type: "error";
      readonly generation: number;
      readonly message: string;
    };

let generation = 0;
let decoder: VideoDecoder | undefined;

self.addEventListener("message", (event: MessageEvent<DecoderRequest>) => {
  const request = event.data;
  if (request.type === "close") {
    decoder?.close();
    decoder = undefined;
    return;
  }
  if (request.type === "configure") {
    generation = request.generation;
    decoder?.close();
    decoder = new VideoDecoder({
      output(frame) {
        if (request.generation !== generation) frame.close();
        else
          self.postMessage(
            { type: "frame", generation, frame } satisfies DecoderResponse,
            { transfer: [frame] }
          );
      },
      error(error) {
        self.postMessage({
          type: "error",
          generation,
          message: error.message
        } satisfies DecoderResponse);
      }
    });
    decoder.configure(request.config);
    self.postMessage({ type: "ready", generation } satisfies DecoderResponse);
    return;
  }
  if (request.generation !== generation || decoder === undefined) return;
  if (request.type === "decode")
    decoder.decode(new EncodedVideoChunk(request.chunk));
  else
    void decoder.flush().then(() => {
      if (request.generation === generation)
        self.postMessage({
          type: "flushed",
          generation
        } satisfies DecoderResponse);
    });
});

export {};
