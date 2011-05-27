import logging
from lamson.routing import route, route_like, stateless
from config.settings import relay
from lamson import view
from lamson.queue import Queue


@route("support\+(case)@(host)", case="[0-9]+")
@stateless
def CASE(message, case=None, host=None):
    print "I received a message from case %s"%case
    print "And I'm creating a case for it"
    q = Queue("run/cases")
    q.push(message)
    # Create a case for it here. Don't bother forwarding it.
    

@route("(account)@(host)", account = "[^+]+", host=".+")
@stateless
def FORWARD(message, account=None, host=None):
    print "Forwarding message now %s, %s, %s"%(message, account, host)
    relay.deliver(message)

