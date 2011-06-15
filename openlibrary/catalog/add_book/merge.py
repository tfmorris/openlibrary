from openlibrary.catalog.merge.merge_marc import build_marc, attempt_merge
from pprint import pprint

threshold = 875

def db_name(a):
    date = None
    if a.date:
        assert not a.birth_date and not a.death_date
        date = a.date
    elif a.birth_date in a.death_date:
        date = a.get('birth_date', '') + '-' + a.get('death_date', '')
    return ' '.join([a['name'], date]) if date else a['name']

def try_merge(e1, edition_key, existing):
    thing_type = existing.type.key
    if thing_type == '/type/delete':
        return False
    assert thing_type == '/type/edition'

    rec2 = {}
    rec2['full_title'] = existing.title
    if existing.subtitle:
        rec2['full_title'] += ' ' + existing.subtitle
    if existing.lccn:
        rec2['lccn'] = existing.lccn
    rec2['authors'] = [{'name': a.name, 'db_name': db_name(a)}
        for a in existing.authors]
    if existing.publishers:
        rec2['publishers'] = existing.publishers
    if existing.publish_date:
        rec2['publisher_date'] = existing.publish_date

    e2 = build_marc(rec2)
    return attempt_merge(e1, e2, threshold, debug=False)
