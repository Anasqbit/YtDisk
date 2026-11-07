import re
src = open('ui/i18n.js', encoding='utf-8').read()
i_en = src.index('\n  en:')
ar_blk, en_blk = src[:i_en], src[i_en:]
pair = re.compile(r'(\w+):\s*"((?:[^"\\]|\\.)*)"')
ar = dict(pair.findall(ar_blk)); en = dict(pair.findall(en_blk))
print('ar keys', len(ar), 'en keys', len(en))
print('missing in ar:', sorted(set(en)-set(ar)))
print('missing in en:', sorted(set(ar)-set(en)))
arabic = re.compile(r'[\u0600-\u06FF]')
print('ar values w/o Arabic letters:')
for k,v in ar.items():
    if not arabic.search(v): print('  ', k, '=', v)
print('ar values with Latin words (>=4 letters):')
for k,v in ar.items():
    w = re.findall(r'[A-Za-z]{4,}', re.sub(r'\{\w+\}','',v))
    if arabic.search(v) and w: print('  ', k, '=', v, '| latin:', w)
used = set()
for f in ('ui/index.html','ui/app.js'):
    t = open(f, encoding='utf-8').read()
    used |= set(re.findall(r'data-i18n(?:-[a-z]+)?="(\w+)"', t))
    used |= set(re.findall(r'\bt\(\s*[\'"`](\w+)[\'"`]', t))
print('used keys missing from ar:', sorted(k for k in used if k not in ar))
print('used keys missing from en:', sorted(k for k in used if k not in en))
print('--- hardcoded text in index.html (no data-i18n):')
h = open('ui/index.html', encoding='utf-8').read()
for m in re.finditer(r'<(\w+)([^>]*)>([^<>{}]*[A-Za-z]{3,}[^<>{}]*)</\1>', h):
    if 'data-i18n' not in m.group(2): print('  ', m.group(1), m.group(2).strip()[:50], '=>', m.group(3).strip()[:60])
print('--- attrs placeholder/title/aria/alt without i18n:')
for m in re.finditer(r'<(\w+)([^>]*)>', h):
    a = m.group(2)
    for attr in ('placeholder','title','aria-label','alt'):
        mm = re.search(attr+r'="([^"]*[A-Za-z]{3,}[^"]*)"', a)
        if mm and ('data-i18n' not in a): print('  ', m.group(1), attr, '=', mm.group(1)[:60])
print('--- string literals in app.js with English words:')
js = open('ui/app.js', encoding='utf-8').read()
for n,line in enumerate(js.splitlines(),1):
    if re.search(r'textContent\s*=\s*[\'"`][^\'"`]*[A-Za-z]{3,}|placeholder|title\s*=\s*[\'"`][A-Za-z]|innerHTML\s*=\s*[\'"`][^<]*[A-Za-z]{3,}', line) and 'data-i18n' not in line:
        print('  ', n, line.strip()[:140])
