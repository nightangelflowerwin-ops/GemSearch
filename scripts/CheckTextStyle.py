import html
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = chr(8212)
ESCAPED = re.compile(r"\\(?:u" + format(ord(FORBIDDEN), '04x') + r"|U" + format(ord(FORBIDDEN), '08x') + r"|u\{" + format(ord(FORBIDDEN), 'x') + r"\})", re.IGNORECASE)


def violations(text):
    return [number for number, line in enumerate(text.splitlines(), 1) if FORBIDDEN in html.unescape(line) or ESCAPED.search(line)]


def main():
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split(chr(0))
    failures = []
    checked = 0
    for name in filter(None, paths):
        if Path(name).name != 'package-lock.json' and any(mark in Path(name).name for mark in ['_', '-']):
            failures.append(name + ': filename contains a separator')
        path = ROOT / name
        try:
            text = path.read_bytes().decode('utf-8-sig')
        except UnicodeDecodeError:
            continue
        checked += 1
        failures.extend(str(path.relative_to(ROOT)) + ':' + str(number) for number in violations(text))
    if failures:
        print('Forbidden punctuation found in tracked files:')
        print('\n'.join(failures))
        return 1
    print('Text style check passed for ' + str(checked) + ' tracked text files.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
