from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, user_agent='Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 SSCP-Mobile/1.6.1')
    page = ctx.new_page()
    page.goto('http://127.0.0.1:8080/mobile')
    page.wait_for_load_state('networkidle')
    time.sleep(1)
    
    js_code = """
    localStorage.setItem('sscp_server_url', 'https://sscp.laxarusdevs.com');
    localStorage.setItem('sscp_relay_clinic_id', 'dr_cristian_garcia');
    if (typeof showMainApp === 'function') {
        currentUser = { id: 2, name: 'Secretaría de Recepción', role: 'secretaria', email: 'secretaria@sscp.com' };
        localStorage.setItem('sscp_user', JSON.stringify(currentUser));
        localStorage.setItem('sscp_token', 'relay-cloud-token');
        showMainApp();
        renderActiveTransportIndicator();
    }
    """
    page.evaluate(js_code)
    time.sleep(2)
    page.screenshot(path=r'C:\Users\Ecommerce\.gemini\antigravity-ide\brain\d0ef121c-e7c2-45ef-a7b4-03f46dd4bd4d\evidence_multinetwork_mobile_cloud_relay.png')
    print('Cloud Relay mobile screenshot saved!')
    b.close()
