# Unit tests of vc_page.py. Every page is built here, in the format the framework it imitates writes:
# html.escape'd JSON inside an attribute, raw JSON inside a <script>, plain server-rendered form controls.

import html
import json

import vc_page as p

PAGE = {'component': 'Apps/Edit', 'version': 'v9', 'props': {'sections': [{'title': 'Company'}]}}


def attr_json(value):
    return html.escape(json.dumps(value), quote=True)


# --- the embedded state ---------------------------------------------------------------------------

def test_inertia_attribute():
    doc = '<div id="app" data-page="' + attr_json(PAGE) + '"></div>'
    assert p.embedded_state(doc) == ('inertia', {'component': 'Apps/Edit', 'version': 'v9', 'props': PAGE['props']})


def test_inertia_2_script_element():
    doc = '<script data-page="app" type="application/json">' + json.dumps(PAGE) + '</script><div id="app"></div>'
    assert p.embedded_state(doc)[0] == 'inertia-script'
    assert p.embedded_state(doc)[1]['props'] == PAGE['props']


def test_react_rails_one_component():
    doc = '<div data-react-class="ApplicationForm" data-react-props="' + attr_json({'questions': []}) + '"></div>'
    assert p.embedded_state(doc) == ('react-rails', {'component': 'ApplicationForm', 'version': None,
                                                     'props': {'questions': []}})


def test_react_rails_several_components_are_combined():
    doc = ('<div data-react-class="Nav" data-react-props="' + attr_json({'a': 1}) + '"></div>'
           '<div data-react-class="Form" data-react-props="' + attr_json({'b': 2}) + '"></div>')
    kind, state = p.embedded_state(doc)
    assert kind == 'react-rails'
    assert state['props'] == {'components': [{'component': 'Nav', 'props': {'a': 1}},
                                             {'component': 'Form', 'props': {'b': 2}}]}


def test_react_on_rails_script():
    doc = ('<script type="application/json" class="js-react-on-rails-component" data-component-name="AppForm">'
           + json.dumps({'fields': []}) + '</script>')
    assert p.embedded_state(doc) == ('react-on-rails', {'component': 'AppForm', 'version': None,
                                                        'props': {'fields': []}})


def test_next_data():
    doc = ('<script id="__NEXT_DATA__" type="application/json">'
           + json.dumps({'page': '/apps/[id]/edit', 'buildId': 'b1', 'props': {'pageProps': {}}}) + '</script>')
    assert p.embedded_state(doc) == ('next', {'component': '/apps/[id]/edit', 'version': 'b1',
                                              'props': {'pageProps': {}}})


def test_other_json_script():
    doc = '<script id="form-schema" type="application/json">{"questions": [1]}</script>'
    assert p.embedded_state(doc) == ('json-script', {'component': 'form-schema', 'version': None,
                                                     'props': {'questions': [1]}})


def test_no_embedded_state():
    assert p.embedded_state('<html><script src="/app.js"></script><div id="root"></div></html>') == (None, None)


COMPONENT = {'divId': '87cc2352', 'component': 'components/ApplyEdit',
             'props': {'questionLabels': {'describe': {'q': 'Describe what your company does'}}}}


def test_react_components_push_of_a_json_literal():
    doc = ('<div id="87cc2352"></div><script>window.REACT_COMPONENTS = window.REACT_COMPONENTS || [];\n'
           'window.REACT_COMPONENTS.push(' + json.dumps(COMPONENT) + ');</script>')
    assert p.embedded_state(doc) == ('react-components', {'component': 'components/ApplyEdit', 'version': None,
                                                          'props': COMPONENT['props']})


def test_react_components_push_of_json_parse():
    doc = '<script>window.REACT_COMPONENTS.push(JSON.parse(' + json.dumps(json.dumps(COMPONENT)) + '));</script>'
    assert p.embedded_state(doc)[1]['props'] == COMPONENT['props']


def test_react_components_several_pushes_are_combined():
    nav = {'divId': 'a', 'component': 'Nav', 'props': {'x': 1}}
    doc = ('<script>window.REACT_COMPONENTS.push(' + json.dumps(nav) + ')</script>'
           '<script>window.REACT_COMPONENTS.push(' + json.dumps(COMPONENT) + ')</script>')
    kind, state = p.embedded_state(doc)
    assert kind == 'react-components'
    assert state['component'] == 'Nav, components/ApplyEdit'
    assert state['props'] == {'components': [{'component': 'Nav', 'props': {'x': 1}},
                                             {'component': 'components/ApplyEdit', 'props': COMPONENT['props']}]}


def test_react_components_push_with_bare_wrapper_keys_as_yc_writes_it():
    # the shape E3 (ExecContext #5295) observed: a JS literal with bare keys around JSON props, across lines
    props = {'app': {'uuid': 'u-1', 'questions': {}}, 'questionLabels': {'describe': {'q': 'Describe {it} "briefly"'}},
             'component': 'not-the-wrapper'}
    doc = ('<div id="5ac0418c"></div><script>\n'
           'window.REACT_COMPONENTS = window.REACT_COMPONENTS || []\n'
           'window.REACT_COMPONENTS.push({\n'
           '  divId: "5ac0418c",\n'
           '  component: "components/apply/ApplicationEdit",\n'
           '  props: ' + json.dumps(props) + '\n'
           '})\n</script>')
    assert p.embedded_state(doc) == ('react-components', {'component': 'components/apply/ApplicationEdit',
                                                          'version': None, 'props': props})


def test_react_component_pushes_empty_props_and_several_pushes():
    text = ('window.REACT_COMPONENTS.push({ divId: "a", component: "Nav", props: {} })\n'
            'window.REACT_COMPONENTS.push({ divId: "b", component: "Edit", props: {"x": 1} })')
    assert p.react_component_pushes(text) == [{'component': 'Nav', 'props': {}}, {'component': 'Edit', 'props': {'x': 1}}]


def test_react_component_pushes_skips_props_that_are_not_json():
    assert p.react_component_pushes('window.REACT_COMPONENTS.push({ divId: "a", component: "X", props: {a: 1} })') == []


def test_call_arguments_braces_inside_strings_do_not_count():
    text = 'X.push({"a": "}{ \\" }", "b": {"c": 1}}); X.push({"d": 2})'
    assert p.call_arguments(text, 'X.push(') == [{'a': '}{ " }', 'b': {'c': 1}}, {'d': 2}]


def test_call_arguments_skips_a_literal_that_is_not_json():
    assert p.call_arguments('X.push({a: 1}); X.push({"b": 2})', 'X.push(') == [{'b': 2}]


def test_sketch_blanks_every_string_literal():
    assert p.sketch('window.X.push({"name": "Acme Rockets", \'k\': `t`, n: 5})') == \
        'window.X.push({"~": "~", \'~\': `~`, n: 5})'


def test_a_data_page_that_is_not_an_inertia_page_is_not_taken():
    assert p.embedded_state('<div data-page="2"></div>') == (None, None)


# --- the page's structure -------------------------------------------------------------------------

def test_page_structure_names_and_counts_only():
    doc = ('<html><head><title>Acme Rockets - application</title>'
           '<script src="https://static.example/vite/app-1.js?v=2"></script><script>var x=1</script>'
           '<script id="s" type="application/json" data-x="1">{"a": "Acme Rockets"}</script></head>'
           '<body><div id="root" data-turbo="false"></div><form><input name="a" value="Acme Rockets">'
           '<textarea name="b">secret plan</textarea><select name="c"></select></form></body></html>')
    st = p.page_structure(doc)
    assert st['scripts'] == ['static.example/vite/app-1.js']
    assert st['inlineScripts'] == 2
    assert st['inlineScriptSketches'] == [{'bytes': 7, 'head': 'var x=1'}, {'bytes': 21, 'head': '{"~": "~"}'}]
    assert st['jsonScripts'] == [{'id': 's', 'type': 'application/json', 'attributes': ['data-x'], 'bytes': 21}]
    assert st['dataAttributes'] == ['data-turbo', 'data-x']
    assert st['elementIds'] == ['root', 's']
    assert st['forms'] == 1
    assert st['controls'] == {'input': 1, 'textarea': 1, 'select': 1}
    text = json.dumps(st)
    assert 'Acme Rockets' not in text
    assert 'secret plan' not in text


# --- the form controls ----------------------------------------------------------------------------

FORM = (
    '<form action="/apps/x" method="post">'
    '<input type="hidden" name="authenticity_token" value="tok">'
    '<h2>Company</h2>'
    '<label for="app_company_name">Company name</label>'
    '<input type="text" id="app_company_name" name="app[company_name]" value="Acme Rockets" maxlength="60" required>'
    '<label>Describe what your company does <textarea name="app[description]" maxlength="500">we build rockets'
    '</textarea></label>'
    '<h2>Progress</h2>'
    '<label for="stage">How far along are you?</label>'
    '<select id="stage" name="app[stage]"><option value="">Choose</option><option value="idea">Just an idea</option>'
    '<option value="live" selected>Live</option></select>'
    '<fieldset><legend>Have you incorporated?</legend>'
    '<label><input type="radio" name="app[incorporated]" value="yes"> Yes</label>'
    '<label><input type="radio" name="app[incorporated]" value="no" checked> No</label></fieldset>'
    '<input type="email" name="app[contact]" placeholder="Contact e-mail" aria-required="true">'
    '<input type="file" name="app[video]">'
    '<input type="submit" name="commit" value="Save">'
    '</form>')


def test_html_fields_every_control_once_in_order():
    fields = p.extract_html_fields(FORM)
    assert [f['key'] for f in fields] == ['app[company_name]', 'app[description]', 'app[stage]', 'app[incorporated]',
                                         'app[contact]', 'app[video]']


def test_html_fields_label_by_for_and_by_wrapping():
    fields = {f['key']: f for f in p.extract_html_fields(FORM)}
    assert fields['app[company_name]']['label'] == 'Company name'
    assert fields['app[description]']['label'] == 'Describe what your company does'


def test_html_fields_types_required_limits():
    fields = {f['key']: f for f in p.extract_html_fields(FORM)}
    assert fields['app[company_name]']['type'] == 'text'
    assert fields['app[company_name]']['required'] is True
    assert fields['app[company_name]']['limits'] == {'maxlength': 60}
    assert fields['app[description]']['type'] == 'textarea'
    assert fields['app[contact]']['required'] is True
    assert fields['app[contact]']['label'] == 'Contact e-mail'
    assert fields['app[video]']['type'] == 'file'
    assert fields['app[video]']['required'] is None


def test_html_fields_select_options_and_sections():
    fields = {f['key']: f for f in p.extract_html_fields(FORM)}
    assert fields['app[stage]']['options'] == [{'value': '', 'label': 'Choose'}, {'value': 'idea', 'label': 'Just an idea'},
                                               {'value': 'live', 'label': 'Live'}]
    assert fields['app[company_name]']['section'] == 'Company'
    assert fields['app[stage]']['section'] == 'Progress'


def test_html_fields_radio_group_is_one_field_with_its_choices():
    fields = {f['key']: f for f in p.extract_html_fields(FORM)}
    radio = fields['app[incorporated]']
    assert radio['type'] == 'radio'
    assert radio['label'] == 'Have you incorporated?'
    assert radio['options'] == [{'value': 'yes', 'label': 'Yes'}, {'value': 'no', 'label': 'No'}]


def test_html_fields_never_carry_what_was_typed():
    text = json.dumps(p.extract_html_fields(FORM))
    assert 'Acme Rockets' not in text
    assert 'we build rockets' not in text
    assert 'authenticity_token' not in text
    assert 'tok' not in text.replace('token', '')


def test_html_fields_none_on_a_page_without_controls():
    assert p.extract_html_fields('<html><div id="root"></div></html>') == []
