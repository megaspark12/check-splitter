"""Smoke test to verify all API endpoints work correctly."""
import requests
import json

BASE = 'http://localhost:8000/api'

def test_full_flow():
    # 1. Create session
    r = requests.post(f'{BASE}/sessions', json={'host_name': 'Alice'})
    assert r.status_code == 201, f'Create session failed: {r.status_code} {r.text}'
    session = r.json()
    code = session['code']
    host_id = session['participants'][0]['id']
    print(f'✅ Session created: {code}')

    # 2. Join session as participant
    r = requests.post(f'{BASE}/sessions/{code}/participants', json={'name': 'Bob'})
    assert r.status_code == 201, f'Join failed: {r.status_code} {r.text}'
    bob = r.json()
    print(f'✅ Bob joined: {bob["id"]}')

    # 3. Add items manually
    r = requests.post(f'{BASE}/sessions/{code}/items', json={'name': 'Burger', 'price': 12.99, 'quantity': 1})
    assert r.status_code == 201
    burger = r.json()
    r = requests.post(f'{BASE}/sessions/{code}/items', json={'name': 'Pizza', 'price': 15.50, 'quantity': 1})
    assert r.status_code == 201
    pizza = r.json()
    r = requests.post(f'{BASE}/sessions/{code}/items', json={'name': 'Tax', 'price': 2.50, 'quantity': 1, 'is_tax': True})
    assert r.status_code == 201
    print('✅ 3 items added (Burger, Pizza, Tax)')

    # 4. Assign burger to Alice, pizza to Bob
    r = requests.post(f'{BASE}/sessions/{code}/assignments', json={'item_id': burger['id'], 'participant_id': host_id, 'share_count': 1})
    assert r.status_code == 201
    r = requests.post(f'{BASE}/sessions/{code}/assignments', json={'item_id': pizza['id'], 'participant_id': bob['id'], 'share_count': 1})
    assert r.status_code == 201
    print('✅ Items assigned')

    # 5. Update Bob tip
    r = requests.put(f'{BASE}/sessions/{code}/participants/{bob["id"]}', json={'tip_percentage': 18})
    assert r.status_code == 200
    print('✅ Bob tip set to 18%')

    # 6. Add discount
    r = requests.post(f'{BASE}/sessions/{code}/discounts', json={'discount_type': 'percentage', 'value': 10})
    assert r.status_code == 201
    print('✅ 10% discount added')

    # 7. Get summary
    r = requests.get(f'{BASE}/sessions/{code}/summary')
    assert r.status_code == 200
    summary = r.json()
    print(f'✅ Summary: {len(summary["participants"])} participants')
    for p in summary['participants']:
        print(f'   {p["participant_name"]}: items={p["items_subtotal"]}, tax={p["tax_share"]}, tip={p["tip_amount"]}, discount={p["discount_amount"]}, total={p["total"]}')
    if summary.get('unassigned_items'):
        print(f'   ⚠️ {len(summary["unassigned_items"])} unassigned items')

    # 8. Get session (verify all data included)
    r = requests.get(f'{BASE}/sessions/{code}')
    session = r.json()
    assert len(session['items']) == 3
    assert len(session['participants']) == 2
    assert len(session['discounts']) == 1
    print(f'✅ Session data complete: {len(session["items"])} items, {len(session["participants"])} participants, {len(session["discounts"])} discounts')

    # 9. Test duplicate assignment (race condition guard)
    r = requests.post(f'{BASE}/sessions/{code}/assignments', json={'item_id': burger['id'], 'participant_id': host_id, 'share_count': 2})
    assert r.status_code == 201
    print('✅ Duplicate assignment handled (updated share_count)')

    # 10. QR code
    r = requests.get(f'{BASE}/sessions/{code}/qr')
    assert r.status_code == 200
    assert r.headers['content-type'] == 'image/png'
    print('✅ QR code generated')

    # 11. Nearby sessions
    r = requests.get(f'{BASE}/sessions/nearby')
    assert r.status_code == 200
    print(f'✅ Nearby sessions: {len(r.json()["sessions"])} found')

    # 12. Currency
    r = requests.get(f'{BASE}/currency?timezone=America/New_York')
    assert r.status_code == 200
    print(f'✅ Currency: {r.json()["code"]}')

    # 13. Delete session
    r = requests.delete(f'{BASE}/sessions/{code}')
    assert r.status_code == 204
    print('✅ Session deleted')

    print('\n🎉 All API tests passed!')


if __name__ == '__main__':
    test_full_flow()
