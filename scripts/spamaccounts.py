# -*- coding: utf-8 -*-
"""
Use the OpenLibrary spam reversion history to create a list of spammers.
The revert history begins 2011-04-20, so earlier spam fighting was done with
individual edits.

Created on 2015-09-02

@author: Tom Morris <tfmorris@gmail.com>
@copyright 2015 Thomas F. Morris
"""

from __future__ import print_function
from datetime import datetime
import requests
import requests_cache

requests_cache.install_cache('openlibrary_cache')

BASE='https://openlibrary.org'
CHANGES = BASE + '/recentchanges'
LIMIT=1000
MAX= 10000 # Currently (Jan 2016) just over 8200 records for 6700 unique accounts
CHANGESET_SAMPLE = 1 # Select one of every SAMPLE records

total_revert_count = 0
sampled_revert_count = 0
changeset_count = 0
changes_count = 0
seen = set()

for offset in range(0,MAX-LIMIT+1,LIMIT):
    url = CHANGES + '/revert.json'
    params = {'offset': offset, 'limit' : LIMIT}
    with requests_cache.disabled(): # disable cache so most recent is fresh
        response = requests.get(url, params = params)
    if not response.ok:
        print('Failed to fetch url %d %s' % (response.status_code, url))
        continue
    reversions = response.json()
    
    # process data
    for reversion in reversions:
        total_revert_count += 1
        # Sample to get better temporal coverage
        if total_revert_count % CHANGESET_SAMPLE != 0:
            continue
        sampled_revert_count += 1
        changeset_count += len(reversion['data']['reverted_changesets'])
        changelen = len(reversion['changes'])
        changes_count += changelen
        key = None
        for change in reversion['changes']:
            if change['key'].startswith('/people/'):
                key = '/' + '/'.join(change['key'].split('/')[1:3])
                if not key in seen:
                    seen.add(key)
                    response = requests.get('https://openlibrary.org'+key+'.json',{'m':'history'})
                    history = response.json()
                    start = datetime.strptime(history[-1]['created'],'%Y-%m-%dT%H:%M:%S.%f')
                    end = datetime.strptime(history[0]['created'],'%Y-%m-%dT%H:%M:%S.%f')
                    days = (end-start).days
                    hours= (end-start).seconds/3600
                    # TODO: this only counts one set of reversions if there are multiple for an account
                    print('\t'.join([key,str(changelen),reversion['timestamp'],str(start),str(end),str(days),str(hours)]))
                break
    # Assume a short read means that we're done
    if len(reversions) < LIMIT:
        break
print('Found %d spam accounts' % len(seen))
print('Processed %d of %d reversions (%2.1f%%) with %d changesets & %d changes' % (sampled_revert_count, total_revert_count, (sampled_revert_count * 100.0) / total_revert_count, changeset_count, changes_count))
