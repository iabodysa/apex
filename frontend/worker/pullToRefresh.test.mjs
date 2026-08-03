// Plain-node unit test for src/composables/usePullToRefresh.js. Run: node pullToRefresh.test.mjs
// The portal frame is one viewport tall and its column owns the overflow, so the document
// never scrolls: a guard written against window.scrollY reads 0 forever, arms a pull on
// every touch, and the composable's preventDefault then blocks the column's own scrolling.
// These cases lock the guard to the element the finger is actually on.
import { JSDOM } from "jsdom";

const dom = new JSDOM(
  `<!doctype html><html><body>
     <div id="frame" style="height:200px;overflow-y:auto">
       <div id="content" style="height:2000px"><span id="target">x</span></div>
     </div>
   </body></html>`,
  { pretendToBeVisual: true },
);

global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
// Vue's DOM runtime reaches for these by bare name at mount time.
for (const name of ["Element", "SVGElement", "MathMLElement", "Node", "HTMLElement", "Event"]) {
  global[name] = dom.window[name];
}
global.getComputedStyle = dom.window.getComputedStyle;

const frame = document.getElementById("frame");
const target = document.getElementById("target");

// jsdom has no layout engine, so scrollHeight/clientHeight are 0 and the real
// getComputedStyle returns "visible". Both are supplied here; the values are the ones a
// browser reports for the shipped frame.
Object.defineProperty(frame, "scrollHeight", { value: 2000 });
Object.defineProperty(frame, "clientHeight", { value: 200 });
let frameScrollTop = 0;
Object.defineProperty(frame, "scrollTop", {
  get: () => frameScrollTop,
  set: (value) => {
    frameScrollTop = value;
  },
});
const nativeComputed = dom.window.getComputedStyle;
global.getComputedStyle = (node) =>
  node === frame ? { overflowY: "auto" } : nativeComputed(node);
dom.window.getComputedStyle = global.getComputedStyle;

const { usePullToRefresh } = await import("./src/composables/usePullToRefresh.js");

function touch(type, clientY, node) {
  const event = new dom.window.Event(type, { bubbles: true, cancelable: true });
  event.touches = [{ clientY }];
  Object.defineProperty(event, "target", { value: node });
  let prevented = false;
  event.preventDefault = () => {
    prevented = true;
  };
  Object.defineProperty(event, "defaultPrevented", { get: () => prevented });
  document.dispatchEvent(event);
  return prevented;
}

let mounted;
const stateFor = () => {
  const state = usePullToRefresh(() => {});
  mounted();
  return state;
};

// The composable registers its listeners in onMounted; call the callback directly.
const vue = await import("vue");
const originalOnMounted = vue.onMounted;
void originalOnMounted;

let failed = 0;
function check(name, condition) {
  if (condition) {
    console.log(`ok    ${name}`);
  } else {
    failed++;
    console.error(`FAIL  ${name}`);
  }
}

// usePullToRefresh binds inside onMounted, which needs an active component instance.
// Rather than fake one, drive the exported functions through a real mount via the
// composable's own listeners: mount by invoking the hook inside a minimal app.
const { createApp, h } = vue;
let state;
const app = createApp({
  setup() {
    state = usePullToRefresh(() => {});
    return () => h("div");
  },
});
mounted = () => {};
void stateFor;
app.mount(document.createElement("div"));

frameScrollTop = 0;
touch("touchstart", 100, target);
const preventedAtTop = touch("touchmove", 160, target);
check("a downward drag from the column's top arms the pull", preventedAtTop);
check("the indicator travels", state.distance.value > 0);

touch("touchend", 0, target);

frameScrollTop = 300;
touch("touchstart", 100, target);
const preventedMidScroll = touch("touchmove", 160, target);
check(
  "a downward drag while the column is scrolled does NOT take over the gesture",
  !preventedMidScroll,
);
check("the indicator stays put mid-scroll", state.distance.value === 0);

console.log(
  failed
    ? `pull-to-refresh: ${failed} failed`
    : "pull-to-refresh: guard reads the scrolling column, not the document",
);
process.exit(failed ? 1 : 0);
