(() => {
'use strict';

const SELECTOR = '.btn, .tab, .seg button, .check input, summary';
const STORAGE_KEY = 'ytdisk.sfx';
const THEME_KEY = 'ytdisk.theme';
const soundButton = document.getElementById('sfxBtn');
const themeButton = document.getElementById('themeBtn');
const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
const darkPreference = window.matchMedia('(prefers-color-scheme: dark)');
let soundOn = true;
let theme = darkPreference.matches ? 'night' : 'day';
try {
  soundOn = localStorage.getItem(STORAGE_KEY) !== 'off';
  const savedTheme = localStorage.getItem(THEME_KEY);
  if (savedTheme === 'day' || savedTheme === 'night') theme = savedTheme;
} catch (_) {}
document.documentElement.dataset.theme = theme;

let audio = null, master = null, noiseBuffer = null;
let lastHover = 0;
const pending = new Map();
const pressed = new Map();
const reboundTimers = new WeakMap();
let frame = 0, keyboardPress = null;

function elementFor(node) {
  if (!node) return null;
  const element = node.nodeType === 1 ? node : node.parentElement;
  return element && element.closest ? element.closest(SELECTOR) : null;
}
function enabled(el) {
  return !!el && el.isConnected && !el.matches(':disabled, [aria-disabled="true"]') && !el.closest('[inert]');
}
function kind(el) {
  if (el.matches('.check input')) return 'toggle';
  if (el.matches('.btn.danger')) return 'danger';
  if (el.matches('.btn.primary')) return 'primary';
  if (el.matches('.tab, .seg button, summary')) return 'selector';
  return 'key';
}
function updateSoundButton() {
  if (!soundButton) return;
  soundButton.setAttribute('aria-pressed', String(soundOn));
  const ar = document.documentElement.lang.toLowerCase().startsWith('ar');
  soundButton.setAttribute('aria-label', ar
    ? (soundOn ? 'إيقاف المؤثرات الصوتية' : 'تشغيل المؤثرات الصوتية')
    : (soundOn ? 'Mute sound effects' : 'Enable sound effects'));
}
function updateThemeButton() {
  if (!themeButton) return;
  const night = theme === 'night';
  const ar = document.documentElement.lang.toLowerCase().startsWith('ar');
  themeButton.setAttribute('aria-pressed', String(night));
  themeButton.setAttribute('aria-label', ar
    ? (night ? 'تفعيل الوضع النهاري' : 'تفعيل الوضع الليلي')
    : (night ? 'Switch to day mode' : 'Switch to night mode'));
  themeButton.title = themeButton.getAttribute('aria-label');
}
function updateHeaderControls() {
  updateSoundButton();
  updateThemeButton();
}
updateHeaderControls();
new MutationObserver(updateHeaderControls).observe(document.documentElement, {
  attributes: true, attributeFilter: ['lang']
});

/* Create audio only during a user gesture. All samples are synthesized locally. */
function unlockAudio() {
  try {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return;
    if (!audio) {
      audio = new Audio();
      master = audio.createGain();
      master.gain.value = soundOn ? .35 : 0;
      master.connect(audio.destination);
      noiseBuffer = audio.createBuffer(1, Math.ceil(audio.sampleRate * .25), audio.sampleRate);
      const samples = noiseBuffer.getChannelData(0);
      for (let i = 0; i < samples.length; i++) samples[i] = Math.random() * 2 - 1;
    }
    if (audio.state === 'suspended') {
      const resume = audio.resume();
      if (resume && resume.catch) resume.catch(() => {});
    }
  } catch (_) { audio = null; master = null; noiseBuffer = null; }
}
function tone(when, frequency, duration, level, type = 'sine', endFrequency = frequency) {
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(Math.max(20, frequency), when);
  oscillator.frequency.exponentialRampToValueAtTime(Math.max(20, endFrequency), when + duration);
  gain.gain.setValueAtTime(.0001, when);
  gain.gain.linearRampToValueAtTime(level, when + .003);
  gain.gain.exponentialRampToValueAtTime(.0001, when + duration);
  oscillator.connect(gain); gain.connect(master);
  oscillator.start(when); oscillator.stop(when + duration + .01);
}
function noise(when, duration, level, frequency, q = .8) {
  const source = audio.createBufferSource();
  const filter = audio.createBiquadFilter();
  const gain = audio.createGain();
  source.buffer = noiseBuffer;
  filter.type = 'bandpass'; filter.frequency.value = frequency; filter.Q.value = q;
  gain.gain.setValueAtTime(level, when);
  gain.gain.exponentialRampToValueAtTime(.0001, when + duration);
  source.connect(filter); filter.connect(gain); gain.connect(master);
  source.start(when, 0, duration); source.stop(when + duration + .01);
}
function play(action, material = 'key', state = false) {
  if (!soundOn || !audio || !master || !noiseBuffer) return;
  try {
    const t = audio.currentTime + .005;
    const r = .92 + Math.random() * .16;
    if (action === 'hover') {
      noise(t, .018, .014, 2600 * r, 1.4);
      tone(t, 1250 * r, .02, .007);
    } else if (action === 'toggle') {
      noise(t, .035, .08, (state ? 2600 : 1350) * r, 1.3);
      tone(t, (state ? 570 : 300) * r, .06, .055, 'triangle', (state ? 440 : 210) * r);
    } else if (action === 'success') {
      tone(t, 540 * r, .16, .075);
      tone(t + .09, 810 * r, .24, .06);
    } else if (action === 'error') {
      tone(t, 140 * r, .18, .095, 'sawtooth', 95 * r);
      noise(t, .12, .035, 450 * r);
    } else if (action === 'down') {
      if (material === 'primary') {
        noise(t, .055, .11, 850 * r);
        tone(t, 115 * r, .12, .23, 'sine', 62 * r);
        tone(t + .05, 770 * r, .09, .022);
      } else if (material === 'danger') {
        noise(t, .085, .16, 610 * r);
        tone(t, 90 * r, .14, .25, 'triangle', 52 * r);
      } else if (material === 'selector') {
        noise(t, .036, .10, 2150 * r, 1.4);
        tone(t, 380 * r, .055, .10, 'triangle', 250 * r);
      } else if (material === 'toggle') {
        noise(t, .025, .045, 1800 * r);
        tone(t, 360 * r, .035, .045, 'triangle', 260 * r);
      } else {
        noise(t, .04, .085, 1450 * r);
        tone(t, 210 * r, .07, .12, 'sine', 120 * r);
      }
    } else if (action === 'up') {
      const hz = material === 'danger' ? 900 : material === 'selector' ? 2500 : 1900;
      noise(t, .032, material === 'danger' ? .11 : .065, hz * r, 1.1);
      tone(t, (material === 'primary' ? 240 : 340) * r, .05, .045, 'sine', 200 * r);
    }
  } catch (_) { /* Audio is optional on restricted WebViews. */ }
}

if (soundButton) soundButton.addEventListener('click', () => {
  soundOn = !soundOn;
  try { localStorage.setItem(STORAGE_KEY, soundOn ? 'on' : 'off'); } catch (_) {}
  if (master && audio) master.gain.setValueAtTime(soundOn ? .35 : 0, audio.currentTime);
  updateSoundButton();
  if (soundOn) play('toggle', 'toggle', true);
});

if (themeButton) themeButton.addEventListener('click', () => {
  theme = theme === 'night' ? 'day' : 'night';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(THEME_KEY, theme); } catch (_) {}
  updateThemeButton();
  play('toggle', 'toggle', theme === 'night');
});

/* One delegated pointer tracker also covers controls inserted later by app.js. */
function resetTilt(el) {
  pending.delete(el);
  el.classList.remove('fx-tracking');
  el.style.setProperty('--rx', '0deg');
  el.style.setProperty('--ry', '0deg');
  el.style.setProperty('--mx', '50%');
  el.style.setProperty('--my', '30%');
}
function renderTilt() {
  frame = 0;
  for (const [el, point] of pending) {
    if (!enabled(el) || motion.matches || !el.classList.contains('fx-tracking')) continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    const x = Math.max(0, Math.min(1, (point.x - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (point.y - rect.top) / rect.height));
    el.style.setProperty('--rx', ((y - .5) * 28).toFixed(2) + 'deg');
    el.style.setProperty('--ry', ((.5 - x) * 28).toFixed(2) + 'deg');
    el.style.setProperty('--mx', (x * 100).toFixed(1) + '%');
    el.style.setProperty('--my', (y * 100).toFixed(1) + '%');
  }
  pending.clear();
}
document.addEventListener('pointerover', e => {
  if (e.pointerType === 'touch') return;
  const el = elementFor(e.target);
  if (!enabled(el) || (e.relatedTarget instanceof Node && el.contains(e.relatedTarget))) return;
  if (!motion.matches) el.classList.add('fx-tracking');
  const now = performance.now();
  if (audio && soundOn && now - lastHover > 120) { lastHover = now; play('hover', kind(el)); }
}, { passive: true });
document.addEventListener('pointermove', e => {
  if (e.pointerType === 'touch' || motion.matches) return;
  const el = elementFor(e.target);
  if (!enabled(el)) return;
  el.classList.add('fx-tracking');
  pending.set(el, { x: e.clientX, y: e.clientY });
  if (!frame) frame = requestAnimationFrame(renderTilt);
}, { passive: true });
document.addEventListener('pointerout', e => {
  const el = elementFor(e.target);
  if (!el || (e.relatedTarget instanceof Node && el.contains(e.relatedTarget))) return;
  resetTilt(el);
}, { passive: true });

function press(el) {
  clearTimeout(reboundTimers.get(el));
  el.classList.remove('fx-rebound');
  el.classList.add('is-pressed');
  play('down', kind(el));
}
function release(el, withSound) {
  el.classList.remove('is-pressed');
  if (!motion.matches && enabled(el)) {
    el.classList.add('fx-rebound');
    clearTimeout(reboundTimers.get(el));
    reboundTimers.set(el, setTimeout(() => el.classList.remove('fx-rebound'), 320));
  }
  if (withSound && enabled(el)) play('up', kind(el));
}
document.addEventListener('pointerdown', e => {
  unlockAudio();
  if (e.button !== 0) return;
  const el = elementFor(e.target);
  if (!enabled(el)) return;
  pressed.set(e.pointerId, el);
  press(el);
}, { passive: true });
document.addEventListener('pointerup', e => {
  const el = pressed.get(e.pointerId);
  if (!el) return;
  pressed.delete(e.pointerId); release(el, true);
}, { passive: true });
document.addEventListener('pointercancel', e => {
  const el = pressed.get(e.pointerId);
  if (!el) return;
  pressed.delete(e.pointerId); release(el, false); resetTilt(el);
}, { passive: true });
document.addEventListener('change', e => {
  const el = e.target;
  if (el && el.matches && el.matches('.check input') && enabled(el)) play('toggle', 'toggle', el.checked);
});
document.addEventListener('keydown', e => {
  unlockAudio();
  if (e.repeat || (e.key !== ' ' && e.key !== 'Enter') || keyboardPress) return;
  const el = elementFor(e.target);
  if (!enabled(el)) return;
  keyboardPress = { el, key: e.key }; press(el);
});
document.addEventListener('keyup', e => {
  if (!keyboardPress || keyboardPress.key !== e.key) return;
  release(keyboardPress.el, true); keyboardPress = null;
});
window.addEventListener('blur', () => {
  for (const el of pressed.values()) release(el, false);
  pressed.clear();
  if (keyboardPress) { release(keyboardPress.el, false); keyboardPress = null; }
  document.querySelectorAll('.fx-tracking').forEach(resetTilt);
});
function motionChanged() {
  if (motion.matches) document.querySelectorAll('.fx-tracking').forEach(resetTilt);
}
if (motion.addEventListener) motion.addEventListener('change', motionChanged);
else if (motion.addListener) motion.addListener(motionChanged);

/* Announce transitions, not every repeated progress update. */
const knownStates = new WeakMap();
function rememberState(run, announce) {
  const next = run.dataset.state;
  const previous = knownStates.get(run);
  knownStates.set(run, next);
  if (announce && previous !== next && (next === 'done' || next === 'error')) play(next === 'done' ? 'success' : 'error');
}
document.querySelectorAll('.run').forEach(run => rememberState(run, false));
new MutationObserver(records => {
  for (const record of records) {
    if (record.type === 'attributes') {
      const el = record.target;
      if (record.attributeName === 'data-state' && el.matches('.run')) rememberState(el, true);
      if (record.attributeName === 'disabled' && el.matches(SELECTOR) && el.disabled) resetTilt(el);
    } else {
      record.addedNodes.forEach(node => {
        if (node.nodeType !== 1) return;
        if (node.matches('.run')) rememberState(node, true);
        node.querySelectorAll('.run').forEach(run => rememberState(run, true));
      });
    }
  }
}).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-state', 'disabled'] });
})();
