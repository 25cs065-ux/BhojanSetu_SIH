import sys, json
sys.path.insert(0, '.')
import app as flask_app

with flask_app.app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 'U0001'
        sess['role'] = 'admin'
        sess['user_name'] = 'Admin'
        sess['institution'] = 'Test'
        sess['email'] = 'a@b.com'

    pages = [
        '/dashboard/kitchen', '/dashboard/ngo', '/dashboard/admin',
        '/ngo-matches', '/route-map', '/surplus-exchange',
        '/production-planning', '/sustainability'
    ]
    for p in pages:
        r = c.get(p)
        status = 'OK' if r.status_code == 200 else f'FAIL ({r.status_code})'
        print(f'  {status}  {p}')

    apis = [
        '/api/kitchens', '/api/ngos', '/api/surplus', '/api/matches',
        '/api/sustainability', '/api/production_planning', '/api/route',
        '/api/exchange/listings', '/api/ngo/matches',
        '/api/sustainability/trend', '/api/sustainability/by-kitchen'
    ]
    for a in apis:
        r = c.get(a)
        status = 'OK' if r.status_code == 200 else f'FAIL ({r.status_code})'
        print(f'  {status}  {a}')

print('Done.')
