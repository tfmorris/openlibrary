"""Controller for home page.
"""
import random
import web

from infogami.utils import delegate
from infogami.utils.view import render_template, public
from infogami.infobase.client import storify
from infogami import config

from openlibrary.core import admin, cache, ia, helpers as h
from openlibrary.plugins.upstream.utils import get_blog_feeds
from openlibrary.plugins.worksearch import search

class home(delegate.page):
    path = "/"
    
    def is_enabled(self):
        return "lending_v2" in web.ctx.features
    
    def GET(self):
        try:
            stats = admin.get_stats()
        except Exception:
            stats = None
        blog_posts = get_blog_feeds()
        
        lending_list = config.get("home", {}).get("lending_list")
        returncart_list = config.get("home", {}).get("returncart_list")
        
        return render_template("home/index", 
            stats=stats,
            blog_posts=blog_posts,
            lending_list=lending_list,
            returncart_list=returncart_list)

@public
def carousel_from_list(key, randomize=False, limit=60):
    id = key.split("/")[-1] + "_carousel"
    
    data = format_list_editions(key)
    if randomize:
        random.shuffle(data)
    data = data[:limit]
    return render_template("books/carousel", storify(data), id=id)
    
@public
def render_returncart(limit=60, randomize=True):
    data = get_returncart(limit*5)
    if randomize:
        random.shuffle(data)
    data = data[:limit]
    return render_template("books/carousel", storify(data), id="returncart_carousel")

def get_returncart(limit):
    if 'env' not in web.ctx:
        delegate.fakeload()
    
    items = web.ctx.site.store.items(type='ebook', name='borrowed', value='false', limit=limit)
    keys = [doc['book_key'] for k, doc in items if 'book_key' in doc]
    books = web.ctx.site.get_many(keys)
    return [format_book_data(book) for book in books]
    
# cache the results of get_returncart in memcache for 15 minutes
get_returncart = cache.memcache_memoize(get_returncart, "home.get_returncart", timeout=15*60)

@public
def readonline_carousel(id="read-carousel"):
    try:
        data = random_ebooks()
        if len(data) > 120:
            data = random.sample(data, 120)
        return render_template("books/carousel", storify(data), id=id)
    except Exception:
        return None

def random_ebooks(limit=1000):
    solr = search.get_works_solr()
    sort = "edition_count desc"
    start = random.randint(0, 1000)
    result = solr.select(
        query='has_fulltext:true -public_scan_b:false', 
        rows=limit, 
        start=start,
        sort=sort,
        fields=[
            'has_fulltext',
            'key',
            'ia',
            "title",
            "cover_edition_key",
            "author_key", "author_name",
        ])
    
    def process_doc(doc):
        d = {}
        d['url'] = "/works/" + doc['key']
        d['title'] = doc.get('title', '')
        
        if 'author_key' in doc and 'author_name' in doc:
            d['authors'] = [{"key": key, "name": name} for key, name in zip(doc['author_key'], doc['author_name'])]
            
        if 'cover_edition_key' in doc:
            d['cover_url'] = h.get_coverstore_url() + "/b/olid/%s-M.jpg" % doc['cover_edition_key']
            
        d['read_url'] = "http://www.archive.org/stream/" + doc['ia'][0]
        return d
        
    return [process_doc(doc) for doc in result['docs'] if doc.get('ia')]

# cache the results of random_ebooks in memcache for 15 minutes
random_ebooks = cache.memcache_memoize(random_ebooks, "home.random_ebooks", timeout=15*60)

def format_list_editions(key):
    """Formats the editions of the list suitable for display in carousel.
    """
    if 'env' not in web.ctx:
        delegate.fakeload()
    
    list = web.ctx.site.get(key)
    if not list:
        return []
    
    editions = {}
    for seed in list.seeds:
        if not isinstance(seed, basestring):
            if seed.type.key == "/type/edition": 
                editions[seed.key] = seed
            else:
                try:
                    e = pick_best_edition(seed)
                except StopIteration:
                    continue
                editions[e.key] = e
    return [format_book_data(e) for e in editions.values()]
    
# cache the results of format_list_editions in memcache for 5 minutes
format_list_editions = cache.memcache_memoize(format_list_editions, "home.format_list_editions", timeout=5*60)

def pick_best_edition(work):
    return (e for e in work.editions if e.ocaid).next()

def format_book_data(book):
    d = web.storage()
    d.key = book.key
    d.url = book.url()
    d.title = book.title or None
    
    def get_authors(doc):
        return [web.storage(key=a.key, name=a.name or None) for a in doc.get_authors()]
        
    work = book.works and book.works[0]
    if work:
        d.authors = get_authors(work)
    else:
        d.authors = get_authors(book)

    cover = book.get_cover()
    if cover:
        d.cover_url = cover.url("M")
        
    overdrive = book.get("identifiers", {}).get('overdrive')
    if overdrive:
        d.overdrive_url = "http://search.overdrive.com/SearchResults.aspx?ReserveID={%s}" % overdrive

    ia_id = book.get("ocaid")
    if ia_id:
        collections = ia.get_meta_xml(ia_id).get("collection", [])
        if 'printdisabled' in collections or 'lendinglibrary' in collections:
            d.daisy_url = book.url("/daisy")
            
        if 'lendinglibrary' in collections:
            d.borrow_url = book.url("/borrow")
        elif 'inlibrary' in collections:
            d.inlibrary_borrow_url = book.url("/borrow")
        else:
            d.read_url = book.url("/borrow")
    return d

def setup():
    pass