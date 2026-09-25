"""Validation precedes credentials/network; --apply explicitly enables writes."""
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from .core import ValidationError, WooClient, load_csv, sync
from .locking import sync_lock

def main(argv=None):
    parser=argparse.ArgumentParser(description='CSV → WooCommerce po SKU; domyślnie podgląd')
    parser.add_argument('command',choices=('validate','sync'))
    parser.add_argument('csv_file',type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--credentials',type=Path,default=Path('.secrets/woocommerce.json'))
    parser.add_argument('--log',type=Path)
    args=parser.parse_args(argv)
    if args.command=='validate' and args.apply: parser.error('--apply tylko dla sync')
    log=args.log or Path('logs')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.jsonl')
    try:
        rows=load_csv(args.csv_file)
        if args.command=='validate':
            log.parent.mkdir(parents=True,exist_ok=True)
            with log.open('x',encoding='utf-8') as f: f.write(json.dumps(dict(event='VALIDATION',valid=True,rows=len(rows)))+'\n')
            print(f'CSV poprawny: {len(rows)} produktów')
            return 0
        creds=json.loads(args.credentials.read_text(encoding='utf-8-sig')) if args.credentials.exists() else {}
        api=WooClient(*[os.getenv(k) or creds.get(k,'') for k in ('WC_URL','WC_CONSUMER_KEY','WC_CONSUMER_SECRET')])
        with sync_lock():
            counts=sync(rows,api,args.apply,log)
        print(json.dumps(dict(mode='APPLIED' if args.apply else 'PLAN',counts=counts,requests=api.stats,log=str(log))))
        return 1 if counts['ERROR'] else 0
    except (ValidationError,OSError,ValueError) as exc:
        message=str(exc) if isinstance(exc,ValidationError) else 'Nie można odczytać wejścia/konfiguracji lub zapisać nowego raportu'
        if not log.exists():
            log.parent.mkdir(parents=True,exist_ok=True)
            with log.open('x',encoding='utf-8') as f: f.write(json.dumps(dict(action='ERROR',phase='VALIDATION',error=message,writes=0),ensure_ascii=False)+'\n')
        print('Błąd: '+message,file=sys.stderr)
        return 2
