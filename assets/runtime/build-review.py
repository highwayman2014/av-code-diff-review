"""Static code review page. Design: DESIGN.md (final, v7). Standard library only.

Usage:
    python -I build-review.py specs/<TASK>.json

The spec (JSON) holds all content. This script and review-template.html hold all form.
Do not edit this script or the template for a single review; write the spec instead.
"""
import difflib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / 'review-template.html'
CONTEXT = 3                      # unchanged lines shown around a change
BLOCK_TYPES = {'text', 'flow', 'pseudo', 'diagram', 'table'}
PLACES = {None, 'summary', 'before'}
esc = html.escape


def fail(msg):
    raise SystemExit(f'spec error: {msg}')


# ---------- git ----------

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args]).decode('utf-8-sig')


def file_lines(repo, rev, path):
    """Lines of a file at a revision; empty when the file does not exist there."""
    try:
        return git(repo, 'show', f'{rev}:{path}').splitlines()
    except subprocess.CalledProcessError:
        return []


def method(lines, name):
    start = next((i for i, l in enumerate(lines) if re.match(r'(Функция|Процедура)\s+' + re.escape(name) + r'\(', l)), None)
    if start is None:
        return [], 0
    end = next(i for i in range(start + 1, len(lines)) if re.match(r'Конец(Функции|Процедуры)', lines[i]))
    return lines[start:end + 1], start + 1


# ---------- BSL highlighting ----------

KW = set('''если тогда иначеесли иначе конецесли для каждого из по цикл конеццикла пока процедура функция
конецпроцедуры конецфункции возврат знач экспорт перем новый и или не попытка исключение конецпопытки
вызватьисключение продолжить прервать выполнить and or not if then else elsif endif for each in to do
enddo while procedure function endprocedure endfunction return val export var new try except endtry
raise continue break'''.split())
LIT = set('истина ложь неопределено null true false undefined'.split())
QW = '''ВЫБРАТЬ РАЗРЕШЕННЫЕ РАЗЛИЧНЫЕ КАК ИЗ ГДЕ И ИЛИ НЕ В ПОМЕСТИТЬ ИНДЕКСИРОВАТЬ ПО СГРУППИРОВАТЬ
УПОРЯДОЧИТЬ ОБЪЕДИНИТЬ ВСЕ ЛЕВОЕ ПРАВОЕ ВНУТРЕННЕЕ ПОЛНОЕ СОЕДИНЕНИЕ ВЫБОР КОГДА ТОГДА ИНАЧЕ КОНЕЦ ЕСТЬ
NULL ЕСТЬNULL СУММА КОЛИЧЕСТВО МАКСИМУМ МИНИМУМ ИМЕЮЩИЕ ЗНАЧЕНИЕ ЛОЖЬ ИСТИНА'''.split()
QRE = re.compile(r'(&\w+)|(?<!\w)(' + '|'.join(sorted(QW, key=len, reverse=True)) + r')(?!\w)')
TOK = re.compile(r'(//.*)|(")|(\d+(?:\.\d+)?)|([^\W\d]\w*)|(\s+|.)')
PSEUDO_KW = set('если тогда иначе конецесли цикл конеццикла возврат'.split())


def span(cls, text):
    return f'<span class="{cls}">{text}</span>'


def hl_string(text):
    out, pos = [], 0
    for m in QRE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        out.append(span('p' if m.group(1) else 'q', esc(m.group(0))))
        pos = m.end()
    out.append(esc(text[pos:]))
    return span('s', ''.join(out))


def string_end(line, i):
    """Index after closing quote, or None if the string continues on the next line."""
    while True:
        j = line.find('"', i)
        if j < 0:
            return None
        if line[j + 1:j + 2] == '"':
            i = j + 2
            continue
        return j + 1


def highlight(lines, kw=KW):
    """Highlight a sequence of BSL lines; string state carries across lines."""
    result, in_str = [], False
    for line in lines:
        out, i = [], 0
        if in_str:
            end = string_end(line, 0)
            if end is None:
                result.append(hl_string(line))
                continue
            out.append(hl_string(line[:end]))
            i, in_str = end, False
        elif re.match(r'\s*[&#]\w+', line):
            result.append(span('p', esc(line)))
            continue
        while i < len(line):
            m = TOK.match(line, i)
            cm, quote, num, word, other = m.groups()
            if cm:
                out.append(span('cm', esc(cm)))
            elif quote:
                end = string_end(line, i + 1)
                if end is None:
                    out.append(hl_string(line[i:]))
                    in_str = True
                    i = len(line)
                    continue
                out.append(hl_string(line[i:end]))
                i = end
                continue
            elif num:
                out.append(span('n', num))
            elif word:
                low = word.lower()
                out.append(span('k', esc(word)) if low in kw else span('n', esc(word)) if low in LIT else esc(word))
            else:
                out.append(esc(other))
            i = m.end()
        result.append(''.join(out))
    return result


# ---------- extra blocks ----------

def diagram(edges, mark, uid):
    nodes = []
    for a, b in edges:
        for n in (a, b):
            if n not in nodes:
                nodes.append(n)
    preds = {n: [a for a, b in edges if b == n] for n in nodes}
    layer = {n: 0 for n in nodes}
    for _ in nodes:
        for a, b in edges:
            layer[b] = max(layer[b], layer[a] + 1)
    last = max(layer.values())          # all outputs share the last column
    for n in nodes:
        if not any(a == n for a, _ in edges):
            layer[n] = last
    layers = [[n for n in nodes if layer[n] == k] for k in range(last + 1)]
    pos = {}
    for k, ln in enumerate(layers):
        if k:
            ln.sort(key=lambda n: sum(pos[p] for p in preds[n]) / len(preds[n]))
            if k == len(layers) - 1:
                ln.sort()               # numbered outputs read top to bottom
        for i, n in enumerate(ln):
            pos[n] = i
    h, vgap, hgap, pad = 28, 16, 56, 2
    width = {n: round(len(n) * 7.4 + 20) for n in nodes}
    lw = [max(width[n] for n in ln) for ln in layers]
    H = max(len(ln) * h + (len(ln) - 1) * vgap for ln in layers)
    box, x = {}, pad
    for k, ln in enumerate(layers):
        top = (H - (len(ln) * h + (len(ln) - 1) * vgap)) / 2 + pad
        for i, n in enumerate(ln):
            box[n] = (x, top + i * (h + vgap), width[n])
        x += lw[k] + hgap
    W = x - hgap + pad
    parts = [f'<svg class="dg" viewBox="0 0 {W:.0f} {H + 2 * pad:.0f}" width="{W:.0f}" role="img" aria-label="{esc(" → ".join(nodes))}">',
             f'<defs><marker id="{uid}" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
             '<path d="M0,0L8,4L0,8z" style="fill:var(--mute);stroke:none"/></marker></defs>']
    for a, b in edges:
        ax, ay, aw = box[a]
        bx, by, _ = box[b]
        x1, y1, x2, y2 = ax + aw, ay + h / 2, bx - 1, by + h / 2
        mx = (x1 + x2) / 2
        parts.append(f'<path d="M{x1:.0f},{y1:.0f}C{mx:.0f},{y1:.0f} {mx:.0f},{y2:.0f} {x2:.0f},{y2:.0f}" marker-end="url(#{uid})"/>')
    for n in nodes:
        nx, ny, nw = box[n]
        cls = f' class="{mark[n]}"' if n in mark else ''
        parts.append(f'<rect{cls} x="{nx:.0f}" y="{ny:.0f}" width="{nw}" height="{h}"/>'
                     f'<text x="{nx + 10:.0f}" y="{ny + 18:.0f}">{esc(n)}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def block(b, uid):
    t = b['type']
    if t == 'pseudo':
        body = '<pre>' + '\n'.join(highlight(b['text'].strip('\n').splitlines(), PSEUDO_KW)) + '</pre>'
        label = 'псевдокод'
    elif t == 'flow':
        steps = [f'<b>{esc(s[1:-1])}</b>' if s.startswith('*') else esc(s) for s in b['steps']]
        body = '<div class="flow">' + '<span> → </span>'.join(steps) + '</div>'
        label = 'путь'
    elif t == 'table':
        head = ''.join(f'<th>{esc(c)}</th>' for c in b['head'])
        rows = ''.join('<tr>' + ''.join(f'<td>{esc(c)}</td>' for c in r) + '</tr>' for r in b['rows'])
        body = f'<table><tr>{head}</tr>{rows}</table>'
        label = 'правило'
    else:
        body = diagram(b['edges'], b.get('mark', {}), uid)
        label = 'схема'
    return f'<div class="blk"><div>{esc(b.get("label", label))}</div>{body}</div>'


def note(blocks):
    """Explanation paragraphs. First sentence of the first paragraph is bold; 'Важно:' is a risk."""
    out = []
    for k, b in enumerate(x for x in blocks if x['type'] == 'text'):
        text = b['text']
        if text.startswith('Важно:'):
            rest = text[6:].lstrip()
            rest = rest[:1].upper() + rest[1:]
            out.append(f'<p class="warn"><b>Важно.</b> {esc(rest)}</p>')
            continue
        head, dot, rest = text.partition('. ')
        if k == 0 and not dot:
            out.append(f'<p><b>{esc(text)}</b></p>')
        elif k == 0:
            out.append(f'<p><b>{esc(head)}.</b> {esc(rest)}</p>')
        else:
            out.append(f'<p>{esc(text)}</p>')
    return ''.join(out)


# ---------- diff ----------

def rows_for(old, oldline, new, newline):
    hl_old, hl_new = highlight(old), highlight(new)
    rows = []
    for kind, i, j, k, l in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        for off in range(max(j - i, l - k)):
            oi = i + off if i + off < j else None
            ni = k + off if k + off < l else None
            rows.append(dict(kind=kind,
                             left=None if oi is None else (oldline + oi, hl_old[oi]),
                             right=None if ni is None else (newline + ni, hl_new[ni])))
    return rows


def cell(side, val, cls):
    if val is None:
        return f'<div class="c {side} pad"></div>'
    n, code = val
    return f'<div class="c {side}{cls}"><i>{n}</i><code>{code or " "}</code></div>'


def row_html(r):
    changed = r['kind'] != 'equal'
    kind = {'equal': 'eq', 'replace': 'rep', 'insert': 'ins', 'delete': 'dl'}[r['kind']]
    return (f'<div class="r {kind}">' + cell('old', r['left'], ' del' if changed else '')
            + cell('new', r['right'], ' add' if changed else '') + '</div>')


def hidden_flags(rows, collapse, removed):
    """Rows to fold. collapse lists new-code line ranges (old-code ranges for a removed method)."""
    changed = [i for i, r in enumerate(rows) if r['kind'] != 'equal']
    flags = []
    for i, r in enumerate(rows):
        far = r['kind'] == 'equal' and all(abs(i - c) > CONTEXT for c in changed)
        side = r['left'] if removed else r['right']
        rn = side[0] if side else None
        forced = rn is not None and any(a <= rn <= b for a, b in collapse)
        flags.append(far or forced)
    return flags


def plural(n):
    if n % 10 == 1 and n % 100 != 11:
        return 'строка'
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return 'строки'
    return 'строк'


def code_html(rows, flags):
    out, i = [], 0
    while i < len(rows):
        if not flags[i] and rows[i]['kind'] != 'equal':
            # each side flows on its own: no blank filler rows inside a change
            j = i
            while j < len(rows) and not flags[j] and rows[j]['kind'] != 'equal':
                j += 1
            run = rows[i:j]
            left = ''.join(cell('old', r['left'], ' del') for r in run if r['left'])
            right = ''.join(cell('new', r['right'], ' add') for r in run if r['right'])
            out.append(f'<div class="rb"><div>{left}</div><div>{right}</div></div>')
            i = j
            continue
        if not flags[i]:
            out.append(row_html(rows[i]))
            i += 1
            continue
        j = i
        while j < len(rows) and flags[j]:
            j += 1
        n = j - i
        word = plural(n)
        folded = {'строка': 'свернута', 'строки': 'свернуты'}.get(word, 'свернуто')
        label = 'без изменений' if all(r['kind'] == 'equal' for r in rows[i:j]) else folded
        out.append(f'<details><summary>··· {n} {word} {label}</summary>'
                   + ''.join(row_html(r) for r in rows[i:j]) + '</details>')
        i = j
    return ''.join(out)


# ---------- method sheet ----------

def section(spec, old, oldline, new, newline, idx, path):
    rows = rows_for(old, oldline, new, newline)
    flags = hidden_flags(rows, spec.get('collapse', []), not new)
    anchors = {h['at']: h['blocks'] for h in spec['hunks']}
    found = {r['right'][0] for r in rows if r['right']} | {r['left'][0] for r in rows if not new and r['left']}
    missing = set(anchors) - found
    if missing:
        fail(f'{spec["method"]}: anchors not found {sorted(missing)}')

    # a unit starts at each anchor line (new code; old code for a removed method)
    segments, cur = [], dict(blocks=[], rows=[], flags=[])
    for r, f in zip(rows, flags):
        n = r['right'][0] if r['right'] else (r['left'][0] if not new else None)
        if n in anchors and cur['rows']:
            segments.append(cur)
            cur = dict(blocks=[], rows=[], flags=[])
        if n in anchors:
            cur['blocks'] = anchors[n]
        cur['rows'].append(r)
        cur['flags'].append(f)
    segments.append(cur)

    state = 'метод добавлен' if not old else 'метод удалён' if not new else 'метод изменён'
    whole = ' whole' if not old or not new else ''
    out = [f'<section class="m{whole}" id="{spec["id"]}"><h2>{esc(spec["method"])} <small>{state}</small>'
           '<a class="up" href="#top">к оглавлению</a></h2>']
    if path:
        out.append(f'<p class="path">{esc(path)}</p>')
    out.append(f'<p class="lead">{esc(spec["lead"])}</p>')
    sums = [b for h in spec['hunks'] for b in h['blocks'] if b.get('place') == 'summary']
    if sums:
        out.append('<div class="sum">' + ''.join(block(b, f's{idx}{i}') for i, b in enumerate(sums)) + '</div>')
    for s in segments:
        s['blocks'] = [b for b in s['blocks'] if b.get('place') != 'summary']
    # leading lines without explanation belong to the first explained unit
    if len(segments) > 1 and not segments[0]['blocks']:
        first = segments.pop(0)
        segments[0]['rows'] = first['rows'] + segments[0]['rows']
        segments[0]['flags'] = first['flags'] + segments[0]['flags']
    for k, s in enumerate(segments):
        code = f'<div class="code">{code_html(s["rows"], s["flags"])}</div>'
        text = note(s['blocks'])
        extras = [x for x in s['blocks'] if x['type'] != 'text']
        pre = ''.join(block(b, f'p{idx}{k}{i}') for i, b in enumerate(extras) if b.get('place') == 'before')
        extra = ''.join(block(b, f'a{idx}{k}{i}') for i, b in enumerate(extras) if b.get('place') != 'before')
        link = f'<a class="ln" href="#{spec["id"]}-{k + 1}" aria-label="ссылка на фрагмент {k + 1}">#</a>'
        txt = f'<div class="note above">{link}{text}</div>' if text else ''
        out.append(f'<div class="u" id="{spec["id"]}-{k + 1}">' + txt + pre + code + extra + '</div>')
    out.append('</section>')
    return ''.join(out)


# ---------- spec ----------

def normalize(spec):
    for key in ('task', 'repo', 'methods'):
        if key not in spec:
            fail(f'missing "{key}"')
    ids = set()
    for m in spec['methods']:
        for key in ('id', 'method', 'lead', 'hunks'):
            if key not in m:
                fail(f'method {m.get("method", "?")}: missing "{key}"')
        if not re.fullmatch(r'[a-z][a-z0-9-]*', m['id']) or m['id'] in ids:
            fail(f'method {m["method"]}: id must be unique latin kebab-case')
        ids.add(m['id'])
        if not (m.get('file') or spec.get('file')):
            fail(f'method {m["method"]}: no "file" in method or spec')
        m['collapse'] = [tuple(c) for c in m.get('collapse', [])]
        for h in m['hunks']:
            h['blocks'] = [dict(type='text', text=b) if isinstance(b, str) else b for b in h['blocks']]
            for b in h['blocks']:
                if b.get('type') not in BLOCK_TYPES:
                    fail(f'{m["method"]} at {h["at"]}: unknown block type {b.get("type")}')
                if b.get('place') not in PLACES:
                    fail(f'{m["method"]} at {h["at"]}: unknown place {b.get("place")}')
    return spec


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    spec_path = Path(sys.argv[1]).resolve()
    spec = normalize(json.loads(spec_path.read_text(encoding='utf-8')))
    repo = Path(spec['repo'])
    base = spec.get('base') or git(repo, 'merge-base', spec.get('main', 'main'), 'HEAD').strip()
    head = spec.get('head') or git(repo, 'rev-parse', 'HEAD').strip()
    base, head = git(repo, 'rev-parse', base).strip(), git(repo, 'rev-parse', head).strip()
    files = list(dict.fromkeys(m.get('file') or spec['file'] for m in spec['methods']))
    cache = {}

    def lines(rev, path):
        if (rev, path) not in cache:
            cache[rev, path] = file_lines(repo, rev, path)
        return cache[rev, path]

    one = len(files) == 1
    where = esc(files[0]) if one else f'{len(files)} файла' if len(files) < 5 else f'{len(files)} файлов'
    body = [f'<p class="top">{esc(spec["task"])} · {where} · {base[:7]}..{head[:7]}</p>',
            '<nav class="ov" id="top"><ol>' + ''.join(
                f'<li><a href="#{m["id"]}">{esc(m["method"])}</a></li>' for m in spec['methods']) + '</ol></nav>']
    for i, m in enumerate(spec['methods']):
        path = m.get('file') or spec['file']
        old, oldline = method(lines(base, path), m['method'])
        new, newline = method(lines(head, path), m['method'])
        if not old and not new:
            fail(f'method {m["method"]} not found in {path}')
        if old == new:
            fail(f'method {m["method"]} has no changes between {base[:7]} and {head[:7]}')
        body.append(section(m, old, oldline, new, newline, i, None if one else path))

    out = HERE / spec.get('out', f'review-{spec["task"]}.html')
    page = (TEMPLATE.read_text(encoding='utf-8')
            .replace('{{TITLE}}', f'{esc(spec["task"])} · ревью кода').replace('{{BODY}}', '\n'.join(body)))
    out.write_text(page, encoding='utf-8')
    css = re.search(r'<style>(.*?)</style>', page, re.S).group(1)
    print(json.dumps({'output': str(out), 'bytes': len(page.encode()), 'css_bytes': len(css.encode()),
                      'base': base[:7], 'head': head[:7]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
