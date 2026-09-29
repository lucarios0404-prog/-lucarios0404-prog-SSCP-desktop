import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models import User
from app.core.deps import require_current_user

def test_appointments_calendar_and_api():
    client = TestClient(app)

    db = SessionLocal()
    admin = db.query(User).filter(User.role == 'admin').first()
    assert admin is not None, "Admin user must exist"

    app.dependency_overrides[require_current_user] = lambda: admin

    # 1. Probar carga de la vista web con calendario
    response = client.get('/appointments')
    assert response.status_code == 200, f'Expected 200, got {response.status_code}'

    content = response.text
    assert 'id="appointmentListView"' in content, 'List view container missing in HTML'
    assert 'id="appointmentCalendarView"' in content, 'Calendar view missing in HTML'
    assert 'id="tabBtnCalendar"' in content, 'Calendar toggle button missing'
    assert 'calMonthGrid' in content, 'Calendar grid missing'
    assert 'calDetailModal' in content, 'Calendar detail modal missing'
    assert 'calDayListModal' in content, 'Calendar day list modal missing'

    # 2. Probar API de eventos del calendario
    api_res = client.get('/appointments/api/events')
    assert api_res.status_code == 200
    data = api_res.json()
    assert 'events' in data
    assert isinstance(data['events'], list)

    # 3. Probar filtro por estado en API
    api_status_res = client.get('/appointments/api/events?status=Confirmada')
    assert api_status_res.status_code == 200
    assert 'events' in api_status_res.json()

if __name__ == '__main__':
    test_appointments_calendar_and_api()
    print("Test passed successfully!")
