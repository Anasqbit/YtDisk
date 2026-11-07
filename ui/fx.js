(() => {
  'use strict';

  const INTERACTIVE = '.btn, .tab, .seg button, .check input, summary';
  const TILTABLE = '.btn, .tab, .seg button, summary';
  const STORAGE_KEY = 'ytdisk.sfx.muted';
  const MAX_TILT = 14;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const sfxButton = document.getElementById('sfxBtn');

  let muted = readMuted();
  let audioContext = null;
  let masterGain = null;
  let noiseBuffer = null;
  let lastHoverSound = 0;
  let hovered = null;
  let tiltFrame = 0;
  let nextPointer = null;

  const pointerPresses = new Map();
  const keyboardPresses = new Set();
  const knownRunStates = new WeakMap();

  function readMuted() {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true';
    } catch (_) {
      return false;
    }
  }

  function setMuted(value, persist = true) {
    muted = Boolean(value);

    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, String(muted));
      } catch (_) {
        // The toggle still works if storage is unavailable.
      }
    }

    if (masterGain && audioContext) {
      const now = audioContext.currentTime;
      masterGain.gain.cancelScheduledValues(now);
      masterGain.gain.setTargetAtTime(muted ? 0 : 0.35, now, 0.018);
    }

    if (sfxButton) {
      sfxButton.classList.toggle('is-muted', muted);
      sfxButton.setAttribute('aria-pressed', String(!muted));
      sfxButton.setAttribute('aria-label', muted ? 'Enable sound effects' : 'Mute sound effects');
    }
  }

  function ensureAudio() {
    if (!audioContext) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return false;

      try {
        audioContext = new AudioContextClass();
        masterGain = audioContext.createGain();
        masterGain.gain.value = muted ? 0 : 0.35;
        masterGain.connect(audioContext.destination);
      } catch (_) {
        audioContext = null;
        masterGain = null;
        return false;
      }
    }

    if (audioContext.state === 'suspended') {
      const resume = audioContext.resume();
      if (resume && typeof resume.catch === 'function') resume.catch(() => {});
    }

    return true;
  }

  function getNoiseBuffer() {
    if (noiseBuffer || !audioContext) return noiseBuffer;

    const length = Math.max(1, Math.floor(audioContext.sampleRate * 0.055));
    noiseBuffer = audioContext.createBuffer(1, length, audioContext.sampleRate);
    const samples = noiseBuffer.getChannelData(0);

    for (let i = 0; i < length; i += 1) {
      const fade = 1 - i / length;
      samples[i] = (Math.random() * 2 - 1) * fade;
    }

    return noiseBuffer;
  }

  function playTone(frequency, duration, volume, waveform = 'sine', endFrequency = null) {
    if (muted || !audioContext || !masterGain) return;

    const now = audioContext.currentTime;
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();

    oscillator.type = waveform;
    oscillator.frequency.setValueAtTime(frequency, now);
    if (endFrequency && endFrequency > 0) {
      oscillator.frequency.exponentialRampToValueAtTime(endFrequency, now + duration);
    }

    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, volume), now + 0.004);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);

    oscillator.connect(gain);
    gain.connect(masterGain);
    oscillator.start(now);
    oscillator.stop(now + duration + 0.012);
  }

  function playNoise(duration, volume, cutoff = 2800) {
    if (muted || !audioContext || !masterGain) return;

    const now = audioContext.currentTime;
    const source = audioContext.createBufferSource();
    const filter = audioContext.createBiquadFilter();
    const gain = audioContext.createGain();

    source.buffer = getNoiseBuffer();
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(cutoff, now);
    filter.Q.setValueAtTime(0.55, now);

    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, volume), now + 0.002);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);

    source.connect(filter);
    filter.connect(gain);
    gain.connect(masterGain);
    source.start(now);
    source.stop(now + duration + 0.008);
  }

  function kindOf(element) {
    if (!element) return 'key';
    if (element.matches('.btn.danger')) return 'danger';
    if (element.matches('.btn.primary')) return 'primary';
    if (element.matches('.tab, .seg button')) return 'selector';
    if (element.matches('summary')) return 'summary';
    return 'key';
  }

  function playHover() {
    if (muted || !audioContext) return;

    const now = performance.now();
    if (now - lastHoverSound < 100) return;
    lastHoverSound = now;
    playTone(1650 + Math.random() * 220, 0.018, 0.018, 'sine');
  }

  function playDown(element) {
    if (muted || !ensureAudio()) return;

    const type = kindOf(element);

    if (type === 'danger') {
      playNoise(0.052, 0.2, 1700);
      playTone(76 + Math.random() * 8, 0.095, 0.22, 'triangle', 44);
      playTone(960 + Math.random() * 120, 0.022, 0.045, 'square', 520);
      return;
    }

    if (type === 'primary') {
      playNoise(0.042, 0.12, 2200);
      playTone(94 + Math.random() * 10, 0.09, 0.23, 'triangle', 52);
      return;
    }

    if (type === 'selector') {
      playNoise(0.024, 0.075, 3900);
      playTone(740 + Math.random() * 100, 0.035, 0.06, 'square', 450);
      return;
    }

    playNoise(0.03, 0.08, type === 'summary' ? 2500 : 3200);
    playTone(138 + Math.random() * 18, 0.055, 0.1, 'triangle', 92);
  }

  function playUp(element) {
    if (muted || !audioContext) return;

    const type = kindOf(element);

    if (type === 'primary') {
      playNoise(0.02, 0.045, 3200);
      playTone(620 + Math.random() * 60, 0.075, 0.075, 'sine', 980);
      return;
    }

    if (type === 'danger') {
      playNoise(0.035, 0.1, 2100);
      playTone(116 + Math.random() * 12, 0.05, 0.08, 'triangle', 76);
      return;
    }

    if (type === 'selector') {
      playNoise(0.018, 0.05, 4200);
      return;
    }

    playNoise(0.018, 0.045, 2800);
  }

  function playToggle(isOn) {
    if (muted || !ensureAudio()) return;

    if (isOn) {
      playNoise(0.025, 0.07, 4200);
      playTone(960 + Math.random() * 100, 0.06, 0.075, 'sine', 1320);
    } else {
      playNoise(0.032, 0.075, 2400);
      playTone(510 + Math.random() * 70, 0.075, 0.085, 'triangle', 260);
    }
  }

  function playOutcome(type) {
    if (muted || !ensureAudio()) return;

    if (type === 'done') {
      playTone(660, 0.12, 0.075, 'sine', 790);
      window.setTimeout(() => playTone(990, 0.16, 0.06, 'sine', 1180), 65);
      return;
    }

    playNoise(0.12, 0.14, 580);
    playTone(112, 0.16, 0.12, 'sawtooth', 72);
  }

  function isDisabled(element) {
    return element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true';
  }

  function closestInteractive(target) {
    if (!(target instanceof Element)) return null;
    return target.closest(INTERACTIVE);
  }

  function resetTilt(element) {
    if (!element) return;
    element.classList.remove('fx-hovering');
    element.style.setProperty('--rx', '0deg');
    element.style.setProperty('--ry', '0deg');
    element.style.setProperty('--lift', '0px');
    element.style.setProperty('--mx', '50%');
    element.style.setProperty('--my', '50%');
  }

  function updateTilt(element, clientX, clientY) {
    if (!element || reducedMotion.matches || !element.matches(TILTABLE) || isDisabled(element)) {
      if (element) resetTilt(element);
      return;
    }

    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const x = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));

    element.style.setProperty('--rx', `${((0.5 - y) * MAX_TILT * 2).toFixed(2)}deg`);
    element.style.setProperty('--ry', `${((x - 0.5) * MAX_TILT * 2).toFixed(2)}deg`);
    element.style.setProperty('--lift', '5px');
    element.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`);
    element.style.setProperty('--my', `${(y * 100).toFixed(1)}%`);
  }

  document.addEventListener('pointerover', event => {
    const element = closestInteractive(event.target);
    if (!element || isDisabled(element)) return;
    if (event.relatedTarget instanceof Node && element.contains(event.relatedTarget)) return;

    if (hovered && hovered !== element) resetTilt(hovered);
    hovered = element;

    if (element.matches(TILTABLE)) {
      element.classList.add('fx-hovering');
      if (event.pointerType === 'mouse') updateTilt(element, event.clientX, event.clientY);
    }

    playHover();
  });

  document.addEventListener('pointerout', event => {
    const element = closestInteractive(event.target);
    if (!element) return;
    if (event.relatedTarget instanceof Node && element.contains(event.relatedTarget)) return;

    resetTilt(element);
    if (hovered === element) hovered = null;
  });

  document.addEventListener('pointermove', event => {
    if (event.pointerType !== 'mouse' || reducedMotion.matches) return;

    const element = closestInteractive(event.target);
    if (!element || !element.matches(TILTABLE) || isDisabled(element)) {
      if (hovered) resetTilt(hovered);
      hovered = null;
      return;
    }

    if (hovered && hovered !== element) resetTilt(hovered);
    hovered = element;
    element.classList.add('fx-hovering');

    nextPointer = { element, x: event.clientX, y: event.clientY };
    if (tiltFrame) return;

    tiltFrame = window.requestAnimationFrame(() => {
      tiltFrame = 0;
      if (nextPointer) updateTilt(nextPointer.element, nextPointer.x, nextPointer.y);
      nextPointer = null;
    });
  }, { passive: true });

  document.addEventListener('pointerdown', event => {
    const element = closestInteractive(event.target);
    if (!element || isDisabled(element)) return;

    ensureAudio();

    if (element.matches('.check input')) return;

    pointerPresses.set(event.pointerId, element);
    element.classList.add('fx-pressed');
    playDown(element);
  });

  function releasePointer(pointerId) {
    const element = pointerPresses.get(pointerId);
    if (!element) return;

    pointerPresses.delete(pointerId);
    element.classList.remove('fx-pressed');
    playUp(element);
  }

  document.addEventListener('pointerup', event => releasePointer(event.pointerId));
  document.addEventListener('pointercancel', event => releasePointer(event.pointerId));

  document.addEventListener('keydown', event => {
    if (event.repeat || (event.key !== 'Enter' && event.key !== ' ')) return;

    const element = closestInteractive(event.target);
    if (!element || isDisabled(element) || element.matches('.check input')) return;

    ensureAudio();
    keyboardPresses.add(element);
    element.classList.add('fx-pressed');
    playDown(element);
  });

  document.addEventListener('keyup', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;

    const element = closestInteractive(event.target);
    if (!element || !keyboardPresses.has(element)) return;

    keyboardPresses.delete(element);
    element.classList.remove('fx-pressed');
    playUp(element);
  });

  document.addEventListener('change', event => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || !target.matches('.check input')) return;
    playToggle(target.checked);
  });

  document.addEventListener('click', event => {
    const element = closestInteractive(event.target);
    if (!element || element.id !== 'sfxBtn') return;
    setMuted(!muted);
  });

  function observeRunStates() {
    const update = () => {
      document.querySelectorAll('.run[data-state]').forEach(run => {
        const state = run.getAttribute('data-state');
        const previous = knownRunStates.get(run);
        knownRunStates.set(run, state);

        if (previous && previous !== state && (state === 'done' || state === 'error')) {
          playOutcome(state);
        }
      });
    };

    update();

    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-state'],
      childList: true,
      subtree: true
    });
  }

  if (reducedMotion.addEventListener) {
    reducedMotion.addEventListener('change', event => {
      if (event.matches && hovered) resetTilt(hovered);
    });
  } else if (reducedMotion.addListener) {
    reducedMotion.addListener(event => {
      if (event.matches && hovered) resetTilt(hovered);
    });
  }

  setMuted(muted, false);
  observeRunStates();
})();
