"""Open Library extension to provide a new kind of client connection with caching support.
"""
from infogami import config
from infogami.infobase import client, lru
import web
import simplejson

default_cache_prefixes = ["/type/", "/l/", "/index.", "/about", "/css/", "/js/"]


class ConnectionMiddleware:
    def __init__(self, conn):
        self.conn = conn
        
    def get_auth_token(self):
        return self.conn.get_auth_token()

    def set_auth_token(self, token):
        self.conn.set_auth_token(token)

    def request(self, sitename, path, method='GET', data=None):
        if path == '/get':
            return self.get(sitename, data)
        elif path == '/get_many':
            return self.get_many(sitename, data)
        elif path == '/write':
            return self.write(sitename, data)
        elif path.startswith('/save/'):
            return self.save(sitename, path, data)
        elif path == '/save_many':
            return self.save_many(sitename, data)
        else:
            return self.conn.request(sitename, path, method, data)

    def get(self, sitename, data):
        return self.conn.request(sitename, '/get', 'GET', data)

    def get_many(self, sitename, data):
        return self.conn.request(sitename, '/get_many', 'GET', data)

    def write(self, sitename, data):
        return self.conn.request(sitename, '/write', 'POST', data)

    def save(self, sitename, path, data):
        return self.conn.request(sitename, path, 'POST', data)

    def save_many(self, sitename, data):
        return self.conn.request(sitename, '/save_many', 'POST', data)
        
        
_memcache = None
        
class MemcacheMiddleware(ConnectionMiddleware):
    def __init__(self, conn, memcache_servers):
        ConnectionMiddleware.__init__(self, conn)
        self.memcache = self.get_memcache(memcache_servers)
        
    def get_memcache(self, memcache_servers):
        global _memcache
        if _memcache is None:
            from openlibrary.utils import olmemcache
            _memcache = olmemcache.Client(memcache_servers)
        return _memcache

    def get(self, sitename, data):
        key = data.get('key')
        revision = data.get('revision')
        
        if revision is None:
            result = self.memcache.get(key) 
        else:
            result = None
            
        return result or ConnectionMiddleware.get(self, sitename, data)
        
    def get_many(self, sitename, data):
        keys = simplejson.loads(data['keys'])
        result = self.memcache.get_multi(keys)
        
        keys2 = [k for k in keys if k not in result]
        if keys2:
            data['keys'] = simplejson.dumps(keys2)
            result2 = ConnectionMiddleware.get_many(self, sitename, data)
            result.update(simplejson.loads(result2))
        
        #@@ too many JSON conversions
        for k in result:
            if isinstance(result[k], basestring):
                result[k] = simplejson.loads(result[k])
                
        return simplejson.dumps(result)


_cache = None
        
class LocalCacheMiddleware(ConnectionMiddleware):
    def __init__(self, conn, cache_prefixes, cache_size=10000):
        ConnectionMiddleware.__init__(self, conn)
        self.cache_prefixes = cache_prefixes
        self.cache = self.get_cache(cache_size)
        
    def get_cache(self, cache_size):
        global _cache
        if _cache is None:
            _cache = lru.LRU(cache_size)

            class hook(client.hook):
                def on_new_version(self, page):
                    if page.key in _cache:
                        _cache.delete(page.key)
            
        return _cache
    
    def get(self, sitename, data):
        key = data.get('key')
        revision = data.get('revision')

        def _get():
            return ConnectionMiddleware.get(self, sitename, data)

        if revision is None and self.cachable(key):
            response = self.cache.get(key)
            if not response:
                response = _get()
                self.cache[key] = response
        else:
            response = _get()
        return response
        
    def write(self, sitename, data):
        response_str = ConnectionMiddleware.write(self, sitename, data)

        result = simplejson.loads(response_str)
        modified = result['created'] + result['updated']
        keys = [k for k in modified if self.cachable(k)]
        self.cache.delete_many(keys)
        return response_str

    def save(self, sitename, path, data):
        response_str = ConnectionMiddleware.save(self, sitename, path, data)
        result = simplejson.loads(response_str)
        if result:
            self.cache.delete(result['key'])
        return response_str

    def save_many(self, sitename, data):
        response_str = ConnectionMiddleware.save_many(self, sitename, data)
        result = simplejson.loads(response_str)
        keys = [r['key'] for r in result]
        self.cache.delete_many(keys)
        return response_str

    def cachable(self, key):
        """Tests if key is cacheable."""
        for prefix in self.cache_prefixes:
            if key.startswith(prefix):
                return True
        return False

def OLConnection():
    """Create a connection to Open Library infobase server."""
    def create_connection():
        if config.get('infobase_server'):
            return client.connect(type='remote', base_url=config.infobase_server)
        elif config.get('db_parameters'):
            return client.connect(type='local', **config.db_parameters)
        else:
            raise Exception("db_parameters are not specified in the configuration")

    conn = create_connection()

    cache_prefixes = config.get("cache_prefixes", default_cache_prefixes)
    if cache_prefixes :
        conn = LocalCacheMiddleware(conn, cache_prefixes)

    if config.get('memcache_servers'):
        conn = MemcacheMiddleware(conn, config.get('memcache_servers'))

    return conn

