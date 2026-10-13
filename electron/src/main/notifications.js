const { Notification, app } = require('electron');
const http = require('http');

class NotificationManager {
  constructor(baseUrl, getMainWindow, getAppIcon) {
    this.baseUrl = baseUrl;
    this.getMainWindow = getMainWindow;
    this.getAppIcon = getAppIcon;
    this.pollInterval = null;
    this.notifiedIds = new Set();
    this.isPolling = false;
  }

  start(intervalMs = 30000) {
    if (this.pollInterval) return;
    console.log(`[Notifications] Iniciando monitor de sala de espera (cada ${intervalMs / 1000}s)...`);
    
    // Ejecutar primera comprobación tras 5 segundos de gracia
    setTimeout(() => {
      this.checkWaitingRoom();
    }, 5000);

    this.pollInterval = setInterval(() => {
      this.checkWaitingRoom();
    }, intervalMs);
  }

  stop() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
      console.log('[Notifications] Monitor de sala de espera detenido.');
    }
  }

  async checkWaitingRoom() {
    if (this.isPolling) return;
    this.isPolling = true;

    try {
      const url = new URL('/appointments/waiting-count', this.baseUrl);
      const data = await this.fetchJson(url);

      if (data && data.patients && Array.isArray(data.patients)) {
        // IDs presentes hoy en sala de espera
        const currentWaitingIds = new Set();

        for (const p of data.patients) {
          const apptId = p.appointment_id;
          currentWaitingIds.add(apptId);

          if (!this.notifiedIds.has(apptId)) {
            this.notifiedIds.add(apptId);
            this.showWaitingNotification(p);
          }
        }

        // Limpiar de notifiedIds aquellos pacientes que ya no están en espera (fueron atendidos o cancelados)
        for (const id of Array.from(this.notifiedIds)) {
          if (!currentWaitingIds.has(id)) {
            this.notifiedIds.delete(id);
          }
        }
      }
    } catch (err) {
      // Errores de red temporales no deben interrumpir el proceso
      // console.warn('[Notifications] Error consultando sala de espera:', err.message);
    } finally {
      this.isPolling = false;
    }
  }

  showWaitingNotification(patient) {
    if (!Notification.isSupported()) {
      console.log('[Notifications] Notificaciones no soportadas en este sistema.');
      return;
    }

    const title = '🏥 Paciente en Sala de Espera';
    const queueText = patient.queue_number ? ` (Turno #${patient.queue_number})` : '';
    const body = `${patient.patient_name}${queueText} ya se encuentra esperando en recepción.`;

    const icon = this.getAppIcon ? this.getAppIcon() : undefined;

    const notification = new Notification({
      title: title,
      body: body,
      icon: icon,
      silent: false
    });

    notification.on('click', () => {
      const win = this.getMainWindow ? this.getMainWindow() : null;
      if (win) {
        if (win.isMinimized()) win.restore();
        win.show();
        win.focus();
        // Opcional: navegar a la lista de citas en espera
        win.loadURL(`${this.baseUrl}/appointments?status=En+Espera`);
      }
    });

    notification.show();
    console.log(`[Notifications] Notificación enviada para: ${patient.patient_name}`);
  }

  fetchJson(url) {
    return new Promise((resolve, reject) => {
      const req = http.get(url, { timeout: 4000 }, (res) => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          return reject(new Error(`HTTP Status ${res.statusCode}`));
        }

        let body = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => (body += chunk));
        res.on('end', () => {
          try {
            const parsed = JSON.parse(body);
            resolve(parsed);
          } catch (e) {
            reject(e);
          }
        });
      });

      req.on('error', reject);
      req.on('timeout', () => {
        req.destroy();
        reject(new Error('Timeout'));
      });
    });
  }
}

module.exports = NotificationManager;
