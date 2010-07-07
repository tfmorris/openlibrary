from openlibrary.catalog.marc.fast_parse import get_subfields, get_tag_lines, translate, handle_wrapped_lines
from openlibrary.catalog.marc import fast_parse
from marc_base import MarcBase
from unicodedata import normalize

def norm(s):
    return normalize('NFC', unicode(s))

class BinaryDataField():
    def __init__(self, line):
        self.line = line

    def translate(self, data):
        return fast_parse.translate(data)

    def ind1(self):
        return self.line[0]

    def ind2(self):
        return self.line[1]

    def remove_brackets(self):
        line = self.line
        if line[3] == '[' and line[-2] == ']':
            self.line = line[0:3] + line[4:-3] + line[-1]

    def get_subfields(self, want):
        want = set(want)
        for i in self.line[3:-1].split('\x1f'):
            if i and i[0] in want:
                yield i[0], self.translate(i[1:])

    def get_contents(self, want):
        contents = {}
        for k, v in self.get_subfields(want):
            contents.setdefault(k, []).append(v)
        return contents

    def get_subfield_values(self, want):
        return [v for k, v in self.get_subfields(want)]

    def get_all_subfields(self):
        return fast_parse.get_all_subfields(self.line)

    def get_all_subfields(self):
        for i in self.line[3:-1].split('\x1f'):
            if i:
                j = self.translate(i)
                yield j[0], j[1:]

    def get_lower_subfields(self):
        for k, v in self.get_all_subfields():
            if k.islower():
                yield v

#class BinaryIaDataField(BinaryDataField):
#    def translate(self, data):
#        return fast_parse.translate(data, bad_ia_charset=True)

class MarcBinary(MarcBase):
    def __init__(self, data):
        assert len(data) and isinstance(data, basestring)
        self.data = data

    def read_fields(self, want):
        want = set(want)
        for tag, line in handle_wrapped_lines(get_tag_lines(self.data, want)):
            if tag not in want:
                continue
            if tag.startswith('00'):
                # marc_upei/marc-for-openlibrary-bigset.mrc:78997353:588
                if tag == '008' and line == '':
                    continue
                assert line[-1] == '\x1e'
                yield tag, line[:-1]
            else:
                yield tag, BinaryDataField(line)

    def decode_field(self, field):
        return field # noop on MARC binary

    def read_isbn(self, f):
        if '\x1f' in f.line:
            return super(MarcBinary, self).read_isbn(f)
        else:
            m = re_isbn.match(line[3:-1])
            if m:
                return [m.group(1)]
        return []
