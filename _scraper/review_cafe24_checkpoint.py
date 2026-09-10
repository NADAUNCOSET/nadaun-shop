"""Reparse saved review HTML without contacting a supplier or publishing products."""
import argparse
from collections import Counter
from contextlib import closing, nullcontext
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

import sync_cafe24_partners as catalog


def review(source, apply=False, work=None):
    work = Path(work) if work is not None else catalog.STATE / source
    database = work / 'checkpoint.sqlite3'
    inventory = json.loads((work / 'inventory-candidate.json').read_text())
    checked_at = catalog.stamp()
    report = {'source': source, 'at': checked_at, 'applied': apply,
              'supplier_requests': 0, 'published': False, 'results': {}}
    with catalog.run_lock(work) if apply else nullcontext():
        db = sqlite3.connect(database.as_uri() + ('?mode=rw' if apply else '?mode=ro'), uri=True)
        try:
            if apply:
                folder = work / 'parser-backups'
                folder.mkdir(exist_ok=True)
                backup = folder / (checked_at.replace(':', '-') + '.sqlite3')
                if backup.exists():
                    raise FileExistsError(backup)
                with closing(sqlite3.connect(backup)) as destination:
                    db.backup(destination)
                    if destination.execute('PRAGMA quick_check').fetchone() != ('ok',):
                        raise RuntimeError('Checkpoint backup failed integrity check')
                report['backup'] = str(backup.relative_to(catalog.ROOT))
            changes = []
            for path in sorted((work / 'review-pages').glob('*.html.gz')):
                sid = path.name.split('.')[0]
                old = db.execute('SELECT record,evidence FROM details WHERE id=?', (sid,)).fetchone()
                error = db.execute('SELECT error,at FROM errors WHERE id=?', (sid,)).fetchone()
                if not old and not error:
                    continue
                previous = json.loads(old[0]) if old else {}
                observed_at = previous.get('detail_checked_at') or (error[1] if error else None)
                if not observed_at:
                    raise ValueError('Missing original observation timestamp: ' + sid)
                raw = gzip.decompress(path.read_bytes())
                digest = hashlib.sha256(raw).hexdigest()
                if old and json.loads(old[1]).get('html_sha256') not in (None, digest):
                    raise ValueError('Saved HTML differs from checkpoint evidence: ' + sid)
                product = inventory['products'][sid]
                product = dict(product)
                nodes = {node['id']: node for node in inventory.get('categories', [])}
                product['brand'] = catalog.inventory_brand(product.get('brand_category_ids', []), nodes, catalog.SITES[source][1]) or product.get('brand', '')
                try:
                    record, evidence = catalog.detail(catalog.soup(raw), product, product['brand'])
                except (ValueError, KeyError, TypeError) as exc:
                    report['results'][sid] = {'status': 'parse_error', 'error': str(exc)}
                    continue
                record['detail_checked_at'] = observed_at
                record['local_reparsed_at'] = checked_at
                evidence.update(html_sha256=digest, local_reparsed_at=checked_at)
                changes.append((sid, record, evidence))
                report['results'][sid] = {'status': record['detail_status'],
                                          'issues': record['content_issues'],
                                          'source_observed_at': observed_at}
            if apply:
                with db:
                    for sid, record, evidence in changes:
                        db.execute('INSERT OR REPLACE INTO details VALUES(?,?,?)',
                                   (sid, json.dumps(record, ensure_ascii=False), json.dumps(evidence, ensure_ascii=False)))
                        db.execute('DELETE FROM errors WHERE id=?', (sid,))
                rows = {sid: json.loads(record) for sid, record in db.execute('SELECT id,record FROM details')}
                errors = dict(db.execute('SELECT id,error FROM errors'))
                reviews = {sid: row['content_issues'] for sid, row in rows.items() if row['detail_status'] != 'verified'}
                candidate_path = work / 'catalogue-candidate.json'
                changed = []
                if candidate_path.exists():
                    candidate = json.loads(candidate_path.read_text())
                    changed = candidate.get('changed_categories', [])
                    report['previous_candidate_sha256'] = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
                    catalog.save_json(folder / (backup.stem + '-candidate.json'), candidate)
                    candidate.update(products={row['id']: row for row in rows.values()}, product_count=len(rows),
                                     detail_errors=errors, content_reviews=reviews, complete=False,
                                     local_reparsed_at=checked_at, reconciliation_required=True)
                    catalog.save_json(candidate_path, candidate)
                remaining = inventory['product_count'] - len(rows) - len(errors)
                phase = 'details' if remaining else 'review_required' if errors or reviews else 'reconciliation_required'
                progress = {'at': checked_at, 'phase': phase, 'products_found': inventory['product_count'],
                            'details_checked': len(rows) + len(errors), 'details_parsed': len(rows),
                            'details_verified': len(rows) - len(reviews), 'detail_errors': len(errors),
                            'content_reviews': len(reviews), 'remaining_details': remaining,
                            'changed_categories': changed, 'complete': False, 'published': False}
                catalog.save_json(work / 'progress.json', progress)
                report['progress'] = progress
            report['summary'] = dict(Counter(row['status'] for row in report['results'].values()))
            if apply:
                catalog.save_json(folder / (backup.stem + '-report.json'), report)
            return report
        finally:
            db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', choices=catalog.SITES)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    result = review(args.source, args.apply)
    print(json.dumps({key: value for key, value in result.items() if key != 'results'}, ensure_ascii=False, indent=2))
