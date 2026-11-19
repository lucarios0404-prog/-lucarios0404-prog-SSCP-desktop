import sys
import os
from datetime import date, timedelta, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app
from app.core.security import create_access_token
from app.database import SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.appointment import Appointment

def main():
    db = SessionLocal()
    user = db.query(User).filter(User.is_active == True).first()
    patient = db.query(Patient).filter(Patient.is_active == True).first()
    if not user or not patient:
        print("User or patient not found")
        return
        
    tomorrow = date.today() + timedelta(days=1)
    
    # Create test upcoming appointment
    test_appt = Appointment(
        patient_id=patient.id,
        doctor_id=user.id,
        date=tomorrow,
        start_time=time(10, 30),
        reason="Seguimiento de Consulta Prenatal",
        status="Pendiente",
        notes="Prueba de seguimiento"
    )
    db.add(test_appt)
    db.commit()
    db.refresh(test_appt)
    print(f"Created temporary upcoming appointment ID: {test_appt.id} for {tomorrow}")

    try:
        token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
        client = TestClient(app)
        
        # Test default
        res = client.get('/api/mobile/appointments/upcoming', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        print("Total count:", data['count'])
        print("Tomorrow count:", data['tomorrow_count'])
        print("Unconfirmed count:", data['unconfirmed_count'])
        assert data['count'] >= 1
        assert data['tomorrow_count'] >= 1
        
        found = next((a for a in data['appointments'] if a['id'] == test_appt.id), None)
        assert found is not None, "Created appointment not found in response"
        print(f"Found upcoming appointment: {found['patient_name']} ({found['date']} at {found['start_time']}) - Status: {found['status']}")
        
        # Test status update
        res_st = client.post(f"/api/mobile/appointments/{test_appt.id}/status", 
                             json={"status": "Confirmada"},
                             headers={'Authorization': f'Bearer {token}'})
        assert res_st.status_code == 200
        print("Updated status to Confirmada:", res_st.json())
        
        # Test reschedule
        day_after = tomorrow + timedelta(days=2)
        res_resched = client.post(f"/api/mobile/appointments/{test_appt.id}/reschedule",
                                  json={"new_date": str(day_after), "new_time": "11:00"},
                                  headers={'Authorization': f'Bearer {token}'})
        assert res_resched.status_code == 200
        print(f"Rescheduled appointment to {day_after}:", res_resched.json())
        
        # Test whatsapp-sent
        res_wa = client.post(f"/api/mobile/appointments/{test_appt.id}/whatsapp-sent",
                             headers={'Authorization': f'Bearer {token}'})
        assert res_wa.status_code == 200
        print("Marked whatsapp sent:", res_wa.json())
        
        print("\nALL BACKEND API CHECKS PASSED SUCCESSFULLY!")
    finally:
        # Cleanup
        db.delete(test_appt)
        db.commit()
        print("Cleaned up temporary appointment.")

if __name__ == '__main__':
    main()
