import os
import time
import sched
import datetime
import subprocess

class BadCronLine(ValueError): pass

class Minicron(object):
    def __init__(self, cronfile, tickfreq = 60):
        self.tickfreq = tickfreq
        self.cronfile = cronfile
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.scheduler.enter(self.tickfreq, 1, self._tick, ())

    def _matches_cron_expression(self, ctime, cronline):
        """Returns True if the provided time matches the expression in
        the given cronline"""
        def match_minute(ctime, exp):
            if exp == "*":
                return True
            if "/" in exp:
                a,b = exp.split("/")
                return not ctime.minute % int(b)
            if ctime.minute == int(exp):
                return True

        def match_hour(ctime, exp):
            if exp == "*":
                return True
            if "/" in exp:
                a,b = exp.split("/")
                return not ctime.hour % int(b)
            if ctime.hour == int(exp):
                return True

        mm, hh, dom, moy, dow, cmd = cronline.split(None, 5)
        
        if not all(x == "*" for x in [dom, moy, dow]):
            raise BadCronLine("Only minutes and hours may be set. The others have to be *")

        return all([match_minute(ctime, mm),
                    match_hour  (ctime, hh)])
            
    def _check_and_run_commands(self, ctime):
        """Checks each line of the cron input file to see if the
        command is to be run. If so, it runs it"""
        f = open(self.cronfile)
        for cronline in f:
            if self._matches_cron_expression(ctime, cronline):
                mm, hh, dom, moy, dow, cmd = cronline.split(None, 5)
                p = subprocess.Popen([cmd], shell = True)
                p.wait()
        f.close()

    def _tick(self):
        "The ticker that gets called once a minute"
        ctime = datetime.datetime.fromtimestamp(time.time())
        self._check_and_run_commands(ctime)
        if self.times == None:
            self.scheduler.enter(self.tickfreq, 1, self._tick, ())
        elif self.times > 0:
            self.times -= 1
            self.scheduler.enter(self.tickfreq, 1, self._tick, ())

        
        

    def run(self, times = None):
        self.times = times
        self.scheduler.run()
