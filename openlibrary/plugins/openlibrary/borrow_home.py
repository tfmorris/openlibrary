"""Controller for /borrow page.
"""
import simplejson
import web

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import helpers as h
from openlibrary.core import inlibrary
from openlibrary.plugins.worksearch.subjects import SubjectEngine

from libraries import LoanStats

class borrow(delegate.page):
    path = "/borrow"
    
    def is_enabled(self):
        return "inlibrary" in web.ctx.features
    
    def GET(self):
        subject = get_lending_library(web.ctx.site, details=True, inlibrary=inlibrary.get_library() is not None, limit=24)
        return render_template("borrow/index", subject, stats=LoanStats())

class borrow(delegate.page):
    path = "/borrow"
    encoding = "json"

    def is_enabled(self):
        return "inlibrary" in web.ctx.features

    @jsonapi
    def GET(self):
        i = web.input(offset=0, limit=24, details="false", has_fulltext="false")

        filters = {}
        if i.get("has_fulltext") == "true":
            filters["has_fulltext"] = "true"

        if i.get("published_in"):
            if "-" in i.published_in:
                begin, end = i.published_in.split("-", 1)

                if h.safeint(begin, None) is not None and h.safeint(end, None) is not None:
                    filters["publish_year"] = [begin, end]
            else:
                y = h.safeint(i.published_in, None)
                if y is not None:
                    filters["publish_year"] = i.published_in

        i.limit = h.safeint(i.limit, 12)
        i.offset = h.safeint(i.offset, 0)

        subject = get_lending_library(web.ctx.site, 
            offset=i.offset, 
            limit=i.limit, 
            details=i.details.lower() == "true", 
            inlibrary=inlibrary.get_library() is not None,
            **filters)
        return simplejson.dumps(subject)

class borrow_about(delegate.page):
    path = "/borrow/about"
    
    def GET(self):
        return render_template("borrow/about")
        
def convert_works_to_editions(site, works):
    """Takes work docs got from solr and converts them into appropriate editions required for lending library.
    """
    ekeys = ['/books/' + w['lending_edition'] for w in works if w.get('lending_edition')]
    editions = {}
    for e in site.get_many(ekeys):
        editions[e['key']] = e.dict()
    
    for w in works:
        if w.get('lending_edition'):
            e = editions['/books/' + w['lending_edition']]
            if 'ocaid' in e:
                covers = e.get('covers') or [None]
                w['key'] = e['key']
                w['cover_id'] = covers[0]
                w['ia'] = e['ocaid']
                w['title'] = e.get('title') or w['title']

def get_lending_library(site, inlibrary=False, **kw):
    kw.setdefault("sort", "first_publish_year desc")
    
    if inlibrary:
        subject = CustomSubjectEngine().get_subject("/subjects/lending_library", in_library=True, **kw)
    else:
        subject = CustomSubjectEngine().get_subject("/subjects/lending_library", in_library=False, **kw)
    
    subject['key'] = '/borrow'
    convert_works_to_editions(site, subject['works'])
    return subject
    
class CustomSubjectEngine(SubjectEngine):
    """SubjectEngine for inlibrary and lending_library combined."""
    def make_query(self, key, filters):
        meta = self.get_meta(key)

        q = {
            meta.facet_key: ["lending_library"], 
            'public_scan_b': "false"
        }

        if filters:
            if filters.get('in_library') is True:
                q[meta.facet_key].append('in_library')
            if filters.get("has_fulltext") == "true":
                q['has_fulltext'] = "true"
            if filters.get("publish_year"):
                q['publish_year'] = filters['publish_year']

        return q
    
    def get_ebook_count(self, name, value, publish_year):
        return 0

def setup():
    pass