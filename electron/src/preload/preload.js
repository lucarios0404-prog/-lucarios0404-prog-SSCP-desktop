const { contextBridge, ipcRenderer } = require('electron');

// Exponer APIs para el Configurador y la App Principal
contextBridge.exposeInMainWorld('electronAPI', {
  getPrintConfig: () => ipcRenderer.invoke('get-print-config'),
  savePrintConfig: (config) => ipcRenderer.invoke('save-print-config', config),
  printTestPage: (config) => ipcRenderer.invoke('print-test-page', config),
  openPrintConfigurator: () => ipcRenderer.send('open-print-configurator')
});

contextBridge.exposeInMainWorld('sscpElectron', {
  platform: process.platform,
  version: process.versions.electron,
  isElectron: true,
  
  // Acciones de ventana
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),

  // Impresión nativa con configuración de márgenes
  printPage: (options) => ipcRenderer.invoke('native-print', options),
  getPrintConfig: () => ipcRenderer.invoke('get-print-config'),
  savePrintConfig: (config) => ipcRenderer.invoke('save-print-config', config),
  openPrintConfigurator: () => ipcRenderer.send('open-print-configurator'),

  // Notificaciones nativas
  showNotification: (title, body) => ipcRenderer.send('show-notification', { title, body }),

  // Recibir eventos de Electron
  onServerStatus: (callback) => ipcRenderer.on('server-status', (event, data) => callback(data)),
  onPrintConfigUpdated: (callback) => ipcRenderer.on('print-config-updated', (event, data) => callback(data))
});

// Inyección automática de @page { margin: ... } para respetar los márgenes clínicos configurados
function injectPrintMargins(config) {
  if (!config) return;
  const top = config.print_margin_top !== undefined ? config.print_margin_top : 15.0;
  const bottom = config.print_margin_bottom !== undefined ? config.print_margin_bottom : 15.0;
  const left = config.print_margin_left !== undefined ? config.print_margin_left : 20.0;
  const right = config.print_margin_right !== undefined ? config.print_margin_right : 15.0;
  const size = config.print_paper_size || 'Letter';

  let styleTag = document.getElementById('sscp-print-margins-style');
  if (!styleTag) {
    styleTag = document.createElement('style');
    styleTag.id = 'sscp-print-margins-style';
    document.head.appendChild(styleTag);
  }

  styleTag.textContent = `
    @media print {
      @page {
        size: ${size};
        margin-top: ${top}mm !important;
        margin-bottom: ${bottom}mm !important;
        margin-left: ${left}mm !important;
        margin-right: ${right}mm !important;
      }
    }
  `;
}

// Al cargar el DOM de cualquier página clínica
window.addEventListener('DOMContentLoaded', async () => {
  try {
    const config = await ipcRenderer.invoke('get-print-config');
    injectPrintMargins(config);
  } catch (err) {
    // Ventanas secundarias o sin conexión al backend
  }
});

// Escuchar actualizaciones dinámicas de márgenes en caliente
ipcRenderer.on('print-config-updated', (event, config) => {
  injectPrintMargins(config);
});
