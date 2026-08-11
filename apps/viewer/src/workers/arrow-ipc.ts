export interface ArrowVectorColumns {
  readonly timestampsNs: BigInt64Array;
  readonly x: Float64Array;
  readonly y: Float64Array;
  readonly z: Float64Array;
}

function align8(value: number): number {
  return (value + 7) & ~7;
}

function field(
  view: DataView,
  table: number,
  index: number
): number | undefined {
  const vtable = table - view.getInt32(table, true);
  const vtableLength = view.getUint16(vtable, true);
  const slot = vtable + 4 + index * 2;
  if (slot + 2 > vtable + vtableLength) return undefined;
  const relative = view.getUint16(slot, true);
  return relative === 0 ? undefined : table + relative;
}

function indirect(view: DataView, at: number): number {
  return at + view.getUint32(at, true);
}

function vector(view: DataView, at: number): { start: number; length: number } {
  const start = indirect(view, at);
  return { start: start + 4, length: view.getUint32(start, true) };
}

function int64Number(view: DataView, at: number): number {
  return Number(view.getBigInt64(at, true));
}

/** Reads uncompressed Arrow IPC stream record batches emitted by AeroMaint's sensor endpoint. */
export function parseArrowVectorStream(
  buffer: ArrayBuffer
): ArrowVectorColumns {
  const view = new DataView(buffer);
  const timestamps: bigint[] = [];
  const axes: [number[], number[], number[]] = [[], [], []];
  let offset = 0;
  while (offset + 4 <= buffer.byteLength) {
    let metadataLength = view.getInt32(offset, true);
    offset += 4;
    if (metadataLength === -1) {
      if (offset + 4 > buffer.byteLength)
        throw new Error("Truncated Arrow continuation marker");
      metadataLength = view.getInt32(offset, true);
      offset += 4;
    }
    if (metadataLength === 0) break;
    if (metadataLength < 0 || offset + metadataLength > buffer.byteLength)
      throw new Error("Invalid Arrow message length");
    const metadataStart = offset;
    const message = metadataStart + view.getUint32(metadataStart, true);
    const headerTypeAt = field(view, message, 1);
    const headerAt = field(view, message, 2);
    const bodyLengthAt = field(view, message, 3);
    const headerType =
      headerTypeAt === undefined ? 0 : view.getUint8(headerTypeAt);
    const bodyLength =
      bodyLengthAt === undefined ? 0 : int64Number(view, bodyLengthAt);
    const bodyStart = align8(metadataStart + metadataLength);
    if (bodyStart + bodyLength > buffer.byteLength)
      throw new Error("Truncated Arrow body");
    if (headerType === 3 && headerAt !== undefined) {
      const batch = indirect(view, headerAt);
      const lengthAt = field(view, batch, 0);
      const nodesAt = field(view, batch, 1);
      const buffersAt = field(view, batch, 2);
      if (
        lengthAt === undefined ||
        nodesAt === undefined ||
        buffersAt === undefined
      )
        throw new Error("Invalid Arrow record batch");
      const rowCount = int64Number(view, lengthAt);
      const nodes = vector(view, nodesAt);
      const buffers = vector(view, buffersAt);
      if (nodes.length < 4 || buffers.length < 8)
        throw new Error("Arrow sensor batch requires four primitive columns");
      for (let column = 0; column < 4; column += 1) {
        const validityOffset = int64Number(view, buffers.start + column * 32);
        const validityLength = int64Number(
          view,
          buffers.start + column * 32 + 8
        );
        const dataOffset = int64Number(view, buffers.start + column * 32 + 16);
        const dataLength = int64Number(view, buffers.start + column * 32 + 24);
        if (dataLength < rowCount * 8)
          throw new Error("Truncated Arrow primitive column");
        for (let row = 0; row < rowCount; row += 1) {
          const valid =
            validityLength === 0 ||
            ((view.getUint8(bodyStart + validityOffset + (row >> 3)) >>
              (row & 7)) &
              1) ===
              1;
          const at = bodyStart + dataOffset + row * 8;
          if (column === 0) timestamps.push(view.getBigInt64(at, true));
          else {
            const axis = axes[column - 1];
            if (axis) axis.push(valid ? view.getFloat64(at, true) : Number.NaN);
          }
        }
      }
    }
    offset = align8(bodyStart + bodyLength);
  }
  if (timestamps.length !== axes[0].length)
    throw new Error("Arrow sensor columns have inconsistent lengths");
  return {
    timestampsNs: BigInt64Array.from(timestamps),
    x: Float64Array.from(axes[0]),
    y: Float64Array.from(axes[1]),
    z: Float64Array.from(axes[2])
  };
}
