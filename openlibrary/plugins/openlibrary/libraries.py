"""Controller for /libraries.
"""
import time
import logging
import datetime
import itertools

import web
import couchdb

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import inlibrary

logger = logging.getLogger("openlibrary.libraries")

class libraries(delegate.page):
    def GET(self):
        return render_template("libraries/index", self.get_branches())
    
    def get_branches(self):
        branches = sorted(get_library_branches(), key=lambda b: b.name.upper())
        return itertools.groupby(branches, lambda b: b.name[0])
        
def get_library_branches():
    """Returns library branches grouped by first letter."""
    libraries = inlibrary.get_libraries()
    for lib in libraries:
        for branch in lib.get_branches():
            branch.library = lib.name
            yield branch
        
class libraries_register(delegate.page):
    path = "/libraries/add"
    def GET(self):
        return render_template("libraries/add")
        
    def POST(self):
        i = web.input()
        return render_template("libraries/postadd")
        
class participating_libraries(delegate.page):
    path = "/libraries/participating"
    
    def GET(self):
        libraries = inlibrary.get_libraries()
        return render_template("libraries/participating", libraries)

class locations(delegate.page):
    path = "/libraries/locations.txt"

    def GET(self):
        libraries = inlibrary.get_libraries()
        web.header("Content-Type", "text/plain")
        return delegate.RawText(render_template("libraries/locations", libraries))

class stats(delegate.page):
    path = "/libraries/stats"

    def GET(self):
        stats  = LoanStats()
        return render_template("libraries/stats", stats);

@web.memoize
def get_admin_couchdb():
    db_url = config.get("admin", {}).get("counts_db")
    return db_url and couchdb.Database(db_url)

class LoanStats:
    def __init__(self):
        self.db = get_admin_couchdb()

    def view(self, viewname, **kw):
        kw['stale'] = 'ok'
        if self.db:
            return self.db.view(viewname, **kw)
        else:
            return web.storage(rows=[])

    def percent(self, value, total):
        if total == 0:
            return 0
        else:
            return (100.0 * value)/total

    def get_summary(self):
        d = web.storage({
            "total_loans": 0,
            "one_hour_loans": 0,
            "expired_loans": 0
        })

        rows = self.view("loans/duration").rows
        if not rows:
            return d

        d['total_loans']  = rows[0].value['count']

        freq = rows[0].value['freq']

        d['one_hour_loans'] = freq.get("0", 0)
        d['expired_loans'] = sum(count for time, count in freq.items() if int(time) >= 14*24)
        return d

    def get_loans_per_day(self):
        rows = self.view("loans/loans", group=True).rows
        return [[self.date2timestamp(*row.key)*1000, row.value] for row in rows]

    def date2timestamp(self, year, month=1, day=1):
        return time.mktime((year, month, day, 0, 0, 0, 0, 0, 0)) # time.mktime takes 9-tuple as argument

    def date2millis(self, year, month=1, day=1):
        return self.date2timestamp(year, month, day) * 1000

    def get_loan_duration_frequency(self):
        rows = self.view("loans/duration").rows
        if not rows:
            return []

        row = rows[0]
        d = {}
        for time, count in row.value['freq'].items():
            n = 1 + int(time)/24

            # The loan entry gets added to couch only when the loan is deleted in the database, which is probably triggered by a cron job.
            # Even though the max loan duration is 2 weeks, there is a chance that duration is more than 14.
            if n > 14:
                n =15

            d[n] = d.get(n, 0) + count
        return sorted(d.items())

    def get_average_duration_per_month(self):
        """Returns average duration per month."""
        rows = self.view("loans/duration", group_level=2).rows
        minutes_per_day = 60.0 * 24.0
        return [[self.date2timestamp(*row.key)*1000, min(14, row.value['avg']/minutes_per_day)] for row in rows]
        
    def get_average_duration_per_day(self):
        """Returns average duration per day."""
        return [[self.date2millis(*key), value] for key, value in self._get_average_duration_per_day()]
        
    def _get_average_duration_per_day(self):
        """Returns (date, duration-in-days) for each day with duration averaged per day."""
        rows = self.view("loans/duration", group=True).rows
        minutes_per_day = 60.0 * 24.0
        return [[row.key, min(14, row.value['avg']/minutes_per_day)] for row in rows]
        
    def _get_average_duration_per_month(self):
        """Returns (date, duration-in-days) for each day with duration averaged per month."""
        for month, chunk in itertools.groupby(self._get_average_duration_per_day(), lambda x: x[0][:2]):
            chunk = list(chunk)
            avg = sum(v for k, v in chunk) / len(chunk)
            for k, v in chunk:
                yield k, avg
        
    def get_average_duration_per_month(self):
        """Returns (date-in-millis, duration-in-days) for each day with duration averaged per month."""
        return [[self.date2millis(*key), value] for key, value in self._get_average_duration_per_month()]

    def get_popular_books(self, limit=10):
        rows = self.view("loans/books", reduce=False, startkey=["", {}], endkey=[""], descending=True, limit=limit).rows
        counts = [row.key[-1] for row in rows]
        keys = [row.id for row in rows]
        books = web.ctx.site.get_many(keys)
        return zip(books, counts)

    def get_loans_per_book(self, key=""):
        """Returns the distribution of #loans/book."""
        rows = self.view("loans/books", group=True, startkey=[key], endkey=[key, {}]).rows
        return [[row.key[-1], row.value] for row in rows]
        
    def get_loans_per_user(self, key=""):
        """Returns the distribution of #loans/user."""
        rows = self.view("loans/people", group=True, startkey=[key], endkey=[key, {}]).rows
        return [[row.key[-1], row.value] for row in rows]

def on_loan_created(loan):
    """Adds the loan info to the admin stats database.
    """
    logger.debug("on_loan_created")
    db = get_admin_couchdb()
    key = "loans/" + loan['_key']

    t_start = datetime.datetime.utcfromtimestamp(loan['loaned_at'])

    d = {
        "_id": key,
        "book": loan['book'],
        "resource_type": loan['resource_type'],
        "t_start": t_start.isoformat(),
        "status": "active"
    }
    
    library = inlibrary.get_library()
    d['library'] = library and library.key

    if key in db:
        logger.warn("loan document is already present in the stats database: %r", key)
    else:
        db[d['_id']] = d

    yyyy_mm = t_start.strftime("%Y-%m")

    logger.debug("incrementing loan count of %s", d['book'])

    # Increment book loan count
    # Loan count is maintained per month so that it is possible to find popular books per month, year and overall.
    book = db.get(d['book']) or {"_id": d['book']}
    book["loans"][yyyy_mm] = book.setdefault("loans", {}).setdefault(yyyy_mm, 0) + 1
    db[d['book']] = book

    # Increment user loan count
    user_key = loan['user']
    user = db.get(user_key) or {"_id": user_key}
    user["loans"][yyyy_mm] = user.setdefault("loans", {}).setdefault(yyyy_mm, 0) + 1
    db[user_key] = user

def on_loan_completed(loan):
    """Marks the loan as completed in the admin stats database.
    """
    logger.debug("on_loan_completed")
    db = get_admin_couchdb()
    key = "loans/" + loan['_key']
    doc = db.get(key)

    t_end = datetime.datetime.utcfromtimestamp(loan['returned_at'])

    if doc:
        doc.update({
            "status": "completed",
            "t_end": t_end.isoformat()
        })
        db[doc['_id']] = doc
    else:
        logger.warn("loan document missing in the stats database: %r", key)

def setup():
    from openlibrary.core import msgbroker

    msgbroker.subscribe("loan-created", on_loan_created)
    msgbroker.subscribe("loan-completed", on_loan_completed)