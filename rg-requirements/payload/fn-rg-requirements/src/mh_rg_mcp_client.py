# A minimal MCP client over Streamable HTTP - just enough to call the two RG tools that exist ONLY over MCP:
# mhdg_rg_open_stage and mhdg_rg_seal_snapshot. RG's REST API writes a requirement into an open STAGE, but it has no
# endpoint to open or to seal one.
#
# This file is NOT a Function. It is a module of the rg-requirements payload, imported by mh_rg_req_store_batch.py.
#
# THE PROTOCOL, as RG serves it (WebMvcStreamableServerTransportProvider, /rest/v1/legal/mcp):
#   1. POST initialize                    -> the answer, plus an Mcp-Session-Id response header
#   2. POST notifications/initialized     -> 202 and no body: a notification has no id and gets no answer
#   3. POST tools/call {name, arguments}  -> the answer
# Every POST offers Accept: application/json, text/event-stream - the server may answer with one JSON body or with a
# Server-Sent Events stream whose data: lines carry the JSON-RPC messages - and every POST after initialize carries
# the session id. Authentication is the HTTP Basic header RG's REST API takes: the server lifts the servlet's Spring
# Security Authentication into the tool call.
#
# A TOOL RESULT, as RG builds it (MhdgMcpToolDefinitions.toCallToolResult / authoringGuarded): one text content
# holding the result object as JSON, isError false - or the exception's message as text, isError true.
#
# ONE SESSION PER TOOL CALL. The store makes two MCP calls with a few hundred REST writes between them; a session of
# its own for each call costs one extra round trip and leaves no session to expire while the writes run.
#
# AN SSE ANSWER IS READ ONLY UP TO THE ANSWER. A stream the server keeps open after answering would otherwise hold
# the read until the timeout.

import json
import urllib.error
import urllib.request

PROTOCOL_VERSION = '2025-03-26'
CLIENT_INFO = {'name': 'mh.asset.rg-req-store-batch', 'version': '1.0'}
ACCEPT = 'application/json, text/event-stream'
SESSION_HEADER = 'Mcp-Session-Id'


def excerpt(text, limit=300):
    text = (text or '').strip()
    return text if len(text) <= limit else text[:limit] + '...'


def sse_events(text):
    """The data of each Server-Sent Event in a stream, in order. data: lines are joined per event with a newline,
    an event ends at an empty line, and every other line (event:, id:, comments) is ignored. Lines are split on
    newline only, never str.splitlines: a JSON payload may carry U+2028, which splitlines would read as a break."""
    events, data = [], []
    for raw in (text or '').split('\n'):
        line = raw.rstrip('\r')
        if line == '':
            if data:
                events.append('\n'.join(data))
            data = []
        elif line.startswith('data:'):
            value = line[5:]
            data.append(value[1:] if value.startswith(' ') else value)
    if data:
        events.append('\n'.join(data))
    return events


def jsonrpc_messages(content_type, text):
    """Every JSON-RPC message of one HTTP answer - an SSE stream or a JSON body (one message or a batch)."""
    if 'text/event-stream' in (content_type or ''):
        return [json.loads(data) for data in sse_events(text) if data.strip()]
    body = (text or '').strip()
    if not body:
        return []
    parsed = json.loads(body)
    return parsed if isinstance(parsed, list) else [parsed]


def answer_to(messages, request_id):
    """The message answering request_id - a result or an error; notifications and other answers are skipped."""
    for message in messages:
        if isinstance(message, dict) and message.get('id') == request_id and ('result' in message or 'error' in message):
            return message
    raise RuntimeError('the MCP server sent no answer to request ' + str(request_id))


def tool_result(answer, tool):
    """What a tools/call answered, as a dict - or a failure naming the tool and carrying the server's own words: a
    JSON-RPC error, a result flagged isError, or a result with no JSON object in it."""
    if 'error' in answer:
        error = answer.get('error') or {}
        raise RuntimeError(tool + ': MCP error ' + str(error.get('code')) + ' ' + str(error.get('message')))
    result = answer.get('result') or {}
    texts = [item.get('text') or '' for item in (result.get('content') or [])
             if isinstance(item, dict) and item.get('type') == 'text']
    if result.get('isError'):
        raise RuntimeError(tool + ' failed: ' + excerpt(' '.join(texts)))
    structured = result.get('structuredContent')
    if isinstance(structured, dict):
        return structured
    for text in texts:
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError(tool + ' answered no JSON object: ' + excerpt(' '.join(texts)))


def _has_answer(event_lines, request_id):
    data = '\n'.join(line[5:].lstrip(' ') for line in event_lines if line.startswith('data:'))
    if not data.strip():
        return False
    try:
        message = json.loads(data)
    except ValueError:
        return False
    return isinstance(message, dict) and message.get('id') == request_id


def http_post(url, headers, body, timeout, request_id=None):
    """POST and return (status, lowercased headers, body text). An HTTP error status is RETURNED, only an unreachable
    server raises. For an SSE answer to request_id, the stream is read only until that answer has arrived."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=body, method='POST', headers=headers)
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as e:
        raise RuntimeError('cannot reach the MCP server at ' + url + ': ' + str(e.reason)) from None
    with response:
        received = {k.lower(): v for k, v in response.headers.items()}
        if request_id is None or 'text/event-stream' not in received.get('content-type', ''):
            return response.status, received, response.read().decode('utf-8', errors='replace')
        lines, event = [], []
        for raw in response:
            line = raw.decode('utf-8', errors='replace').rstrip('\r\n')
            lines.append(line)
            if line == '':
                if _has_answer(event, request_id):
                    break
                event = []
            else:
                event.append(line)
        return response.status, received, '\n'.join(lines) + '\n'


class McpSession:
    """One MCP session: initialize() once, then call_tool()."""

    def __init__(self, url, authorization, timeout):
        self.url = url
        self.authorization = authorization
        self.timeout = timeout
        self.session_id = None
        self.last_id = 0

    def _headers(self):
        headers = {'Authorization': self.authorization, 'Content-Type': 'application/json', 'Accept': ACCEPT}
        if self.session_id:
            headers[SESSION_HEADER] = self.session_id
        return headers

    def _post(self, message, request_id):
        status, headers, text = http_post(self.url, self._headers(), json.dumps(message).encode('utf-8'),
                                          self.timeout, request_id)
        if status == 401:
            raise RuntimeError('the MCP server rejected the credential (HTTP 401)')
        if status == 403:
            raise RuntimeError('the MCP server refused the request (HTTP 403)')
        return status, headers, text

    def _request(self, method, params):
        self.last_id += 1
        request_id = self.last_id
        status, headers, text = self._post(
            {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}, request_id)
        if status != 200:
            raise RuntimeError(method + ': the MCP server answered HTTP ' + str(status) + ': ' + excerpt(text))
        return headers, answer_to(jsonrpc_messages(headers.get('content-type'), text), request_id)

    def initialize(self):
        headers, answer = self._request('initialize', {'protocolVersion': PROTOCOL_VERSION, 'capabilities': {},
                                                       'clientInfo': CLIENT_INFO})
        if 'error' in answer:
            raise RuntimeError('initialize: MCP error ' + str((answer.get('error') or {}).get('message')))
        self.session_id = headers.get(SESSION_HEADER.lower())
        status, _, text = self._post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, None)
        if status not in (200, 202, 204):
            raise RuntimeError('notifications/initialized: the MCP server answered HTTP ' + str(status) + ': '
                               + excerpt(text))
        return self

    def call_tool(self, name, arguments):
        _, answer = self._request('tools/call', {'name': name, 'arguments': arguments})
        return tool_result(answer, name)


def call_tool(url, authorization, name, arguments, timeout):
    """One tool call, in a session of its own."""
    return McpSession(url, authorization, timeout).initialize().call_tool(name, arguments)
