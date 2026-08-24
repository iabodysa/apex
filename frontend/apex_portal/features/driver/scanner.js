import { __ } from "../../core/i18n.js";

export function createQrScanner({
  mediaDevices = globalThis.navigator?.mediaDevices,
  detectorFactory = () => new globalThis.BarcodeDetector({ formats: ["qr_code"] }),
  schedule = globalThis.requestAnimationFrame,
} = {}) {
  let stream;
  let running = false;

  const stop = () => {
    running = false;
    for (const track of stream?.getTracks?.() || []) track.stop();
    stream = undefined;
  };

  return Object.freeze({
    async start(video, onCode) {
      stop();
      if (!mediaDevices?.getUserMedia || !globalThis.BarcodeDetector) {
        throw new TypeError(__("Camera scanning is not available on this device."));
      }
      const detector = detectorFactory();
      stream = await mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      video.srcObject = stream;
      await video.play();
      running = true;
      const read = async () => {
        if (!running) return;
        const [result] = await detector.detect(video);
        if (result?.rawValue) {
          stop();
          await onCode(result.rawValue);
          return;
        }
        schedule(read);
      };
      schedule(read);
    },
    stop,
  });
}
