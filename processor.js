// processor.js
class MicProcessor extends AudioWorkletProcessor {
    process(inputs) {
      const input = inputs[0][0];
      if (input) {
        const buffer = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          buffer[i] = input[i] * 0x7FFF;
        }
        this.port.postMessage(buffer);
      }
      return true;
    }
  }
  
  registerProcessor("mic-processor", MicProcessor);  