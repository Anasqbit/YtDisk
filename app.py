"""YtDisk GUI: Python + pywebview (WebView2) + HTML/CSS/JS.

Run:    python app.py
Debug:  python app.py --debug
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import webview

import ytdisk
import ytdl
from ytdisk import Cancelled, YtdiskError

APP_NAME = "YtDisk"
APP_VERSION = "1.0.0"
WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"
VIDEO_TYPES = ("Video files (*.mp4;*.webm;*.mkv;*.mov;*.avi)", "All files (*.*)")
UNSAFE_EXT = {".exe", ".bat", ".cmd", ".com", ".ps1", ".msi", ".lnk", ".js", ".vbs", ".scr", ".reg", ".jar"}

try:
    FD_OPEN, FD_FOLDER, FD_SAVE = webview.FileDialog.OPEN, webview.FileDialog.FOLDER, webview.FileDialog.SAVE
except AttributeError:  # older pywebview
    FD_OPEN, FD_FOLDER, FD_SAVE = webview.OPEN_DIALOG, webview.FOLDER_DIALOG, webview.SAVE_DIALOG


def resource_path(rel: str) -> str:
    return str(ytdisk.app_dir() / rel)


def data_dir() -> Path:
    d = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- selectable UIs (UI folders are never modified; the app just loads the chosen folder) ----------
# Every design has its own name, character, icon and switcher look. The switcher button is created with the
# page's own ".btn glass sm" classes, so it is drawn exactly like that design's native buttons; SWITCH_CSS only
# dresses the dropdown so it matches that design's panels. To add a design: add an entry here + a SWITCH_CSS entry.
UIS = {
    "default": {"dir": "ui", "icon": "foundry",
                "ar": "المصنع", "en": "Foundry",
                "ar_d": "معدن غرافيت، مصابيح كهرمانية، أزرار ميكانيكية",
                "en_d": "Graphite metal, amber lamps, mechanical keys",
                "sw": ["#202728", "#f4a947", "#7fdda7"]},
    "design1": {"dir": "ui desien/desien 1", "icon": "aurora",
                "ar": "الشفق", "en": "Aurora",
                "ar_d": "زجاج شفاف وأضواء قطبية متحركة",
                "en_d": "Frosted glass and drifting aurora light",
                "sw": ["#171c3f", "#6f8dff", "#b57bff"]},
    "design2": {"dir": "ui desien/desien 2", "icon": "analog",
                "ar": "أنالوج", "en": "Analog",
                "ar_d": "ورق كريمي ولوحة أجهزة كلاسيكية، نهاري وليلي",
                "en_d": "Cream paper and a vintage instrument panel, day & night",
                "sw": ["#eeeee3", "#ee7950", "#96bd79"]},
}
DEFAULT_UI = "default"

ICONS = {
    "foundry": '<path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z"/><circle cx="12" cy="12" r="3"/>',
    "aurora": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>'
              '<path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>',
    "analog": '<circle cx="12" cy="12" r="8"/><path d="M12 12l3.6-3.6"/><path d="M12 4.5V6M19.5 12H18M4.5 12H6"/>',
}


def ui_index(ui_id: str) -> Path:
    return Path(resource_path(UIS[ui_id]["dir"])) / "index.html"


# "§" is replaced by the switcher root selector.
SWITCH_CSS_COMMON = r"""
header.top{z-index:60}
§{position:relative;display:inline-flex;flex:none}
§.usw-float{position:fixed;top:14px;inset-inline-end:14px;z-index:2147483000}
§ .usw-btn{display:inline-flex;align-items:center;gap:7px;white-space:nowrap}
§ .usw-btn svg{width:16px;height:16px;flex:none}
§ .usw-menu{position:absolute;top:calc(100% + 12px);inset-inline-end:0;z-index:70;display:none;box-sizing:border-box;
  width:300px;max-width:calc(100vw - 32px);padding:8px;text-align:start;font:13px/1.35 "Segoe UI",Tahoma,Arial,sans-serif}
§.open .usw-menu{display:block;animation:usw-in .22s cubic-bezier(.2,.9,.3,1) both}
@keyframes usw-in{from{opacity:0;transform:translateY(-8px) scale(.97)}}
§ .usw-head{font-weight:700}
§ .usw-it{display:grid;grid-template-columns:48px minmax(0,1fr) 18px;align-items:center;gap:12px;box-sizing:border-box;
  width:100%;margin:0;padding:9px 10px;border:1px solid transparent;background:none;color:inherit;font:inherit;text-align:start;cursor:pointer}
§ .usw-it + .usw-it{margin-top:6px}
§ .usw-sw{position:relative;display:block;width:48px;height:34px;overflow:hidden;background:var(--c0)}
§ .usw-sw i{position:absolute;width:13px;height:13px;border-radius:50%}
§ .usw-sw i:nth-child(1){top:6px;inset-inline-start:7px;background:var(--c1)}
§ .usw-sw i:nth-child(2){bottom:6px;inset-inline-end:7px;background:var(--c2)}
§ .usw-tx{display:flex;flex-direction:column;min-width:0}
§ .usw-nm{font-size:14px}
§ .usw-ds{font-size:11.5px;line-height:1.35}
§ .usw-ck{width:12px;height:12px;border-radius:50%;justify-self:center}
§ .usw-toast{position:absolute;top:calc(100% + 10px);inset-inline-end:0;z-index:71;display:none;white-space:nowrap;padding:8px 12px;
  border-radius:8px;border:1px solid #78483e;background:#3b211c;color:#ffd9d2;font:12px "Segoe UI",Tahoma,sans-serif}
§ .usw-toast.show{display:block}
"""

SWITCH_CSS = {
    # Foundry: graphite panel, keycap-style rows, amber indicator lamp
    "default": r"""
§ .usw-menu{border:1px solid #485354;border-radius:13px;color:#e4e9e8;
  background:linear-gradient(155deg,rgba(255,255,255,.055),transparent 27%),
    repeating-linear-gradient(176deg,rgba(255,255,255,.012) 0 1px,transparent 1px 5px),linear-gradient(145deg,#293233,#202728 54%,#1b2223);
  box-shadow:0 4px 0 #111718,0 18px 34px rgba(0,0,0,.5),inset 0 1px 1px rgba(255,255,255,.16)}
§ .usw-head{padding:5px 8px 10px;color:#91a09f;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase}
§ .usw-it{border-color:#596463;border-radius:8px;
  background:linear-gradient(155deg,rgba(255,255,255,.1),transparent 40%),linear-gradient(#384142,#293132);
  box-shadow:0 1px 0 #6b7673,0 3px 0 #171d1e,inset 0 1px rgba(255,255,255,.14);transition:transform .12s,box-shadow .12s,filter .15s}
§ .usw-it:hover{filter:brightness(1.12)}
§ .usw-it:active{transform:translateY(3px);box-shadow:0 0 0 #171d1e,inset 0 2px 5px rgba(0,0,0,.4)}
§ .usw-it.cur{border-color:#8a6a35}
§ .usw-sw{border:1px solid #0d1213;border-radius:5px;box-shadow:inset 0 1px 3px rgba(0,0,0,.6)}
§ .usw-nm{font-weight:700;color:#e4e9e8}
§ .usw-ds{color:#91a09f}
§ .usw-ck{background:#10161a;box-shadow:inset 0 1px 3px #000,0 1px 0 rgba(255,255,255,.12)}
§ .usw-it.cur .usw-ck{background:#ffd17a;box-shadow:0 0 8px 2px rgba(244,169,71,.7)}
""",
    # Aurora: frosted glass, soft glow, gradient selection
    "design1": r"""
§ .usw-menu{border:1px solid rgba(255,255,255,.18);border-radius:22px;color:#f3f5ff;
  background:linear-gradient(145deg,rgba(62,68,134,.80),rgba(20,22,52,.93));
  backdrop-filter:blur(26px) saturate(160%);-webkit-backdrop-filter:blur(26px) saturate(160%);
  box-shadow:0 26px 64px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.24)}
§ .usw-head{padding:6px 12px 8px;color:rgba(236,239,255,.62);font-size:12px}
§ .usw-it{border-radius:16px;transition:background .25s,transform .25s,box-shadow .25s}
§ .usw-it:hover{background:rgba(255,255,255,.1);transform:translateY(-1px)}
§ .usw-it:active{transform:scale(.97)}
§ .usw-it.cur{background:linear-gradient(120deg,rgba(111,141,255,.42),rgba(181,123,255,.36));
  box-shadow:0 8px 24px rgba(130,120,255,.32),inset 0 1px 0 rgba(255,255,255,.3)}
§ .usw-sw{border-radius:12px;border:1px solid rgba(255,255,255,.22);box-shadow:0 6px 16px rgba(0,0,0,.3)}
§ .usw-sw i{filter:blur(3px);width:20px;height:20px;opacity:.95}
§ .usw-nm{font-weight:700}
§ .usw-ds{color:rgba(236,239,255,.62)}
§ .usw-ck{border:1.5px solid rgba(255,255,255,.35)}
§ .usw-it.cur .usw-ck{border-color:transparent;background:linear-gradient(120deg,#6f8dff,#b57bff);box-shadow:0 0 12px rgba(130,120,255,.8)}
""",
    # Analog: cream instrument panel with pressed-in selection and orange lamp (day + night)
    "design2": r"""
§ .usw-menu{border:1px solid #8b9583;border-radius:9px;color:#202e25;
  background:linear-gradient(180deg,#f1f2e9,#d9ddd0);
  box-shadow:inset 0 1px rgba(255,255,255,.9),0 3px 0 #7a8474,0 7px 0 #111c16,0 16px 26px rgba(0,0,0,.35)}
§ .usw-head{margin-bottom:6px;padding:5px 8px 9px;border-bottom:1px solid #b7bbae;box-shadow:0 1px rgba(255,255,255,.7);
  color:#687466;font-size:10.5px;font-weight:800;letter-spacing:.16em;text-transform:uppercase}
§ .usw-it{border-color:#a9b1a0;border-radius:6px;background:linear-gradient(180deg,#f7f8f0,#e1e5d8);
  box-shadow:inset 0 1px #fff,0 2px 0 #9aa391;transition:transform .12s,box-shadow .12s,background .15s}
§ .usw-it:hover{background:linear-gradient(180deg,#fff,#ebeee2)}
§ .usw-it:active{transform:translateY(2px);box-shadow:inset 0 2px 4px rgba(0,0,0,.2)}
§ .usw-it.cur{border-color:#8b9583;background:#cfd5c8;box-shadow:inset 0 3px 6px rgba(39,54,42,.25),0 1px rgba(255,255,255,.8)}
§ .usw-sw{border:1px solid #6d7968;border-radius:4px;box-shadow:inset 0 2px 4px rgba(0,0,0,.25)}
§ .usw-nm{font-weight:800;color:#202e25}
§ .usw-ds{color:#687466}
§ .usw-ck{background:#b9bfae;box-shadow:inset 0 2px 3px rgba(0,0,0,.35),0 1px rgba(255,255,255,.8)}
§ .usw-it.cur .usw-ck{background:#ee7950;box-shadow:0 0 8px 2px rgba(238,121,80,.65),inset 0 1px rgba(255,255,255,.5)}
html[data-theme='night'] § .usw-menu{border-color:#405047;color:#dce6d9;background:linear-gradient(180deg,#344139,#222e27);
  box-shadow:inset 0 1px rgba(255,255,255,.08),0 3px 0 #18221d,0 7px 0 #050a07,0 16px 28px rgba(0,0,0,.5)}
html[data-theme='night'] § .usw-head{border-bottom-color:#445349;box-shadow:0 1px rgba(255,255,255,.04);color:#93a297}
html[data-theme='night'] § .usw-it{border-color:#526359;background:linear-gradient(180deg,#46564c,#2e3d34);color:#e0e9df;
  box-shadow:inset 0 1px rgba(255,255,255,.12),0 2px 0 #18221d}
html[data-theme='night'] § .usw-it:hover{background:linear-gradient(180deg,#506256,#35463c)}
html[data-theme='night'] § .usw-it.cur{background:#19271f;border-color:#405349;box-shadow:inset 0 3px 6px rgba(0,0,0,.5),0 1px rgba(255,255,255,.05)}
html[data-theme='night'] § .usw-nm{color:#eef4ea}
html[data-theme='night'] § .usw-ds{color:#93a297}
html[data-theme='night'] § .usw-ck{background:#17251c;box-shadow:inset 0 2px 3px rgba(0,0,0,.6),0 1px rgba(255,255,255,.06)}
html[data-theme='night'] § .usw-it.cur .usw-ck{background:#fa9b6c;box-shadow:0 0 9px 2px rgba(250,155,108,.6)}
""",
}

# Native-looking design picker, injected into the header of whichever UI is loaded (after every page load).
SWITCHER_JS = r"""
(function () {
  if (document.getElementById('__uiSwitch')) return;
  var UIS = __UIS__, CUR = __CUR__, CSS = __CSS__, ICONS = __ICONS__;
  var TITLE = {ar: 'تغيير التصميم', en: 'Change design'};
  var BUSY = {ar: 'أنهِ العملية الحالية أولاً', en: 'Finish the current task first'};
  var FAIL = {ar: 'تعذّر تغيير التصميم', en: 'Could not switch design'};
  var st = document.createElement('style');
  st.id = '__uiSwitchCss'; st.textContent = CSS; document.head.appendChild(st);
  function icon(n) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
           'stroke-linejoin="round" aria-hidden="true" focusable="false">' + (ICONS[n] || '') + '</svg>';
  }
  var cur = UIS.filter(function (u) { return u.id === CUR; })[0] || UIS[0];
  var host = document.createElement('div');
  host.id = '__uiSwitch';
  host.innerHTML =
    '<button type="button" class="btn glass sm usw-btn" aria-haspopup="true" aria-expanded="false">' +
      icon(cur.icon) + '<span class="usw-cur"></span></button>' +
    '<div class="usw-menu" role="menu"><div class="usw-head"></div>' +
      UIS.map(function (u) {
        return '<button type="button" class="usw-it" role="menuitemradio" data-ui="' + u.id + '" ' +
          'style="--c0:' + u.sw[0] + ';--c1:' + u.sw[1] + ';--c2:' + u.sw[2] + '">' +
          '<span class="usw-sw"><i></i><i></i></span>' +
          '<span class="usw-tx"><b class="usw-nm"></b><small class="usw-ds"></small></span>' +
          '<span class="usw-ck" aria-hidden="true"></span></button>';
      }).join('') +
    '</div><div class="usw-toast" role="status"></div>';
  var end = document.querySelector('.top-end'), lb = document.getElementById('langBtn');
  if (end) end.insertBefore(host, lb && lb.parentNode === end ? lb : null);
  else { host.className = 'usw-float'; document.body.appendChild(host); }

  var btn = host.querySelector('.usw-btn'), menu = host.querySelector('.usw-menu'), toastEl = host.querySelector('.usw-toast');
  var items = Array.prototype.slice.call(host.querySelectorAll('.usw-it'));
  function lang() { return (document.documentElement.lang || 'ar').toLowerCase().indexOf('en') === 0 ? 'en' : 'ar'; }
  function find(id) { return UIS.filter(function (x) { return x.id === id; })[0]; }
  function refresh() {
    var l = lang();
    btn.title = TITLE[l];
    host.querySelector('.usw-cur').textContent = cur[l];
    host.querySelector('.usw-head').textContent = TITLE[l];
    items.forEach(function (it) {
      var u = find(it.dataset.ui);
      it.querySelector('.usw-nm').textContent = u[l];
      it.querySelector('.usw-ds').textContent = u[l + '_d'];
      it.classList.toggle('cur', u.id === CUR);
      it.setAttribute('aria-checked', u.id === CUR ? 'true' : 'false');
    });
  }
  function setOpen(v) {
    host.classList.toggle('open', v);
    btn.setAttribute('aria-expanded', v ? 'true' : 'false');
    if (v) toastEl.classList.remove('show');
  }
  var tt = null;
  function toast(msg) {
    toastEl.textContent = msg; toastEl.classList.add('show'); setOpen(false);
    clearTimeout(tt); tt = setTimeout(function () { toastEl.classList.remove('show'); }, 2600);
  }
  btn.addEventListener('click', function (e) { e.stopPropagation(); setOpen(!host.classList.contains('open')); });
  document.addEventListener('click', function (e) { if (!host.contains(e.target)) setOpen(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });
  items.forEach(function (it) {
    it.addEventListener('click', function () {
      if (it.dataset.ui === CUR) { setOpen(false); return; }
      var api = window.pywebview && window.pywebview.api;
      if (!api || !api.set_ui) { toast(FAIL[lang()]); return; }
      api.set_ui(it.dataset.ui).then(function (r) {
        if (r && r.ok) setOpen(false);
        else toast((r && r.code === 'busy' ? BUSY : FAIL)[lang()]);
      }, function () { toast(FAIL[lang()]); });
    });
  });
  new MutationObserver(refresh).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
  refresh();
})();
"""

# Used by --selftest: proves the switcher button is drawn with the design's own button style and the menu is usable.
SWITCH_PROBE = r"""
(function () {
  var h = document.getElementById('__uiSwitch'); if (!h) return 'MISSING';
  var b = h.querySelector('.usw-btn'), l = document.getElementById('langBtn');
  var cb = getComputedStyle(b), cl = getComputedStyle(l);
  var same = cb.borderRadius === cl.borderRadius && cb.borderTopColor === cl.borderTopColor &&
             cb.fontFamily === cl.fontFamily && cb.color === cl.color;
  b.click();
  var m = h.querySelector('.usw-menu'), r = m.getBoundingClientRect();
  var inside = r.left >= -1 && r.right <= innerWidth + 1 && r.top >= -1 && r.bottom <= innerHeight + 1;
  var pt = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  var onTop = !!pt && h.contains(pt);
  var names = [].map.call(h.querySelectorAll('.usw-it'), function (i) { return i.querySelector('.usw-nm').textContent; });
  b.click();
  return JSON.stringify({label: b.innerText.trim(), sameStyleAsLangBtn: same, menuInsideWindow: inside,
                         menuOnTop: onTop, items: names, closedAgain: getComputedStyle(m).display === 'none'});
})()
"""


def switcher_js(cur: str) -> str:
    uis = [{"id": k, "ar": v["ar"], "en": v["en"], "ar_d": v["ar_d"], "en_d": v["en_d"], "icon": v["icon"], "sw": v["sw"]}
           for k, v in UIS.items() if ui_index(k).is_file()]
    css = (SWITCH_CSS_COMMON + SWITCH_CSS.get(cur, "")).replace("§", "#__uiSwitch")
    return (SWITCHER_JS.replace("__UIS__", json.dumps(uis, ensure_ascii=False))
            .replace("__CUR__", json.dumps(cur))
            .replace("__ICONS__", json.dumps(ICONS))
            .replace("__CSS__", json.dumps(css, ensure_ascii=False)))


def webview2_installed() -> bool:
    if os.name != "nt":
        return True
    import winreg
    guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    keys = ((winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
            (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
            (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{guid}"))
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as k:
                v, _ = winreg.QueryValueEx(k, "pv")
                if v and v != "0.0.0.0":
                    return True
        except OSError:
            pass
    return False


class Job:
    _counter = 0

    def __init__(self, kind, stages):
        Job._counter += 1
        self.id, self.kind = Job._counter, kind
        self.stages = [{"id": i, "weight": w, "state": "pending", "frac": 0.0} for i, w in stages]
        self.logs, self.extra = [], {}
        self.status, self.result, self.error = "running", None, None
        self.t0, self.t_end = time.time(), None
        self.cancel = threading.Event()

    def stage(self, sid):
        return next((s for s in self.stages if s["id"] == sid), None)

    def percent(self):
        live = [s for s in self.stages if s["state"] != "skipped"]
        total = sum(s["weight"] for s in live) or 1
        done = sum(s["weight"] * (1.0 if s["state"] == "done" else s["frac"]) for s in live)
        return min(100.0, done / total * 100)


class Api:
    """Methods of this class are callable from JavaScript: pywebview.api.<name>(...)"""

    def __init__(self):
        self._lock = threading.RLock()
        self._job = None
        self._window = None
        self._ffver = None
        self._settings_file = data_dir() / "settings.json"
        saved = self.get_settings().get("ui")
        self._ui = saved if saved in UIS and ui_index(saved).is_file() else DEFAULT_UI

    # ---------- info / settings ----------
    def get_info(self):
        if self._ffver is None:
            self._ffver = ytdisk.ffmpeg_version()
        info = {"version": APP_VERSION, "ffmpeg": bool(self._ffver), "ffmpeg_version": self._ffver,
                "frozen": bool(getattr(sys, "frozen", False))}
        try:
            info.update(ytdl.status())
        except Exception as e:
            info.update({"ytdlp": None, "js_runtime": None, "ejs": False, "ytdlp_error": str(e)})
        return info

    def get_settings(self):
        try:
            return json.loads(self._settings_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def set_settings(self, patch):
        s = self.get_settings()
        s.update(patch or {})
        try:
            self._settings_file.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return True

    # ---------- UI switching ----------
    def get_uis(self):
        return {"current": self._ui,
                "uis": [{"id": k, "ar": v["ar"], "en": v["en"]} for k, v in UIS.items() if ui_index(k).is_file()]}

    def set_ui(self, ui_id):
        if ui_id not in UIS or not ui_index(ui_id).is_file():
            return {"ok": False, "code": "unknown_ui"}
        with self._lock:
            if self._busy():          # don't swap the page under a running encode/restore
                return {"ok": False, "code": "busy"}
            self._ui = ui_id
        self.set_settings({"ui": ui_id})
        threading.Thread(target=self._navigate, args=(ui_id,), daemon=True).start()
        return {"ok": True, "ui": ui_id}

    def _navigate(self, ui_id):
        time.sleep(0.12)              # let the JS call return before the page is replaced
        try:
            self._window.load_url(ui_index(ui_id).as_uri())
        except Exception:
            traceback.print_exc()

    # ---------- dialogs / files ----------
    def _first(self, r):
        if not r:
            return None
        return r if isinstance(r, str) else r[0]

    def pick_file(self, kind="any", directory=""):
        types = VIDEO_TYPES if kind == "video" else ("All files (*.*)",)
        return self._first(self._window.create_file_dialog(
            FD_OPEN, directory=directory or "", allow_multiple=False, file_types=types))

    def pick_folder(self, directory=""):
        return self._first(self._window.create_file_dialog(FD_FOLDER, directory=directory or ""))

    def pick_save(self, name="video.mp4", directory=""):
        return self._first(self._window.create_file_dialog(
            FD_SAVE, directory=directory or "", save_filename=name, file_types=("MP4 video (*.mp4)",)))

    def file_info(self, path):
        p = Path(path or "")
        if not p.is_file():
            return {"ok": False}
        return {"ok": True, "path": str(p), "name": p.name, "size": p.stat().st_size, "dir": str(p.parent),
                "default_out": str(p.with_name(p.stem + "_ytdisk.mp4"))}

    def estimate(self, size, block, nsym, encrypted):
        try:
            return ytdisk.estimate(int(size), int(block), int(nsym), bool(encrypted))
        except Exception:
            return None

    def reveal(self, path):
        p = Path(path or "")
        if p.is_file():
            subprocess.Popen(["explorer", f"/select,{p}"])
        elif p.is_dir():
            os.startfile(str(p))
        elif p.parent.is_dir():
            os.startfile(str(p.parent))
        return True

    def open_path(self, path):
        p = Path(path or "")
        if p.is_file() and p.suffix.lower() not in UNSAFE_EXT:
            os.startfile(str(p))
            return True
        return False

    def open_url(self, url):
        if str(url).startswith("https://"):
            webbrowser.open(url)
        return True

    def check_url(self, url, browser=None):
        try:
            return {"ok": True, **ytdl.check_url(url, browser)}
        except YtdiskError as e:
            return {"ok": False, "code": e.code, "message": e.message}
        except Exception as e:
            return {"ok": False, "code": "unexpected", "message": str(e)[:300]}

    # ---------- jobs ----------
    def _progress(self, job):
        def cb(stage, frac, info=None):
            with self._lock:
                s = job.stage(stage)
                if not s:
                    return
                for p in job.stages:
                    if p is s:
                        break
                    if p["state"] in ("pending", "active"):
                        p["state"], p["frac"] = "done", 1.0
                if stage == "header" and info is not None and not info.get("encrypted"):
                    d = job.stage("decrypt")
                    if d:
                        d["state"] = "skipped"
                s["frac"] = max(0.0, min(1.0, frac))
                s["state"] = "done" if frac >= 1 else "active"
        return cb

    def _log(self, job):
        def cb(msg):
            with self._lock:
                job.logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        return cb

    def _finish(self, job, status, result=None, error=None):
        with self._lock:
            job.status, job.result, job.error, job.t_end = status, result, error, time.time()
            for s in job.stages:
                if status == "done" and s["state"] in ("pending", "active"):
                    s["state"], s["frac"] = "done", 1.0
                elif s["state"] == "active":
                    s["state"] = "error" if status == "error" else "cancelled"
            job.extra = {}

    def _start(self, job, fn, *args):
        def run():
            try:
                fn(job, *args)
            except Cancelled:
                self._finish(job, "cancelled")
            except YtdiskError as e:
                self._finish(job, "error", error={"code": e.code, "message": e.message, "detail": e.detail, **e.info})
            except Exception as e:
                self._finish(job, "error", error={"code": "unexpected", "message": str(e),
                                                  "trace": traceback.format_exc()})
        self._job = job
        threading.Thread(target=run, daemon=True).start()

    def _busy(self):
        return bool(self._job and self._job.status == "running")

    def start_encode(self, o):
        with self._lock:
            if self._busy():
                return {"ok": False, "code": "busy"}
            src = Path(o.get("file") or "")
            if not src.is_file():
                return {"ok": False, "code": "file_missing"}
            pw = o.get("password") or None
            out = Path(o.get("output") or src.with_name(src.stem + "_ytdisk.mp4"))
            if out.suffix.lower() != ".mp4":
                out = out.with_suffix(".mp4")
            if not o.get("overwrite"):
                out = ytdisk.unique_path(out)
            stages = [("read", 5)] + ([("encrypt", 3)] if pw else []) + [("ecc", 27), ("frames", 60), ("finish", 5)]
            job = Job("encode", stages)
            self._start(job, self._run_encode, o, src, out, pw)
            return {"ok": True, "id": job.id}

    def _run_encode(self, job, o, src, out, pw):
        log = self._log(job)
        log(f"encode: {src.name}")
        res = ytdisk.encode_file(src, out, int(o.get("block", ytdisk.BLOCK)), int(o.get("nsym", ytdisk.NSYM)), pw,
                                 on_progress=self._progress(job), on_log=log, should_cancel=job.cancel.is_set)
        self._finish(job, "done", result={
            "out": res["out"], "name": res["name"], "size": res["size"], "sha": res["sha256"],
            "video_bytes": res["video_bytes"], "video_seconds": res["video_seconds"],
            "frames": res["frames"], "encrypted": res["encrypted"], "elapsed": res["elapsed"]})

    def start_restore(self, o):
        with self._lock:
            if self._busy():
                return {"ok": False, "code": "busy"}
            url = (o.get("url") or "").strip()
            from_url = o.get("source") == "url"
            if from_url and not url:
                return {"ok": False, "code": "url_missing"}
            if not from_url and not Path(o.get("file") or "").is_file():
                return {"ok": False, "code": "file_missing"}
            out_dir = o.get("out_dir") or str(Path.home() / "Downloads")
            pw = o.get("password") or None
            stages = ([("download", 40)] if from_url else []) + [("header", 4), ("frames", 34), ("ecc", 14)] \
                + ([("decrypt", 3)] if pw else []) + [("verify", 5)]
            job = Job("restore", stages)
            self._start(job, self._run_restore, o, from_url, url, out_dir, pw)
            return {"ok": True, "id": job.id}

    def _run_restore(self, job, o, from_url, url, out_dir, pw):
        log = self._log(job)
        video, downloaded = o.get("file"), False
        try:
            if from_url:
                log("yt-dlp: " + url)

                def dl(frac, info):
                    with self._lock:
                        s = job.stage("download")
                        s["state"], s["frac"] = "active", frac
                        job.extra = {k: info.get(k) for k in ("speed", "eta", "done", "total")}
                video = ytdl.download_video(url, out_dir, dl, job.cancel.is_set, o.get("browser"))
                downloaded = True
                with self._lock:
                    s = job.stage("download")
                    s["state"], s["frac"], job.extra = "done", 1.0, {}
                log("downloaded: " + os.path.basename(video))
            res = ytdisk.decode_video_ex(video, out_dir, pw, on_progress=self._progress(job), on_log=log,
                                         should_cancel=job.cancel.is_set, overwrite=False)
            res["video_path"] = None
            if downloaded:
                if res["ok"] and not o.get("keep_video"):
                    try:
                        os.remove(video)
                    except OSError:
                        pass
                else:
                    res["video_path"] = video
            self._finish(job, "done", result=res)
        except YtdiskError as e:
            self._finish(job, "error", error={"code": e.code, "message": e.message, "detail": e.detail, **e.info,
                                              "video_path": video if downloaded else None})

    def cancel(self):
        with self._lock:
            if self._busy():
                self._job.cancel.set()
        return True

    def poll(self, since=0, job_id=0):
        with self._lock:
            j = self._job
            if not j:
                return {"job": None}
            if j.id != job_id:
                since = 0
            elapsed = (j.t_end or time.time()) - j.t0
            p = j.percent()
            eta = elapsed * (100 - p) / p if j.status == "running" and p > 3 else None
            return {"job": {
                "id": j.id, "kind": j.kind, "status": j.status, "percent": round(p, 2),
                "stages": [{"id": s["id"], "state": s["state"], "frac": round(s["frac"], 4)} for s in j.stages],
                "logs": j.logs[since:], "log_next": len(j.logs), "elapsed": elapsed, "eta": eta,
                "extra": j.extra, "result": j.result, "error": j.error}}


def selftest(window, api, outfile):
    """Drives the real UI of EVERY design (switcher click, tabs, encode, restore, YouTube check) and writes a report."""
    from urllib.parse import unquote
    lines = []

    def L(*a):
        lines.append(" ".join(str(x) for x in a))
        Path(outfile).write_text("\n".join(lines), encoding="utf-8")

    def js(code):
        try:
            return window.evaluate_js(code)
        except Exception:
            return None

    def wait_state(tab, timeout=300):
        t = time.time()
        while time.time() - t < timeout:
            st = js(f"document.querySelector('#tab-{tab} [data-role=badge]').dataset.state")
            if st in ("done", "error", "cancelled"):
                return st
            time.sleep(0.4)
        return "timeout"

    def wait_ready(timeout=40):
        t = time.time()
        while time.time() - t < timeout:
            if js("window.__ready===true && window.__old!==true && !!document.getElementById('__uiSwitch')") is True:
                return True
            time.sleep(0.3)
        return False

    orig_ui = api.get_settings().get("ui")
    orig_lang = api.get_settings().get("lang")
    try:
        import hashlib
        L("frozen:", bool(getattr(sys, "frozen", False)))
        if not wait_ready():
            L("FIRST PAGE NOT READY", js("JSON.stringify(window.__errors||[])"))
        info = api.get_info()
        L("js runtime:", info.get("js_runtime"), "| path:", info.get("js_runtime_path"),
          "| BUNDLED inside exe:", info.get("js_runtime_bundled"), "| ejs:", info.get("ejs"), "| yt-dlp:", info.get("ytdlp"))
        L("ffmpeg:", info.get("ffmpeg_version"))
        import shutil
        L("node on PATH:", shutil.which("node"), "| deno on PATH:", shutil.which("deno"))
        jp = info.get("js_runtime_path")
        if jp:
            try:
                L("js runtime runs:", subprocess.check_output(
                    [jp, "--version"], text=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).strip())
            except Exception as e:
                L("js runtime FAILED to run:", repr(e))

        tmp = Path(tempfile.mkdtemp(prefix="ytd_ui_"))
        src = tmp / "hello world.bin"
        src.write_bytes(os.urandom(250_000))
        sha = hashlib.sha256(src.read_bytes()).hexdigest()
        order = [k for k in ("design1", "design2", "default") if ui_index(k).is_file()]
        busy_checked = False

        for ui in order:
            L(f"\n===== UI: {ui} =====")
            # switch through the real floating picker (same path a user takes)
            js("window.__old=true")
            clicked = js(f"(function(){{var b=document.querySelector('#__uiSwitch [data-ui=\"{ui}\"]');"
                         f"if(!b)return false;b.click();return true}})()")
            ok = wait_ready()
            sheet = unquote(js("(document.querySelector('link[rel=stylesheet]')||{}).href||''") or "")
            expect = UIS[ui]["dir"] + "/style.css"
            L("picker click:", clicked, "| loaded:", ok, "| right folder:", sheet.endswith(expect),
              "| saved in settings:", api.get_settings().get("ui") == ui)
            L("errors:", js("JSON.stringify(window.__errors||[])"))
            L("switcher:", js(SWITCH_PROBE))
            L("tabs:", js("document.querySelectorAll('.tab').length"), "| lang/dir:",
              js("document.documentElement.lang+'/'+document.documentElement.dir"))
            js("document.getElementById('langBtn').click()")
            time.sleep(0.3)
            L("lang toggled ->", js("document.documentElement.lang+'/'+document.documentElement.dir"))
            js("document.getElementById('langBtn').click()")
            L("chips:", js("document.getElementById('chips').innerText.replace(/\\n/g,' | ')"))

            # YouTube link check through the UI
            js("var e=document.getElementById('rsUrl');e.value='https://www.youtube.com/watch?v=jNQXAC9IVRw';"
               "e.dispatchEvent(new Event('input'))")
            js("document.getElementById('rsCheck').click()")
            t = time.time()
            while time.time() - t < 90 and js("document.getElementById('rsCheckOut').hidden") is not False:
                time.sleep(0.5)
            L("yt check (UI):", (js("document.getElementById('rsCheckOut').innerText") or "").replace("\n", " | ")[:140])

            # encode with password
            js(f"window.__test.setEncodeFile({json.dumps(str(src))})")
            time.sleep(1.2)
            L("enc estimate:", js("document.getElementById('encEstimate').innerText"))
            js("document.getElementById('encPwToggle').click()")
            js("var e=document.getElementById('encPw');e.value='s3cret';e.dispatchEvent(new Event('input'))")
            js("document.getElementById('encStart').click()")
            if not busy_checked:
                time.sleep(0.8)
                L("switch while encoding ->", api.set_ui("design1" if ui != "design1" else "design2"))
                busy_checked = True
            st = wait_state("encode")
            res = json.loads(js("JSON.stringify(window.__lastResult||window.__lastError||null)") or "null")
            L("encode:", st, {k: res.get(k) for k in ("video_bytes", "video_seconds", "code")} if res else None)

            if st == "done":
                js("document.querySelector('[data-tab=restore]').click()")
                js(f"window.__test.setRestoreFile({json.dumps(res['out'])})")
                js(f"window.__test.setRestoreOut({json.dumps(str(tmp / ('restored_' + ui)))})")
                time.sleep(1)
                js("document.getElementById('rsStart').click()")      # no password on purpose
                st2 = wait_state("restore")
                err = json.loads(js("JSON.stringify(window.__lastError||null)") or "null")
                L("restore w/o password:", st2, err and err.get("code"))
                js("document.getElementById('rsPwToggle').click()")
                js("var e=document.getElementById('rsPw');e.value='s3cret';e.dispatchEvent(new Event('input'))")
                js("document.getElementById('rsStart').click()")
                st3 = wait_state("restore")
                r3 = json.loads(js("JSON.stringify(window.__lastResult||window.__lastError||null)") or "null")
                L("restore with password:", st3, r3 and {k: r3.get(k) for k in ("ok", "code")})
                if st3 == "done":
                    got = hashlib.sha256(Path(r3["out"]).read_bytes()).hexdigest()
                    L("BYTE-IDENTICAL:", got == sha)
            L("final errors:", js("JSON.stringify(window.__errors||[])"))

        L("\n===== YouTube download (engine) =====")
        try:
            dl = ytdl.download_video("https://www.youtube.com/watch?v=jNQXAC9IVRw", tmp / "dl",
                                     lambda f, i: None, None, None, fmt="bestvideo[height<=360]")
            L("yt download ok:", dl, Path(dl).stat().st_size)
        except Exception as e:
            L("yt download FAILED:", repr(e))
        L("SELFTEST DONE")
    except Exception:
        L("SELFTEST EXCEPTION\n" + traceback.format_exc())
    finally:
        try:   # leave the user's real settings as they were
            api.set_settings({"ui": orig_ui or DEFAULT_UI, "lang": orig_lang or "ar"})
        except Exception:
            pass
        try:
            window.destroy()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--selftest", metavar="REPORT_FILE")
    args = ap.parse_args()

    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YtDisk.App")
        except Exception:
            pass
        if not webview2_installed():
            import ctypes
            if ctypes.windll.user32.MessageBoxW(
                    0, "WebView2 Runtime غير مثبّت / is not installed.\n\nOpen the download page?",
                    APP_NAME, 0x24) == 6:
                webbrowser.open(WEBVIEW2_URL)
            return

    api = Api()
    window = webview.create_window(
        APP_NAME, url=str(ui_index(api._ui)), js_api=api, width=1120, height=800,
        min_size=(960, 700), background_color="#0a0c14", hidden=bool(args.selftest))
    api._window = window

    last_drop = {"sig": None, "t": 0.0}

    def on_loaded():
        try:                                   # floating design picker (re-injected after every page load)
            window.evaluate_js(switcher_js(api._ui))
        except Exception:
            pass
        try:
            from webview.dom import DOMEventHandler

            def on_drop(e):
                files = (e.get("dataTransfer") or {}).get("files") or []
                paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
                now = time.time()
                if paths and not (last_drop["sig"] == paths and now - last_drop["t"] < 0.6):   # handlers pile up per page load
                    last_drop["sig"], last_drop["t"] = paths, now
                    window.evaluate_js(f"window.onNativeDrop&&window.onNativeDrop({json.dumps(paths)})")
            window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        except Exception:
            pass

    window.events.loaded += on_loaded
    window.events.closing += lambda: api.cancel()

    if args.selftest:
        webview.start(selftest, (window, api, args.selftest), debug=args.debug,
                      private_mode=True)
    else:
        webview.start(debug=args.debug, private_mode=False, storage_path=str(data_dir() / "webview"))


if __name__ == "__main__":
    main()
