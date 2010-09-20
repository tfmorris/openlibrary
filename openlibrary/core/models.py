"""Models of various OL objects.
"""

import urllib, urllib2
import simplejson
import web
from infogami.infobase import client

import helpers as h

#TODO: fix this. openlibrary.core should not import plugins.
from openlibrary.plugins.upstream.utils import get_history


class Image:
    def __init__(self, site, category, id):
        self._site = site
        self.category = category
        self.id = id
        
    def info(self):
        url = '%s/%s/id/%s.json' % (h.get_coverstore_url(), self.category, self.id)
        try:
            d = simplejson.loads(urllib2.urlopen(url).read())
            d['created'] = h.parse_datetime(d['created'])
            if d['author'] == 'None':
                d['author'] = None
            d['author'] = d['author'] and self._site.get(d['author'])
            
            return web.storage(d)
        except IOError:
            # coverstore is down
            return None
                
    def url(self, size="M"):
        return "%s/%s/id/%s-%s.jpg" % (h.get_coverstore_url(), self.category, self.id, size.upper())
        
    def __repr__(self):
        return "<image: %s/%d>" % (self.category, self.id)


class Thing(client.Thing):
    """Base class for all OL models."""
    def get_history_preview(self):
        if '_history_preview' not in self.__dict__:
            self.__dict__['_history_preview'] = get_history(self)
        return self._history_preview
        
    def get_most_recent_change(self):
        """Returns the most recent change.
        """
        preview = self.get_history_preview()
        if preview.recent:
            return preview.recent[0]
        else:
            return preview.initial[0]
    
    def prefetch(self):
        """Prefetch all the anticipated data."""
        preview = self.get_history_preview()
        authors = set(v.author.key for v in preview.initial + preview.recent if v.author)
        # preload them
        self._site.get_many(list(authors))
        
    def _make_url(self, label, suffix, **params):
        """Make url of the form $key/$label$suffix?$params.
        """
        u = self.key + "/" + h.urlsafe(label) + suffix
        if params:
            u += '?' + urllib.urlencode(params)
        return u
        

class Edition(Thing):
    """Class to represent /type/edition objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.title or "untitled", suffix, **params)

    def __repr__(self):
        return "<Edition: %s>" % repr(self.title)
    __str__ = __repr__

    def full_title(self):
        # retained for backward-compatibility. Is anybody using this really?
        return self.title            


class Work(Thing):
    """Class to represent /type/work objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.title or "untitled", suffix, **params)

    def __repr__(self):
        return "<Work: %s>" % repr(self.title)
    __str__ = __repr__

    def get_edition_count(self):
        if '_editon_count' not in self.__dict__:
            self.__dict__['_editon_count'] = self._site._request(
                                                '/count_editions_by_work', 
                                                data={'key': self.key})
        return self.__dict__['_editon_count']


class Author(Thing):
    """Class to represent /type/author objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.name or "unnamed", suffix, **params)

    def __repr__(self):
        return "<Author: %s>" % repr(self.name)
    __str__ = __repr__

    def get_edition_count(self):
        return self._site._request(
                '/count_editions_by_author', 
                data={'key': self.key})
    edition_count = property(get_edition_count)


class User(Thing):
    def get_usergroups(self):
        keys = self._site.things({
            'type': '/type/usergroup', 
            'members': self.key})
        return self._site.get_many(keys)
    usergroups = property(get_usergroups)

    def is_admin(self):
        return '/usergroup/admin' in [g.key for g in self.usergroups]


def register_models():
    client.register_thing_class(None, Thing) # default
    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/work', Work)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/user', User)
    
def register_types():
    """Register default types for various path patterns used in OL.
    """
    from infogami.utils import types

    types.register_type('^/authors/[^/]*$', '/type/author')
    types.register_type('^/works/[^/]*$', '/type/work')
    types.register_type('^/books/[^/]*$', '/type/edition')

    types.register_type('^/usergroup/[^/]*$', '/type/usergroup')
    types.register_type('^/permission/[^/]*$', '/type/permision')

    types.register_type('^/(css|js)/[^/]*$', '/type/rawtext')
    