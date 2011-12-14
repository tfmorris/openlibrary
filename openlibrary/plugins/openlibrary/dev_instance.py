"""Special customizations for dev instance.

This module is imported only if dev_instance is set to True in openlibrary config.
"""
import web
import infogami
from infogami.utils import delegate
from openlibrary.core.task import oltask
from openlibrary.tasks import other_on_edit_tasks

def setup():
    print "dev_instance.setup"
    setup_solr_updater()
    
    # Run update_solr on every edit
    other_on_edit_tasks.append(update_solr)
        
def setup_solr_updater():
    from infogami import config
    
    # solr-updater reads configuration from openlibrary.config.runtime_config
    from openlibrary import config as olconfig
    olconfig.runtime_config = config.__dict__
    
    # The solr-updater makes a http call to the website insted of using the 
    # infobase API. It requires setting the host before start using it.
    from openlibrary.catalog.utils.query import set_query_host
    
    dev_instance_url = config.get("dev_instance_url", "http://127.0.0.1:8080/")
    host = web.lstrips(dev_instance_url, "http://").strip("/")
    set_query_host(host)

class is_loaned_out(delegate.page):
    path = "/is_loaned_out/.*"
    def GET(self):
        return delegate.RawText("[]", content_type="application/json")

@oltask
def update_solr(changeset):
    """Updates solr on edit.
    """
    from openlibrary.solr import update_work
    
    keys = set()
    docs = changeset['docs'] + changeset['old_docs']
    docs = [doc for doc in docs if doc] # doc can be None if it is newly created.
    for doc in docs:
        if doc['type']['key'] == '/type/edition':
            keys.update(w['key'] for w in doc.get('works', []))
        elif doc['type']['key'] == '/type/work':
            keys.add(doc['key'])
            keys.update(a['author']['key'] for a in doc.get('authors', []) if 'author' in a)
        elif doc['type']['key'] == '/type/author':
            keys.add(doc['key'])

    update_work.update_keys(list(keys))
    
@infogami.install_hook
def add_ol_user():
    """Creates openlibrary user with admin previleges.
    """
    # Create openlibrary user
    if web.ctx.site.get("/people/openlibrary") is None:
        web.ctx.site.register(
            username="openlibrary",
            email="openlibrary@example.com",
            password="openlibrary",
            displayname="Open Library")
        web.ctx.site.activate_account(username="openlibrary")
        
    if web.ctx.site.get("/usergroup/api") is None:
        g_api = web.ctx.site.new("/usergroup/api", {
            "key": "/usergroup/api",
            "type": "/type/usergroup",
            "members": [{"key": "/people/openlibrary"}]
        })
        g_api._save(comment="Added openlibrary user to API usergroup.")
        
    g_admin = web.ctx.site.get("/usergroup/admin").dict()
    g_admin.setdefault('members', [])
    members = [m['key'] for m in g_admin["members"]]
    if 'openlibrary' not in members:
        g_admin['members'].append({"key": "/people/openlibrary"})
        web.ctx.site.save(g_admin, "Added openlibrary user to admin usergroup.")