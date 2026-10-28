# Reading a fund's form page without a browser - fund-independent.
#
# This file is NOT part of any bundle - see vc_http.py.
#
# A form page carries its fields in one of two places, and a survey reads both:
#   - the STATE a JS framework embeds in the server's HTML for its first render (embedded_state): Inertia
#     (a data-page attribute, or a <script data-page> in Inertia 2), react-rails (data-react-props),
#     react_on_rails (a js-react-on-rails-component JSON script), Next.js (__NEXT_DATA__), or any other
#     application/json script
#   - the FORM CONTROLS server-rendered HTML carries (extract_html_fields): input, textarea, select, with their
#     labels
# and describes the page's STRUCTURE (page_structure) for the case where neither yields a field: script
# paths, JSON scripts, data-* attribute names, control counts - names and counts only.
#
# NO APPLICANT CONTENT IS READ OUT. An input's value attribute and a textarea's text are never taken; the only
# values read are a choice's (an <option>, a radio or checkbox value), which define the field. The page title
# is left out: it may carry the company's name.

import json
import re
from html.parser import HTMLParser
import urllib.parse

SKIPPED_INPUT_TYPES = ('hidden', 'submit', 'button', 'reset', 'image')
SKIPPED_NAMES = ('authenticity_token', 'utf8', '_method', 'commit', 'csrf_token', 'csrfmiddlewaretoken')
CHOICE_INPUT_TYPES = ('radio', 'checkbox')
NUMERIC_LIMIT_ATTRS = ('maxlength', 'minlength', 'min', 'max', 'size')


class _PageParser(HTMLParser):
    """One pass over a page, collecting what the three readers need. Attribute values arrive unescaped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements = []          # (tag, attrs) of every start tag, in order
        self.scripts = []           # {'attrs', 'text'} of every <script>
        self.controls = []          # {'tag', 'attrs', 'label_index', 'section', 'options'}
        self.labels = []            # {'for', 'text'}
        self.forms = 0
        self._script = None
        self._label_stack = []      # indices into self.labels of the labels currently open
        self._select = None
        self._option = None
        self._heading = None
        self._section = None
        self._in_textarea = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else '') for k, v in attrs}
        self.elements.append((tag, a))
        if tag == 'script':
            self._script = {'attrs': a, 'text': []}
        elif tag == 'form':
            self.forms += 1
        elif tag == 'label':
            self.labels.append({'for': a.get('for'), 'text': []})
            self._label_stack.append(len(self.labels) - 1)
        elif tag in ('h1', 'h2', 'h3', 'h4', 'legend'):
            self._heading = []
        elif tag in ('input', 'textarea', 'select'):
            control = {'tag': tag, 'attrs': a, 'label_index': self._label_stack[-1] if self._label_stack else None,
                       'section': self._section, 'options': []}
            self.controls.append(control)
            if tag == 'select':
                self._select = control
            elif tag == 'textarea':
                # what is between <textarea> and </textarea> is what the applicant typed: never read
                self._in_textarea = True
        elif tag == 'option' and self._select is not None:
            self._option = {'value': a.get('value'), 'text': []}

    def handle_endtag(self, tag):
        if tag == 'script' and self._script is not None:
            self.scripts.append({'attrs': self._script['attrs'], 'text': ''.join(self._script['text'])})
            self._script = None
        elif tag == 'label' and self._label_stack:
            self._label_stack.pop()
        elif tag in ('h1', 'h2', 'h3', 'h4', 'legend') and self._heading is not None:
            text = ' '.join(''.join(self._heading).split())
            if text:
                self._section = text
            self._heading = None
        elif tag == 'option' and self._option is not None and self._select is not None:
            text = ' '.join(''.join(self._option['text']).split())
            value = self._option['value'] if self._option['value'] is not None else text
            self._select['options'].append({'value': value, 'label': text or None})
            self._option = None
        elif tag == 'select':
            self._select = None
        elif tag == 'textarea':
            self._in_textarea = False

    def handle_data(self, data):
        if self._script is not None:
            self._script['text'].append(data)
            return
        if self._in_textarea:
            return
        if self._option is not None:
            self._option['text'].append(data)
        for index in self._label_stack:
            self.labels[index]['text'].append(data)
        if self._heading is not None:
            self._heading.append(data)


def _parse(page_html):
    parser = _PageParser()
    parser.feed(page_html or '')
    parser.close()
    return parser


def _json_object(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _literal_end(text, start):
    """The index just past the JS object literal opening at text[start] == '{', or None when it never closes.
    Braces inside string literals do not count."""
    depth = 0
    quote = None
    escaped = False
    for k in range(start, len(text)):
        ch = text[k]
        if quote:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in '"\'`':
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return k + 1
    return None


JSON_PARSE_STRING = re.compile(r'\s*JSON\.parse\(\s*("(?:[^"\\]|\\.)*")\s*\)', re.S)


def call_arguments(text, marker):
    """Every object passed to a call that follows marker - e.g. marker 'REACT_COMPONENTS.push(' - as a dict. The
    argument may be a JSON object literal or JSON.parse("...") of a JSON string; anything else is skipped."""
    found = []
    position = 0
    while True:
        i = text.find(marker, position)
        if i < 0:
            return found
        after = i + len(marker)
        parsed = JSON_PARSE_STRING.match(text, after)
        if parsed:
            try:
                obj = _json_object(json.loads(parsed.group(1)))
            except ValueError:
                obj = None
            if obj is not None:
                found.append(obj)
            position = parsed.end()
            continue
        start = text.find('{', after)
        end = _literal_end(text, start) if start >= 0 else None
        if end is None:
            return found
        obj = _json_object(text[start:end])
        if obj is not None:
            found.append(obj)
        position = end


def sketch(text, limit=160):
    """The head of a script with the content of every string literal blanked - its shape, never its data."""
    s = re.sub(r'"(?:[^"\\]|\\.)*"', '"~"', text or '', flags=re.S)
    s = re.sub(r"'(?:[^'\\]|\\.)*'", "'~'", s, flags=re.S)
    s = re.sub(r'`(?:[^`\\]|\\.)*`', '`~`', s, flags=re.S)
    s = ' '.join(s.split())
    return s if len(s) <= limit else s[:limit] + '...'


# ---------------------------------------------------------------------------------------------------
# THE EMBEDDED STATE

def embedded_state(page_html):
    """(kind, {'component', 'version', 'props'}) for the first framework state found in the page, or (None, None).

    react-rails pages may carry several components; their props are combined as {'components': [...]}."""
    parser = _parse(page_html)

    for tag, a in parser.elements:
        if tag != 'script' and 'data-page' in a:
            page = _json_object(a['data-page'])
            if page and 'component' in page:
                return 'inertia', {'component': page.get('component'), 'version': page.get('version'),
                                   'props': page.get('props')}
    for s in parser.scripts:
        if 'data-page' in s['attrs']:
            page = _json_object(s['text'])
            if page and 'component' in page:
                return 'inertia-script', {'component': page.get('component'), 'version': page.get('version'),
                                          'props': page.get('props')}
    react = [(a.get('data-react-class'), _json_object(a.get('data-react-props')))
             for tag, a in parser.elements if 'data-react-class' in a and 'data-react-props' in a]
    react = [(c, p) for c, p in react if p is not None]
    if react:
        if len(react) == 1:
            return 'react-rails', {'component': react[0][0], 'version': None, 'props': react[0][1]}
        return 'react-rails', {'component': ', '.join(str(c) for c, _ in react), 'version': None,
                               'props': {'components': [{'component': c, 'props': p} for c, p in react]}}
    for s in parser.scripts:
        if 'js-react-on-rails-component' in (s['attrs'].get('class') or ''):
            props = _json_object(s['text'])
            if props is not None:
                return 'react-on-rails', {'component': s['attrs'].get('data-component-name'), 'version': None,
                                          'props': props}
    for s in parser.scripts:
        if s['attrs'].get('id') == '__NEXT_DATA__':
            data = _json_object(s['text'])
            if data is not None:
                return 'next', {'component': data.get('page'), 'version': data.get('buildId'),
                                'props': data.get('props')}
    # YC's apply site (E2, ExecContext #5286): inline scripts push {divId, component, props} onto
    # window.REACT_COMPONENTS, and the app bundle mounts each component on its divId
    pushed = [c for s in parser.scripts if not s['attrs'].get('src')
              for c in call_arguments(s['text'], 'REACT_COMPONENTS.push(')]
    if pushed:
        if len(pushed) == 1:
            return 'react-components', {'component': pushed[0].get('component'), 'version': None,
                                        'props': pushed[0].get('props')}
        return 'react-components', {'component': ', '.join(str(c.get('component')) for c in pushed), 'version': None,
                                    'props': {'components': [{'component': c.get('component'), 'props': c.get('props')}
                                                             for c in pushed]}}
    for s in parser.scripts:
        if (s['attrs'].get('type') or '').lower() == 'application/json':
            props = _json_object(s['text'])
            if props is not None:
                return 'json-script', {'component': s['attrs'].get('id'), 'version': None, 'props': props}
    return None, None


# ---------------------------------------------------------------------------------------------------
# THE PAGE'S STRUCTURE - names and counts only

def _path_only(src):
    parts = urllib.parse.urlsplit(src)
    return parts.netloc + parts.path


def page_structure(page_html):
    parser = _parse(page_html)
    controls = {'input': 0, 'textarea': 0, 'select': 0}
    for c in parser.controls:
        controls[c['tag']] += 1
    return {
        'bytes': len(page_html or ''),
        'scripts': [_path_only(s['attrs']['src']) for s in parser.scripts if s['attrs'].get('src')],
        'inlineScripts': sum(1 for s in parser.scripts if not s['attrs'].get('src')),
        'inlineScriptSketches': [{'bytes': len(s['text']), 'head': sketch(s['text'])}
                                 for s in parser.scripts if not s['attrs'].get('src')],
        'jsonScripts': [{'id': s['attrs'].get('id'), 'type': s['attrs'].get('type'),
                         'attributes': sorted(k for k in s['attrs'] if k not in ('id', 'type')),
                         'bytes': len(s['text'])}
                        for s in parser.scripts if 'json' in (s['attrs'].get('type') or '').lower()],
        'dataAttributes': sorted({k for _, a in parser.elements for k in a if k.startswith('data-')}),
        'elementIds': sorted({a['id'] for _, a in parser.elements if a.get('id')})[:60],
        'forms': parser.forms,
        'controls': controls,
    }


# ---------------------------------------------------------------------------------------------------
# THE FORM CONTROLS OF SERVER-RENDERED HTML

def _int_or_none(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def extract_html_fields(page_html):
    """Every form control of the page as a field, in document order; radios and checkboxes sharing a name are one
    field whose options are their values. Hidden, submit and token controls are skipped."""
    parser = _parse(page_html)
    label_for = {}
    for lab in parser.labels:
        text = ' '.join(''.join(lab['text']).split())
        if lab['for'] and text:
            label_for.setdefault(lab['for'], text)

    fields = []
    by_name = {}
    for index, c in enumerate(parser.controls):
        a = c['attrs']
        tag = c['tag']
        input_type = (a.get('type') or 'text').lower() if tag == 'input' else tag
        key = a.get('name') or a.get('id')
        if not key or input_type in SKIPPED_INPUT_TYPES or key in SKIPPED_NAMES:
            continue
        wrapping = parser.labels[c['label_index']] if c['label_index'] is not None else None
        wrapping_text = ' '.join(''.join(wrapping['text']).split()) if wrapping else None
        label = (label_for.get(a.get('id')) if a.get('id') else None) or wrapping_text or a.get('aria-label') \
            or a.get('placeholder') or a.get('title')
        if input_type in CHOICE_INPUT_TYPES:
            choice = {'value': a.get('value', 'on'), 'label': wrapping_text or label_for.get(a.get('id') or '')}
            if key in by_name:
                by_name[key]['options'].append(choice)
                continue
            field = {'key': key, 'label': c['section'] or label, 'type': input_type,
                     'required': True if 'required' in a or a.get('aria-required') == 'true' else None,
                     'options': [choice], 'limits': None, 'help': None, 'section': c['section'],
                     'path': 'html:' + tag + '[' + str(index) + ']'}
            by_name[key] = field
            fields.append(field)
            continue
        limits = {k: _int_or_none(a[k]) for k in NUMERIC_LIMIT_ATTRS if k in a and _int_or_none(a[k]) is not None}
        fields.append({
            'key': key,
            'label': label,
            'type': input_type + (' multiple' if tag == 'select' and 'multiple' in a else ''),
            'required': True if 'required' in a or a.get('aria-required') == 'true' else None,
            'options': c['options'] or None,
            'limits': limits or None,
            'help': a.get('placeholder') if a.get('placeholder') and a.get('placeholder') != label else None,
            'section': c['section'],
            'path': 'html:' + tag + '[' + str(index) + ']',
        })
    return fields
