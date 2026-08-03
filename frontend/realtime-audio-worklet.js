class LingshanPcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
    this.sourceSampleRate = sampleRate;
    this.ratio = this.sourceSampleRate / this.targetSampleRate;
    this.frameSamples = 3200;
    this.pending = new Int16Array(this.frameSamples * 2);
    this.pendingLength = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;

    const channel = input[0];
    const outLength = Math.floor(channel.length / this.ratio);
    if (outLength <= 0) return true;

    const pcm = new Int16Array(outLength);
    for (let i = 0; i < outLength; i += 1) {
      const sourceIndex = Math.min(channel.length - 1, Math.floor(i * this.ratio));
      const sample = Math.max(-1, Math.min(1, channel[sourceIndex]));
      pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    if (this.pendingLength + pcm.length > this.pending.length) {
      const grown = new Int16Array((this.pendingLength + pcm.length) * 2);
      grown.set(this.pending.subarray(0, this.pendingLength), 0);
      this.pending = grown;
    }
    this.pending.set(pcm, this.pendingLength);
    this.pendingLength += pcm.length;

    while (this.pendingLength >= this.frameSamples) {
      const frame = new Int16Array(this.frameSamples);
      frame.set(this.pending.subarray(0, this.frameSamples), 0);
      this.port.postMessage(frame.buffer, [frame.buffer]);
      this.pending.copyWithin(0, this.frameSamples, this.pendingLength);
      this.pendingLength -= this.frameSamples;
    }
    return true;
  }
}

registerProcessor("lingshan-pcm-processor", LingshanPcmProcessor);
