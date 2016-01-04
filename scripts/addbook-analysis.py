# -*- coding: utf-8 -*-
"""
Analyze rate at which books were added to OpenLibrary over time using
the recentchanges API.

Created on 2015-09-02

@author: Tom Morris <tfmorris@gmail.com>
@copyright 2015 Thomas F. Morris
"""

import datetime
import matplotlib.pyplot as plt
import requests
import requests_cache

requests_cache.install_cache('openlibrary_cache')

BASE='https://openlibrary.org'
CHANGES = BASE + '/recentchanges/%04d/%02d/%02d/'
LIMIT=1000
MAX= 10000 # 10000
PLOTCLIP = 1000
START = datetime.datetime(2010, 8, 1)
END = datetime.datetime.today() + datetime.timedelta(days = 1)
FLAGS = '?bot=false' # human edits only

counts = []
dates = []
outliers = []

date = START
while date < END:
    count = 0
    kind = 'add-book'
    url = (CHANGES % (date.year, date.month, date.day)) + kind + '.json' + FLAGS
    for offset in range(0, MAX-LIMIT, LIMIT):
        params = {'offset': offset, 'limit' : LIMIT}
        response = requests.get(url, params = params)
        if not response.ok: # TODO: retry on 5xx?
            print('Failed to fetch url %d %s' % (response.status_code, url))
            break
        books = response.json()
        count += len(books)
        if len(books) < LIMIT:
            break
            
    #print(date,count)
    dates.append(date)
    counts.append(min(count, PLOTCLIP))
    if count > PLOTCLIP:
        print(date, count)
        outliers.append((len(dates), count))
    
    #print('%s\t%d' % (date.isoformat(), count))
    date += datetime.timedelta(days = 1)

fig = plt.figure()
ax = fig.add_subplot(111)

ax.plot(dates, counts)
plt.ylabel('OpenLibrary new books')
#ax.annotate('Outlier = %d' % outliers[0][1], xy=(outliers[0][0],200), xytext=(10,10),
#            arrowprops=dict(facecolor='black', shrink=0.05))
fig.savefig('openlibrary-books.svg',format='svg')
plt.show()
