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

# relative imports
from lists.model import ListMixin, Seed

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
        
    def _get_lists(self, limit=50, offset=0, sort=True):
        q = {
            "type": "/type/list",
            "seeds": {"key": self.key},
            "limit": limit,
            "offset": offset
        }
        keys = self._site.things(q)
        lists = self._site.get_many(keys)
        if sort:
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_update)
        return lists

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

class Work(Thing):
    """Class to represent /type/work objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.title or "untitled", suffix, **params)

    def __repr__(self):
        return "<Work: %s>" % repr(self.key)
    __str__ = __repr__

    def get_edition_count(self):
        if '_editon_count' not in self.__dict__:
            self.__dict__['_editon_count'] = self._site._request(
                                                '/count_editions_by_work', 
                                                data={'key': self.key})
        return self.__dict__['_editon_count']
    
    edition_count = property(get_edition_count)

    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)

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
    def get_usergroups(self):
        keys = self._site.things({
            'type': '/type/usergroup', 
            'members': self.key})
        return self._site.get_many(keys)
    usergroups = property(get_usergroups)
    
    def get_account(self):
        username = self.get_username()
        return Account.find(username=username)
        
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
            
        keys = self._site.things(q)
        lists = self._site.get_many(keys)
        if sort:
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_update)
        return lists
        
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

re_range_star = re.compile(r'(\d+\.\d+)\.(\d+)-(\d+)\.\*$')
re_three_octet = re.compile(r'(\d+\.\d+\.\d+)\.$')
re_four_octet = re.compile(r'(\d+\.\d+\.\d+\.\d+)(/\d+)?$')

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
        bad = []
        for orig in text.splitlines():
            line = orig.split("#")[0].strip()
            if not line or "-" in line:
                continue
            if re_four_octet.match(line):
                continue
            if re_range_star.match(line):
                continue
            if re_three_octet.match(line):
                continue
            if '*' in line:
                collected = []
                octets = line.split('.')
                while octets[0].isdigit():
                    collected.append(octets.pop(0))
                if collected and all(octet == '*' for octet in octets):
                    continue
            bad.append(orig)
        return bad
    
    def parse_ip_ranges(self, text):
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            m = re_four_octet.match(line)
            if m:
                yield line
                continue
            m = re_range_star.match(line)
            if m:
                start = '%s.%s.0' % (m.group(1), m.group(2))
                end = '%s.%s.255' % (m.group(1), m.group(3))
                yield (start, end)
                continue
            m = re_three_octet.match(line)
            if m:
                yield ('%s.0' % m.group(1), '%s.255' % m.group(1))
                continue
            if "-" in line:
                start, end = line.split("-", 1)
                yield (start.strip(), end.strip())
                continue
            if '*' in line:
                collected = []
                octets = line.split('.')
                while octets[0].isdigit():
                    collected.append(octets.pop(0))
                if collected and all(octet == '*' for octet in octets):
                    yield '%s/%d' % ('.'.join(collected + ['0'] * len(octets)), len(collected) * 8)
                continue
    
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
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_update)
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
