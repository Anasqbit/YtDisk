import shutil
from pathlib import Path

root = Path(__file__).resolve().parent
app = root / "app.py"
src = app.read_text(encoding="utf-8")
shutil.copyfile(app, root / "app.py.pre_switcher.bak")

new_block = (root / "_new_block.txt").read_text(encoding="utf-8")

a = src.index("# ---------- selectable UIs")
b = src.index("def webview2_installed")
src = src[:a] + new_block + src[b:]


def rep(old, new, count=1):
    global src
    assert src.count(old) == count, (old[:60], src.count(old))
    src = src.replace(old, new)


# selftest: click the real (now non-shadow) picker
rep('''            clicked = js(f"(function(){{var r=document.getElementById('__uiSwitch').shadowRoot;"
                         f"var b=r.querySelector('[data-ui=\\"{ui}\\"]');if(!b)return false;b.click();return true}})()")''',
    '''            clicked = js(f"(function(){{var b=document.querySelector('#__uiSwitch [data-ui=\\"{ui}\\"]');"
                         f"if(!b)return false;b.click();return true}})()")''')

# selftest: per-design switcher checks
rep('''            L("errors:", js("JSON.stringify(window.__errors||[])"))\n''',
    '''            L("errors:", js("JSON.stringify(window.__errors||[])"))
            L("switcher:", js(SWITCH_PROBE))\n''')

# selftest: prove the JS runtime is the bundled one and really runs on a PC without node on PATH
rep('''        L("ffmpeg:", info.get("ffmpeg_version"))\n''',
    '''        L("ffmpeg:", info.get("ffmpeg_version"))
        import shutil
        L("node on PATH:", shutil.which("node"), "| deno on PATH:", shutil.which("deno"))
        jp = info.get("js_runtime_path")
        if jp:
            try:
                L("js runtime runs:", subprocess.check_output(
                    [jp, "--version"], text=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).strip())
            except Exception as e:
                L("js runtime FAILED to run:", repr(e))\n''')

app.write_text(src, encoding="utf-8")
print("patched", app, len(src))
