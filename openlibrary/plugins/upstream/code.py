"""Upstream customizations."""

import os.path
import web
import random
import simplejson
import md5
import datetime 

from infogami import config
from infogami.infobase import client
from infogami.utils import delegate, app, types
from infogami.utils.view import public, safeint, render
from infogami.utils.context import context

from utils import render_template

from openlibrary.plugins.openlibrary.processors import ReadableUrlProcessor
from openlibrary.plugins.openlibrary import code as ol_code

import utils
import addbook
import models
import covers

if not config.get('coverstore_url'):
    config.coverstore_url = "http://covers.openlibrary.org"

class static(delegate.page):
    path = "/images/.*"
    def GET(self):
        raise web.seeother('/static/upstream' + web.ctx.path)

# handlers for change photo and change cover

class change_cover(delegate.page):
    path = "(/books/OL\d+M)/cover"
    def GET(self, key):
        return ol_code.change_cover().GET(key)
    
class change_photo(change_cover):
    path = "(/authors/OL\d+A)/photo"

del delegate.modes['change_cover']     # delete change_cover mode added by openlibrary plugin

@web.memoize
@public
def vendor_js():
    pardir = os.path.pardir 
    path = os.path.abspath(os.path.join(__file__, pardir, pardir, pardir, pardir, 'static', 'upstream', 'js', 'vendor.js'))
    digest = md5.md5(open(path).read()).hexdigest()
    return '/static/upstream/js/vendor.js?v=' + digest
    
class DynamicDocument:
    """Dynamic document is created by concatinating various rawtext documents in the DB.
    Used to generate combined js/css using multiple js/css files in the system.
    """
    def __init__(self, root):
        self.root = web.rstrips(root, '/')
        self.docs = None 
        self._text = None
        self.last_modified = None
        
    def update(self):
        keys = web.ctx.site.things({'type': '/type/rawtext', 'key~': self.root + '/*'})
        docs = sorted(web.ctx.site.get_many(keys), key=lambda doc: doc.key) 
        if docs:
            self.last_modified = min(doc.last_modified for doc in docs)
            self._text = "\n\n".join(doc.get('body', '') for doc in docs)
        else:
            self.last_modified = datetime.datetime.utcnow()
            self._text = ""
        
    def get_text(self):
        """Returns text of the combined documents"""
        if self._text is None:
            self.update()
        return self._text
        
    def md5(self):
        """Returns md5 checksum of the combined documents"""
        return md5.md5(self.get_text()).hexdigest()

def create_dynamic_document(url, prefix):
    """Creates a handler for `url` for servering combined js/css for `prefix/*` pages"""
    doc = DynamicDocument(prefix)
    
    if url.endswith('.js'):
        content_type = "text/javascript"
    elif url.endswith(".css"):
        content_type = "text/css"
    else:
        content_type = "text/plain"
    
    class page(delegate.page):
        """Handler for serving the combined content."""
        path = "__registered_later_without_using_this__"
        def GET(self):
            i = web.input(v=None)
            v = doc.md5()
            if v != i.v:
                raise web.seeother(web.changequery(v=v))
                
            if web.modified(etag=v):
                oneyear = 365 * 24 * 3600
                web.header("Content-Type", content_type)
                web.header("Cache-Control", "Public, max-age=%d" % oneyear)
                web.lastmodified(doc.last_modified)
                web.expires(oneyear)
                return delegate.RawText(doc.get_text())
                
        def url(self):
            return url + "?v=" + doc.md5()
            
    class hook(client.hook):
        """Hook to update the DynamicDocument when any of the source pages is updated."""
        def on_new_version(self, page):
            if page.key.startswith(doc.root):
                doc.update()

    # register the special page
    delegate.pages[url] = {}
    delegate.pages[url][None] = page
    return page
            
all_js = create_dynamic_document("/js/all.js", "/js")
web.template.Template.globals['all_js'] = all_js()

all_css = create_dynamic_document("/css/all.css", "/css")
web.template.Template.globals['all_css'] = all_css()

def setup_jquery_urls():
    if config.get('use_google_cdn', True):
        jquery_url = "http://ajax.googleapis.com/ajax/libs/jquery/1.3.2/jquery.min.js"
        jqueryui_url = "http://ajax.googleapis.com/ajax/libs/jqueryui/1.7.2/jquery-ui.min.js"
    else:
        jquery_url = "/static/upstream/js/jquery-1.3.2.min.js" 
        jqueryui_url = "/static/upstream/js/jquery-ui-1.7.2.min.js" 
        
    web.template.Template.globals['jquery_url'] = jquery_url
    web.template.Template.globals['jqueryui_url'] = jqueryui_url
    web.template.Template.globals['use_google_cdn'] = config.get('use_google_cdn', True)

class redirects(delegate.page):
    path = "/(a|b|user)/(.*)"
    def GET(self, prefix, path):
        d = dict(a="authors", b="books", user="people")
        raise web.redirect("/%s/%s" % (d[prefix], path))
        
@public
def get_document(key):
    return web.ctx.site.get(key)
    
class revert(delegate.mode):
    def POST(self, key):
        i = web.input("v", _comment=None)
        v = i.v and safeint(i.v, None)
        if v is None:
            raise web.seeother(web.changequery({}))
        
        thing = web.ctx.site.get(key, i.v)
        
        if not thing:
            raise web.notfound()
            
        def revert(thing):
            if thing.type.key == "/type/delete" and thing.revision > 1:
                prev = web.ctx.site.get(thing.key, thing.revision-1)
                if prev.type.key in ["/type/delete", "/type/redirect"]:
                    return revert(prev)
                else:
                    prev._save("revert to revision %d" % prev.revision)
                    return prev
            elif thing.type.key == "/type/redirect":
                redirect = web.ctx.site.get(thing.location)
                if redirect and redirect.type.key not in ["/type/delete", "/type/redirect"]:
                    return redirect
                else:
                    # bad redirect. Try the previous revision
                    prev = web.ctx.site.get(thing.key, thing.revision-1)
                    return revert(prev)
            else:
                return thing
                
        def process(value):
            if isinstance(value, list):
                return [process(v) for v in value]
            elif isinstance(value, client.Thing):
                if value.key:
                    if value.type.key in ['/type/delete', '/type/revert']:
                        return revert(value)
                    else:
                        return value
                else:
                    for k in value.keys():
                        value[k] = process(value[k])
                    return value
            else:
                return value
            
        for k in thing.keys():
            thing[k] = process(thing[k])
                    
        comment = i._comment or "reverted to revision %d" % v
        thing._save(comment)
        raise web.seeother(key)

class report_spam(delegate.page):
    path = '/contact'
    def GET(self):
        i = web.input(path=None)
        email = context.user and context.user.email
        return render_template("contact/spam", email=email, irl=i.path)

    def POST(self):
        i = web.input(email='', irl='', comment='')
        fields = web.storage({
            'email': i.email,
            'irl': i.irl,
            'comment': i.comment,
            'sent': datetime.datetime.utcnow(),
        })
        msg = render_template('email/spam_report', fields)
        web.sendmail(config.from_address, config.report_spam_address, msg.subject, str(msg))
        return render_template("contact/spam/sent")

def setup():
    """Setup for upstream plugin"""
    models.setup()
    utils.setup()
    addbook.setup()
    covers.setup()
    
    # overwrite ReadableUrlProcessor patterns for upstream
    ReadableUrlProcessor.patterns = [
        (r'/books/OL\d+M', '/type/edition', 'title', 'untitled'),
        (r'/authors/OL\d+A', '/type/author', 'name', 'noname'),
        (r'/works/OL\d+W', '/type/work', 'title', 'untitled')
    ]

    # Types for upstream paths
    types.register_type('^/authors/[^/]*$', '/type/author')
    types.register_type('^/books/[^/]*$', '/type/edition')
    types.register_type('^/languages/[^/]*$', '/type/language')

    types.register_type('^/subjects/places/[^/]*$', '/type/place')
    types.register_type('^/subjects/people/[^/]*$', '/type/person')
    types.register_type('^/subjects/[^/]*$', '/type/subject')

    # fix photo/cover url pattern
    ol_code.Author.photo_url_patten = "%s/photo"
    ol_code.Edition.cover_url_patten = "%s/cover"

    # setup template globals
    from openlibrary.i18n import ugettext, ungettext
            
    web.template.Template.globals.update({
        "gettext": ugettext,
        "ugettext": ugettext,
        "_": ugettext,
        "ungettext": ungettext,
        "random": random.Random(),
        "commify": web.commify,
        "group": web.group,
        "storage": web.storage,
        "all": all,
        "any": any,
        "locals": locals
    });
    
    import jsdef
    web.template.STATEMENT_NODES["jsdef"] = jsdef.JSDefNode
    
    setup_jquery_urls()
    
setup()
