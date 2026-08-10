export class DecodeGeneration {
  #value = 0;

  begin(): number {
    this.#value += 1;
    return this.#value;
  }

  isCurrent(generation: number): boolean {
    return generation === this.#value;
  }

  invalidate(): void {
    this.#value += 1;
  }
}
