"""CORS-enabled relay for git-over-HTTPS, so the in-browser terminal can clone, fetch and push.

Browsers can't call github.com directly (no CORS), so isomorphic-git sends requests to
    /git-proxy/<host>/<owner>/<repo>.git/<git endpoint>
and this view forwards them. It is deliberately narrow:
  * only allow-listed hosts (exact match), over https;
  * only the three git smart-HTTP endpoints, with the matching HTTP method;
  * redirects are never followed server-side (no hopping to internal addresses);
  * request/response size caps and a small per-client rate limit.
The caller's Authorization header (their own token) is passed through and never logged.
"""
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = tuple(
    h.strip().lower() for h in os.environ.get('GIT_PROXY_HOSTS', 'github.com,gitlab.com,bitbucket.org').split(',') if h.strip()
)
ALLOWED_ORIGINS = os.environ.get('GIT_PROXY_ORIGINS', '*')
MAX_REQUEST_BYTES = 25 * 1024 * 1024
MAX_RESPONSE_BYTES = 40 * 1024 * 1024
TIMEOUT_SECONDS = 60
RATE_LIMIT = (120, 60)  # requests per window (seconds) per client address

PATH_RE = re.compile(r'^[\w.\-]+(?:/[\w.\-]+){1,4}/(info/refs|git-upload-pack|git-receive-pack)$')
SERVICES = {'git-upload-pack', 'git-receive-pack'}
FORWARD_HEADERS = ('Authorization', 'Content-Type', 'Accept', 'Git-Protocol', 'Content-Encoding')
RETURN_HEADERS = ('Content-Type', 'WWW-Authenticate', 'Cache-Control', 'Expires', 'Pragma')

_hits = defaultdict(deque)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # surface 3xx to the caller instead of following it


_opener = urllib.request.build_opener(_NoRedirect)


def _cors(response, request):
    origin = request.headers.get('Origin')
    response['Access-Control-Allow-Origin'] = origin if ALLOWED_ORIGINS == '*' and origin else ALLOWED_ORIGINS
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, Accept, Git-Protocol, Content-Encoding'
    response['Access-Control-Expose-Headers'] = 'Content-Type, WWW-Authenticate, Location'
    response['Access-Control-Max-Age'] = '600'
    response['Vary'] = 'Origin'
    return response


def _reply(request, status, body=b'', content_type='text/plain'):
    return _cors(HttpResponse(body, status=status, content_type=content_type), request)


def _client(request):
    forwarded = request.headers.get('X-Forwarded-For', '')
    return forwarded.split(',')[0].strip() or request.META.get('REMOTE_ADDR', '?')


def _limited(client):
    now = time.monotonic()
    window = _hits[client]
    while window and now - window[0] > RATE_LIMIT[1]:
        window.popleft()
    if len(window) >= RATE_LIMIT[0]:
        return True
    window.append(now)
    return False


def parse_target(target):
    """'github.com/o/r.git/info/refs' -> (host, path), or None if it isn't an allowed git endpoint."""
    host, _, path = target.partition('/')
    host = host.lower()
    if host not in ALLOWED_HOSTS or '..' in path.split('/') or not PATH_RE.match(path):
        return None
    return host, path


@csrf_exempt
def git_proxy(request, target):
    try:
        return _handle(request, target)
    except Exception:  # keep CORS headers on the error so the browser reports the real problem
        logger.exception('git proxy crashed')
        return _reply(request, 500, b'The git proxy hit an internal error')


def _handle(request, target):
    if request.method == 'OPTIONS':
        return _reply(request, 204)

    parsed = parse_target(target)
    if not parsed:
        return _reply(request, 403, b'This host or path is not allowed through the git proxy.')
    host, path = parsed
    endpoint = path.rsplit('/', 1)[-1]
    is_refs = path.endswith('info/refs')

    if is_refs and request.method != 'GET':
        return _reply(request, 405, b'Method not allowed')
    if not is_refs and request.method != 'POST':
        return _reply(request, 405, b'Method not allowed')
    if is_refs and request.GET.get('service') not in SERVICES:
        return _reply(request, 400, b'Missing or unsupported service')
    if not is_refs and int(request.META.get('CONTENT_LENGTH') or 0) > MAX_REQUEST_BYTES:
        return _reply(request, 413, b'Request too large')
    if _limited(_client(request)):
        return _reply(request, 429, b'Too many requests')

    url = f'https://{host}/{path}' + (f"?service={request.GET['service']}" if is_refs else '')
    headers = {name: request.headers[name] for name in FORWARD_HEADERS if name in request.headers}
    headers['User-Agent'] = 'git/2.43.0 (codewithfriend-proxy)'
    upstream_request = urllib.request.Request(
        url, data=None if is_refs else request.body, headers=headers, method=request.method
    )

    try:
        upstream = _opener.open(upstream_request, timeout=TIMEOUT_SECONDS)
        status = upstream.status
    except urllib.error.HTTPError as error:  # 3xx/4xx/5xx still carry a body worth relaying
        upstream, status = error, error.code
    except (urllib.error.URLError, TimeoutError) as error:
        logger.warning('git proxy upstream failure for %s %s: %s', request.method, endpoint, error)
        return _reply(request, 502, b'Could not reach the git host')

    body = upstream.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        return _reply(request, 502, b'Response too large for the git proxy')

    response = _cors(HttpResponse(body, status=status), request)
    for name in RETURN_HEADERS:
        if upstream.headers.get(name):
            response[name] = upstream.headers[name]
    location = upstream.headers.get('Location')
    if location and status in (301, 302, 303, 307, 308):
        match = re.match(r'^https://([^/]+)/(.*)$', location)
        if match and match.group(1).lower() in ALLOWED_HOSTS:  # keep redirects inside the proxy
            response['Location'] = request.build_absolute_uri(f'/git-proxy/{match.group(1)}/{match.group(2)}')
    return response
