"""Hooks for in-library lending.
"""
import web
from infogami.utils import filters
from openlibrary.core import inlibrary

def setup():
    web.template.Template.globals.update({
        "get_library", inlibrary.get_library
    })
    
    filters.register_filter("inlibrary", inlibrary.filter_inlibrary)