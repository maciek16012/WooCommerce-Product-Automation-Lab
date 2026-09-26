"""Initialize only a missing/placeholder local review token without printing it."""
import os
import re
import secrets
import tempfile
from pathlib import Path


def main():
    path = Path(__file__).resolve().parents[1] / '.env'
    if not path.is_file():
        raise SystemExit('Create .env from .env.example and configure database passwords first.')
    text = path.read_text(encoding='utf-8-sig')
    matches = list(re.finditer(r'^AI_REVIEW_TOKEN=(.*)$', text, re.M))
    if len(matches) > 1:
        raise SystemExit('Duplicate AI_REVIEW_TOKEN entries; resolve local configuration first.')
    if matches and matches[0].group(1).strip() not in ('', 'replace-with-random-local-token'):
        print('Existing review token preserved; no values displayed.')
        return
    entry = 'AI_REVIEW_TOKEN=' + secrets.token_hex(32)
    updated = (text[:matches[0].start()] + entry + text[matches[0].end():]
               if matches else text.rstrip() + '\n' + entry + '\n')
    fd, temporary = tempfile.mkstemp(prefix='.env.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    print('Random review token saved only to ignored .env; no values displayed.')


if __name__ == '__main__': main()
