# The decode every NRVV check applies to CC's stored answer (plan 045 Phase 36): the JSON value at the start of the
# answer, with nothing after it but whitespace and stray closing punctuation. Pure.
#
# Observed in acceptance runs with haiku: a whole, valid answer object stored with one '}' more (TEST_AUTHOR #107,
# the environment answer) and with '"}' more (TEST_AUTHOR #114, two test answers). json.loads refuses both as "Extra
# data" and the Task ends ERROR with no retry - the check is a separate Function from the CC call. The object is
# complete in both; the tail carries nothing. Any OTHER content after the object - a second object, prose, an opening
# bracket - is still refused: the answer would then hold something the check never looked at.
#
# The caller strips the answer and removes a markdown fence first, as every check already did.

import json
import re

EXCERPT = 300
# what may follow the decoded value: whitespace and the closing punctuation } ] "
STRAY_TAIL = re.compile(r'[\s}\]"]*')


def excerpt(text):
    text = text or ''
    return text if len(text) <= EXCERPT else text[:EXCERPT] + '...'


def loads(text):
    """The JSON value `text` starts with - or a ValueError 'CC answered something that is not JSON: ...' when it does
    not start with one, or when anything but whitespace and stray closers } ] " follows it."""
    text = text or ''
    try:
        data, end = json.JSONDecoder().raw_decode(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + excerpt(text)) from None
    if not STRAY_TAIL.fullmatch(text[end:]):
        raise ValueError('CC answered something that is not JSON: ' + excerpt(text))
    return data
