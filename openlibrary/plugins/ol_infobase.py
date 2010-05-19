#!/usr/bin/env python
"""Open Library plugin for infobase.
"""
import os
import datetime
import urllib
import simplejson

import web
from infogami.infobase import config, common, server, cache, dbstore

# relative import
from openlibrary import schema

def init_plugin():
    """Initialize infobase plugin."""
    from infogami.infobase import common, dbstore, server, logger
    dbstore.default_schema = schema.get_schema()

    if config.get('errorlog'):
        common.record_exception = lambda: save_error(config.errorlog, 'infobase')

    ol = server.get_site('openlibrary.org')
    ib = server._infobase
    
    # install custom indexer
    ol.store.indexer = Indexer()

    if config.get('writelog'):
        ib.add_event_listener(logger.Logger(config.writelog))
        
    ib.add_event_listener(invalidate_most_recent_change)

    if ol:
        if config.get('http_listeners'):
            ol.add_trigger(None, http_notify)
        if config.get('booklog'):
            global booklogger
            booklogger = logger.Logger(config.booklog)
            ol.add_trigger('/type/edition', write_booklog)
            ol.add_trigger('/type/author', write_booklog2)
    
    # hook to add count functionality
    server.app.add_mapping("/([^/]*)/count_editions_by_author", __name__ + ".count_editions_by_author")
    server.app.add_mapping("/([^/]*)/count_editions_by_work", __name__ + ".count_editions_by_work")
    server.app.add_mapping("/([^/]*)/count_edits_by_user", __name__ + ".count_edits_by_user")
    server.app.add_mapping("/([^/]*)/most_recent", __name__ + ".most_recent")
    server.app.add_mapping("/([^/]*)/clear_cache", __name__ + ".clear_cache")
    server.app.add_mapping("/([^/]*)/stats/(\d\d\d\d-\d\d-\d\d)", __name__ + ".stats")
    server.app.add_mapping("/([^/]*)/has_user", __name__ + ".has_user")
    server.app.add_mapping("/([^/]*)/olid_to_key", __name__ + ".olid_to_key")
        
def get_db():
    site = server.get_site('openlibrary.org')
    return site.store.db
    
@web.memoize
def get_property_id(type, name):
    db = get_db()
    type_id = get_thing_id(type)
    try:
        return db.where('property', type=type_id, name=name)[0].id
    except IndexError:
        return None
    
def get_thing_id(key):
    try:
        return get_db().where('thing', key=key)[0].id
    except IndexError:
        return None

def count(table, type, key, value):
    pid = get_property_id(type, key)

    value_id = get_thing_id(value)
    if value_id is None:
        return 0                
    return get_db().query("SELECT count(*) FROM " + table + " WHERE key_id=$pid AND value=$value_id", vars=locals())[0].count
        
class count_editions_by_author:
    @server.jsonify
    def GET(self, sitename):
        i = server.input('key')
        return count('edition_ref', '/type/edition', 'authors', i.key)
        
class count_editions_by_work:
    @server.jsonify
    def GET(self, sitename):
        i = server.input('key')
        return count('edition_ref', '/type/edition', 'works', i.key)
        
class count_edits_by_user:
    @server.jsonify
    def GET(self, sitename):
        i = server.input('key')
        author_id = get_thing_id(i.key)
        return get_db().query("SELECT count(*) as count FROM transaction WHERE author_id=$author_id", vars=locals())[0].count

class has_user:
    @server.jsonify
    def GET(self, sitename):
        i = server.input("username")
        
        # Don't allows OLIDs to be usernames
        if web.re_compile(r"OL\d+[A-Z]").match(i.username.upper()):
            return True
        
        key = "/user/" + i.username.lower()
        type_user = get_thing_id("/type/user")
        d = get_db().query("SELECT * from thing WHERE lower(key) = $key AND type=$type_user", vars=locals())
        return bool(d)
    
class stats:
    @server.jsonify
    def GET(self, sitename, today):
        return dict(self.stats(today))
        
    def stats(self, today):
        tomorrow = self.nextday(today)
        yield 'edits', self.edits(today, tomorrow)
        yield 'edits_by_bots', self.edits(today, tomorrow, bots=True)
        yield 'new_accounts', self.new_accounts(today, tomorrow)
        
    def nextday(self, today):
        return get_db().query("SELECT date($today) + 1 AS value", vars=locals())[0].value

    def edits(self, today, tomorrow, bots=False):
        tables = 'version v, transaction t'
        where = 'v.transaction_id=t.id AND t.created >= date($today) AND t.created < date($tomorrow)'

        if bots:
            where += " AND t.author_id IN (SELECT thing_id FROM account WHERE bot = 't')"

        return self.count(tables=tables, where=where, vars=locals())
        
    def new_accounts(self, today, tomorrow):
        type_user = get_thing_id('/type/user')
        return self.count(
            'thing', 
            'type=$type_user AND created >= date($today) AND created < date($tomorrow)',
            vars=locals())
    
    def total_accounts(self):
        type_user = get_thing_id('/type/user')
        return self.count(tables='thing', where='type=$type_user', vars=locals())
        
    def count(self, tables, where, vars):
        return get_db().select(
            what="count(*) as value",
            tables=tables,
            where=where,
            vars=vars
        )[0].value
    
most_recent_change = None

def invalidate_most_recent_change(event):
    global most_recent_change
    most_recent_change = None

class most_recent:
    @server.jsonify
    def GET(self, sitename):
        global most_recent_change
        if most_recent_change is None:
            site = server.get_site('openlibrary.org')
            most_recent_change = site.versions({'limit': 1})[0]
        return most_recent_change
        
class clear_cache:
    @server.jsonify
    def POST(self, sitename):
        from infogami.infobase import cache
        cache.global_cache.clear()
        return {'done': True}
        
class olid_to_key:
    @server.jsonify
    def GET(self, sitename):
        i = server.input("olid")
        d = get_db().query("SELECT key FROM thing WHERE get_olid(key) = $i.olid", vars=locals())
        key = d and d[0].key or None
        return {"olid": i.olid, "key": key}
        
def write(path, data):
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    f = open(path, 'w')
    f.write(data)
    f.close()
    
def save_error(dir, prefix):
    try:
        import traceback
        traceback.print_exc()

        error = web.djangoerror()
        now = datetime.datetime.utcnow()
        path = '%s/%04d-%02d-%02d/%s-%02d%02d%02d.%06d.html' % (dir, \
            now.year, now.month, now.day, prefix,
            now.hour, now.minute, now.second, now.microsecond)
        print >> web.debug, 'Error saved to', path
        write(path, web.safestr(error))
    except:
        import traceback
        traceback.print_exc()
    
def get_object_data(site, thing):
    """Return expanded data of specified object."""
    def expand(value):
        if isinstance(value, list):
            return [expand(v) for v in value]
        elif isinstance(value, common.Reference):
            t = site._get_thing(value)
            return t and t._get_data()
        else:
            return value

    d = thing._get_data()
    for k, v in d.iteritems():
        # save some space by not expanding type
        if k != 'type':
            d[k] = expand(v)
    return d

booklogger = None

def write_booklog(site, old, new):
    """Log modifications to book records."""
    sitename = site.sitename
    if new.type.key == '/type/edition':
        booklogger.write('book', sitename, new.last_modified, get_object_data(site, new))
    else:
        booklogger.write('delete', sitename, new.last_modified, {'key': new.key})
        
def write_booklog2(site, old, new):
    """This function is called when any author object is changed.
    to log all books of the author if name is changed.
    """
    sitename = site.sitename
    if old and old.type.key == new.type.key == '/type/author' and old.name != new.name:
        query = {'type': '/type/edition', 'authors': new.key, 'limit': 1000}
        for d in site.things(query):
            book = site._get_thing(d['key'])
            booklogger.write('book', sitename, new.last_modified, get_object_data(site, book))

def http_notify(site, old, new):
    """Notify listeners over http."""
    data = new.format_data()
    json = simplejson.dumps(data)
    key = data['key']

    # optimize the most common case. 
    # The following prefixes are never cached at the client. Avoid cache invalidation in that case.
    not_cached = ['/b/', '/a/', '/books/', '/authors/', '/works/', '/subjects/', '/publishers/', '/user/', '/usergroup/', '/people/']
    for prefix in not_cached:
        if key.startswith(prefix):
            return
    
    for url in config.http_listeners:
        try:
            response = urllib.urlopen(url, json).read()
            print >> web.debug, "http_notify", repr(url), repr(key), repr(response)
        except:
            print >> web.debug, "failed to send http_notify", repr(url), repr(key)
            import traceback
            traceback.print_exc()
            
# openlibrary.utils can't be imported directly because 
# openlibrary.plugins.openlibrary masks openlibrary module
olmemcache = __import__("openlibrary.utils.olmemcache", None, None, ['x'])

def MemcachedDict(servers=[]):
    """Cache implementation with OL customized memcache client."""
    client = olmemcache.Client(servers)
    return cache.MemcachedDict(memcache_client=client)

cache.register_cache('memcache', MemcachedDict)

def _process_key(key):
    mapping = (
        "/l/", "/languages/",
        "/a/", "/authors/",
        "/b/", "/books/",
        "/user/", "/people/"
    )
    for old, new in web.group(mapping, 2):
        if key.startswith(old):
            return new + key[len(old):]
    return key

def _process_data(data):
    if isinstance(data, list):
        return [_process_data(d) for d in data]
    elif isinstance(data, dict):
        if 'key' in data:
            data['key'] = _process_key(data['key'])
        return dict((k, _process_data(v)) for k, v in data.iteritems())
    else:
        return data

def process_json(key, json):
    if key is None or json is None:
        return None
    base = key[1:].split("/")[0]
    if base in ['authors', 'books', 'works', 'people', 'usergroup', 'permission']:
        data = simplejson.loads(json)
        data = _process_data(data)
        json = simplejson.dumps(data)
    return json
    
dbstore.process_json = process_json

_Indexer = dbstore.Indexer

class Indexer(_Indexer):
    """Overwrite default indexer to reduce the str index for editions."""
    def compute_index(self, doc):
        index = _Indexer.compute_index(self, doc)
        whitelist = ['identifiers', 'classifications', 'isbn_10', 'isbn_13', 'lccn', 'oclc_numbers']
        index = [(datatype, name, value) for datatype, name, value in index 
                if datatype == 'ref' or name.split(".")[0] in whitelist]
        return index

