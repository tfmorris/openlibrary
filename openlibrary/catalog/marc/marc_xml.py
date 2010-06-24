from lxml import etree
from marc_base import MarcBase
from unicodedata import normalize

data_tag = '{http://www.loc.gov/MARC21/slim}datafield'
control_tag = '{http://www.loc.gov/MARC21/slim}controlfield'
subfield_tag = '{http://www.loc.gov/MARC21/slim}subfield'
leader_tag = '{http://www.loc.gov/MARC21/slim}leader'
record_tag = '{http://www.loc.gov/MARC21/slim}record'

def read_marc_file(f):
    for event, elem in etree.iterparse(f, tag=record_tag):
        yield MarcXml(elem)
        elem.clear()

class BlankTag:
    pass

class BadSubtag:
    pass

def norm(s):
    return normalize('NFC', unicode(s.replace(u'\xa0', ' ')))

def get_text(e):
    return norm(e.text) if e.text else u''

class DataField:
    def __init__(self, element):
        assert element.tag == data_tag
        self.element = element
    def ind1(self):
        return self.element.attrib['ind1']
    def ind2(self):
        return self.element.attrib['ind2']

    def read_subfields(self):
        for i in self.element:
            assert i.tag == subfield_tag
            k = i.attrib['code']
            if k == '':
                raise BadSubtag
            yield k, i

    def get_lower_subfields(self):
        for k, v in self.read_subfields():
            if k.islower():
                yield get_text(v)

    def get_all_subfields(self):
        for k, v in self.read_subfields():
            yield k, get_text(v)

    def get_subfields(self, want):
        want = set(want)
        for k, v in self.read_subfields():
            if k not in want:
                continue
            yield k, get_text(v)

    def get_subfield_values(self, want):
        return [v for k, v in self.get_subfields(want)]

    def get_contents(self, want):
        contents = {}
        for k, v in self.get_subfields(want):
            if v:
                contents.setdefault(k, []).append(v)
        return contents

class MarcXml(MarcBase):
    def __init__(self, record):
        assert record.tag == record_tag
        self.record = record

    def all_fields(self):
        for i in self.record:
            if i.tag != data_tag and i.tag != control_tag:
                continue
            if i.attrib['tag'] == '':
                raise BlankTag
            assert i.attrib['tag'].isdigit() 
            yield i.attrib['tag'], i

    def read_fields(self, want):
        want = set(want)

        for i in self.record:
            if i.tag != data_tag and i.tag != control_tag:
                continue
            if i.attrib['tag'] == '':
                raise BlankTag
            assert i.attrib['tag'].isdigit() 
            if i.attrib['tag'] not in want:
                continue
            yield i.attrib['tag'], i

    def decode_field(self, field):
        if field.tag == control_tag:
            return get_text(field)
        if field.tag == data_tag:
            return DataField(field)
