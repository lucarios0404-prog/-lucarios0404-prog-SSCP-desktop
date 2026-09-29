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
          label: 'Acerca de SSCP Desktop (Electron)',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'Acerca de SSCP Desktop',
              message: 'SSCP Desktop - Edición Electron',
              detail: `Versión Electron: ${process.versions.electron}\nVersión Node: ${process.versions.node}\nMotor Chromium: ${process.versions.chrome}\n\nDiseñado para consultas médicas profesionales de alto rendimiento con soporte de márgenes personalizados y notificaciones de sala de espera.`,
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
