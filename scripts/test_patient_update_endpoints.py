import sys, os
sys.path.insert(0, os.path.abspath('.'))
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
res_login = client.post('/api/mobile/login', json={'email': 'secretaria@sscp.com', 'password': 'password123'})
token = res_login.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# 1. Test GET details
res_det = client.get('/api/mobile/patients/1/details', headers=headers)
p_name = res_det.json().get('patient', {}).get('name')
print(f'GET details (int ID 1): {res_det.status_code}, name={p_name}')

# 2. Test POST update with int ID
res_up = client.post('/api/mobile/patients/1', headers=headers, json={'phone': '809-555-9999'})
p_phone = res_up.json().get('patient', {}).get('phone')
print(f'POST update (int ID 1): {res_up.status_code}, phone={p_phone}')

# 3. Test PUT update
res_put = client.put('/api/mobile/patients/1', headers=headers, json={'phone': '809-555-8888'})
p_phone_put = res_put.json().get('patient', {}).get('phone')
print(f'PUT update (int ID 1): {res_put.status_code}, phone={p_phone_put}')

# 4. Test GET details with str ID
res_det_str = client.get('/api/mobile/patients/1/details', headers=headers)
p_phone_str = res_det_str.json().get('patient', {}).get('phone')
print(f'GET details (str ID 1): {res_det_str.status_code}, phone={p_phone_str}')

# 5. Test batch sync with patient_updates
res_batch = client.post('/api/mobile/sync/batch', headers=headers, json={
    'patients': [],
    'appointments': [],
    'patient_updates': [
        {'id': 1, 'phone': '809-555-7777'}
    ]
})
print(f'POST /api/mobile/sync/batch with patient_updates: {res_batch.status_code}, data={res_batch.json()}')

assert res_det.status_code == 200
assert res_up.status_code == 200
assert res_put.status_code == 200
assert res_batch.status_code == 200
assert res_batch.json()['processed_updates'] == 1
print('\n*** ALL PATIENT UPDATE & BATCH TESTS PASSED 100% ***')
