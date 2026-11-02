"""Offline integration checks. Uses a disposable Git repository, never the project."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(*args, cwd=None, ok=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8')
    if ok and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    if not ok:
        assert result.returncode, result.stdout
    return result


def main():
    skill = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='av-review-test-') as folder:
        root = Path(folder)
        copied = root / 'portable skill'
        shutil.copytree(skill, copied)
        repo = root / 'repo'
        repo.mkdir()
        run('git', 'init', str(repo))
        def git(*args):
            return run('git', '-c', 'user.name=Review Test', '-c', 'user.email=review@example.invalid', *args, cwd=repo).stdout.strip()
        (repo / 'one.bsl').write_text('Функция СтарыйМетод() Экспорт\n\tВозврат 1;\nКонецФункции\n', encoding='utf-8')
        git('add', '.')
        git('commit', '-m', 'fixture before')
        base = git('rev-parse', 'HEAD')
        (repo / 'one.bsl').write_text('Функция НовыйМетод() Экспорт\n\tВозврат 2;\nКонецФункции\n', encoding='utf-8')
        (repo / 'two.bsl').write_text('Процедура Вторая() Экспорт\n\tСообщить("готово");\nКонецПроцедуры\n', encoding='utf-8')
        git('add', '.')
        git('commit', '-m', 'fixture after')
        head = git('rev-parse', 'HEAD')
        spec = dict(task='TEST', repo='repo', base=base, head=head, methods=[
            dict(id='removed', method='СтарыйМетод', file='one.bsl', lead='Старый метод удален.', hunks=[dict(at=1, blocks=['Старый вызов удален. Новый метод заменяет его.'])]),
            dict(id='added', method='НовыйМетод', file='one.bsl', lead='Новый метод возвращает другое значение.', hunks=[dict(at=1, blocks=['Результат изменен. Метод возвращает два.'])]),
            dict(id='second', method='Вторая', file='two.bsl', lead='Добавлено сообщение.', hunks=[dict(at=1, blocks=['Появилось сообщение. Второй модуль выводит результат.'])])])
        source = root / 'spec.json'
        source.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        source_bytes = source.read_bytes()
        output = root / 'output' / 'review.html'
        renderer = copied / 'scripts' / 'render-review.py'
        def render(ok=True, extra=()):
            return run(sys.executable, '-I', str(renderer), str(source), '--out', str(output), *extra, cwd=root, ok=ok)
        render()
        assert source.read_bytes() == source_bytes
        html = output.read_text(encoding='utf-8')
        assert 'метод удалён' in html and 'метод добавлен' in html
        assert 'one.bsl' in html and 'two.bsl' in html
        saved = output.read_bytes()
        render(ok=False)  # explicit overwrite required
        spec['methods'][0]['hunks'][0]['at'] = 900
        source.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        failure = render(ok=False, extra=('--overwrite',))
        assert 'anchors not found' in failure.stdout + failure.stderr
        assert output.read_bytes() == saved  # failed build preserves prior report
        bad = root / 'bad.html'
        bad.write_text(html.replace('</style>', 'body{color:red}</style>'), encoding='utf-8')
        failure = run(sys.executable, '-I', str(copied/'assets/runtime/check-review.py'), str(bad), ok=False)
        assert 'CSS differs' in failure.stdout
        print('OK: relocated skill; relative repo; added/deleted methods; two files; unchanged spec; overwrite guard; invalid anchor; previous result preserved; altered CSS rejected.')


if __name__ == '__main__':
    main()
