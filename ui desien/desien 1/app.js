(() => {
'use strict';
window.__errors = []; window.__ready = false; window.__lastResult = null; window.__lastError = null;
window.addEventListener('error', e => window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection', e => window.__errors.push(String(e.reason)));

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const BROWSERS = ['chrome', 'edge', 'firefox', 'brave', 'opera', 'vivaldi'];
const BIG = 500 * 1024 * 1024;

let lang = 'ar', info = {}, settings = {}, lastJob = null, booted = false;
const S = {
  enc: { file: null, name: '', size: 0, out: '' },
  rs: { source: 'url', file: null, name: '', size: 0, outDir: '', check: null },
  job: { id: 0, next: 0, timer: null, kind: null, running: false },
};
const pane = { encode: $('#tab-encode'), restore: $('#tab-restore') };

const call = async (m, ...a) => {
  try { return await window.pywebview.api[m](...a); }
  catch (e) { window.__errors.push(m + ': ' + e); return null; }
};
const t = (k, v) => {
  let s = (I18N[lang] || {})[k] ?? I18N.en[k] ?? k;
  if (v) for (const n in v) s = s.split('{' + n + '}').join(v[n] ?? '');
  return s;
};
const has = k => k in (I18N[lang] || {});
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmtBytes = n => {
  if (n == null) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0;
  while (n >= 1024 && i < 4) { n /= 1024; i++; }
  return (i ? n.toFixed(n < 10 ? 2 : 1) : n) + ' ' + u[i];
};
const fmtTime = s => {
  if (s == null || !isFinite(s)) return '—';
  s = Math.round(s);
  const m = Math.floor(s / 60), h = Math.floor(m / 60), p = x => String(x).padStart(2, '0');
  return h ? `${h}:${p(m % 60)}:${p(s % 60)}` : `${m}:${p(s % 60)}`;
};
const save = patch => { Object.assign(settings, patch); call('set_settings', patch); };

// ---------------- language ----------------
function fillSelects() {
  const keep = id => $(id).value;
  const b = keep('#encBlock'), n = keep('#encNsym'), c = keep('#rsBrowser');
  $('#encBlock').innerHTML = [2, 4, 8, 16].map(v => `<option value="${v}">${v}${v === 4 ? ' (' + t('def') + ')' : ''}</option>`).join('');
  $('#encNsym').innerHTML = [0, 16, 32, 64, 96].map(v =>
    `<option value="${v}">${v === 0 ? t('nsym_0') : v}${v === 32 ? ' (' + t('def') + ')' : ''}</option>`).join('');
  $('#rsBrowser').innerHTML = `<option value="">${t('cookies_none')}</option>` +
    BROWSERS.map(v => `<option value="${v}">${v}</option>`).join('');
  $('#encBlock').value = b || settings.block || '4';
  $('#encNsym').value = n || settings.nsym || '32';
  $('#rsBrowser').value = c || settings.browser || '';
}

function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  $$('[data-i18n]').forEach(e => { e.textContent = t(e.dataset.i18n); });
  $$('[data-i18n-ph]').forEach(e => { e.placeholder = t(e.dataset.i18nPh); });
  $('#langBtn').textContent = t('lang_btn');
  fillSelects(); renderChips(); renderEncFile(); renderRsFile(); renderCheck(); updateEstimate();
  $('#jsWarn').hidden = !!info.js_runtime;
  if (lastJob) renderJob(lastJob);
}

function renderChips() {
  const c = [];
  c.push(info.ffmpeg ? ['ok', t('chip_ffmpeg_ok', { v: info.ffmpeg_version || '' })] : ['bad', t('chip_ffmpeg_bad')]);
  c.push(info.js_runtime ? ['ok', t('chip_js_ok', { name: info.js_runtime })] : ['bad', t('chip_js_bad')]);
  if (info.ytdlp) c.push(['', t('chip_yt', { v: info.ytdlp })]);
  $('#chips').innerHTML = c.map(([k, s]) => `<span class="chip ${k}">${esc(s)}</span>`).join('');
}

// ---------------- encode tab ----------------
function renderEncFile() {
  const f = S.enc;
  $('#encDrop').hidden = !!f.file; $('#encFile').hidden = !f.file;
  $('#encName').textContent = f.name; $('#encSize').textContent = f.file ? fmtBytes(f.size) : '';
  $('#encOut').value = f.out || '';
  $('#encOutBtn').disabled = !f.file;
}
async function setEncodeFile(path) {
  const r = await call('file_info', path);
  if (!r || !r.ok) return;
  S.enc = { file: r.path, name: r.name, size: r.size, out: r.default_out };
  hideMsg('#encMsg'); renderEncFile(); updateEstimate();
}
async function updateEstimate() {
  const el = $('#encEstimate');
  if (!S.enc.file) { el.textContent = ''; return; }
  const e = await call('estimate', S.enc.size, +$('#encBlock').value, +$('#encNsym').value, $('#encPwToggle').checked);
  if (!e) { el.textContent = ''; return; }
  let s = t('est', { dur: fmtTime(e.seconds), frames: e.frames.toLocaleString(), ovh: Math.round(e.overhead_pct) });
  if (S.enc.size > BIG) s += '\n' + t('est_big', { gb: (S.enc.size * 5 / 1e9).toFixed(1) });
  el.textContent = s; el.style.whiteSpace = 'pre-line';
}
async function startEncode() {
  hideMsg('#encMsg');
  if (!S.enc.file) return showMsg('#encMsg', t('file_err_none'));
  const pw = $('#encPwToggle').checked ? $('#encPw').value : '';
  if ($('#encPwToggle').checked && !pw) return showMsg('#encMsg', t('pw_empty'));
  save({ block: $('#encBlock').value, nsym: $('#encNsym').value });
  preStart('encode');
  const r = await call('start_encode', {
    file: S.enc.file, output: S.enc.out, block: +$('#encBlock').value, nsym: +$('#encNsym').value, password: pw || null,
  });
  if (!r || !r.ok) { resetRun('encode'); setBusy(false); return showMsg('#encMsg', errText(r && r.code || 'unexpected', {})); }
  beginJob(r.id, 'encode');
}

// ---------------- restore tab ----------------
function setSource(src) {
  S.rs.source = src;
  $('.seg').style.setProperty('--i', src === 'url' ? 0 : 1);
  $$('.seg [data-src]').forEach(b => b.classList.toggle('active', b.dataset.src === src));
  $('#srcUrlBox').hidden = src !== 'url'; $('#srcFileBox').hidden = src !== 'file';
}
function renderRsFile() {
  const f = S.rs;
  $('#rsDrop').hidden = !!f.file; $('#rsFile').hidden = !f.file;
  $('#rsName').textContent = f.name; $('#rsSize').textContent = f.file ? fmtBytes(f.size) : '';
  $('#rsOut').value = f.outDir || '';
}
async function setRestoreFile(path) {
  const r = await call('file_info', path);
  if (!r || !r.ok) return;
  Object.assign(S.rs, { file: r.path, name: r.name, size: r.size });
  setSource('file'); hideMsg('#rsMsg'); renderRsFile();
}
function setRestoreOut(path) { S.rs.outDir = path || ''; renderRsFile(); save({ outDir: S.rs.outDir }); }

function renderCheck() {
  const box = $('#rsCheckOut'), c = S.rs.check;
  if (!c) { box.hidden = true; return; }
  box.hidden = false;
  if (!c.ok) { box.className = 'msg err'; box.textContent = errText(c.code, { detail: c.message, message: c.message }); return; }
  box.className = 'ytcard';
  const q = c.has_4k ? `<span class="q ok">${esc(t('q_ready'))}</span>`
    : `<span class="q wait">${esc(t('q_wait', { h: c.max_height }))}</span><div class="m">${esc(t('q_note_wait'))}</div>`;
  box.innerHTML = `${c.thumbnail ? `<img alt="" src="${esc(c.thumbnail)}">` : ''}<div><div class="t">${esc(c.title)}</div>
    <div class="m">${esc(c.channel || '')} ${c.duration ? '· ' + fmtTime(c.duration) : ''}</div>${q}</div>`;
}
async function checkUrl() {
  const url = $('#rsUrl').value.trim();
  if (!url) return showMsg('#rsMsg', t('e_url_missing'));
  hideMsg('#rsMsg');
  const b = $('#rsCheck'); b.disabled = true; b.textContent = t('checking');
  S.rs.check = await call('check_url', url, $('#rsBrowser').value || null);
  b.disabled = false; b.textContent = t('check'); renderCheck();
}
async function startRestore() {
  hideMsg('#rsMsg');
  const url = $('#rsUrl').value.trim(), fromUrl = S.rs.source === 'url';
  if (fromUrl && !url) return showMsg('#rsMsg', t('e_url_missing'));
  if (!fromUrl && !S.rs.file) return showMsg('#rsMsg', t('file_err_none'));
  const pw = $('#rsPwToggle').checked ? $('#rsPw').value : '';
  if ($('#rsPwToggle').checked && !pw) return showMsg('#rsMsg', t('pw_empty'));
  save({ browser: $('#rsBrowser').value });
  preStart('restore');
  const r = await call('start_restore', {
    source: S.rs.source, url, file: S.rs.file, out_dir: S.rs.outDir || '', password: pw || null,
    keep_video: $('#rsKeep').checked, browser: $('#rsBrowser').value || null,
  });
  if (!r || !r.ok) { resetRun('restore'); setBusy(false); return showMsg('#rsMsg', errText(r && r.code || 'unexpected', {})); }
  beginJob(r.id, 'restore');
}

// ---------------- messages ----------------
function showMsg(sel, text) { const e = $(sel); e.textContent = text; e.hidden = false; }
function hideMsg(sel) { $(sel).hidden = true; }
function errText(code, v) {
  const k = 'e_' + code;
  return has(k) || I18N.en[k] ? t(k, v) : (v.message || code);
}

// ---------------- jobs ----------------
const runOf = kind => $('.run', pane[kind]);
const role = (run, r) => $(`[data-role=${r}]`, run);

function resetRun(kind) {
  const run = runOf(kind);
  run.dataset.state = 'idle';
  const b = role(run, 'badge'); b.dataset.state = 'idle'; b.textContent = t('b_idle');
  role(run, 'pct').textContent = '0%'; role(run, 'fill').style.setProperty('--p', 0);
  ['stages', 'log', 'result', 'error', 'elapsed', 'eta', 'extra'].forEach(r => { role(run, r).textContent = ''; });
  role(run, 'result').hidden = true; role(run, 'error').hidden = true;
}
function preStart(kind) {            // reset instantly on click so old results are never mistaken for the new run
  window.__lastResult = null; window.__lastError = null; lastJob = null;
  resetRun(kind);
  const run = runOf(kind), b = role(run, 'badge');
  run.dataset.state = 'running'; b.dataset.state = 'running'; b.textContent = t('b_running');
  $$('#encStart,#rsStart').forEach(x => { x.disabled = true; });
}
function beginJob(id, kind) {
  clearInterval(S.job.timer);
  S.job = { id, next: 0, kind, running: true, timer: null };
  if (!runOf(kind).dataset.state || runOf(kind).dataset.state === 'idle') preStart(kind);
  setBusy(true);
  S.job.timer = setInterval(poll, 400); poll();
}
function setBusy(b) {
  ['#encStart', '#rsStart'].forEach(s => { $(s).disabled = b; });
  $$('[data-role=cancel]').forEach(c => { c.hidden = !(b && c.closest('.pane') === pane[S.job.kind]); });
}
let polling = false;
async function poll() {
  if (polling) return; polling = true;
  try {
    const r = await call('poll', S.job.next, S.job.id);
    const j = r && r.job;
    if (!j || j.id !== S.job.id) return;
    S.job.next = j.log_next;
    renderJob(j);
    if (j.status !== 'running') {
      clearInterval(S.job.timer); S.job.running = false;
      window.__lastResult = j.result || null; window.__lastError = j.error || null;
      finishRun(j);
      setBusy(false);
    }
  } finally { polling = false; }
}
function renderJob(j) {
  lastJob = j;
  const run = runOf(j.kind); run.dataset.state = j.status;
  const b = role(run, 'badge'); b.dataset.state = j.status === 'running' ? 'running' : j.status;
  b.textContent = t('b_' + j.status);
  role(run, 'pct').textContent = Math.round(j.percent) + '%';
  role(run, 'fill').style.setProperty('--p', j.percent);
  const ul = role(run, 'stages');
  if (ul.children.length !== j.stages.length) {
    ul.innerHTML = j.stages.map(() => '<li><span class="sq"></span><span class="sl"></span><span class="sp"></span></li>').join('');
  }
  j.stages.forEach((s, i) => {
    const li = ul.children[i]; li.dataset.state = s.state;
    li.children[1].textContent = t(`s_${j.kind}_${s.id}`);
    li.children[2].textContent = s.state === 'active' ? Math.round(s.frac * 100) + '%' : '';
  });
  role(run, 'elapsed').textContent = t('elapsed') + ' ' + fmtTime(j.elapsed);
  role(run, 'eta').textContent = j.status === 'running' && j.eta != null ? t('eta') + ' ' + fmtTime(j.eta) : '';
  const x = j.extra || {};
  role(run, 'extra').textContent = x.total != null && j.status === 'running'
    ? `${fmtBytes(x.done)} / ${fmtBytes(x.total)}${x.speed ? ' · ' + fmtBytes(x.speed) + '/s' : ''}` : '';
  if (j.logs && j.logs.length) { const l = role(run, 'log'); l.textContent += j.logs.join('\n') + '\n'; l.scrollTop = l.scrollHeight; }
  const c = role(run, 'cancel');
  if (!c.dataset.armed || j.status !== 'running') { c.textContent = t('btn_cancel'); c.disabled = false; delete c.dataset.armed; }
}
function finishRun(j) {
  const run = runOf(j.kind), res = role(run, 'result'), er = role(run, 'error');
  if (j.status === 'error' && j.error) {
    const e = j.error;
    er.innerHTML = `<strong>${esc(t('e_title'))}</strong><br>${esc(errText(e.code, e))}` +
      (e.video_path ? `<br>${esc(t('video_kept'))}` : '');
    er.hidden = false;
  }
  if (j.status === 'done' && j.result) {
    const r = j.result, enc = j.kind === 'encode';
    const row = (k, v, m) => `<dt>${esc(t(k))}</dt><dd${m ? ' class="mono"' : ''}>${esc(v)}</dd>`;
    let h;
    if (enc) {
      h = `<h3 class="ok">${esc(t('r_enc_h'))}</h3><dl class="stat">${row('r_size', fmtBytes(r.video_bytes))}${row('r_dur', fmtTime(r.video_seconds))}
        ${row('r_frames', (r.frames || 0).toLocaleString())}${row('r_time', fmtTime(r.elapsed))}${row('r_file', r.out, 1)}</dl>
        <p class="hint">${esc(t('r_enc_tip'))}</p>`;
    } else {
      h = `<h3 class="${r.ok ? 'ok' : 'bad'}">${esc(t(r.ok ? 'r_ok_h' : 'r_bad_h'))}</h3><dl class="stat">${row('r_size', fmtBytes(r.size))}
        ${row('r_fixed', (r.fixed || 0).toLocaleString())}${row('r_time', fmtTime(r.elapsed))}${row('r_sha', r.sha, 1)}${row('r_file', r.out, 1)}</dl>
        ${r.ok ? '' : `<p class="hint">${esc(t('r_bad_tip'))}</p>`}`;
    }
    h += `<div class="acts"><button class="btn sm" data-act="reveal" type="button">${esc(t('open_folder'))}</button>` +
      (enc ? `<button class="btn ghost sm" data-act="open" type="button">${esc(t('play'))}</button>` : '') +
      (!enc && r.sha ? `<button class="btn ghost sm" data-act="copy" type="button">${esc(t('copy'))} SHA-256</button>` : '') + '</div>';
    res.innerHTML = h; res.hidden = false; res.dataset.out = r.out || ''; res.dataset.sha = r.sha || '';
  }
}

// ---------------- init ----------------
function wire() {
  // ---- living background: mouse parallax, glow particles, pause when hidden ----
  const bg = $('.bg');
  let px = 0, py = 0, raf = 0;
  window.addEventListener('pointermove', e => {
    px = e.clientX / innerWidth - .5; py = e.clientY / innerHeight - .5;
    if (!raf) raf = requestAnimationFrame(() => {
      raf = 0; bg.style.setProperty('--mx', px.toFixed(3)); bg.style.setProperty('--my', py.toFixed(3));
    });
  }, { passive: true });
  for (let k = 0; k < 22; k++) {
    const b = document.createElement('b');
    b.style.cssText = `left:${(Math.random() * 100).toFixed(1)}%;--s:${(2 + Math.random() * 4).toFixed(1)}px;` +
      `--d:${(16 + Math.random() * 22).toFixed(1)}s;--dl:-${(Math.random() * 30).toFixed(1)}s;--dx:${Math.round(Math.random() * 90 - 45)}px`;
    bg.append(b);
  }
  document.addEventListener('visibilitychange', () => document.body.classList.toggle('paused', document.hidden));

  $$('.runmount').forEach(m => m.append($('#runTpl').content.cloneNode(true)));
  $$('.tab').forEach((b, idx) => b.addEventListener('click', () => {
    $('.tabs').style.setProperty('--i', idx);
    $$('.tab').forEach(x => x.classList.toggle('active', x === b));
    $$('.pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + b.dataset.tab));
  }));
  $('#langBtn').onclick = () => { lang = lang === 'ar' ? 'en' : 'ar'; save({ lang }); applyLang(); };
  $$('.seg [data-src]').forEach(b => b.onclick = () => setSource(b.dataset.src));

  const pick = async (fn, kind) => { const p = await call('pick_file', kind); if (p) fn(p); };
  $('#encBrowse').onclick = $('#encChange').onclick = () => pick(setEncodeFile, 'any');
  $('#encRemove').onclick = () => { S.enc = { file: null, name: '', size: 0, out: '' }; renderEncFile(); updateEstimate(); };
  $('#encOutBtn').onclick = async () => {
    const p = await call('pick_save', S.enc.out.split(/[\\/]/).pop(), S.enc.out.replace(/[\\/][^\\/]*$/, ''));
    if (p) { S.enc.out = p; renderEncFile(); }
  };
  $('#rsBrowse').onclick = $('#rsChange').onclick = () => pick(setRestoreFile, 'video');
  $('#rsRemove').onclick = () => { Object.assign(S.rs, { file: null, name: '', size: 0 }); renderRsFile(); };
  $('#rsOutBtn').onclick = async () => { const p = await call('pick_folder', S.rs.outDir); if (p) setRestoreOut(p); };

  [['#encPwToggle', '#encPwBox', '#encPw'], ['#rsPwToggle', '#rsPwBox', '#rsPw']].forEach(([tg, box, inp]) => {
    $(tg).addEventListener('change', () => { $(box).hidden = !$(tg).checked; if ($(tg).checked) $(inp).focus(); updateEstimate(); });
  });
  $('#encPwShow').onclick = () => { const i = $('#encPw'); i.type = i.type === 'password' ? 'text' : 'password'; };
  $('#rsPwShow').onclick = () => { const i = $('#rsPw'); i.type = i.type === 'password' ? 'text' : 'password'; };
  $('#encBlock').onchange = $('#encNsym').onchange = updateEstimate;

  $('#rsPaste').onclick = async () => { try { $('#rsUrl').value = (await navigator.clipboard.readText()).trim(); } catch (e) {} };
  $('#rsCheck').onclick = checkUrl;
  $('#rsUrl').addEventListener('keydown', e => { if (e.key === 'Enter') checkUrl(); });
  $('#rsUrl').addEventListener('input', () => { S.rs.check = null; renderCheck(); });
  $('#rsKeep').onchange = () => save({ keep: $('#rsKeep').checked });
  $('#encStart').onclick = startEncode; $('#rsStart').onclick = startRestore;

  $$('[data-role=cancel]').forEach(c => c.onclick = async () => {
    c.dataset.armed = '1'; c.disabled = true; c.textContent = t('btn_cancelling'); await call('cancel');
  });
  $$('.run').forEach(run => role(run, 'result').addEventListener('click', e => {
    const a = e.target.closest('[data-act]'); if (!a) return;
    const res = role(run, 'result');
    if (a.dataset.act === 'reveal') call('reveal', res.dataset.out);
    else if (a.dataset.act === 'open') call('open_path', res.dataset.out);
    else if (a.dataset.act === 'copy') navigator.clipboard.writeText(res.dataset.sha).then(() => { a.textContent = t('copied'); });
  }));

  let depth = 0;
  window.addEventListener('dragenter', () => { depth++; document.body.classList.add('dragging'); });
  window.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; document.body.classList.remove('dragging'); } });
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => { e.preventDefault(); depth = 0; document.body.classList.remove('dragging'); });
}

window.onNativeDrop = paths => {
  document.body.classList.remove('dragging');
  if (!paths || !paths.length || S.job.running) return;
  if (pane.encode.classList.contains('active')) setEncodeFile(paths[0]); else setRestoreFile(paths[0]);
};
window.__test = { setEncodeFile, setRestoreFile, setRestoreOut };

async function boot() {
  if (booted) return; booted = true;
  try {
    wire();
    settings = (await call('get_settings')) || {};
    info = (await call('get_info')) || {};
    lang = settings.lang === 'en' ? 'en' : 'ar';
    S.rs.outDir = settings.outDir || '';
    $('#rsKeep').checked = !!settings.keep;
    applyLang();
    ['encode', 'restore'].forEach(resetRun);
    setBusy(false);
    const j = await call('poll', 0, 0);           // resume display if a job is already running
    if (j && j.job && j.job.status === 'running') { beginJob(j.job.id, j.job.kind); }
  } catch (e) { window.__errors.push('boot: ' + e); }
  window.__ready = true;
}
if (window.pywebview && window.pywebview.api) boot();
else { window.addEventListener('pywebviewready', boot); setTimeout(boot, 3000); }
})();
