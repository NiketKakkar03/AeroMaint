export interface IvfFrame {
  readonly timestampUs: number;
  readonly key: boolean;
  readonly data: Uint8Array;
}

export interface IvfVideo {
  readonly config: VideoDecoderConfig;
  readonly durationUs: number;
  readonly frames: readonly IvfFrame[];
}

function ascii(bytes: Uint8Array, offset: number, length: number): string {
  return String.fromCharCode(...bytes.subarray(offset, offset + length));
}

/** Demuxes the deliberately small IVF container used for VP8/VP9 browser delivery. */
export function demuxIvf(input: ArrayBuffer): IvfVideo {
  const bytes = new Uint8Array(input);
  if (bytes.byteLength < 32 || ascii(bytes, 0, 4) !== "DKIF")
    throw new Error("Invalid IVF header");
  const view = new DataView(input);
  const headerLength = view.getUint16(6, true);
  const fourcc = ascii(bytes, 8, 4);
  const codec =
    fourcc === "VP80" ? "vp8" : fourcc === "VP90" ? "vp09.00.10.08" : undefined;
  if (!codec) throw new Error(`Unsupported IVF codec ${fourcc}`);
  const width = view.getUint16(12, true);
  const height = view.getUint16(14, true);
  const rate = view.getUint32(16, true);
  const scale = view.getUint32(20, true);
  if (
    headerLength < 32 ||
    rate === 0 ||
    scale === 0 ||
    width === 0 ||
    height === 0
  )
    throw new Error("Invalid IVF stream metadata");
  const frames: IvfFrame[] = [];
  let offset = headerLength;
  while (offset + 12 <= bytes.byteLength) {
    const size = view.getUint32(offset, true);
    const low = view.getUint32(offset + 4, true);
    const high = view.getUint32(offset + 8, true);
    offset += 12;
    if (offset + size > bytes.byteLength)
      throw new Error("Truncated IVF frame");
    const timestamp = Number((BigInt(high) << 32n) | BigInt(low));
    const data = bytes.slice(offset, offset + size);
    frames.push({
      timestampUs: Math.round((timestamp * scale * 1_000_000) / rate),
      key: fourcc === "VP80" ? ((data[0] ?? 1) & 1) === 0 : frames.length === 0,
      data
    });
    offset += size;
  }
  return {
    config: { codec, codedWidth: width, codedHeight: height },
    durationUs: frames.at(-1)?.timestampUs ?? 0,
    frames
  };
}
