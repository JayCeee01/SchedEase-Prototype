"""Spreadsheet-safe CSV output; never use this module to normalize stored data.

Suspicious text receives a leading apostrophe. CSV quoting remains responsible
for delimiters/quotes/newlines. Typed numbers remain numeric. See CSV_EXPORT_SECURITY.md.
"""
import csv
from numbers import Number
import unicodedata


def safe_cell(value):
    if value is None or isinstance(value, Number):
        return value
    text = str(value)
    prefix = []
    for character in text:
        if character.isspace() or unicodedata.category(character) in ('Cc', 'Cf'):
            prefix.append(character)
        else:
            break
    remainder = text[len(prefix):]
    controls = any(unicodedata.category(c) in ('Cc', 'Cf') for c in prefix)
    if controls or remainder.startswith(('=', '+', '-', '@', '\uff1d', '\uff0b', '\uff0d', '\uff20')):
        return "'" + text
    return text


class _SafeWriter:
    def __init__(self, underlying):
        self.underlying = underlying

    def writerow(self, row):
        return self.underlying.writerow([safe_cell(value) for value in row])

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def writer(stream, *args, **kwargs):
    kwargs.setdefault('quoting', csv.QUOTE_ALL)
    return _SafeWriter(csv.writer(stream, *args, **kwargs))


class DictWriter(csv.DictWriter):
    def __init__(self, stream, fieldnames, *args, **kwargs):
        kwargs.setdefault('quoting', csv.QUOTE_ALL)
        super().__init__(stream, fieldnames, *args, **kwargs)
        self.writer = _SafeWriter(self.writer)
