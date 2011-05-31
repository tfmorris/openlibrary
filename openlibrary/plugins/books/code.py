"""Open Library Books API
"""

from infogami.plugins.api.code import add_hook
import dynlinks

import web
from infogami.infobase import _json as simplejson

from infogami.utils import delegate
from infogami.plugins.api.code import jsonapi

import readlinks


class books:
    def GET(self):
        i = web.input(bibkeys='', callback=None, details="false")
        
        web.ctx.headers = []
        if i.get("format") == "json":
            web.header('Content-Type', 'application/json')
        else:
            web.header('Content-Type', 'text/javascript')
        
        return dynlinks.dynlinks(i.bibkeys.split(","), i)
        
add_hook("books", books)


class read_singleget(delegate.page):
    """Handle the single-lookup form of the Hathi-style API
    """
    path = r"/api/volumes/(brief|full)/(oclc|lccn|issn|isbn|htid|olid|recordnumber)/(.+)"
    encoding = "json"
    @jsonapi
    def GET(self, brief_or_full, idtype, idval):
        i = web.input()
        
        web.ctx.headers = []
        bibkey = '%s:%s' % (idtype, idval)
        return readlinks.readlink_single(bibkey, i)


class read_multiget(delegate.page):
    """Handle the multi-lookup form of the Hathi-style API
    """
    path = r"/api/volumes/(brief|full)/json/(.+)"
    @jsonapi
    def GET(self, brief_or_full, bibkey_str):
        i = web.input()

        web.ctx.headers = []
        return readlinks.readlink_multiple(bibkey_str, i)

    
# if __name__ == "__main__":
#     import doctest
#     doctest.testmod()
