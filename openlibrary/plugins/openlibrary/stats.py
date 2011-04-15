"""Hooks for collecting performance stats.
"""
import logging
import traceback

from openlibrary.core import stats as graphite_stats

import web
from infogami import config
from infogami.utils import stats

import filters

l = logging.getLogger("openlibrary.stats")

def evaluate_and_store_stat(name, stat):
    """Evaluates whether the given statistic is to be recorded and if
    so, records it."""
    summary = stats.stats_summary()
    try:
        f = getattr(filters, stat.filter)
    except AttributeError:
        l.critical("Couldn't find filter %s", stat.filter)
        raise
    try:
        if f(web.ctx, params = stat):
            if stat.has_key("time"):
                graphite_stats.put(name, summary[stat.time]["time"] * 100)
            elif stat.has_key("count"):
                print "Storing count for key %s"%stat.count
    except Exception, k:
        tb = traceback.format_exc()
        l.warning("Error while storing stats (%s). Complete traceback follows"%k)
        l.warning(tb)
        
        
    
def update_all_stats():
    """
    Run through the filters and record requested items in graphite
    """
    for stat in config.stats:
        l.debug("Storing stat %s", stat)
        evaluate_and_store_stat(stat, config.stats.get(stat))
        
        
def stats_hook():
    """web.py unload hook to add X-OL-Stats header.
    
    This info can be written to lighttpd access log for collecting
    """
    update_all_stats()
    try:
        if "stats-header" in web.ctx.features:
            web.header("X-OL-Stats", format_stats(stats.stats_summary()))
    except Exception, e:
        # don't let errors in stats collection break the app.
        print >> web.debug, str(e)
        
def format_stats(stats):
    s = " ".join("%s %d %0.03f" % entry for entry in process_stats(stats))
    return '"%s"' %s

labels = {
    "total": "TT",
    "memcache": "MC",
    "infobase": "IB",
    "solr": "SR",
    "archive.org": "IA",
}

def process_stats(stats):
    """Process stats and returns a list of (label, count, time) for each entry.
    
    Entries like "memcache.get" and "memcache.set" will be collapsed into "memcache".
    """
    d = {}
    for name, value in stats.items():
        name = name.split(".")[0]
        
        label = labels.get(name, "OT")
        count = value.get("count", 0)
        time = value.get("time", 0.0)
        
        xcount, xtime = d.get(label, [0, 0])
        d[label] = xcount + count, xtime + time
        
    return [(label, count, time) for label, (count, time) in sorted(d.items())]

