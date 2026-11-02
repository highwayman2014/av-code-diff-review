"""Check a built review page against the final design. Standard library only.

Usage:
    python -I check-review.py review-<TASK>.html

Exit code 0: the page keeps the template form. Exit code 1: list of violations.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALLOWED_SCRIPT = "onbeforeprint=()=>document.querySelectorAll('details').forEach(d=>d.open=true)"


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    page = Path(sys.argv[1]).read_text(encoding='utf-8')
    tpl = (HERE / 'review-template.html').read_text(encoding='utf-8')
    errors = []

    style = lambda s: re.search(r'<style>(.*?)</style>', s, re.S).group(1)
    if style(page) != style(tpl):
        errors.append('CSS differs from review-template.html')
    if page.count('<style') != 1:
        errors.append('extra <style> blocks')
    if re.search(r'\sstyle="', page.split('<svg', 1)[0]):
        errors.append('inline style attributes outside SVG')
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', page, re.S)
    if scripts != [ALLOWED_SCRIPT]:
        errors.append('scripts differ from the single print script')
    if re.search(r'(?:src|href)="(?:https?:)?//', page):
        errors.append('external resources or links')
    if '<link' in page or '@import' in page or '@font-face' in page:
        errors.append('external stylesheets or fonts')

    sections = re.findall(r'<section class="m[^"]*" id="([^"]+)">(.*?)</section>', page, re.S)
    if not sections:
        errors.append('no method sheets')
    toc = re.findall(r'<li><a href="#([^"]+)">', page)
    if toc != [s[0] for s in sections]:
        errors.append('table of contents does not match method sheets')
    for sid, body in sections:
        if not re.search(r'<h2>.+? <small>метод (добавлен|удалён|изменён)</small><a class="up" href="#top">', body):
            errors.append(f'{sid}: heading without state or link to contents')
        if '<p class="lead">' not in body:
            errors.append(f'{sid}: no thesis (lead)')
        units = re.findall(r'<div class="u" id="([^"]+)">(.*?)(?=<div class="u" id=|$)', body, re.S)
        for uid, unit in units:
            if not uid.startswith(sid + '-'):
                errors.append(f'{sid}: unit id {uid} does not follow <method>-<n>')
            if '<div class="note above">' not in unit:
                errors.append(f'{uid}: unit without explanation')
            elif not re.search(r'<div class="note above"><a class="ln"[^>]*>#</a><p(?: class="warn")?><b>', unit):
                errors.append(f'{uid}: first sentence of the explanation is not bold')
    size = len(page.encode())
    if size > 200_000:
        errors.append(f'page is {size} bytes; split the review or fold more lines (collapse)')

    if errors:
        print('\n'.join('FAIL ' + e for e in errors))
        sys.exit(1)
    print(f'OK {len(sections)} methods, {size} bytes')


if __name__ == '__main__':
    main()
