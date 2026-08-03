const fs = require("fs");
const path = require("path");

const bundlePath = path.join(__dirname, "..", "frontend", "cubism", "assets", "index-Chr99YS7.js");
let text = fs.readFileSync(bundlePath, "utf8");

const originalState = "_externalLipSync={enabled:!1,text:``,phase:0,value:0}";
const patchedState = "_externalLipSync={enabled:!1,text:``,phase:0,value:0,manual:!1,manualValue:0}";
if (text.includes(originalState)) {
  text = text.replace(originalState, patchedState);
}

const originalMethods = "setExternalLipSync(e,t=``){let n=this._externalLipSync;n.enabled=e,n.text=t,e||(n.value=0)}applyExternalLipSync(e){if(this._lipSyncIds.length===0)return;let t=this._externalLipSync;if(t.enabled){t.phase+=e*13;let n=Math.min(1,Math.max(.35,t.text.length/28)),r=.2+Math.abs(Math.sin(t.phase))*.8*n;t.value+=(r-t.value)*Math.min(1,e*12)}else t.value+=(0-t.value)*Math.min(1,e*8);for(let e=0;e<this._lipSyncIds.length;e++)this._model.setParameterValueById(this._lipSyncIds[e],t.value,1)}";
const patchedMethods = "setExternalLipSync(e,t=``){let n=this._externalLipSync;n.enabled=e,n.text=t,e||(n.value=0,n.manual=!1,n.manualValue=0)}setExternalMouth(e){let t=this._externalLipSync;t.manual=!0,t.manualValue=Math.max(0,Math.min(1,Number(e)||0)),t.enabled=t.manualValue>0}applyExternalLipSync(e){if(this._lipSyncIds.length===0)return;let t=this._externalLipSync;if(t.manual)t.value+=(t.manualValue-t.value)*Math.min(1,e*28);else if(t.enabled){t.phase+=e*13;let n=Math.min(1,Math.max(.35,t.text.length/28)),r=.2+Math.abs(Math.sin(t.phase))*.8*n;t.value+=(r-t.value)*Math.min(1,e*12)}else t.value+=(0-t.value)*Math.min(1,e*8);for(let e=0;e<this._lipSyncIds.length;e++)this._model.setParameterValueById(this._lipSyncIds[e],t.value,1)}";
if (text.includes(originalMethods)) {
  text = text.replace(originalMethods, patchedMethods);
} else if (!text.includes("setExternalMouth(e)")) {
  throw new Error("Could not find Live2D lip sync method block.");
}

const originalManager = "setExternalLipSync(e,t=``){let n=this._models[0];n&&n.setExternalLipSync(e,t)}changeScene";
const patchedManager = "setExternalLipSync(e,t=``){let n=this._models[0];n&&n.setExternalLipSync(e,t)}setExternalMouth(e){let t=this._models[0];t&&t.setExternalMouth(e)}changeScene";
if (text.includes(originalManager)) {
  text = text.replace(originalManager, patchedManager);
} else if (!text.includes("setExternalMouth(e){let t=this._models[0]")) {
  throw new Error("Could not find Live2D manager method block.");
}

const originalBridge = "setListening:t=>{document.body.classList.toggle(`listening`,t),t||e()?.setExternalLipSync(!1,``)},setModel:t=>{e()?.changeModelByName(t)}}";
const patchedBridge = "setListening:t=>{document.body.classList.toggle(`listening`,t),t||e()?.setExternalLipSync(!1,``)},setMouth:t=>{e()?.setExternalMouth(t)},setModel:t=>{e()?.changeModelByName(t)}}";
if (text.includes(originalBridge)) {
  text = text.replace(originalBridge, patchedBridge);
} else if (!text.includes("setMouth:t=>{e()?.setExternalMouth(t)}")) {
  throw new Error("Could not find Live2D bridge object block.");
}

const originalMessage = "t.speak!==void 0&&window.LingshanLive2D?.setSpeaking(!!t.speak,t.text||``)";
const patchedMessage = "t.speak!==void 0&&window.LingshanLive2D?.setSpeaking(!!t.speak,t.text||``),t.mouth!==void 0&&window.LingshanLive2D?.setMouth(Number(t.mouth)||0)";
if (text.includes(originalMessage)) {
  text = text.replace(originalMessage, patchedMessage);
} else if (!text.includes("t.mouth!==void 0&&window.LingshanLive2D?.setMouth")) {
  throw new Error("Could not find Live2D message handler block.");
}

fs.writeFileSync(bundlePath, text, "utf8");
console.log("Live2D mouth sync patch applied.");
