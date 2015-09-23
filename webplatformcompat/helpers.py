"""Helper functions for Jinja2 templates."""

from datetime import date

from django.conf import settings
from django.utils.html import escape
from jinja2 import contextfunction, Markup
from rest_framework.templatetags.rest_framework import (
    replace_query_param, urlize_quoted_links, break_long_headers, add_class)


@contextfunction
def pick_translation(context, trans_obj):
    """Pick a translation from a translation object.

    A translation object may be:
    Empty -- No content, return ('', None)
    A string -- A canonical string, return (string, None)
    A dictionary -- Language/string pairs, return (string, language)
    """
    if not trans_obj:
        return '', None
    if not hasattr(trans_obj, 'keys'):
        return trans_obj, None
    lang = context.get('lang', 'en')
    if lang not in trans_obj:
        assert 'en' in trans_obj
        lang = 'en'
    return trans_obj[lang], lang


@contextfunction
def trans_span(context, trans_obj, **attrs):
    """Pick a translation for an HTML element.

    The text is HTML-escaped and marked HTML-safe.  If the requested language
    does not match, the result is wrapped in a <span> with a lang= attribute.
    Other key=value pairs are added as span attributes.  If the requested
    language matches, and there are no span attributes, the <span> element is
    omitted and plain (HTML-safe) text is returned.
    """
    desired_lang = context.get('lang', 'en')
    trans, lang = pick_translation(context, trans_obj)
    if not lang:
        if trans:
            return Markup(u'<code>{0}</code>'.format(escape(trans)))
        else:
            return ''
    if desired_lang != lang:
        attrs['lang'] = lang
    if attrs:
        attrstr = ' '.join(
            ['{0}="{1}"'.format(k, attrs[k]) for k in sorted(attrs.keys())])
        return Markup(u'<span {1}>{0}</span>'.format(trans, attrstr))
    else:
        return Markup(trans)


@contextfunction
def trans_str(context, trans_obj):
    """Pick a translation as an unescaped string.

    The string is not wrapped in an HTML element and not marked as HTML safe.
    """
    return pick_translation(context, trans_obj)[0]


def current_year():
    return date.today().year


def is_debug():
    return settings.DEBUG


def add_query_param(url, **query):
    for key, val in query.items():
        url = replace_query_param(url, key, val)
    return url


env = {
    'globals': {
        'add_query_param': add_query_param,
        'current_year': current_year,
        'is_debug': is_debug,
        'pick_translation': pick_translation,
        'trans_span': trans_span,
        'trans_str': trans_str,
    },
    'filters': {
        'add_class': add_class,
        'urlize_quoted_links': urlize_quoted_links,
        'break_long_headers': break_long_headers,
    }
}
