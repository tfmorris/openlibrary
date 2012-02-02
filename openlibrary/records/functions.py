"""
Functions which are used by the records package. The two public ones
are `search` and `create` which are callable from the outside world.
"""

import web

class NoQueryParam(KeyError):
    """
    Exception that is used internally when a find_by_X function is
    called but no X parameters were provided.
    """
    pass
    


def search(params):
    """
    Takes a search parameter and returns a result set

    Input:
    ------

    {'doc': {'identifiers': {'goodreads': ['12345', '12345'],
                             'isbn': ['1234567890'],
                             'lcc': ['123432'],
                             'librarything': ['12312', '231123']},
             'publish_year': '1995',
             'publisher': 'Bantam',
             'title': 'A study in Scarlet'}}

    Output:
    -------

    {'doc': {'isbn': ['1234567890'],
             'key': '/books/OL1M',
             'publish_year': '1995',
             'publisher': 'Bantam',
             'title': 'A study in Scarlet',
             'type': {'key': '/type/edition'},
             'work': [{'authors': [{'authors': [{'birth_date': '1859',
                                                 'death_date': '1930',
                                                 'key': '/author/OL1A',
                                                 'name': 'Arthur Conan Doyle'}]}],
                       'key': '/works/OL1M',
                       'title': 'A study in scarlet',
                       'type': {'key': '/type/work'}}]},
     'matches': [{'edition': '/books/OL1M', 'work': '/works/OL1W'},
                 {'edition': None, 'work': '/works/OL234W'}]}

    'doc' is the best fit match. It's denormalised for convenience. 
    'matches' is a list of possible matches. 

    If a match couldn't be found for a record (e.g. edition), the
    corresponding key will be None.

    """
    doc = params.pop("doc")
    matches = []
    # {'doc': {'identifiers': {'goodreads': ['12345', '12345'],
    #                          'isbn': ['1234567890'],
    #                          'lcc': ['123432'],
    #                          'librarything': ['12312', '231123']},
    #          'publish_year': '1995',
    #          'publisher': 'Bantam',
    #          'title': 'A study in Scarlet'}}

    # Step 1: Search for the results.
    # 1.1 If we have ISBNS, search using that.
    try:
        matches.extend(find_matches_by_isbn(doc))
    except NoQueryParam,e:
        pass


    # Step 2: Pick the best one and expand it.

    # Step 3: Construct the response and return it. 
    print matches
    results = massage_search_results(matches)
    return results


    
def create(records):
    """
    Creates one or more new records in the system.
    TODO: Describe Input/output
    """
    doc = records.pop("doc")
    typ = doc['type']['key']
    if doc['key'] == None:
        key = web.ctx.site.new_key(typ)
        doc['key'] = key
    key = doc['key']
    
    works = authors = []
    if "works" in doc:
        work_records = doc.pop("works")
        works, authors = process_work_records(work_records)
        # Add work references into the edition.
        for w in works:
            wref = {'key': w['key']}
            doc.setdefault("works",[]).append(wref)

    # Now, doc, works and authors contain the documents that need to
    # be put into the database
    docs = [doc] + works + authors
    web.ctx.site.save_many(docs, 'Import new book')
    return key
        
    
    
def process_work_records(work_records):
    """Converts the given 'work_records' into a list of works and
    accounts that can then be directly saved into Infobase"""
    

    works = []
    authors = []
    for w in work_records:

        # Give the work record a key
        if w['key'] == None:
            w['key'] = web.ctx.site.new_key("/type/work")

        # Process any author records which have been provided. 
        if "authors" in w:
            author_records = w.pop("authors")
            for author in author_records:
                role = author.keys()[0]
                author = author[role]
                if author['key'] == None:
                    author['key'] = web.ctx.site.new_key("/type/author")
                authors.append(author) # Add the author to list of records to be saved.
                a = {'type': '/type/author_role', 'author': author['key']}
                w.setdefault('authors',[]).append(a) # Attach this author to the work

        works.append(w) # Add the work to list of records to be saved.

    return works, authors
    



def find_matches_by_isbn(doc):
    "Find matches using isbns."
    try:
        isbns = doc['identifiers']["isbn"]
        q = {
            'type':'/type/edition',
            'isbn_10': isbns[0] #TODO: Change this to isbn_
            }
        ekeys = list(web.ctx.site.things(q))
        if ekeys:
            return ekeys[:1] # TODO: We artificially match only one item here
        else:
            return []
    except KeyError, e:
        raise NoQueryParam(str(e))

def denormalise(item):
    "Denormalises the given item as required by the search results. Used for the best match."
    def expand_authors(authors):
        expanded_authors = []
        for a in authors:
            expanded_authors.append(a.dict())
        return expanded_authors

    def expand_works(works):
        expanded_works = []
        for w in works:
            d = w.dict()
            authors = expand_authors(w.authors)
            d['authors'] = authors
            expanded_works.append(d)
        return expanded_works

    def expand_edition(edition):
        "Expands an edition"
        expanded_edition = edition.dict()
        # First expand the identifiers
        identifiers = {}
        if "isbn_10" in edition and edition["isbn_10"]:
            identifiers.setdefault('isbn',[]).extend(edition["isbn_10"])
        if "isbn_13" in edition and edition["isbn_13"]:
            identifiers.setdefault('isbn',[]).extend(edition["isbn_13"])
        edition.identifiers.update(identifiers)
        # Recursively expand the works
        works = expand_works(edition.works)
        # Fixup the return value and return it. 
        expanded_edition['identifiers'] = identifiers
        expanded_edition['works'] = works
        return expanded_edition

    thing = web.ctx.site.get(item)
    if item.startswith("/books/"):
        return expand_edition(thing)
    elif item.startswith("/works/"):
        return expand_works([thing])[0]
        
def expand(item):
    "Expands an edition or thing into a dictionary used for the search results"
    thing = web.ctx.site.get(item)
    if item.startswith("/books/"):
        return {"edition" : item, "work" : thing.works and thing.works[0].key} #TODO: Is it right to simply use the first?
    if item.startswith("/works/"):
        return {"edition" : None, "work" : item} 

def massage_search_results(matches):
    "Converts a list of keys into the return format of the search API"

    first = matches[0]
    all = matches
    # Denormalise the best match
    best_match = denormalise(first)
    
    # Enumerage the rest of the matches
    matches = []
    for i in all:
        matches.append(expand(i))

    return {"doc" : best_match,
            "matches" : matches}
    

