const { Menu, app, dialog } = require('electron');
const { openPrintConfigurator } = require('./print-configurator');

function buildAppMenu(mainWindow, baseUrl, getAppIcon) {
  const template = [
    {
      label: 'Archivo',
      submenu: [
        {
          label: 'Panel Principal (Dashboard)',
          accelerator: 'CmdOrCtrl+H',
          click: () => mainWindow.loadURL(`${baseUrl}/dashboard`)
        },
        {
          label: 'Nuevo Paciente',
          accelerator: 'CmdOrCtrl+Alt+P',
          click: () => mainWindow.loadURL(`${baseUrl}/patients/create`)
        },
        {
          label: 'Nueva Cita',
          accelerator: 'CmdOrCtrl+Alt+A',
          click: () => mainWindow.loadURL(`${baseUrl}/appointments/create`)
        },
        { type: 'separator' },
        {
          label: 'Imprimir Documento / Receta...',
          accelerator: 'CmdOrCtrl+P',
          click: () => {
            if (mainWindow && mainWindow.webContents) {
              mainWindow.webContents.send('trigger-print');
              mainWindow.webContents.print({ silent: false, printBackground: true });
            }
          }
        },
        {
          label: 'Configurar Márgenes de Impresión...',
          accelerator: 'CmdOrCtrl+Alt+M',
          click: () => {
            openPrintConfigurator(mainWindow, baseUrl, getAppIcon);
          }
        },
        { type: 'separator' },
        {
          label: 'Salir',
          accelerator: 'CmdOrCtrl+Q',
          click: () => app.quit()
        }
      ]
    },
    {
      label: 'Edición',
      submenu: [
        { role: 'undo', label: 'Deshacer', accelerator: 'CmdOrCtrl+Z' },
        { role: 'redo', label: 'Rehacer', accelerator: 'CmdOrCtrl+Y' },
        { type: 'separator' },
        { role: 'cut', label: 'Cortar', accelerator: 'CmdOrCtrl+X' },
        { role: 'copy', label: 'Copiar', accelerator: 'CmdOrCtrl+C' },
        { role: 'paste', label: 'Pegar', accelerator: 'CmdOrCtrl+V' },
        { role: 'pasteAndMatchStyle', label: 'Pegar sin formato', accelerator: 'CmdOrCtrl+Shift+V' },
        { role: 'delete', label: 'Eliminar' },
        { type: 'separator' },
        { role: 'selectAll', label: 'Seleccionar todo', accelerator: 'CmdOrCtrl+A' }
      ]
    },
    {
      label: 'Módulos Clínicos',
      submenu: [
        {
          label: 'Expedientes de Pacientes',
          click: () => mainWindow.loadURL(`${baseUrl}/patients`)
        },
        {
          label: 'Agenda de Citas',
          click: () => mainWindow.loadURL(`${baseUrl}/appointments`)
        },
        {
          label: 'Sala de Espera (Turnos del Día)',
          accelerator: 'CmdOrCtrl+Alt+E',
          click: () => mainWindow.loadURL(`${baseUrl}/appointments?status=En+Espera`)
        },
        {
          label: 'Historial de Consultas',
          click: () => mainWindow.loadURL(`${baseUrl}/consultations`)
        },
        {
          label: 'Resultados de Laboratorio',
          click: () => mainWindow.loadURL(`${baseUrl}/lab-results`)
        },
        {
          label: 'Inventario Médico',
          click: () => mainWindow.loadURL(`${baseUrl}/inventory`)
        },
        {
          label: 'Reportes y Estadísticas',
          click: () => mainWindow.loadURL(`${baseUrl}/reports`)
        },
        { type: 'separator' },
        {
          label: 'Configuración de la Clínica',
          click: () => mainWindow.loadURL(`${baseUrl}/settings`)
        }
      ]
    },
    {
      label: 'Ver',
      submenu: [
        {
          label: 'Recargar',
          accelerator: 'F5',
          click: () => mainWindow.reload()
        },
        {
          label: 'Recarga Forzada (Limpiar Caché)',
          accelerator: 'CmdOrCtrl+F5',
          click: () => mainWindow.webContents.reloadIgnoringCache()
        },
        { type: 'separator' },
        {
          label: 'Pantalla Completa',
          accelerator: 'F11',
          click: () => mainWindow.setFullScreen(!mainWindow.isFullScreen())
        }
      ]
    },
    {
      label: 'Ayuda',
      submenu: [
        {
          label: 'Configurar Impresora y Márgenes...',
          click: () => {
            openPrintConfigurator(mainWindow, baseUrl, getAppIcon);
          }
        },
        { type: 'separator' },
        {
          label: 'Garantías de Seguridad & Privacidad Clínica...',
          accelerator: 'CmdOrCtrl+Alt+S',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'Centro de Confianza & Privacidad Clínica — Laxarus',
              message: 'SSCP Desktop: Soberanía de Datos y Protección Médica',
              detail: `• Soberanía Local-First: La base de datos SQLite WAL se almacena localmente en su consultorio. Ningún dato clínico se envía a nubes públicas sin su autorización explícita.\n\n• Enlace P2P Doctor-Secretaría: Canales autenticados con tokens criptográficos (X-Peer-Key) y soporte de túnel WireGuard/Tailscale.\n\n• Licenciamiento Ed25519: Validación criptográfica autónoma sin telemetría de monitoreo.\n\n• Cumplimiento Sanitario: Alineado con la Ley No. 42-01 (General de Salud RD), Ley No. 172-13 de Protección de Datos Personales y directrices HIPAA.\n\n• Binario Certificado: Firmado digitalmente por Laxarus Developers con SHA-256.\n\nSoporte y Respuesta a Incidentes: seguridad@laxarusdevs.com`,
              buttons: ['Visitar Portal Web', 'Entendido'],
              defaultId: 1
            }).then(({ response }) => {
              if (response === 0) {
                const { shell } = require('electron');
                shell.openExternal('https://laxarusdevs.com/seguridad.html');
              }
            }).catch(() => {});
          }
        },
        { type: 'separator' },
        {
          label: 'Acerca de SSCP Desktop (Electron)',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'Acerca de SSCP Desktop',
              message: 'SSCP Desktop - Edición Electron',
              detail: `Versión Suite: ${app.getVersion()}\nVersión Electron: ${process.versions.electron}\nVersión Node: ${process.versions.node}\nMotor Chromium: ${process.versions.chrome}\n\nDiseñado para consultas médicas profesionales de alto rendimiento con soporte de márgenes personalizados y notificaciones de sala de espera.`,
              buttons: ['Entendido']
            });
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

module.exports = { buildAppMenu };
