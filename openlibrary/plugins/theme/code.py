import os
import re
import web
import simplejson
import logging
from collections import defaultdict

from infogami.utils import delegate
from infogami.utils.view import render_template, add_flash_message

from openlibrary import accounts

from .git import Git, CommandError

logger = logging.getLogger("openlibrary.theme")


def admin_only(f):
    def g(*a, **kw):
        user = accounts.get_current_user()
        if user is None or not user.is_admin():
            return render_template("permission_denied",  web.ctx.path, "Permission denied.")
        return f(*a, **kw)
    return g


def find_files(root, filter):
    '''Find all files that pass the filter function in and below
    the root directory.
    '''
    absroot = os.path.abspath(root)
    for path, dirs, files in os.walk(os.path.abspath(root)):
        path = root + web.lstrips(path, absroot)
        
        for file in files:
            f = os.path.join(path, file)
            if filter(f):
                yield f

RE_PATH = re.compile("(/templates/.*.html|/macros/.*.html|/js/.*.js|/css/.*.css)$")
        
def list_files():
    dirs = [
        "openlibrary/plugins/openlibrary", 
        "openlibrary/plugins/upstream", 
        "openlibrary/plugins/admin",
        "openlibrary/plugins/worksearch",
        "openlibrary/plugins/theme",
        "openlibrary/admin", 
        "static"
    ]
        
    files = []
    for d in dirs:
        files += list(find_files(d, RE_PATH.search))    
    return sorted(files)

class index(delegate.page):
    path = "/theme"
    
    def GET(self):
        raise web.seeother("/theme/files")

class file_index(delegate.page):
    path = "/theme/files"

    @admin_only
    def GET(self):
        files = list_files()
        modified = Git().status()
        return render_template("theme/files", files, modified)

class file_view(delegate.page):
    path = "/theme/files/(.+)"

    @admin_only
    def delegate(self, path):
        if not os.path.isfile(path) or not RE_PATH.search(path):
            raise web.seeother("/theme/files#" + path)
            
        i = web.input(_method="GET")
        name = web.ctx.method.upper() + "_" + i.get("m", "view")
        f = getattr(self, name, None)
        if f:
            return f(path)
        else:
            return self.GET_view(path)
            
    GET = POST = delegate
    
    def GET_view(self, path):
        text = open(path).read()
        diff = Git().diff(path)
        return render_template("theme/viewfile", path, text, diff=diff)

    def GET_edit(self, path):
        text = open(path).read()
        return render_template("theme/editfile", path, text)
        
    def POST_edit(self, path):
        i = web.input(_method="POST", text="")
        i.text = i.text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        f = open(path, 'w')
        f.write(i.text)
        f.close()
        
        logger.info("Saved %s", path)
        
        # run make after editing js or css files
        if not path.endswith(".html"):
            logger.info("Running make")
            cmd = Git().system("make")
            logger.info(cmd.stdout)
        
        add_flash_message("info", "Page has been saved successfully.")
        raise web.seeother(web.ctx.path)
        
    def POST_revert(self, path):
        logger.info("running git checkout %s", path)
        cmd = Git().system("git checkout " + path)
        logger.info(cmd.stdout)
        add_flash_message("info", "All changes to this page have been reverted successfully.")
        raise web.seeother(web.ctx.path)
                
class gitview(delegate.page):
    path = "/theme/modifications"
    
    @admin_only
    def GET(self):
        modified = [f for f in Git().modified() if RE_PATH.search(f.name)]
        return render_template("theme/git", modified)

    @admin_only
    def POST(self):
        i = web.input(files=[], message="")
                
        git = Git()
        commit = git.commit(i.files, author=self.get_author(), message=i.message or "Changes from dev.")
        push = git.push()
        
        return render_template("theme/committed", commit, push)

    def get_author(self):
        user = accounts.get_current_user()
        return "%s <%s>" % (user.displayname, user.get_email())
        
class manage(delegate.page):
    path = "/theme/manage"
    
    @admin_only
    def GET(self):
        return render_template("theme/manage")
        
class gitmerge(delegate.page):
    path = "/theme/git-merge"
    
    @admin_only
    def POST(self):
        git = Git()
        
        d = web.storage(commands=[], success=True)
        
        def run(command):
            if d.success:
                cmd = git.system(command, check_status=False)
                d.commands.append(cmd)
                d.success = (cmd.status == 0)
                
        run("git fetch origin")
        run("git merge origin/master")
        run("git push")
        run("make")
        # Send SIGUP signal to master gunicorn process to reload
        run("kill -HUP %s" % os.getppid())
        return render_template("theme/commands", d.success, d.commands)
    
