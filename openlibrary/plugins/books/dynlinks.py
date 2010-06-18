import urllib2
import urllib
import simplejson
import web
import os
import traceback

from openlibrary.plugins.openlibrary.processors import urlsafe

def split_key(bib_key):
    """
        >>> split_key('1234567890')
        ('isbn_10', '1234567890')
        >>> split_key('ISBN:1234567890')
        ('isbn_10', '1234567890')
        >>> split_key('ISBN1234567890')
        ('isbn_10', '1234567890')
        >>> split_key('ISBN1234567890123')
        ('isbn_13', '1234567890123')
        >>> split_key('LCCNsa 64009056')
        ('lccn', 'sa 64009056')
        >>> split_key('badkey')
        (None, None)
    """
    bib_key = bib_key.lower().strip()
    if not bib_key:
        return None, None

    valid_keys = ['isbn', 'lccn', 'oclc', 'ocaid', 'olid']
    key, value = None, None

    # split with : when possible
    if ':' in bib_key:
        key, value = bib_key.split(':', 1)
        key = key.lower()
    else:
        # try prefix match
        for k in valid_keys:
            if bib_key.startswith(k):
                key = k
                value = bib_key[len(k):]
                continue
                
    # treat plain number as ISBN
    if key is None and bib_key[0].isdigit():
        key = 'isbn'
        value = bib_key
        
    # treat OLxxxM as OLID
    if key is None and bib_key.startswith('ol') and bib_key.endswith('m'):
        key = 'olid'
        value = bib_key
    
    # decide isbn_10 or isbn_13 based on length.
    if key == 'isbn':
        if len(value.replace('-', '')) == 13:
            key = 'isbn_13'
        else:
            key = 'isbn_10'

    if key == 'oclc':
        key = 'oclc_numbers'
        
    if key == 'olid':
        key = 'key'
        value = '/books/' + value.upper()

    return key, value


def ol_query(name, value):
    query = {
        'type': '/type/edition',
        name: value,
    }
    keys = web.ctx.site.things(query)
    if keys:
        return keys[0]

def ol_get_many(keys):
    return [doc.dict() for doc in web.ctx.site.get_many(keys)]
    
def query_keys(bib_keys):
    """Given a list of bibkeys, returns a mapping from bibkey to OL key.
    
        >> query(["isbn:1234567890"])
        {"isbn:1234567890": "/books/OL1M"}
    """
    def query(bib_key):
        name, value = split_key(bib_key)
        if name is None:
            return None
        elif name == 'key':
            return value
        else:
            return ol_query(name, value)
    
    d = dict((bib_key, query(bib_key)) for bib_key in bib_keys)
    return dict((k, v) for k, v in d.items() if v is not None)
    
def query_docs(bib_keys):
    """Given a list of bib_keys, returns a mapping from bibkey to OL doc.
    """
    mapping = query_keys(bib_keys)
    things = ol_get_many(uniq(mapping.values()))
    thingdict = dict((t['key'], t) for t in things)
    return dict((bib_key, thingdict[key]) for bib_key, key in mapping.items() if key in thingdict)
    
def uniq(values):
    return list(set(values))
    
def process_result(result, jscmd):
    d = {
        "details": process_result_for_details,
        "data": DataProcessor().process,
        "viewapi": process_result_for_viewapi
    }
    
    f = d.get(jscmd) or d['viewapi']
    return f(result)
    
def get_many_as_dict(keys):
    return dict((doc['key'], doc) for doc in ol_get_many(keys))
    
def get_url(doc):
    if doc['key'].startswith("/books/") or doc['key'].startswith("/works/"):
        return "http://openlibrary.org" + doc['key'] + "/" + urlsafe(doc.get("title", "untitled"))
    elif doc['key'].startswith("/authors/"):
        return "http://openlibrary.org" + doc['key'] + "/" + urlsafe(doc.get("name", "unnamed"))
    else:
        return "http://openlibrary.org" + doc['key']
    
class DataProcessor:
    """Processor to process the result when jscmd=data.
    """
    def process(self, result):
        work_keys = [w['key'] for doc in result.values() for w in doc.get('works', [])]
        self.works = get_many_as_dict(work_keys)
        
        author_keys = [a['author']['key'] for w in self.works.values() for a in w.get('authors', [])]
        self.authors = get_many_as_dict(author_keys)
        
        return dict((k, self.process_doc(doc)) for k, doc in result.items())
        
    def get_authors(self, work):
        author_keys = [a['author']['key'] for a in work.get('authors', [])]
        return [{"url": get_url(self.authors[key]), "name": self.authors[key].get("name", "")} for key in author_keys]
    
    def get_work(self, doc):
        works = [self.works[w['key']] for w in doc.get('works', [])]
        if works:
            return works[0]
        else:
            return {}
        
    def process_doc(self, doc):
        """Processes one document.
        Should be called only after initializing self.authors and self.works.
        """
        w = self.get_work(doc)
        
        def subject(name, prefix):
            return {
                "name": name,
                "url": "http://openlibrary.org/subjects/%s%s" % (prefix, name.lower().replace(" ", "_"))
            }
            
        def get_subjects(name, prefix):
            return [subject(s, prefix) for s in w.get(name, '')]
                    
        d = {
            "url": get_url(doc),
            "title": doc.get("title", ""),
            "subtitle": doc.get("subtitle", ""),
            
            "authors": self.get_authors(w),

            "number_of_pages": doc.get("number_of_pages", ""),
            "weight": doc.get("weight", ""),

            'identifiers': web.dictadd(doc.get('identifiers', {}), {
                'isbn_10': doc.get('isbn_10', []),
                'isbn_13': doc.get('isbn_13', []),
                'lccn': doc.get('lccn', []),
                'oclc': doc.get('oclc_numbers', []),
            }),
            
            'classifications': {},
            
            "publishers": [{"name": p} for p in doc.get("publishers", "")],
            "publish_places": [{"name": p} for p in doc.get("publish_places", "")],
            "publish_date": doc.get("publish_date"),
            
            "subjects": get_subjects("subjects", ""),
            "subject_places": get_subjects("subject_places", "place:"),
            "subject_people": get_subjects("subject_people", "person:"),
            "subject_times": get_subjects("subject_times", "time:"),
            
            "links": [dict(title=link.get("title"), url=link['url']) for link in w.get('links', '') if link.get('url')],
        }
        
        if doc.get('covers'):
            cover_id = doc['covers'][0]
            d['cover'] = {
                "small": "http://covers.openlibrary.org/b/id/%s-S.jpg" % cover_id,
                "medium": "http://covers.openlibrary.org/b/id/%s-M.jpg" % cover_id,
                "large": "http://covers.openlibrary.org/b/id/%s-L.jpg" % cover_id,
            }

        d['identifiers'] = trim(d['identifiers'])
        d['classifications'] = trim(d['classifications'])
        return trim(d)
        
def trim(d):
    """Remote empty values from given dictionary.
    
        >>> trim({"a": "x", "b": "", "c": [], "d": {}})
        {'a': 'x'}
    """
    return dict((k, v) for k, v in d.iteritems() if v)
    
def get_authors(docs):
    """Returns a dict of author_key to {"key", "...", "name": "..."} for all authors in docs.
    """
    authors = [a['key'] for doc in docs for a in doc.get('authors', [])]
    author_dict = {}
    
    if authors:
        for a in ol_get_many(uniq(authors)):
            author_dict[a['key']] = {"key": a['key'], "name": a.get("name", "")}
    
    return author_dict

def process_result_for_details(result):
    def f(bib_key, doc):
        d = process_doc_for_viewapi(bib_key, doc)
        
        if 'authors' in doc:
            doc['authors'] = [author_dict[a['key']] for a in doc['authors']]
            
        d['details'] = doc
        return d
    
    author_dict = get_authors(result.values())
    return dict((k, f(k, doc)) for k, doc in result.items())

def process_result_for_viewapi(result):
    return dict((k, process_doc_for_viewapi(k, doc)) for k, doc in result.items())

def process_doc_for_viewapi(bib_key, page):
    key = page['key']
    
    url = get_url(page)
    
    if 'ocaid' in page:
        preview = 'full'
        preview_url = 'http://www.archive.org/details/' + page['ocaid']
    else:
        preview = 'noview'
        preview_url = url
        
    d = {
        'bib_key': bib_key,
        'info_url': url,
        'preview': preview,
        'preview_url': preview_url,
    }
    
    if page.get('covers'):
        d['thumbnail_url'] = 'http://covers.openlibrary.org/b/id/%s-S.jpg' % page["covers"][0]

    return d      

def format_result(result, options):
    """Format result as js or json.
    
        >>> format_result({'x': 1}, {})
        'var _OLBookInfo = {"x": 1};'
        >>> format_result({'x': 1}, {'callback': 'f'})
        'f({"x": 1});'
    """
    format = options.get('format', '').lower()
    if format == 'json':
        return simplejson.dumps(result)
    else: # js
        json = simplejson.dumps(result)
        callback = options.get("callback")
        if callback:
            return "%s(%s);" % (callback, json)
        else:
            return "var _OLBookInfo = %s;" % json    

def dynlinks(bib_keys, options):
    # for backward-compatibility
    if options.get("details", "").lower() == "true":
        options["jscmd"] = "details"
    
    try:    
        result = query_docs(bib_keys)
        result = process_result(result, options.get('jscmd'))
    except:
        print >> sys.stderr, "Error in processing Books API"
        traceback.print_exc()
        result = {}
    return format_result(result, options)
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()