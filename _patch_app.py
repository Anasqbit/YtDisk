import io, re, sys
P = r"D:\Download\YtDisk-main\app.py"
s = io.open(P, encoding="utf-8").read()

def rep(old, new, count=1):
    global s
    assert s.count(old) == count, ("not found / ambiguous", old[:60], s.count(old))
    s = s.replace(old, new)

# ---------- A) UI registry + switcher widget ----------
rep('''def webview2_installed() -> bool:''', r'''# ---------- selectable UIs (files are never modified, the app just loads the chosen folder) ----------
UIS = {
    "default": {"dir": "ui",                  "ar": "الافتراضي", "en": "Default"},
    "design1": {"dir": "ui desien/desien 1",  "ar": "تصميم 1",   "en": "Design 1"},
    "design2": {"dir": "ui desien/desien 2",  "ar": "تصميم 2",   "en": "Design 2"},
}
DEFAULT_UI = "default"


def ui_index(ui_id: str) -> Path:
    return Path(resource_path(UIS[ui_id]["dir"])) / "index.html"


# Floating design picker, injected on top of whichever UI is loaded (lives in a shadow root, so it
# can't clash with the page CSS and the UI folders stay untouched).
SWITCHER_JS = r"""
(function () {
  if (document.getElementById('__uiSwitch')) return;
  var UIS = __UIS__, CUR = __CUR__;
  var TITLE = {ar: 'تغيير التصميم', en: 'Change design'};
  var BUSY = {ar: 'أنهِ العملية الحالية أولاً', en: 'Finish the current task first'};
  var FAIL = {ar: 'تعذّر تغيير التصميم', en: 'Could not switch design'};
  var host = document.createElement('div');
  host.id = '__uiSwitch';
  host.style.cssText = 'position:fixed;left:14px;bottom:14px;z-index:2147483000;direction:ltr';
  var root = host.attachShadow({mode: 'open'});
  root.innerHTML = `
    <style>
      *{box-sizing:border-box}
      .fab{width:38px;height:38px;border-radius:50%;border:1px solid rgba(255,255,255,.22);background:rgba(18,20,32,.80);
        backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);color:#fff;cursor:pointer;display:grid;place-items:center;
        padding:0;box-shadow:0 4px 18px rgba(0,0,0,.35);transition:transform .15s,background .15s}
      .fab:hover{transform:scale(1.07);background:rgba(34,38,60,.92)}
      .fab svg{width:19px;height:19px}
      .menu{position:absolute;left:0;bottom:46px;min-width:150px;padding:6px;border-radius:12px;display:none;
        border:1px solid rgba(255,255,255,.18);background:rgba(18,20,32,.95);backdrop-filter:blur(12px);
        box-shadow:0 8px 28px rgba(0,0,0,.45);font:13px/1.3 "Segoe UI",Tahoma,sans-serif;color:#e8eaf2}
      .menu.open{display:block}
      .it{display:flex;align-items:center;gap:9px;width:100%;padding:8px 10px;border:0;border-radius:8px;background:none;
        color:inherit;font:inherit;cursor:pointer;text-align:start}
      .it:hover{background:rgba(255,255,255,.09)}
      .dot{width:8px;height:8px;border-radius:50%;border:1.5px solid rgba(255,255,255,.45);flex:none}
      .it.cur .dot{background:#7c9cff;border-color:#7c9cff}
      .it.cur{font-weight:600}
      .toast{position:absolute;left:0;bottom:46px;white-space:nowrap;padding:7px 11px;border-radius:9px;display:none;
        background:rgba(60,24,30,.95);border:1px solid rgba(255,120,130,.4);color:#ffd9dc;font:12px "Segoe UI",Tahoma,sans-serif}
      .toast.show{display:block}
    </style>
    <button class="fab" type="button" aria-haspopup="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3a9 9 0 100 18c1.1 0 1.8-.8 1.8-1.7 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-.9.8-1.7 1.7-1.7H17a4 4 0 004-4c0-4.4-4-8.2-9-8.2z"/>
        <circle cx="7.5" cy="11" r="1"/><circle cx="10.5" cy="7.5" r="1"/><circle cx="15" cy="7.5" r="1"/>
      </svg>
    </button>
    <div class="menu" role="menu"></div>
    <div class="toast" role="status"></div>`;
  var btn = root.querySelector('.fab'), menu = root.querySelector('.menu'), toastEl = root.querySelector('.toast');
  UIS.forEach(function (u) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'it'; b.dataset.ui = u.id; b.setAttribute('role', 'menuitem');
    b.innerHTML = '<span class="dot"></span><span class="lb"></span>';
    menu.appendChild(b);
  });
  var items = Array.prototype.slice.call(menu.querySelectorAll('.it'));
  function lang() { return (document.documentElement.lang || 'ar').toLowerCase().indexOf('en') === 0 ? 'en' : 'ar'; }
  function refresh() {
    var l = lang(); btn.title = TITLE[l];
    items.forEach(function (it) {
      var u = UIS.filter(function (x) { return x.id === it.dataset.ui; })[0];
      it.querySelector('.lb').textContent = u[l];
      it.classList.toggle('cur', u.id === CUR);
    });
  }
  var tt = null;
  function toast(msg) {
    toastEl.textContent = msg; toastEl.classList.add('show'); menu.classList.remove('open');
    clearTimeout(tt); tt = setTimeout(function () { toastEl.classList.remove('show'); }, 2600);
  }
  btn.addEventListener('click', function (e) { e.stopPropagation(); toastEl.classList.remove('show'); menu.classList.toggle('open'); });
  document.addEventListener('click', function (e) { if (e.target !== host) menu.classList.remove('open'); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') menu.classList.remove('open'); });
  items.forEach(function (it) {
    it.addEventListener('click', function () {
      if (it.dataset.ui === CUR) { menu.classList.remove('open'); return; }
      var api = window.pywebview && window.pywebview.api;
      if (!api || !api.set_ui) { toast(FAIL[lang()]); return; }
      api.set_ui(it.dataset.ui).then(function (r) {
        if (r && r.ok) menu.classList.remove('open');
        else toast((r && r.code === 'busy' ? BUSY : FAIL)[lang()]);
      }, function () { toast(FAIL[lang()]); });
    });
  });
  new MutationObserver(refresh).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
  refresh();
  document.body.appendChild(host);
})();
"""


def switcher_js(cur: str) -> str:
    uis = [{"id": k, "ar": v["ar"], "en": v["en"]} for k, v in UIS.items() if ui_index(k).is_file()]
    return SWITCHER_JS.replace("__UIS__", json.dumps(uis, ensure_ascii=False)).replace("__CUR__", json.dumps(cur))


def webview2_installed() -> bool:''')

# ---------- B) Api: remember chosen UI ----------
rep('''        self._settings_file = data_dir() / "settings.json"
''', '''        self._settings_file = data_dir() / "settings.json"
        saved = self.get_settings().get("ui")
        self._ui = saved if saved in UIS and ui_index(saved).is_file() else DEFAULT_UI
''')

# ---------- C) Api: get_uis / set_ui ----------
rep('''    # ---------- dialogs / files ----------''', '''    # ---------- UI switching ----------
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

    # ---------- dialogs / files ----------''')

# ---------- D) replace selftest ----------
a = s.index("def selftest(window, api, outfile):")
b = s.index("def main():")
NEW_SELFTEST = r'''def selftest(window, api, outfile):
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
            clicked = js(f"(function(){{var r=document.getElementById('__uiSwitch').shadowRoot;"
                         f"var b=r.querySelector('[data-ui=\"{ui}\"]');if(!b)return false;b.click();return true}})()")
            ok = wait_ready()
            sheet = unquote(js("(document.querySelector('link[rel=stylesheet]')||{}).href||''") or "")
            expect = UIS[ui]["dir"] + "/style.css"
            L("picker click:", clicked, "| loaded:", ok, "| right folder:", sheet.endswith(expect),
              "| saved in settings:", api.get_settings().get("ui") == ui)
            L("errors:", js("JSON.stringify(window.__errors||[])"))
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


'''
s = s[:a] + NEW_SELFTEST + s[b:]

# ---------- E) main(): load chosen UI, inject picker, de-duplicate drops ----------
rep('APP_NAME, url=resource_path("ui/index.html"), js_api=api,', 'APP_NAME, url=str(ui_index(api._ui)), js_api=api,')

old_loaded = s[s.index("    def on_loaded():"):s.index("    window.events.loaded += on_loaded")]
new_loaded = '''    last_drop = {"sig": None, "t": 0.0}

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

'''
s = s.replace(old_loaded, new_loaded)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched OK", len(s))
