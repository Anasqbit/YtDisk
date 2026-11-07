import io, shutil
P = r"D:\Download\YtDisk-main\ui desien\desien 2\i18n.js"
shutil.copyfile(P, P + ".bak")
s = io.open(P, encoding="utf-8").read()
i = s.index("/* This mock is only for the static preview")
tail = s[i:]
assert "if (!window.pywebview)" in tail and tail.rstrip().endswith("}")
s = s[:i].rstrip() + "\n"
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("mock removed; bytes:", len(s))
