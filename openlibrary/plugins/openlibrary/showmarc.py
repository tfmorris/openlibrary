"""
Hook to show mark details in Open Library.
"""
from infogami.utils import delegate
from infogami.utils.view import render

import web
import urllib2
import os.path
import sys, re

class old_show_marc(delegate.page):
    path = "/show-marc/(.*)"

    def GET(self, param):
        raise web.seeother('/show-records/' + param)

class show_ia(delegate.page):
    path = "/show-records/ia:(.*)"

    def GET(self, ia):
        filename = ia + "/" + ia + "_meta.mrc"

        url = 'http://www.archive.org/download/%s'% filename

        try:        
            data = urllib2.urlopen(url).read()
        except urllib2.HTTPError, e:
            return "ERROR:" + str(e)

        from openlibrary.catalog.marc import html

        if len(data) != int(data[:5]):
            data = data.decode('utf-8').encode('raw_unicode_escape')
        assert len(data) == int(data[:5])

        try:
            record = html.html_record(data)
        except ValueError:
            record = None

        return render.showia(ia, record)
        
class show_amazon(delegate.page):
    path = "/show-records/amazon:(.*)"
    
    def GET(self, asin):
        return render.showamazon(asin)

re_bad_meta_mrc = re.compile('^([^/]+)_meta\.mrc$')

class show_marc(delegate.page):
    path = "/show-records/(.*):(\d+):(\d+)"
	
    def GET(self, filename, offset, length):
        m = re_bad_meta_mrc.match(filename)
        if m:
            raise web.seeother('/show-records/ia:' + m.group(1))

        offset = int(offset)
        length = int(length)

        #print "record_locator: <code>%s</code><p/><hr>" % locator

        r0, r1 = offset, offset+100000
        url = 'http://www.archive.org/download/%s'% filename

        ureq = urllib2.Request(url,
                               None,
                               {'Range':'bytes=%d-%d'% (r0, r1)},
                               )

        try:        
            result = urllib2.urlopen(ureq).read(100000)
        except urllib2.HTTPError, e:
            return "ERROR:" + str(e)

        len_in_rec = int(result[:5])
        if len_in_rec != length:
            raise web.seeother('/show-records/%s:%d:%d' % (filename, offset, len_in_rec))

        from openlibrary.catalog.marc import html

        try:
            record = html.html_record(result[0:length])
        except ValueError:
            record = None

        return render.showmarc(record, filename, offset, length)
