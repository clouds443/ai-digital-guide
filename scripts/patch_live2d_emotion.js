const fs = require("fs");
const path = require("path");

const bundlePath = path.join(__dirname, "..", "frontend", "cubism", "assets", "index-Chr99YS7.js");
let text = fs.readFileSync(bundlePath, "utf8");

const originalBridge = "setMouth:t=>{e()?.setExternalMouth(t)},setModel:t=>{e()?.changeModelByName(t)}}";
const patchedBridge = "setMouth:t=>{e()?.setExternalMouth(t)},setEmotion:t=>{document.body.dataset.emotion=String(t||\"neutral\"),document.body.classList.remove(\"emotion-neutral\",\"emotion-happy\",\"emotion-thanks\",\"emotion-surprised\",\"emotion-confused\"),document.body.classList.add(\"emotion-\"+String(t||\"neutral\"))},setModel:t=>{e()?.changeModelByName(t)}}";
if (text.includes(originalBridge)) {
  text = text.replace(originalBridge, patchedBridge);
} else if (!text.includes("setEmotion:t=>{document.body.dataset.emotion")) {
  throw new Error("Could not find Live2D bridge object block.");
}

const originalMessage = "t.mouth!==void 0&&window.LingshanLive2D?.setMouth(Number(t.mouth)||0)";
const patchedMessage = "t.mouth!==void 0&&window.LingshanLive2D?.setMouth(Number(t.mouth)||0),t.emotion!==void 0&&window.LingshanLive2D?.setEmotion(String(t.emotion||\"neutral\"))";
if (text.includes(originalMessage)) {
  text = text.replace(originalMessage, patchedMessage);
} else if (!text.includes("t.emotion!==void 0&&window.LingshanLive2D?.setEmotion")) {
  throw new Error("Could not find Live2D message handler block.");
}

fs.writeFileSync(bundlePath, text, "utf8");
console.log("Live2D emotion patch applied.");
