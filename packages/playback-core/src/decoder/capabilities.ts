export interface DecoderCapability {
  readonly mode: "webcodecs" | "html-media";
  readonly reason: string;
}

export async function selectDecoderCapability(
  codec: string,
  videoDecoder?: typeof VideoDecoder | null
): Promise<DecoderCapability> {
  const decoder =
    videoDecoder === undefined
      ? "VideoDecoder" in globalThis
        ? globalThis.VideoDecoder
        : null
      : videoDecoder;
  if (decoder === null)
    return { mode: "html-media", reason: "WebCodecs is unavailable" };
  try {
    const support = await decoder.isConfigSupported({ codec });
    return support.supported === true
      ? { mode: "webcodecs", reason: `${codec} is supported` }
      : { mode: "html-media", reason: `${codec} is unsupported` };
  } catch {
    return { mode: "html-media", reason: `${codec} capability check failed` };
  }
}
