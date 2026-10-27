# A small standard-library HTTP session for the vc-application Functions.
#
# This file is NOT part of any bundle. It is reached only through the git block of a vc-application
# Function descriptor (vc-application/functions/*/mh-function.yaml), which copies the whole payload
# directory into {task.home}/asset, so it is always the sibling of the script that imports it.
#
# Standard library only, deliberately: the Processor's Python has no requests and no browser driver
# (checked 2026-10-27), and a Function must not depend on a package nobody installed there. Cloudflare in
# front of the YC sites serves urllib with a browser-like agent (probe of 2026-10-27).
#
# What a session gives a caller:
#   - one cookie jar for every request it makes, so a sign-in carries over to the pages after it
#   - no proxy: urllib would otherwise pick one up from the OS, and whether a desktop proxy setting sits
#     between a Function and a fund's site is not a decision this Function can see being made
#   - ONE console line per request - method, host and path, never the query, a body, a cookie or a
#     header - and one per redirect hop
#   - a guard, may_send(method, url), asked BEFORE a request is sent and again before every redirect is
#     followed. A refusal raises RequestRefused and nothing leaves the Processor. The guard is the
#     caller's: each fund's adapter decides what a survey of that fund may send.

import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple

DEFAULT_TIMEOUT_SEC = 20

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/130.0 Safari/537.36')

# status: the HTTP status of the LAST hop; url: where the request ended after redirects; text: the body
Response = namedtuple('Response', ['status', 'url', 'text'])

# get(url, headers=None) -> Response; post_json(url, payload, headers=None) -> Response; cookie(name) -> str|None
Session = namedtuple('Session', ['get', 'post_json', 'cookie'])


class RequestRefused(RuntimeError):
    """The session's guard refused a request, or a redirect, before anything was sent."""


def describe(method, url):
    """The console form of a request: method, host and path. The query is dropped - a 'continue' url, a
    token or an id may ride in it."""
    parts = urllib.parse.urlsplit(url)
    return method + ' ' + parts.netloc + parts.path


def _guarded_redirect_handler(may_send, log):
    """urllib's redirect handler, asking the guard before each hop is followed and logging the hop."""

    class GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            new = super().redirect_request(req, fp, code, msg, headers, newurl)
            if new is not None:
                method = new.get_method()
                if not may_send(method, new.full_url):
                    raise RequestRefused('refused to follow a redirect (HTTP ' + str(code) + ') to '
                                         + describe(method, new.full_url))
                log('  redirect ' + str(code) + ' -> ' + describe(method, new.full_url))
            return new

    return GuardedRedirectHandler()


def open_session(may_send, log, timeout=DEFAULT_TIMEOUT_SEC):
    """A Session whose every request and redirect is first put to may_send(method, url)."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPCookieProcessor(jar),
                                         _guarded_redirect_handler(may_send, log))

    def send(method, url, headers, body):
        if not may_send(method, url):
            raise RequestRefused('refused before sending: ' + describe(method, url))
        request = urllib.request.Request(url, data=body, method=method,
                                         headers={'User-Agent': USER_AGENT, **(headers or {})})
        log(describe(method, url))
        try:
            with opener.open(request, timeout=timeout) as response:
                result = Response(response.status, response.geturl(),
                                  response.read().decode('utf-8', errors='replace'))
        except urllib.error.HTTPError as e:
            # an HTTP error status is RETURNED, not raised: which status it was is what the caller reads
            result = Response(e.code, e.geturl() or url, e.read().decode('utf-8', errors='replace'))
        except urllib.error.URLError as e:
            raise RuntimeError('cannot reach ' + describe(method, url) + ': ' + str(e.reason)) from None
        log('  -> HTTP ' + str(result.status) + ' at ' + describe(method, result.url).split(' ', 1)[1])
        return result

    def get(url, headers=None):
        return send('GET', url, {'Accept': 'text/html,application/xhtml+xml', **(headers or {})}, None)

    def post_json(url, payload, headers=None):
        body = json.dumps(payload).encode('utf-8')
        return send('POST', url, {'Content-Type': 'application/json', 'Accept': 'application/json',
                                  **(headers or {})}, body)

    def cookie(name):
        for c in jar:
            if c.name == name:
                return c.value
        return None

    return Session(get, post_json, cookie)
