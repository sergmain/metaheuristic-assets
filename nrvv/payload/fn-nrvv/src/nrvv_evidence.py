"""Evidence rules of a requirement set: the words a top-level requirement or an interpretation item rests on are quoted in
its Rationale as `evidence: <reqId> "<words>"` lines, and these rules refuse a quote that is not verbatim in its source, a
universal word or a number no quote carries, a bound from a cost-only NEED, and a programming-language name.

The same rules and word lists as the Dispatcher's re-check; both are tested on one table of cases
(tests/data/evidence-cases.json). Every refusal names the item's key and the rule as `<key>: rule <n> (<name>) - ...`, so
a check can hand it to the model as is. Pure: no I/O.
"""

import re

# rule 2: a statement holding one of these needs a quote holding one
UNIVERSAL_WORDS = frozenset(['each', 'every', 'all', 'any', 'always', 'never'])

# rule 4: a top-level requirement of a cost-only NEED holds none of these phrases, none of these words and no digit
COST_PHRASES = ('shall not', 'must not', 'may not', 'will not', 'at most', 'at least', 'no more than', 'no fewer than',
                'not exceed', 'not more than')
COST_WORDS = frozenset(['never', 'only', 'limit', 'limits', 'bound', 'bounds', 'minimum', 'maximum', 'minimise', 'minimize',
                        'minimal', 'fewest'])

# rule 5: no statement or Rationale names a programming language or a test framework (case-sensitive words)
LANGUAGE_NAMES = ('Python', 'Java', 'JavaScript', 'TypeScript', 'Rust', 'COBOL', 'Kotlin', 'Scala', 'C#', 'C++', 'Golang',
                  'Ruby', 'PHP', 'Swift', 'pytest', 'JUnit')

CLAUSE_KINDS = ('OBLIGATION', 'COST_OBJECTIVE', 'ENVIRONMENT_FACT', 'SCOPE_LIMITER')
INTERPRETATION_KINDS = ('ASSUMPTION', 'READING', 'OPEN_CHOICE')

_EVIDENCE_LINE = re.compile(r'^\s*evidence:\s*(\S+)\s+"(.*)"\s*$', re.IGNORECASE)
_WHITESPACE = re.compile(r'\s+')
_DIGITS = re.compile(r'[0-9]+')
_WORD = re.compile(r'[a-z]+')
_LANGUAGE_PATTERNS = [re.compile(r'(?<![A-Za-z0-9_#+])' + re.escape(name) + r'(?![A-Za-z0-9_#+])') for name in LANGUAGE_NAMES]
_PLAIN = str.maketrans({
    '\u201c': '"', '\u201d': '"', '\u201e': '"', '\u00ab': '"', '\u00bb': '"',
    '\u2018': "'", '\u2019': "'", '\u201a': "'",
    '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2013': '-', '\u2014': '-', '\u2015': '-', '\u2212': '-',
})


def normalize(text):
    """Lower case; curly quotes plain, every dash a hyphen; every run of whitespace one space; leading and trailing
    punctuation removed. '' for None."""
    if text is None:
        return ''
    s = _WHITESPACE.sub(' ', text.lower().translate(_PLAIN)).strip()
    start, end = 0, len(s)
    while start < end and not (s[start].isalnum() or s[start].isspace()):
        start += 1
    while end > start and not (s[end - 1].isalnum() or s[end - 1].isspace()):
        end -= 1
    return s[start:end].strip()


def parse_evidence(rationale):
    """The `evidence: <reqId> "<words>"` lines of a Rationale, in order, as (source, quote) pairs."""
    if not rationale:
        return []
    out = []
    for line in rationale.splitlines():
        m = _EVIDENCE_LINE.match(line)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def parse_list(rationale, label):
    """The entries of the first line that begins with `<label>:` (any case), split at commas, stripped, each once."""
    if not rationale:
        return []
    p = re.compile(r'^\s*' + re.escape(label) + r':(.*)$', re.IGNORECASE)
    for line in rationale.splitlines():
        m = p.match(line)
        if not m:
            continue
        out = []
        for entry in m.group(1).split(','):
            e = entry.strip()
            if e and e not in out:
                out.append(e)
        return out
    return []


def _words(normalized):
    return _WORD.findall(normalized)


def quote_refusal(key, evidence, source_statements):
    """Rule 1: at least one entry; each entry's source is a key of source_statements (a NEED the item cites, an item it
    names in reading:); its normalised quote has at least two words, holds no `"` and is a substring of the normalised
    source statement. None when every entry holds."""
    if not evidence:
        return key + ': rule 1 (quote) - no evidence: quote the words of a cited NEED the statement rests on'
    for source, raw in evidence:
        statement = source_statements.get(source)
        if statement is None:
            return (key + ': rule 1 (quote) - evidence source ' + source + ' is neither a NEED it cites nor an item it'
                    + ' names in reading: - allowed ' + str(sorted(source_statements)))
        quote = normalize(raw)
        if '"' in quote:
            return key + ': rule 1 (quote) - the quote from ' + source + ' holds a double quote: "' + raw + '"'
        if len(quote.split(' ')) < 2 or not quote.strip():
            return key + ': rule 1 (quote) - the quote from ' + source + ' has fewer than two words: "' + raw + '"'
        if quote not in normalize(statement):
            return key + ': rule 1 (quote) - "' + raw + '" is not verbatim in ' + source + "'s statement"
    return None


def universal_refusal(key, statement, evidence):
    """Rule 2: a statement holding a universal word needs a quote holding one. None otherwise."""
    held = []
    for w in _words(normalize(statement)):
        if w in UNIVERSAL_WORDS and w not in held:
            held.append(w)
    if not held:
        return None
    if any(w in UNIVERSAL_WORDS for _, q in evidence for w in _words(normalize(q))):
        return None
    return (key + ': rule 2 (universal word) - the statement says [' + ', '.join(held)
            + '] but no quote holds a universal word: state only the scope the NEEDs state')


def number_refusal(key, statement, evidence):
    """Rule 3: every number in a top-level statement appears in one of its quotes. None when it does."""
    quoted = set()
    for _, q in evidence:
        quoted.update(_DIGITS.findall(q))
    for n in _DIGITS.findall(statement):
        if n not in quoted:
            return (key + ': rule 3 (number) - ' + n + ' is in the statement and in no quote: state no number the'
                    + ' NEEDs do not state')
    return None


def cost_refusal(key, statement, cited_derivation_kinds):
    """Rule 4: when every cited derivation NEED is COST_OBJECTIVE (and there is one), the statement holds no cost phrase,
    no cost word and no digit - a cost is measured and reported, never bounded. None otherwise."""
    if not cited_derivation_kinds or not all(k == 'COST_OBJECTIVE' for k in cited_derivation_kinds):
        return None
    words = _words(normalize(statement))
    spaced = ' ' + ' '.join(words) + ' '
    for phrase in COST_PHRASES:
        if ' ' + phrase + ' ' in spaced:
            return key + ': rule 4 (cost) - "' + phrase + '" bounds a cost a cost-only NEED states: measure and report it'
    for w in words:
        if w in COST_WORDS:
            return key + ': rule 4 (cost) - "' + w + '" bounds a cost a cost-only NEED states: measure and report it'
    if _DIGITS.search(statement):
        return key + ': rule 4 (cost) - a number bounds a cost a cost-only NEED states: measure and report it'
    return None


def language_refusal(key, text):
    """Rule 5: no programming-language or test-framework name, as a case-sensitive word. None when there is none."""
    if not text:
        return None
    for name, p in zip(LANGUAGE_NAMES, _LANGUAGE_PATTERNS):
        if p.search(text):
            return (key + ': rule 5 (language) - "' + name + '": the requirements stage names no programming language'
                    + ' or test framework')
    return None


def rationale(need_citations, kind, governs, readings, evidence, ambiguities, prose):
    """Item 2 of a top-level requirement or an interpretation item: need:, interpretation:, governs:, reading:, one
    evidence: line per quote, one ambiguity: line per ambiguity, then the prose; an empty part writes no line."""
    lines = []
    if need_citations:
        lines.append('need: ' + ', '.join(need_citations))
    if kind:
        lines.append('interpretation: ' + kind)
    if governs:
        lines.append('governs: ' + ', '.join(governs))
    if readings:
        lines.append('reading: ' + ', '.join(readings))
    for source, quote in evidence:
        lines.append('evidence: ' + source + ' "' + quote + '"')
    for a in ambiguities:
        lines.append('ambiguity: ' + a)
    if prose and prose.strip():
        lines.append(prose.strip())
    return '\n'.join(lines)


def top_level_refusal(key, statement, rationale_text, evidence, source_statements, cited_derivation_kinds):
    """Rules 1 - 5 on a top-level requirement, in rule order (rule 5 on the statement, then on the Rationale)."""
    return (quote_refusal(key, evidence, source_statements)
            or universal_refusal(key, statement, evidence)
            or number_refusal(key, statement, evidence)
            or cost_refusal(key, statement, cited_derivation_kinds)
            or language_refusal(key, statement)
            or language_refusal(key, rationale_text))


def interpretation_refusal(key, kind, statement, rationale_text, evidence, source_statements):
    """Rules 1, 2 (not on an OPEN_CHOICE) and 5 on an interpretation item."""
    return (quote_refusal(key, evidence, source_statements)
            or (None if kind == 'OPEN_CHOICE' else universal_refusal(key, statement, evidence))
            or language_refusal(key, statement)
            or language_refusal(key, rationale_text))


def is_derivation_subject(clause_kind):
    """OBLIGATION, COST_OBJECTIVE, or none (a NEED a person wrote) - the NEEDs requirements are derived from."""
    return clause_kind in (None, '', 'OBLIGATION', 'COST_OBJECTIVE') or clause_kind not in CLAUSE_KINDS


def is_qualifier(clause_kind):
    """ENVIRONMENT_FACT, SCOPE_LIMITER and COST_OBJECTIVE - the NEEDs that qualify the derivation subjects."""
    return clause_kind in ('ENVIRONMENT_FACT', 'SCOPE_LIMITER', 'COST_OBJECTIVE')
