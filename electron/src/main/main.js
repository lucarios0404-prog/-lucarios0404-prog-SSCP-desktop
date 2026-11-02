const { app, BrowserWindow, ipcMain, Tray, Menu, dialog, Notification } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');

// Configurar nombre consistente de la aplicación en Windows
app.setName('SSCP Desktop');

// Prevenir caídas no controladas del proceso principal
process.on('uncaughtException', (error) => {
  console.error('[Main] Excepción no capturada:', error);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('[Main] Rechazo no controlado en promesa:', reason);
});

const ServerManager = require('./server-manager');
const { buildAppMenu } = require('./menu');
const { openPrintConfigurator } = require('./print-configurator');
const NotificationManager = require('./notifications');

// Cargar configuración
const configPath = path.resolve(__dirname, '../../config/config.json');
let config = {};
try {
  const raw = fs.readFileSync(configPath, 'utf-8').replace(/^\uFEFF/, '');
  config = JSON.parse(raw);
} catch (err) {
  console.error('[Main] Error al cargar config.json, usando valores por defecto:', err);
  config = {
    appName: "SSCP Desktop (Electron)",
    backendDir: "../",
    pythonExe: "venv/Scripts/python.exe",
    defaultPort: 8080,
    useIsolatedData: false
  };
}

let mainWindow = null;
let splashWindow = null;
let tray = null;
let serverManager = null;
let notificationManager = null;
let baseUrl = null;

// Caché en memoria de configuración de impresión
let cachedPrintConfig = {
  print_margin_top: 15.0,
  print_margin_bottom: 15.0,
  print_margin_left: 20.0,
  print_margin_right: 15.0,
  print_paper_size: 'Letter'
};

// Asegurar instancia única
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

function getAppIcon() {
  const localIcon = path.resolve(__dirname, '../assets/icon.ico');
  if (fs.existsSync(localIcon)) return localIcon;
  const baseConfigDir = path.resolve(__dirname, '../../');
  const backendDir = path.isAbsolute(config.backendDir)
    ? config.backendDir
    : path.resolve(baseConfigDir, config.backendDir);
  const backendIcon = path.resolve(backendDir, 'static/app_icon.ico');
  if (fs.existsSync(backendIcon)) return backendIcon;
  return undefined;
}

function fetchBackendJson(urlPath, method = 'GET', data = null) {
  return new Promise((resolve) => {
    if (!baseUrl) return resolve(null);
    try {
      const url = new URL(urlPath, baseUrl);
      const postData = data ? JSON.stringify(data) : null;

      const options = {
        method: method,
        headers: {
          'Accept': 'application/json'
        }
      };
      if (postData) {
        options.headers['Content-Type'] = 'application/json';
        options.headers['Content-Length'] = Buffer.byteLength(postData);
      }

      const req = http.request(url, options, (res) => {
        let body = '';
        res.setEncoding('utf8');
        res.on('data', chunk => (body += chunk));
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            resolve(null);
          }
        });
      });

      req.on('error', () => resolve(null));
      req.on('timeout', () => { req.destroy(); resolve(null); });
      if (postData) req.write(postData);
      req.end();
    } catch (e) {
      resolve(null);
    }
  });
}

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 480,
    height: 380,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    center: true,
    show: false,
    icon: getAppIcon(),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  const splashFile = path.resolve(__dirname, '../splash/splash.html');
  splashWindow.loadFile(splashFile);
  splashWindow.once('ready-to-show', () => {
    splashWindow.show();
  });
}

// Función universal de Menú Contextual (Clic Derecho) para todas las ventanas y vistas
function setupGlobalContextMenu(targetWebContents) {
  if (!targetWebContents || targetWebContents._hasContextMenuAttached) return;
  targetWebContents._hasContextMenuAttached = true;

  targetWebContents.on('context-menu', (event, params) => {
    const { Menu, MenuItem } = require('electron');
    const menu = new Menu();

    // 1. Sugerencias ortográficas del motor Chromium si la palabra tiene error
    if (params.misspelledWord) {
      if (params.dictionarySuggestions && params.dictionarySuggestions.length > 0) {
        for (const suggestion of params.dictionarySuggestions) {
          menu.append(new MenuItem({
            label: suggestion,
            click: () => targetWebContents.replaceMisspelling(suggestion)
          }));
        }
      } else {
        menu.append(new MenuItem({
          label: 'Sin sugerencias de ortografía',
          enabled: false
        }));
      }

      menu.append(new MenuItem({ type: 'separator' }));
      menu.append(new MenuItem({
        label: 'Añadir "' + params.misspelledWord + '" al diccionario',
        click: () => {
          try {
            targetWebContents.session.addWordToSpellCheckerDictionary(params.misspelledWord);
          } catch (e) {
            console.error(e);
          }
        }
      }));
      menu.append(new MenuItem({ type: 'separator' }));
    }

    // 2. Opciones de edición si está en un campo editable (cualquier input o textarea)
    if (params.isEditable) {
      menu.append(new MenuItem({
        role: 'undo',
        label: 'Deshacer',
        accelerator: 'CmdOrCtrl+Z'
      }));
      menu.append(new MenuItem({
        role: 'redo',
        label: 'Rehacer',
        accelerator: 'CmdOrCtrl+Y'
      }));
      menu.append(new MenuItem({ type: 'separator' }));
      menu.append(new MenuItem({
        role: 'cut',
        label: 'Cortar',
        accelerator: 'CmdOrCtrl+X',
        enabled: params.editFlags ? params.editFlags.canCut : true
      }));
      menu.append(new MenuItem({
        role: 'copy',
        label: 'Copiar',
        accelerator: 'CmdOrCtrl+C',
        enabled: params.editFlags ? params.editFlags.canCopy : true
      }));
      menu.append(new MenuItem({
        role: 'paste',
        label: 'Pegar',
        accelerator: 'CmdOrCtrl+V',
        enabled: params.editFlags ? params.editFlags.canPaste : true
      }));
      menu.append(new MenuItem({
        role: 'pasteAndMatchStyle',
        label: 'Pegar texto sin formato',
        accelerator: 'CmdOrCtrl+Shift+V',
        enabled: params.editFlags ? params.editFlags.canPaste : true
      }));
      menu.append(new MenuItem({ type: 'separator' }));
      menu.append(new MenuItem({
        role: 'selectAll',
        label: 'Seleccionar todo',
        accelerator: 'CmdOrCtrl+A',
        enabled: params.editFlags ? params.editFlags.canSelectAll : true
      }));
      menu.popup();
    } else if (params.selectionText && params.selectionText.trim().length > 0) {
      // 3. Texto seleccionado en cualquier elemento de solo lectura (tablas, reportes, fichas)
      menu.append(new MenuItem({
        role: 'copy',
        label: 'Copiar',
        accelerator: 'CmdOrCtrl+C'
      }));
      menu.append(new MenuItem({
        role: 'selectAll',
        label: 'Seleccionar todo',
        accelerator: 'CmdOrCtrl+A'
      }));
      menu.popup();
    } else {
      // 4. Clic derecho en espacio general (fondo, panel, tarjetas, dashboard)
      menu.append(new MenuItem({
        role: 'selectAll',
        label: 'Seleccionar todo',
        accelerator: 'CmdOrCtrl+A'
      }));
      menu.append(new MenuItem({ type: 'separator' }));
      menu.append(new MenuItem({
        role: 'reload',
        label: 'Recargar',
        accelerator: 'F5'
      }));
      menu.popup();
    }
  });
}

function createMainWindow() {
  const winConfig = config.window || {};
  mainWindow = new BrowserWindow({
    width: winConfig.width || 1360,
    height: winConfig.height || 860,
    minWidth: winConfig.minWidth || 1024,
    minHeight: winConfig.minHeight || 700,
    show: false,
    icon: getAppIcon(),
    title: (config.appName || "SSCP Desktop") + " v" + (require('../../package.json').version || "1.8.3"),
    webPreferences: {
      preload: path.resolve(__dirname, '../preload/preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      spellcheck: true
    }
  });

  // Configurar menú nativo
  buildAppMenu(mainWindow, baseUrl, getAppIcon);

  // Configuración de idiomas para el corrector ortográfico (Español)
  try {
    mainWindow.webContents.session.setSpellCheckerLanguages(['es-419', 'es-ES', 'es']);
  } catch (err) {
    console.warn('[SpellCheck] No se pudieron configurar idiomas de ortografia:', err);
  }

    // Menú Contextual Universal
  setupGlobalContextMenu(mainWindow.webContents);

  // Manejar apertura de enlaces externos en el navegador por defecto con validación de protocolos seguros
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(baseUrl)) {
      try {
        const parsed = new URL(url);
        // Whitelist estricta de protocolos seguros: bloquea file:, ms-msdt:, smb:, powershell:, etc.
        if (['https:', 'http:', 'mailto:'].includes(parsed.protocol)) {
          require('electron').shell.openExternal(url);
        } else {
          console.warn(`[Security] Bloqueada apertura de protocolo no seguro: ${parsed.protocol} (${url})`);
        }
      } catch (err) {
        console.warn(`[Security] URL externa malformada rechazada: ${url}`);
      }
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  mainWindow.once('ready-to-show', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      setTimeout(() => {
        if (splashWindow && !splashWindow.isDestroyed()) {
          splashWindow.close();
          splashWindow = null;
        }
        mainWindow.show();
        mainWindow.focus();
      }, 500);
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  console.log(`[Main] Cargando URL principal: ${baseUrl}`);
  mainWindow.loadURL(baseUrl);
}

function createTray() {
  const iconPath = getAppIcon();
  if (!iconPath) return;

  try {
    tray = new Tray(iconPath);
    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'Abrir SSCP Desktop',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
          }
        }
      },
      {
        label: 'Sala de Espera (Turnos)',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
            mainWindow.loadURL(`${baseUrl}/appointments?status=En+Espera`);
          }
        }
      },
      {
        label: 'Configurar Márgenes...',
        click: () => {
          openPrintConfigurator(mainWindow, baseUrl, getAppIcon);
        }
      },
      { type: 'separator' },
      {
        label: 'Minimizar',
        click: () => {
          if (mainWindow) mainWindow.minimize();
        }
      },
      {
        label: 'Cerrar Aplicación',
        click: () => app.quit()
      }
    ]);

    tray.setToolTip('SSCP Desktop - Consultas Médicas');
    tray.setContextMenu(contextMenu);

    tray.on('double-click', () => {
      if (mainWindow) {
        if (mainWindow.isVisible()) {
          mainWindow.focus();
        } else {
          mainWindow.show();
        }
      }
    });
  } catch (err) {
    console.warn('[Main] No se pudo inicializar la bandeja del sistema:', err);
  }
}

// Configurar IPC Handlers
function setupIpc() {
  ipcMain.on('window-minimize', () => {
    if (mainWindow) mainWindow.minimize();
  });

  ipcMain.on('window-maximize', () => {
    if (mainWindow) {
      if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
      } else {
        mainWindow.maximize();
      }
    }
  });

  ipcMain.on('window-close', () => {
    if (mainWindow) mainWindow.close();
  });

  ipcMain.on('open-print-configurator', () => {
    openPrintConfigurator(mainWindow, baseUrl, getAppIcon);
  });

  // Obtener configuración de impresión
  ipcMain.handle('get-print-config', async () => {
    const res = await fetchBackendJson('/settings/print-config', 'GET');
    if (res && res.success) {
      cachedPrintConfig = {
        ...cachedPrintConfig,
        ...res
      };
    }
    return cachedPrintConfig;
  });

  // Guardar configuración de impresión
  ipcMain.handle('save-print-config', async (event, newConfig) => {
    const res = await fetchBackendJson('/settings/print-config', 'POST', newConfig);
    if (res && res.success) {
      cachedPrintConfig = {
        ...cachedPrintConfig,
        ...newConfig
      };
      // Notificar a la ventana principal para actualizar los estilos de impresión CSS inyectados
      if (mainWindow && mainWindow.webContents) {
        mainWindow.webContents.send('print-config-updated', cachedPrintConfig);
      }
    }
    return res || { success: true, config: cachedPrintConfig };
  });

  // Imprimir página de prueba desde el configurador
  ipcMain.handle('print-test-page', async (event, customMargins) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return false;

    const marginsToUse = customMargins || cachedPrintConfig;
    const topInInches = (marginsToUse.print_margin_top || marginsToUse.top || 15) / 25.4;
    const bottomInInches = (marginsToUse.print_margin_bottom || marginsToUse.bottom || 15) / 25.4;
    const leftInInches = (marginsToUse.print_margin_left || marginsToUse.left || 20) / 25.4;
    const rightInInches = (marginsToUse.print_margin_right || marginsToUse.right || 15) / 25.4;

    return new Promise((resolve) => {
      win.webContents.print(
        {
          silent: false,
          printBackground: true,
          pageSize: marginsToUse.print_paper_size || marginsToUse.paperSize || 'Letter',
          margins: {
            marginType: 'custom',
            top: topInInches,
            bottom: bottomInInches,
            left: leftInInches,
            right: rightInInches
          }
        },
        (success, failureReason) => {
          if (!success) {
            console.warn('[PrintTest] Fallo al imprimir prueba:', failureReason);
          }
          resolve(success);
        }
      );
    });
  });

  // Impresión nativa general (inyecta márgenes personalizados si se solicitan)
  ipcMain.handle('native-print', async (event, options = {}) => {
    const targetWin = BrowserWindow.fromWebContents(event.sender) || mainWindow;
    if (!targetWin) return false;

    const currentUrl = (targetWin.webContents && targetWin.webContents.getURL) ? targetWin.webContents.getURL().toLowerCase() : '';
    const isPreauthOrLetterDoc = 
      currentUrl.includes('/insurance-forms') || 
      (currentUrl.includes('/licenses') && !currentUrl.includes('/talonario')) ||
      currentUrl.includes('/reports') || 
      currentUrl.includes('/consents') ||
      currentUrl.includes('/history');

    // Si el llamador provee márgenes explícitos, los usamos; de lo contrario, 'printableArea'
    // permite que la regla CSS @page inyectada por preload.js defina los márgenes exactos sin duplicación
    const printMargins = options.margins || { marginType: options.marginType || 'printableArea' };
    const defaultPageSize = isPreauthOrLetterDoc ? 'Letter' : (cachedPrintConfig.print_paper_size || 'Letter');

    return new Promise((resolve) => {
      targetWin.webContents.print(
        {
          silent: options.silent || false,
          printBackground: true,
          pageSize: options.pageSize || defaultPageSize,
          margins: printMargins,
          ...options
        },
        (success, failureReason) => {
          if (!success) {
            console.warn('[Print] Error o cancelación:', failureReason);
          }
          resolve(success);
        }
      );
    });
  });

  ipcMain.on('show-notification', (event, { title, body }) => {
    if (Notification.isSupported()) {
      new Notification({ title, body, icon: getAppIcon() }).show();
    }
  });
}

// Inicialización de la aplicación

// Garantizar Menú Contextual en TODAS las ventanas y vistas creadas
app.on('web-contents-created', (event, contents) => {
  setupGlobalContextMenu(contents);
});
app.whenReady().then(async () => {
  setupIpc();
  createSplashWindow();

  serverManager = new ServerManager(config);

  try {
    baseUrl = await serverManager.start();
    createMainWindow();
    createTray();

    // Inicializar Monitor de Notificaciones de Sala de Espera
    notificationManager = new NotificationManager(
      baseUrl,
      () => mainWindow,
      getAppIcon
    );
    notificationManager.start(30000); // Poll cada 30 segundos
  } catch (err) {
    console.error('[Main] Fallo al iniciar el servidor backend:', err);
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
    }
    dialog.showErrorBox(
      'Error al iniciar SSCP',
      `No se pudo iniciar el servicio clínico en segundo plano:\n\n${err.message}\n\nRevisa el archivo de log en data/backend.log.`
    );
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow();
  }
});

// Limpieza al cerrar la aplicación
let isQuitting = false;

app.on('before-quit', () => {
  isQuitting = true;
  if (notificationManager) {
    notificationManager.stop();
  }
  if (serverManager) {
    serverManager.stop();
  }
});

app.on('window-all-closed', () => {
  if (notificationManager) {
    notificationManager.stop();
  }
  if (serverManager) {
    serverManager.stop();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

process.on('SIGINT', () => {
  if (notificationManager) notificationManager.stop();
  if (serverManager) serverManager.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  if (notificationManager) notificationManager.stop();
  if (serverManager) serverManager.stop();
  process.exit(0);
});
