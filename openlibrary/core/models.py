"""Models of various OL objects.
"""
import urllib, urllib2
import simplejson
import web
import re

import iptools
from infogami.infobase import client

import helpers as h

#TODO: fix this. openlibrary.core should not import plugins.
from openlibrary.plugins.upstream.utils import get_history
from openlibrary.plugins.upstream.account import Account
from openlibrary import accounts

# relative imports
from lists.model import ListMixin, Seed
from . import cache, iprange, inlibrary

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
    
    @cache.method_memoize
    def get_history_preview(self):
        """Returns history preview.
        """
        history = self._get_history_preview()
        history = web.storage(history)
        
        history.revision = self.revision
        history.lastest_revision = self.revision
        history.created = self.created
        
        def process(v):
            """Converts entries in version dict into objects.
            """
            v = web.storage(v)
            v.created = h.parse_datetime(v.created)
            v.author = v.author and self._site.get(v.author, lazy=True)
            return v
        
        history.initial = [process(v) for v in history.initial]
        history.recent = [process(v) for v in history.recent]
        
        return history

    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "h"))
    def _get_history_preview(self):
        h = {}
        if self.revision < 5:
            h['recent'] = self._get_versions(limit=5)
            h['initial'] = h['recent'][-1:]
            h['recent'] = h['recent'][:-1]
        else:
            h['initial'] = self._get_versions(limit=1, offset=self.revision-1)
            h['recent'] = self._get_versions(limit=4)
        return h
            
    def _get_versions(self, limit, offset=0):
        q = {"key": self.key, "limit": limit, "offset": offset}
        versions = self._site.versions(q)
        for v in versions:
            v.created = v.created.isoformat()
            v.author = v.author and v.author.key

            # XXX-Anand: hack to avoid too big data to be stored in memcache.
            # v.changes is not used and it contrinutes to memcache bloat in a big way.
            v.changes = '[]'
        return versions
                
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
                
    def _get_lists(self, limit=50, offset=0, sort=True):
        # cache the default case
        if limit == 50 and offset == 0:
            keys = self._get_lists_cached()
        else:
            keys = self._get_lists_uncached(limit=limit, offset=offset)
            
        lists = self._site.get_many(keys)
        if sort:
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists
        
    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "l"))
    def _get_lists_cached(self):
        return self._get_lists_uncached(limit=50, offset=0)
        
    def _get_lists_uncached(self, limit, offset):
        q = {
            "type": "/type/list",
            "seeds": {"key": self.key},
            "limit": limit,
            "offset": offset
        }
        return self._site.things(q)
        
    def _get_d(self):
        """Returns the data that goes into memcache as d/$self.key.
        Used to measure the memcache usage.
        """
        return {
            "h": self._get_history_preview(),
            "l": self._get_lists_cached(),
        }
        
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
    
    def get_publish_year(self):
        if self.publish_date:
            m = web.re_compile("(\d\d\d\d)").search(self.publish_date)
            return m and int(m.group(1))

    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)
        

    def get_ebook_info(self):
        """Returns the ebook info with the following fields.
        
        * read_url - url to read the book
        * borrow_url - url to borrow the book
        * borrowed - True if the book is already borrowed
        * daisy_url - url to access the daisy format of the book
        
        Sample return values:

            {
                "read_url": "http://www.archive.org/stream/foo00bar",
                "daisy_url": "/books/OL1M/foo/daisy"
            }

            {
                "daisy_url": "/books/OL1M/foo/daisy",
                "borrow_url": "/books/OL1M/foo/borrow",
                "borrowed": False
            }
        """
        d = {}
        if self.ocaid:
            d['daisy_url'] = self.url('/daisy')

            meta = self.get_ia_meta_fields()
            collections = meta.get('collection', [])

            borrowable = ('lendinglibrary' in collections or
                         ('inlibrary' in collections and inlibrary.get_library() is not None))

            if borrowable:
                d['borrow_url'] = self.url("/borrow")
                key = "ebooks" + self.key
                doc = self._site.store.get(key) or {}
                d['borrowed'] = doc.get("borrowed") == "true"
            elif 'printdisabled' in collections:
                pass # ebook is not available 
            else:
                d['read_url'] = "http://www.archive.org/stream/%s" % self.ocaid
        return d



class Work(Thing):
    """Class to represent /type/work objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.title or "untitled", suffix, **params)

    def __repr__(self):
        return "<Work: %s>" % repr(self.key)
    __str__ = __repr__

    @property
    @cache.method_memoize
    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "e"))
    def edition_count(self):
        return self._site._request("/count_editions_by_work", data={"key": self.key})

    def get_one_edition(self):
        """Returns any one of the editions.
        
        Used to get the only edition when edition_count==1.
        """
        # If editions from solr are available, use that. 
        # Otherwise query infobase to get the editions (self.editions makes infobase query).
        editions = self.get_sorted_editions() or self.editions
        return editions and editions[0] or None

    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)

    def _get_d(self):
        """Returns the data that goes into memcache as d/$self.key.
        Used to measure the memcache usage.
        """
        return {
            "h": self._get_history_preview(),
            "l": self._get_lists_cached(),
            "e": self.edition_count
        }

class Author(Thing):
    """Class to represent /type/author objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.name or "unnamed", suffix, **params)

    def __repr__(self):
        return "<Author: %s>" % repr(self.key)
    __str__ = __repr__

    def get_edition_count(self):
        return self._site._request(
                '/count_editions_by_author', 
                data={'key': self.key})
    edition_count = property(get_edition_count)
    
    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)
    
class User(Thing):
    def get_status(self):
        account = self.get_account() or {}
        return account.get("status")

    def get_usergroups(self):
        keys = self._site.things({
            'type': '/type/usergroup', 
            'members': self.key})
        return self._site.get_many(keys)
    usergroups = property(get_usergroups)
    
    def get_account(self):
        username = self.get_username()
        return accounts.find(username=username)
        
    def get_email(self):
        account = self.get_account() or {}
        return account.get("email")
    
    def get_username(self):
        return self.key.split("/")[-1]

    def is_admin(self):
        return '/usergroup/admin' in [g.key for g in self.usergroups]
        
    def get_lists(self, seed=None, limit=100, offset=0, sort=True):
        """Returns all the lists of this user.
        
        When seed is specified, this returns all the lists which contain the
        given seed.
        
        seed could be an object or a string like "subject:cheese".
        """
        # cache the default case
        if seed is None and limit == 100 and offset == 0:
            keys = self._get_lists_cached()
        else:
            keys = self._get_lists_uncached(seed=seed, limit=limit, offset=offset)
        
        lists = self._site.get_many(keys)
        if sort:
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists

    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "l"))
    def _get_lists_cached(self):
        return self._get_lists_uncached(limit=100, offset=0)
        
    def _get_lists_uncached(self, seed=None, limit=100, offset=0):
        q = {
            "type": "/type/list", 
            "key~": self.key + "/lists/*",
            "limit": limit,
            "offset": offset
        }
        if seed:
            if isinstance(seed, Thing):
                seed = {"key": seed.key}
            q['seeds'] = seed
            
        return self._site.things(q)
        
    def new_list(self, name, description, seeds, tags=[]):
        """Creates a new list object with given name, description, and seeds.

        seeds must be a list containing references to author, edition, work or subject strings.

        Sample seeds:

            {"key": "/authors/OL1A"}
            {"key": "/books/OL1M"}
            {"key": "/works/OL1W"}
            "subject:love"
            "place:san_francisco"
            "time:1947"
            "person:gerge"

        The caller must call list._save(...) to save the list.
        """
        id = self._site.seq.next_value("list")

        # since the owner is part of the URL, it might be difficult to handle
        # change of ownerships. Need to think of a way to handle redirects.
        key = "%s/lists/OL%sL" % (self.key, id)
        doc = {
            "key": key,
            "type": {
                "key": "/type/list"
            },
            "name": name,
            "description": description,
            "seeds": seeds,
            "tags": tags
        }
        return self._site.new(key, doc)

    def __repr__(self):
        return "<User: %s>" % repr(self.key)
    __str__ = __repr__

class List(Thing, ListMixin):
    """Class to represent /type/list objects in OL.
    
    List contains the following properties:
    
        * name - name of the list
        * description - detailed description of the list (markdown)
        * members - members of the list. Either references or subject strings.
        * cover - id of the book cover. Picked from one of its editions.
        * tags - list of tags to describe this list.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.name or "unnamed", suffix, **params)
        
    def get_owner(self):
        match = web.re_compile(r"(/people/[^/]+)/lists/OL\d+L").match(self.key)
        if match:
            key = match.group(1)
            return self._site.get(key)
            
    def get_cover(self):
        """Returns a cover object.
        """
        return self.cover and Image(self._site, "b", self.cover)
        
    def get_tags(self):
        """Returns tags as objects.
        
        Each tag object will contain name and url fields.
        """
        return [web.storage(name=t, url=self.key + u"/tags/" + t) for t in self.tags]
        
    def _get_subjects(self):
        """Returns list of subjects inferred from the seeds.
        Each item in the list will be a storage object with title and url.
        """
        # sample subjects
        return [
            web.storage(title="Cheese", url="/subjects/cheese"),
            web.storage(title="San Francisco", url="/subjects/place:san_francisco")
        ]
        
    def add_seed(self, seed):
        """Adds a new seed to this list.
        
        seed can be:
            - author, edition or work object
            - {"key": "..."} for author, edition or work objects
            - subject strings.
        """
        if isinstance(seed, Thing):
            seed = {"key": seed.key}

        index = self._index_of_seed(seed)
        if index >= 0:
            return False
        else:
            self.seeds = self.seeds or []
            self.seeds.append(seed)
            return True
        
    def remove_seed(self, seed):
        """Removes a seed for the list.
        """
        if isinstance(seed, Thing):
            seed = {"key": seed.key}
            
        index = self._index_of_seed(seed)
        if index >= 0:
            self.seeds.pop(index)
            return True
        else:
            return False
        
    def _index_of_seed(self, seed):
        for i, s in enumerate(self.seeds):
            if isinstance(s, Thing):
                s = {"key": s.key}
            if s == seed:
                return i
        return -1

    def __repr__(self):
        return "<List: %s (%r)>" % (self.key, self.name)

class Library(Thing):
    """Library document.
    
    Each library has a list of IP addresses belongs to that library. 
    """
    def url(self, suffix="", **params):
        u = self.key + suffix
        if params:
            u += '?' + urllib.urlencode(params)
        return u

    def find_bad_ip_ranges(self, text):
        return iprange.find_bad_ip_ranges(text)
    
    def parse_ip_ranges(self, text):
        return iprange.parse_ip_ranges(text)
    
    def get_ip_range_list(self):
        """Returns IpRangeList object for the range of IPs of this library.
        """
        ranges = list(self.parse_ip_ranges(self.ip_ranges or ""))
        return iptools.IpRangeList(*ranges)
        
    def has_ip(self, ip):
        """Return True if the the given ip is part of the library's ip range.
        """
        return ip in self.get_ip_range_list()
        
    def get_branches(self):
        # Library Name | Street | City | State | Zip | Country | Telephone | Website | Lat, Long
        columns = ["name", "street", "city", "state", "zip", "country", "telephone", "website", "latlong"]
        def parse(line):
            branch = web.storage(zip(columns, line.strip().split("|")))
            
            # add empty values for missing columns
            for c in columns:
                branch.setdefault(c, "")
            
            try:
                branch.lat, branch.lon = branch.latlong.split(",", 1)
            except ValueError:
                branch.lat = "0"
                branch.lon = "0"
            return branch
        return [parse(line) for line in self.addresses.splitlines() if line.strip()]
        
class Subject(web.storage):
    def get_lists(self, limit=1000, offset=0, sort=True):
        q = {
            "type": "/type/list",
            "seeds": self.get_seed(),
            "limit": limit,
            "offset": offset
        }
        keys = web.ctx.site.things(q)
        lists = web.ctx.site.get_many(keys)
        if sort:
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists
        
    def get_seed(self):
        seed = self.key.split("/")[-1]
        if seed.split(":")[0] not in ["place", "person", "time"]:
            seed = "subject:" + seed
        return seed
        
    def url(self, suffix="", **params):
        u = self.key + suffix
        if params:
            u += '?' + urllib.urlencode(params)
        return u
        
    def get_default_cover(self):
        for w in self.works:
            cover_id = w.get("cover_id")
            if cover_id:
                return Image(web.ctx.site, "b", cover_id)

def register_models():
    client.register_thing_class(None, Thing) # default
    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/work', Work)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/user', User)
    client.register_thing_class('/type/list', List)
    client.register_thing_class('/type/library', Library)
    
def register_types():
    """Register default types for various path patterns used in OL.
    """
    from infogami.utils import types

    types.register_type('^/authors/[^/]*$', '/type/author')
    types.register_type('^/books/[^/]*$', '/type/edition')
    types.register_type('^/works/[^/]*$', '/type/work')
    types.register_type('^/languages/[^/]*$', '/type/language')
    types.register_type('^/libraries/[^/]*$', '/type/library')

    types.register_type('^/usergroup/[^/]*$', '/type/usergroup')
    types.register_type('^/permission/[^/]*$', '/type/permision')

    types.register_type('^/(css|js)/[^/]*$', '/type/rawtext')
