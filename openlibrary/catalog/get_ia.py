import openlibrary.catalog.marc.fast_parse as fast_parse
import openlibrary.catalog.marc.read_xml as read_xml
import xml.etree.ElementTree as et
import xml.parsers.expat
import urllib2, os.path, re
from openlibrary.catalog.read_rc import read_rc
from time import sleep
from subprocess import Popen, PIPE

base = "http://archive.org/download/"

xml_path = '/home/edward/get_new_books/xml'

rc = read_rc()

re_loc = re.compile('^(ia\d+\.us\.archive\.org):(/\d/items/(.*))$')

class NoMARCXML:
    pass

def urlopen_keep_trying(url):
    for i in range(3):
        try:
            f = urllib2.urlopen(url)
        except urllib2.HTTPError, error:
            if error.code == 404:
                print "404 for '%s'" % url
                raise
            pass
        except urllib2.URLError:
            pass
        else:
            return f
        print url, "failed"
        sleep(2)
        print "trying again"

def find_item(ia):
    # ignore erorrs
    ret = Popen(["/petabox/sw/bin/find_item.php", ia], stdout=PIPE, stderr=PIPE).communicate()[0]
    if not ret:
        return (None, None)
    assert ret[-1] == '\n'
    loc = ret[:-1]
    m = re_loc.match(loc)
    assert m
    ia_host = m.group(1)
    ia_path = m.group(2)
    assert m.group(3) == ia
    filename = ia + "_meta.xml"
    url = "http://" + ia_host + ia_path + "/" + filename
    return (ia_host, ia_path)

def get_ia(ia):
    ia = ia.strip() # 'cyclopdiaofedu00kidd '
    # read MARC record of scanned book from archive.org
    # try the XML first because it has better character encoding
    # if there is a problem with the XML switch to the binary MARC
    xml_file = ia + "_marc.xml"
    loc = ia + "/" + xml_file
    if os.path.exists(xml_path + xml_file):
        f = open(xml_path + xml_file)
    else:
        try:
            f = urlopen_keep_trying(base + loc)
        except urllib2.HTTPError, error:
            if error.code == 404:
                raise NoMARCXML
            else:
                raise
    if f:
        try:
            return loc, read_xml.read_edition(f)
        except read_xml.BadXML:
            pass
        except xml.parsers.expat.ExpatError:
            print 'IA:', `ia`
            print 'XML parse error:', base + loc
            pass
    if '<title>Internet Archive: Page Not Found</title>' in urllib2.urlopen(base + loc).read(200):
        raise NoMARCXML
    url = base + ia + "/" + ia + "_meta.mrc"
    print url
    try:
        f = urlopen_keep_trying(url)
    except urllib2.URLError:
        pass
    if not f:
        return None, None
    data = f.read()
    length = data[0:5]
    loc = ia + "/" + ia + "_meta.mrc:0:" + length
    if len(data) == 0:
        print 'zero length MARC for', url
        return None, None
    if 'Internet Archive: Error' in data:
        print 'internet archive error for', url
        return None, None
    try:
        return ia, fast_parse.read_edition(data, accept_electronic = True)
    except (ValueError, AssertionError):
        print `data`
        raise

def files(archive_id):
    url = base + archive_id + "/" + archive_id + "_files.xml"
    for i in range(5):
        try:
            tree = et.parse(urlopen_keep_trying(url))
            break
        except xml.parsers.expat.ExpatError:
            sleep(2)
    try:
        tree = et.parse(urlopen_keep_trying(url))
    except:
        print "error reading", url
        raise
    assert tree
    for i in tree.getroot():
        assert i.tag == 'file'
        name = i.attrib['name']
        if name == 'wfm_bk_marc' or name.endswith('.mrc') or name.endswith('.marc') or name.endswith('.out') or name.endswith('.dat') or name.endswith('.records.utf8'):
            size = i.find('size')
            if size is not None:
                yield name, int(size.text)
            else:
                yield name, None

def get_data(loc):
    try:
        filename, p, l = loc.split(':')
    except ValueError:
        return None
    if not os.path.exists(rc['marc_path'] + '/' + filename):
        return None
    f = open(rc['marc_path'] + '/' + filename)
    f.seek(int(p))
    buf = f.read(int(l))
    f.close()
    return buf

def get_from_archive(locator):
    if locator.startswith('marc:'):
        locator = locator[5:]
    file, offset, length = locator.split (":")
    offset = int (offset)
    length = int (length)

    r0, r1 = offset, offset+length-1
    url = 'http://www.archive.org/download/%s'% file

    assert 0 < length < 100000

    ureq = urllib2.Request(url, None, {'Range':'bytes=%d-%d'% (r0, r1)},)
    f = urlopen_keep_trying(ureq)
    if f:
        return f.read(100000)

def get_from_local(locator):
    try:
        file, offset, length = locator.split(':')
    except:
        print 'locator:', `locator`
        raise
    f = open(rc['marc_path'] + '/' + file)
    f.seek(int(offset))
    buf = f.read(int(length))
    f.close()
    return buf

def read_marc_file(part, f, pos=0):
    try:
        for data, int_length in fast_parse.read_file(f):
            loc = "marc:%s:%d:%d" % (part, pos, int_length)
            pos += int_length
            yield (pos, loc, data)
    except ValueError:
        print f
        raise

def test_get_ia():
    ia = "poeticalworksoft00grayiala"
    expect = {
        'publisher': ['Printed by C. Whittingham for T. N. Longman and O. Rees [etc]'],
        'number_of_pages': 223,
        'full_title': 'The poetical works of Thomas Gray with some account of his life and writings ; the whole carefully revised and illustrated by notes ; to which are annexed, Poems addressed to, and in memory of Mr. Gray ; several of which were never before collected.',
        'publish_date': '1800',
        'publish_country': 'enk',
        'authors': [
            {'db_name': 'Gray, Thomas 1716-1771.', 'name': 'Gray, Thomas'}
        ],
        'oclc': ['5047966']
    }
    assert get_ia(ia) == expect

