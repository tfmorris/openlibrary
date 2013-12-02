"""Loan Stats"""
import web
from .. import app
from ..core.loanstats import LoanStats

class stats(app.view):
    path = "/stats"

    def GET(self):
        raise web.seeother("/stats/lending")

class lending_stats(app.view):
    path = "/stats/lending(?:/(libraries|regions|collections)/(.+))?"

    def GET(self, key, value):
        stats = LoanStats()
        if key == 'libraries':
            stats.library = value
        elif key == 'regions':
            stats.region = value
        elif key == 'collections':
            stats.collection = value
        return app.render_template("stats/lending.html", stats)
