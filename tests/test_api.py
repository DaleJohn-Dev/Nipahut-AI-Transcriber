from fastapi.testclient import TestClient
from app.server import app

client = TestClient(app)

def test_local_page_and_security_headers():
    response = client.get('/')
    assert response.status_code == 200
    assert 'Speaker introductions' in response.text
    assert response.headers['cross-origin-resource-policy'] == 'same-origin'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']

def test_cross_origin_and_dns_rebinding_rejected():
    assert client.post('/api/jobs/cancel', headers={'Origin':'https://example.com'}).status_code == 403
    assert client.get('/api/state', headers={'Host':'example.com:8765'}).status_code == 403

def test_settings_validate_language_and_limits():
    assert client.put('/api/settings', json={'language':'not-real'}).status_code == 422
    assert client.put('/api/settings', json={'speaker_count':10000}).status_code == 422
    assert client.put('/api/settings', json={'cleanup': {'strength':20}}).status_code == 422

def test_recording_ids_cannot_escape_storage():
    assert client.get('/api/recordings/not-a-recording').status_code == 400
    assert client.get('/api/recordings/'+'0'*32).status_code == 404

def test_empty_upload_rejected():
    response = client.post('/api/recordings', files={'file':('test.wav',b'', 'audio/wav')})
    assert response.status_code == 400

def test_model_unknown_rejected():
    assert client.post('/api/models/not-a-model/load').status_code == 400
