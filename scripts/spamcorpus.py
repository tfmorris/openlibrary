# -*- coding: utf-8 -*-
"""
Use the OpenLibrary spam reversion history to create a corpus of spam.

Signals to look at:
- edit frequency, edit history, total edits, most recent edit for account
- add-book frequency/count
- letter distribution of user name (fasdasdfa)
- word frequency in text fields
- readability / grammar 
- URL count
- delta time between account creation & first edit
- username & displayname letter N-grams
- username vs displayname correspondance
- consenant vs vowel distribution
- digit vs letter distribution
- link targets & anchor text
- repetition in text or table of content

Created on 2015-09-02

@author: Tom Morris <tfmorris@gmail.com>
@copyright 2015 Thomas F. Morris
"""

import requests
import requests_cache
from collections import Counter

requests_cache.install_cache('openlibrary_cache')

BASE='https://openlibrary.org'
CHANGES = BASE + '/recentchanges'
LIMIT=1000
MAX= 10000 # 10000
FETCH_CHANGESETS = True # True to fetch reverted change sets
CHANGESET_SAMPLE = 1 # Select one of every SAMPLE records
CHANGESETS_MAX = 10 # Only fetch first N changes of revert (ie last N to be reverted)
FETCH_CHANGES = True

total_revert_count = 0
sampled_revert_count = 0
changeset_count = 0
changes_count = 0
kinds = Counter() # kinds of changesets
types = Counter() # types of changed documents (book, work, etc)
for offset in range(0,MAX-LIMIT+1,LIMIT):
    print('=============== %d ==================' % offset)
    url = CHANGES + '/revert.json'
    params = {'offset': offset, 'limit' : LIMIT}
    # TODO: In production, don't use cache for recentchange list
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
        # Only sample changesets?  Be sure to include last reverted (add-user)
        if CHANGESETS_MAX <= 0:
            continue
        for changeid in reversion['data']['reverted_changesets'][-1*(CHANGESETS_MAX+1):99999]:
            # Use dummy date and default type to fetch change set by ID
            url = CHANGES + ('/0000/00/00/default/%s.json' % changeid)
            response = requests.get(url)
            if not response.ok:
                print('Failed to fetch url %d %s' % (response.status_code, url))
                continue
            changeset = response.json()
            assert changeid == changeset['id']
            # fields: author or ip, kind, timestamp, comment
            if changeset['author']:
                author = changeset['author']['key']
            else:
                author = changeset['ip']
            #print changeset['timestamp']
            kind = changeset['kind']
            kinds[kind] += 1
            changes = changeset['changes']
            changes_count += len(changes) # typically only 1-2 changes
            #print('---', kind, len(changes), author)
            for change in changes:
                key = change['key']
                rev = change['revision']
                types[key.split('/')[1]] +=1
                if not FETCH_CHANGES:
                    print(key, rev)
                    continue
                if '/lists/' in key: # BUG neither .json nor ?format=json works
                    continue
                url = BASE + key + '.json'
                response = requests.get(url, {'v':rev})
                try:
                    spam = response.json()
                except:
                    print('Unabled to decode response for: ' + url)
                if key.startswith('/people/') and len(key.split('/')) == 3:
                    username = key[8:9999]
                    displayname = spam[u'displayname']
                    created = spam['created']['value']
                    # TODO: track deltatime between account creation & revert
                    print(username, displayname, created)
                elif key.startswith('/book') or key.startswith('/work'):
                    text = ''
                    if 'title' in spam:
                        text += spam['title']
                    for key in ['table_of_contents']:
                        if key in spam:
                            for t in spam[key]:
                                text += t['title']
                    for key in ['subjects','subject_people','subject_places','subject_times']:
                        if key in spam:
                            for t in spam[key]:
                                text += t
                    if 'description' in spam:
                        d = spam['description']
                        if isinstance(d, basestring):
                            text += d
                        else:
                            text += d['value']
                    if 'table_of_contents' in spam:
                        #print('**TOC**')
                        for t in spam['table_of_contents']:
                            text += t['title']
                # print spam
                # TODO: need to check for multiple spams in a row
                # no ham for add-book or edit-book after add-book
                # ?? Do ham entirely separately by sample human edits? ??
                # previous good version could be a bot bulk add with entirely
                # different signature from human edit
                #if rev > 1:
                #    response = requests.get(url, {'v':rev-1})
                #    ham = response.json()
    # Assume a short read means that we're done
    if len(reversions) < LIMIT:
        break
        
print('Processed %d of %d reversions (%2.1f%%) with %d changesets & %d changes (capped at %d per reversion)' % (sampled_revert_count, total_revert_count, (sampled_revert_count * 100.0) / total_revert_count, changeset_count, changes_count, CHANGESETS_MAX))
print('Changeset kinds:')
for (k, n) in kinds.most_common():
    print(k, n)
print('Document types:')
for (t, n) in types.most_common():
    print(t, n)