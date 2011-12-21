import datetime
import textwrap

import web
from infogami.utils.view import render_template, add_flash_message
from infogami import config

from openlibrary.core import support
from openlibrary import accounts

support_db = None

class cases(object):
    def GET(self, typ = "new"):
        current_user = accounts.get_current_user()
        if not support_db:
            return render_template("admin/cases", None, None, True, False)
        i = web.input(sort="status", desc = "false", all = "false")
        sortby = i['sort']
        desc = i['desc']
        cases = support_db.get_all_cases(typ, summarise = False, sortby = sortby, desc = desc)
        if i['all'] == "false":
            cases = (x for x in cases if x.assignee == current_user.get_email())
            summary = support_db.get_all_cases(typ, summarise = True, user = current_user.get_email())
        else:
            summary = support_db.get_all_cases(typ, summarise = True)
        total = sum(int(x) for x in summary.values())
        desc = desc == "false" and "true" or "false"
        return render_template("admin/cases", summary, total, cases, desc)
    POST = GET

class case(object):
    def GET(self, caseid):
        if not support_db:
            return render_template("admin/cases", None, None, True, False)
        case = support_db.get_case(caseid)
        date_pretty_printer = lambda x: x.strftime("%B %d, %Y")
        if len(case.history) == 1:
            last_email = case.description
        else:
            last_email = case.history[-1]['text']
        try:
            last_email = "\n".join("  > %s"%x for x in last_email.split("\n")) + "\n\n"
        except Exception:
            last_email = ""
        admins = ((x.get_email(), x.get_name(), x.get_email() == case.assignee) for x in accounts.get_group("admin").members)
        return render_template("admin/case", case, last_email, admins, date_pretty_printer)

    def POST(self, caseid):
        if not support_db:
            return render_template("admin/cases", None, None, True, False)
        case = support_db.get_case(caseid)
        form = web.input()
        action = form.get("button","")
        {"SEND REPLY" : self.POST_sendreply,
         "UPDATE"     : self.POST_update,
         "CLOSE CASE" : self.POST_closecase,
         "REOPEN CASE": self.POST_reopencase}[action](form,case)
        date_pretty_printer = lambda x: x.strftime("%B %d, %Y")
        last_email = case.history[-1]['text']
        last_email = "\n".join("> %s"%x for x in textwrap.wrap(last_email))
        admins = ((x.get_email(), x.get_name(), x.get_email() == case.assignee) for x in accounts.get_group("admin").members)
        return render_template("admin/case", case, last_email, admins, date_pretty_printer)
    
    def POST_sendreply(self, form, case):
        user = accounts.get_current_user()
        assignee = case.assignee
        casenote = form.get("casenote1", "")
        casenote = "%s replied:\n\n%s"%(user.get_name(), casenote)
        case.add_worklog_entry(by = user.get_email(),
                               text = casenote)
        case.change_status("replied", user.get_email())
        email_to = form.get("email", False)
        subject = "Case #%s: %s"%(case.caseno, case.subject)
        if assignee != user.get_email():
            case.reassign(user.get_email(), user.get_name(), "")
        if email_to:
            message = render_template("admin/email", case, casenote)
            web.sendmail(config.get("support_case_control_address","support@openlibrary.org"), email_to, subject, message)
        add_flash_message("info", "Reply sent")
        raise web.redirect("/admin/support")

    def POST_update(self, form, case):
        casenote = form.get("casenote2", False)
        assignee = form.get("assignee", False)
        user = accounts.get_current_user()
        by = user.get_email()
        text = casenote or ""
        if case.status == "closed":
            case.change_status("new", by)
        if assignee != case.assignee:
            case.reassign(assignee, by, text)
            subject = "Case #%s has been assigned to you"%case.caseno
            message = render_template("admin/email_reassign", case, text)
            web.sendmail(config.get("support_case_control_address","support@openlibrary.org"), assignee, subject, message)
        else:
            case.add_worklog_entry(by = by,
                                   text = text)
        add_flash_message("info", "Case updated")


    def POST_closecase(self, form, case):
        user = accounts.get_current_user()
        by = user.get_email()
        text = "Case closed"
        case.add_worklog_entry(by = by,
                               text = text)
        case.change_status("closed", by)
        add_flash_message("info", "Case closed")
        raise web.redirect("/admin/support")

    def POST_reopencase(self, form, case):
        user = accounts.get_current_user()
        by = user.get_email()
        text = "Case reopened"
        case.add_worklog_entry(by = by,
                               text = text)
        case.change_status("new", by)
        add_flash_message("info", "Case reopened")

def setup():
    global support_db
    try:
        support_db = support.Support()
    except support.DatabaseConnectionError:
        support_db = None


