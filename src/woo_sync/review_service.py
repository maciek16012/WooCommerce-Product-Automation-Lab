"""Internal, token-authenticated adapter to the Stage 3 workflow (stdlib only).

No browser API, arbitrary file paths, provider URLs or write-on-GET endpoints.
Configuration is checked at startup, never at module import.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .ai_providers import get_provider, PROVIDER_NAMES
from .content_proposals import CONTENT_FIELDS, apply_approved, build_proposal
from .core import ApiError, ValidationError, WooClient, load_csv, sync, validate_sku
from .locking import sync_lock
from .proposal_io import (load_proposal, replace_proposal, review_proposal,
                          write_materialized_csv, write_new_proposal)
from .sources import load_source

MAX_BODY = 64 * 1024
MESSAGES = {
    'unauthorized': 'Backend authentication failed. Check server configuration.',
    'bad_request': 'Invalid request. Reload the product and try again.',
    'not_found': 'Product or proposal not found. Select a product and generate a proposal.',
    'conflict': 'Proposal is stale, unreviewed or busy. Reload, review or regenerate it.',
    'source_invalid': 'Catalog validation failed. Check the local source and media manifest.',
    'provider_failed': 'AI provider unavailable, unconfigured or returned invalid content. Retry after checking configuration.',
    'woo_failed': 'WooCommerce operation failed. Inspect the local report and run PLAN again; do not blindly repeat APPLY.',
    'unavailable': 'Backend configuration or storage is unavailable.',
    'too_large': 'Request exceeds the allowed size.',
    'media_type': 'Content-Type application/json is required.',
    'method': 'Unsupported request method.',
}


class ServiceError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(MESSAGES[code])


@dataclass(frozen=True)
class Config:
    token: str = field(repr=False)
    source: Path = Path('/app/data/catalog.json')
    media: Path | None = Path('/app/data/media.local.json')
    state: Path = Path('/app/state')
    credentials: Path = Path('/run/secrets/woocommerce.json')
    wc_url: str = 'http://localhost:8090'
    wc_transport_url: str = 'http://wordpress'

    def __post_init__(self):
        if not isinstance(self.token, str) or not self.token.strip():
            raise ValueError('AI_REVIEW_TOKEN must be configured before startup')
        if any(ord(c) <= 32 or ord(c) >= 127 for c in self.token):
            raise ValueError('AI_REVIEW_TOKEN must be a printable ASCII token without spaces')

    @classmethod
    def from_env(cls):
        if os.getenv('AI_REVIEW_STOCK_AUTHORITY', 'woocommerce') != 'woocommerce':
            raise ValueError('Review service requires WooCommerce stock ownership')
        media = os.getenv('AI_REVIEW_MEDIA', '/app/data/media.local.json')
        return cls(os.getenv('AI_REVIEW_TOKEN', ''),
                   Path(os.getenv('AI_REVIEW_SOURCE', '/app/data/catalog.json')),
                   Path(media) if media else None,
                   Path(os.getenv('AI_REVIEW_STATE', '/app/state')),
                   Path(os.getenv('AI_REVIEW_CREDENTIALS', '/run/secrets/woocommerce.json')),
                   os.getenv('AI_REVIEW_WC_URL', 'http://localhost:8090'),
                   os.getenv('AI_REVIEW_WC_TRANSPORT_URL', 'http://wordpress'))


class ReviewService:
    def __init__(self, config):
        self.config = config
        self.proposals = config.state / 'proposals'
        self.logs = config.state / 'logs'
        self.materialized = config.state / 'materialized'
        for path in (self.proposals, self.logs, self.materialized):
            path.mkdir(parents=True, exist_ok=True)

    def source_rows(self):
        try:
            return load_source(self.config.source, media_path=self.config.media)
        except (ValidationError, OSError, ValueError):
            raise ServiceError(409, 'source_invalid') from None

    def proposal_path(self, sku):
        validate_sku(sku)
        return self.proposals / (hashlib.sha256(sku.casefold().encode()).hexdigest() + '.json')

    def row(self, rows, sku):
        matches = [row for row in rows if row.sku.casefold() == sku.casefold()]
        if len(matches) != 1:
            raise ServiceError(404, 'not_found')
        return matches[0]

    def load_active(self, path, sku, expected=None):
        if not path.is_file():
            raise ServiceError(404, 'not_found')
        proposal = load_proposal(path)
        if (len(proposal['items']) != 1
                or proposal['items'][0]['sku'].casefold() != sku.casefold()
                or (expected and proposal['proposal_id'] != expected)):
            raise ServiceError(409, 'conflict')
        return proposal

    @staticmethod
    def content(row):
        return {field: row.extra.get(field, '') for field in CONTENT_FIELDS}

    def view(self, row, proposal=None):
        result = {'exists': proposal is not None, 'sku': row.sku,
                  'current': self.content(row)}
        if proposal:
            item = proposal['items'][0]
            result.update(proposal_id=proposal['proposal_id'],
                          created_at=str(proposal.get('created_at', '')),
                          approval=item['approval'],
                          proposed={key: item['proposed'].get(key, row.extra.get(key, ''))
                                    for key in CONTENT_FIELDS},
                          review={key: item.get('review', {}).get(key, '')
                                  for key in ('decision', 'reviewed_at')})
        return result

    def client(self):
        try:
            values = json.loads(self.config.credentials.read_text(encoding='utf-8'))
            key, secret = (values[k] for k in ('WC_CONSUMER_KEY', 'WC_CONSUMER_SECRET'))
            if not all(isinstance(v, str) and v for v in (key, secret)):
                raise ValueError
            return WooClient(self.config.wc_url, key, secret,
                             allowed_http_hosts=('wordpress',),
                             transport_url=self.config.wc_transport_url)
        except (OSError, ValueError, KeyError, TypeError):
            raise ServiceError(503, 'unavailable') from None

    def run_sync(self, rows, proposal, apply):
        # One full-source synchronization at a time, also across processes.
        with sync_lock(self.config.state / 'woocommerce.lock'):
            materialized = apply_approved(rows, proposal)
            run_id = uuid.uuid4().hex
            csv_path = self.materialized / (run_id + '.csv')
            write_materialized_csv(csv_path, materialized)
            validated = load_csv(csv_path)
            api = self.client()
            log = self.logs / (run_id + '.jsonl')
            counts = sync(validated, api, apply, log,
                          stock_authority='woocommerce', quiet=True)
            operations = []
            allowed_changes = {'type', 'sku', 'name', 'regular_price', 'manage_stock',
                               'stock_quantity', 'status', 'description',
                               'short_description', 'categories', 'images', 'meta_data'}
            for line in log.read_text(encoding='utf-8').splitlines():
                record = json.loads(line)
                if 'action' in record:
                    operations.append({
                        'sku': record.get('sku', ''),
                        'action': record['action'],
                        'product_id': record.get('product_id'),
                        'changes': {key: value for key, value in record.get('changes', {}).items()
                                    if key in allowed_changes},
                    })
            result = dict(mode='APPLIED' if apply else 'PLAN', counts=counts,
                          requests=api.stats, operations=operations,
                          proposal_id=proposal['proposal_id'])
            if counts['ERROR']:
                result['error'] = 'woo_failed'
                result['message'] = MESSAGES['woo_failed']
            return result

    def execute(self, method, path, data):
        if method == 'GET' and path == '/products':
            return {'products': [dict(sku=row.sku, name=row.name, **self.content(row))
                                 for row in self.source_rows()]}
        expected_fields = {'sku'}
        if path == '/propose': expected_fields.add('provider')
        if path == '/review': expected_fields.add('decision')
        if set(data) - expected_fields - {'proposal_id'} or not expected_fields <= set(data):
            raise ServiceError(400, 'bad_request')
        sku = data['sku']
        try: validate_sku(sku)
        except ValidationError: raise ServiceError(400, 'bad_request') from None
        expected = data.get('proposal_id')
        if expected is not None and (not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{32}', expected)):
            raise ServiceError(400, 'bad_request')
        if path == '/propose' and data['provider'] not in PROVIDER_NAMES:
            raise ServiceError(400, 'bad_request')
        if path == '/review' and data['decision'] not in ('approved', 'rejected'):
            raise ServiceError(400, 'bad_request')
        proposal_path = self.proposal_path(sku)
        # Different from review_proposal's inner lock: avoids recursive OS locking.
        with sync_lock(proposal_path.with_suffix('.operation.lock')):
            rows = self.source_rows()
            row = self.row(rows, sku)
            if path == '/propose':
                try:
                    proposal = build_proposal([row], get_provider(data['provider']), 'canonical catalog')
                except Exception:
                    raise ServiceError(502, 'provider_failed') from None
                if proposal_path.exists(): replace_proposal(proposal_path, proposal)
                else: write_new_proposal(proposal_path, proposal)
                return self.view(row, proposal)
            if path == '/proposal' and not proposal_path.exists():
                return self.view(row)
            proposal = self.load_active(proposal_path, sku, expected)
            if path == '/review':
                # set_approval is called by the existing serialized review helper.
                proposal = review_proposal(proposal_path, row.sku, data['decision'])
                return self.view(row, proposal)
            if path == '/proposal': return self.view(row, proposal)
            if proposal['items'][0]['approval'] != 'approved':
                raise ServiceError(409, 'conflict')
            return self.run_sync(rows, proposal, apply=(path == '/apply'))

    def redact(self, result):
        # Defense in depth for unexpected secret-bearing catalog/API strings.
        hidden = [self.config.token, str(self.config.credentials), str(self.config.source),
                  os.getenv('OPENAI_API_KEY', ''), os.getenv('LLAMACPP_BASE_URL', ''),
                  self.config.wc_url, self.config.wc_transport_url]
        try:
            credentials = json.loads(self.config.credentials.read_text(encoding='utf-8'))
            hidden += [credentials.get(key, '') for key in ('WC_CONSUMER_KEY', 'WC_CONSUMER_SECRET')]
        except (OSError, ValueError, TypeError, AttributeError): pass
        hidden = [v for v in hidden if isinstance(v, str) and v]
        def clean(value):
            if isinstance(value, str):
                for secret in hidden: value = value.replace(secret, '[redacted]')
                return value
            if isinstance(value, list): return [clean(v) for v in value]
            if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
            return value
        return clean(result)

    def dispatch(self, method, target, headers, body_reader):
        """Transport-independent boundary, exercised offline without sockets."""
        try:
            if method == 'GET' and target == '/health':
                return 200, {'status': 'ok', 'service': 'ai-review'}
            supplied = headers.get_all('X-Lab-Token', [])
            if len(supplied) != 1 or not secrets.compare_digest(supplied[0].encode(), self.config.token.encode()):
                raise ServiceError(401, 'unauthorized')
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                raise ServiceError(400, 'bad_request')
            if method not in ('GET', 'POST'): raise ServiceError(405, 'method')
            if (method, parsed.path) not in {('GET', '/products'), ('GET', '/proposal'),
                    ('POST', '/propose'), ('POST', '/review'), ('POST', '/plan'), ('POST', '/apply')}:
                raise ServiceError(404, 'not_found')
            if method == 'GET':
                if parsed.path == '/products' and parsed.query:
                    raise ServiceError(400, 'bad_request')
                values = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=3)
                if parsed.path == '/proposal' and (set(values) != {'sku'} or len(values['sku']) != 1):
                    raise ServiceError(400, 'bad_request')
                data = {key: value[0] for key, value in values.items()}
            else:
                if parsed.query or headers.get_all('Transfer-Encoding'):
                    raise ServiceError(400, 'bad_request')
                types = headers.get_all('Content-Type', [])
                if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
                    raise ServiceError(415, 'media_type')
                lengths = headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not re.fullmatch('[0-9]+', lengths[0]):
                    raise ServiceError(400, 'bad_request')
                length = int(lengths[0])
                if length > MAX_BODY: raise ServiceError(413, 'too_large')
                raw = body_reader(length)
                if len(raw) != length: raise ServiceError(400, 'bad_request')
                def unique(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result: raise ValueError
                        result[key] = value
                    return result
                data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if not isinstance(data, dict): raise ServiceError(400, 'bad_request')
            result = self.redact(self.execute(method, parsed.path, data))
            return (502 if result.get('error') else 200), result
        except ServiceError as exc:
            return exc.status, {'error': exc.code, 'message': MESSAGES[exc.code]}
        except ValidationError:
            return 409, {'error': 'conflict', 'message': MESSAGES['conflict']}
        except (ValueError, UnicodeError, TypeError, RecursionError):
            return 400, {'error': 'bad_request', 'message': MESSAGES['bad_request']}
        except ApiError:
            return 502, {'error': 'woo_failed', 'message': MESSAGES['woo_failed']}
        except Exception:
            return 503, {'error': 'unavailable', 'message': MESSAGES['unavailable']}


class Handler(BaseHTTPRequestHandler):
    server_version = 'AIReview'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass  # Do not log URL, headers, request content or exceptions.

    def handle_request(self):
        status, result = self.server.service.dispatch(self.command, self.path, self.headers, self.rfile.read)
        payload = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = handle_request


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, service):
        self.service = service
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try: super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Never print internal tracebacks, even on disconnected clients.


def main():
    try:
        service = ReviewService(Config.from_env())
        server = Server(('0.0.0.0', 8081), service)
    except Exception:
        print('AI review service refused startup: check private configuration and storage.')
        return 2
    print('AI review service started (internal API).', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0
