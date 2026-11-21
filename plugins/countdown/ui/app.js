/* The countdown's own document.
 *
 * It is a document, a page the shell mounts, and nothing else. It reads no
 * global the shell injects, calls no command, and asks no question of the API:
 * the mount is sandboxed to an opaque origin (#42), so a request would leave
 * this page with the authority of `null` and no credential of its own, and the
 * channel that answers to a plugin's declared capabilities — the message bridge,
 * #23 — is not in this tree yet. What is on screen here is therefore the timer
 * this page owns: it starts, it ticks, it says when it is done, and it sounds a
 * chime through the Web Audio API, which is the one declared capability
 * (`audio-out`) a document can exercise on its own.
 *
 * `notifications` and `dock-badge` ride this declaration for the same reason a
 * manifest names a route before the route has a caller: the vocabulary is closed
 * (`core/plugin_ui_capabilities.py`), and a capability a later layer confines has
 * to be paid for here first. Neither is exercised by this file, and
 * `ENFORCED_CAPABILITIES` is still empty, so nothing in this page would be
 * refused by a layer that is watching.
 *
 * The state the agent's tool writes is one file under this plugin's data root;
 * this page never reads it. The two meet at the manifest, nowhere else.
 */
const remaining = document.getElementById("remaining");
const phase = document.getElementById("phase");
const root = document.querySelector(".countdown");

const TICK_MS = 200;
const CHIME_HZ = 880;
const CHIME_MS = 320;

let timerId = null;
let endsAt = null;

function leftMs() {
  return endsAt === null ? 0 : Math.max(0, endsAt - Date.now());
}

function render() {
  const left = leftMs();
  const totalSeconds = Math.ceil(left / 1000);
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  remaining.textContent = `${minutes}:${seconds}`;
  if (endsAt === null) {
    phase.textContent = "Idle";
    root.classList.remove("running", "done");
    return;
  }
  if (left > 0) {
    phase.textContent = "Running";
    root.classList.add("running");
    root.classList.remove("done");
    return;
  }
  phase.textContent = "Time";
  root.classList.add("done");
  root.classList.remove("running");
}

function stopTicking() {
  if (timerId !== null) {
    window.clearInterval(timerId);
    timerId = null;
  }
}

function chime() {
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context) return;
  const context = new Context();
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.type = "sine";
  oscillator.frequency.value = CHIME_HZ;
  gain.gain.value = 0.2;
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + CHIME_MS / 1000);
}

function start(minutes) {
  stopTicking();
  endsAt = Date.now() + minutes * 60 * 1000;
  render();
  timerId = window.setInterval(() => {
    if (leftMs() <= 0) {
      stopTicking();
      render();
      chime();
      return;
    }
    render();
  }, TICK_MS);
}

function pause() {
  stopTicking();
  if (endsAt !== null) {
    endsAt = null;
    phase.textContent = "Paused";
  }
  render();
}

function reset() {
  stopTicking();
  endsAt = null;
  render();
}

document.getElementById("start").addEventListener("click", () => start(1));
document.getElementById("start-five").addEventListener("click", () => start(5));
document.getElementById("pause").addEventListener("click", pause);
document.getElementById("reset").addEventListener("click", reset);

render();
