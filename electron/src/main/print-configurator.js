const { BrowserWindow } = require('electron');
const path = require('path');

let printConfigWindow = null;

function openPrintConfigurator(parentWindow, baseUrl, getAppIcon) {
  if (printConfigWindow && !printConfigWindow.isDestroyed()) {
    if (printConfigWindow.isMinimized()) printConfigWindow.restore();
    printConfigWindow.focus();
    return printConfigWindow;
  }

  printConfigWindow = new BrowserWindow({
    width: 980,
    height: 720,
    minWidth: 860,
    minHeight: 640,
    title: 'Configurador de Márgenes de Impresión - SSCP Desktop',
    icon: getAppIcon ? getAppIcon() : undefined,
    parent: parentWindow || undefined,
    modal: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.resolve(__dirname, '../preload/preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false
    }
  });

  const htmlPath = path.resolve(__dirname, '../renderer/print-configurator.html');
  printConfigWindow.loadFile(htmlPath);

  printConfigWindow.on('closed', () => {
    printConfigWindow = null;
  });

  return printConfigWindow;
}

module.exports = { openPrintConfigurator };
