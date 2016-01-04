# -*- coding: utf-8 -*-
"""
Analyze new account creation on OpenLibrary using the recentchanges API.

Additional things to analyze
- look at time to first edit, edit rate over time
- characteristics of spam vs non-spam accounts


Created on 2015-09-02

@author: Tom Morris <tfmorris@gmail.com>
@copyright 2015 Thomas F. Morris
"""

from __future__ import print_function
import datetime
import matplotlib.pyplot as plt
import requests
import requests_cache

requests_cache.install_cache('openlibrary_cache')

BASE='https://openlibrary.org'
CHANGES = BASE + '/recentchanges/%04d/%02d/%02d/'
LIMIT=1000
MAX= 100000
PLOTCLIP = 3000
START = datetime.datetime(2007, 5, 2) # Beginning of time for OpenLibrary
TRANSITION1 = datetime.datetime(2009, 3, 9)
TRANSITION2 = datetime.datetime(2009, 12, 25)
TRANSITION3 = datetime.datetime(2010, 7, 22)
TRANSITION4 = datetime.datetime(2011, 6, 9)
END = datetime.datetime.utcnow() + datetime.timedelta(days = 1)

total = 0
counts = []
dates = []
outliers = []

date = START
while date < END:
    count = 0
    # Before 2011 it's 'create' then 'register' not 'new-account'
    if date < TRANSITION1:
        kind = 'create'
    elif date >= TRANSITION1 and date < TRANSITION2:
        kind = 'register'
    elif date >= TRANSITION2 and date < TRANSITION3:
        kind = 'create' # back to create - yea, chaos!
    elif date >= TRANSITION3 and date < TRANSITION4:
        kind = 'update' # Do we need to screen for rev=1 or something else here?
    else:
        kind = 'new-account'
    url = (CHANGES % (date.year, date.month, date.day)) + kind + '.json'
    url += '?bot=false' # Is this safe to assume?
    for offset in range(0, MAX-LIMIT, LIMIT):
        params = {'offset': offset, 'limit' : LIMIT}
        response = requests.get(url, params = params)
        if not response.ok: # TODO retry 5XX ?
            print('Failed to fetch url %d %s' % (response.status_code, url))
            continue
        accounts = response.json()
        for account in accounts:
            key = account['changes'][0]['key']
            aid = account['id']
            time = account['timestamp']
            if key.startswith('/people/') and len(key.split('/')) < 4: # Only necessary 2007-2009
                print('%s\t%s\t%s' % (key,aid,time))
                count += 1
        if len(accounts) < LIMIT:
            break
    total += count
    dates.append(date)
    counts.append(min(count, PLOTCLIP))
    if count > PLOTCLIP:
        # print(date, count)  # 2014-3-13 6549 mentioned on reddit.com/r/books https://redd.it/209un2
        outliers.append((len(dates), count))
        # TODO label outliers with value label on graph where clipped?

    date += datetime.timedelta(days = 1)

# Write CSV file with data
#for date, count in zip(dates,counts):
    #print('%s\t%d' % (date.isoformat(), count))

today = datetime.datetime.utcnow().isoformat().split('T')[0]
print('Found %d total OpenLibrary accounts as of %s' % (total, today))

fig = plt.figure()
ax = fig.add_subplot(111)

ax.plot(dates, counts)
plt.ylabel('New OpenLibrary accounts')
#ax.annotate('Outlier = %d' % outliers[0][1], xy=(outliers[0][0],200), xytext=(10,10),
#            arrowprops=dict(facecolor='black', shrink=0.05))
fig.savefig('openlibrary-accounts-'+today+'.svg',format='svg')
plt.show()
