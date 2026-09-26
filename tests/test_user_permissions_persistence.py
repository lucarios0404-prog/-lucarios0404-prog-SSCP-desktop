import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from fastapi.testclient import TestClient
from main import app
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User

def test_permissions_add_remove_and_reset():
    db = next(get_db())
    admin = db.query(User).filter_by(role='admin').first()
    doc = db.query(User).filter_by(role='doctor').first()
    
    # Save original state to restore at end of test
    orig_perms = doc.permissions

    try:
        admin_token = create_access_token(data={'email': admin.email, 'role': 'admin'})
        client = TestClient(app, cookies={'access_token': f'Bearer {admin_token}'})

        # 1. Doctor adds 'payments' (Facturación/Caja)
        doc_perms_with_payment = [
            'dashboard', 'patients', 'appointments', 'consultations', 'prescriptions',
            'print_prescriptions', 'templates', 'licenses', 'references', 'labs',
            'vaccines', 'inventory', 'messages', 'reports', 'payments'
        ]

        form_data = {
            'name': doc.name,
            'email': doc.email,
            'role': 'doctor',
            'is_active': '1',
            'use_custom_perms': '1',
            'reset_to_defaults': '0',
            'custom_permissions': doc_perms_with_payment
        }

        resp = client.post(f'/users/{doc.id}/edit', data=form_data, follow_redirects=False)
        assert resp.status_code == 303, f"Expected 303 redirect, got {resp.status_code}"

        db.refresh(doc)
        assert doc.permissions is not None, "Permissions should be saved in DB"
        assert doc.has_permission('payments') is True, "Doctor should have payments permission"

        # 2. Doctor removes 'reports' and 'payments'
        doc_perms_without_reports = [
            'dashboard', 'patients', 'appointments', 'consultations', 'prescriptions',
            'print_prescriptions', 'templates', 'licenses', 'references', 'labs',
            'vaccines', 'inventory', 'messages'
        ]
        form_data_2 = {
            'name': doc.name,
            'email': doc.email,
            'role': 'doctor',
            'is_active': '1',
            'use_custom_perms': '1',
            'reset_to_defaults': '0',
            'custom_permissions': doc_perms_without_reports
        }

        resp2 = client.post(f'/users/{doc.id}/edit', data=form_data_2, follow_redirects=False)
        assert resp2.status_code == 303

        db.refresh(doc)
        assert doc.has_permission('reports') is False, "Doctor should NOT have reports permission"
        assert doc.has_permission('payments') is False, "Doctor should NOT have payments permission"
        assert doc.has_permission('consultations') is True, "Doctor should still have consultations"

        # 3. Verify Edit Form renders with custom perms
        edit_page = client.get(f'/users/{doc.id}/edit')
        assert edit_page.status_code == 200
        assert 'Permisos personalizados' in edit_page.text

        # 4. Reset to role defaults
        reset_data = {
            'name': doc.name,
            'email': doc.email,
            'role': 'doctor',
            'is_active': '1',
            'reset_to_defaults': '1',
        }
        resp3 = client.post(f'/users/{doc.id}/edit', data=reset_data, follow_redirects=False)
        assert resp3.status_code == 303

        db.refresh(doc)
        assert doc.permissions is None, "Doctor permissions should be None after reset to defaults"
        assert doc.has_permission('reports') is True, "Doctor should have reports restored by defaults"
        assert doc.has_permission('payments') is False, "Doctor should not have payments in defaults"

        # 5. Implicit custom detection: user submits modified checkboxes without explicitly checking use_custom_perms
        doc.permissions = None
        db.commit()

        form_data_implicit = {
            'name': doc.name,
            'email': doc.email,
            'role': 'doctor',
            'is_active': '1',
            # NOTE: 'use_custom_perms' omitted intentionally
            'reset_to_defaults': '0',
            'custom_permissions': doc_perms_with_payment
        }
        resp4 = client.post(f'/users/{doc.id}/edit', data=form_data_implicit, follow_redirects=False)
        assert resp4.status_code == 303

        db.refresh(doc)
        assert doc.permissions is not None, "Implicit custom permissions must be saved when checkboxes differ from defaults"
        assert doc.has_permission('payments') is True, "Payments must be granted even if use_custom_perms was omitted"

        print("--> All permission tests passed successfully!")

    finally:
        # Restore original state
        doc.permissions = orig_perms
        db.commit()

if __name__ == '__main__':
    test_permissions_add_remove_and_reset()
