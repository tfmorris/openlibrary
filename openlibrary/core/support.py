import datetime

import couchdb
from couchdb.mapping import TextField, IntegerField, DateTimeField, ListField, DictField, Mapping, Document

import web
from infogami import config

def get_admin_database():
    admin_db = config.get("admin", {}).get("admin_db",None)
    if admin_db:
        return couchdb.Database(admin_db)
        

class Support(object):
    def __init__(self, db = None):
        if db:
            self.db = db
        else:
            self.db = get_admin_database()
    
    def create_case(self, creator_name, creator_email, creator_useragent, subject, description, assignee):
        "Creates a support case with the given parameters"
        seq = web.ctx.site.sequence.next_value("support-case")
        created = datetime.datetime.utcnow()
        caseid = "case-%s"%seq
        c = Case(_id = caseid,
                 creator_name = creator_name,
                 creator_email = creator_email,
                 creator_useragent = creator_useragent,
                 subject = subject,
                 description = description,
                 assignee = assignee,
                 created = created,
                 status = "new")
        c.store(self.db)
        return c

    def get_case(self, caseid):
        "Returns the case with the given id"
        if not str(caseid).startswith("case"):
            caseid = "case-%s"%caseid
        c = Case.load(self.db, caseid)
        return c
        
            
            
    

class Case(Document):
    _id               = TextField()
    type              = TextField(default = "case")
    status            = TextField()
    assignee          = TextField()
    description       = TextField()
    subject           = TextField()
    creator_email     = TextField()
    creator_useragent = TextField()
    creator_name      = TextField()
    created           = DateTimeField()
    history           = ListField(DictField(Mapping.build(at    = DateTimeField(),
                                                          by    = TextField(),
                                                          text  = TextField())))

    def __init__(self, **kargs):
        super(Case, self).__init__(**kargs)
        item = dict (at = self.created,
                     by = self.creator_name or self.creator_email,
                     text = "Case created")
        self.history.append(item)
        

    @property
    def caseid(self):
        return self._id

    def __eq__(self, second):
        return self._id == second._id

        
                 

        
             
        
        
        
