const { spawn, exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const net = require('net');

class ServerManager {
  constructor(config) {
    this.config = config;
    this.process = null;
    this.port = null;
    this.baseUrl = null;
  }

  // Comprueba si un puerto está disponible
  async isPortAvailable(port) {
    return new Promise((resolve) => {
      const tester = net.createServer()
        .once('error', () => resolve(false))
        .once('listening', () => {
          tester.once('close', () => resolve(true)).close();
        })
        .listen(port, '127.0.0.1');
    });
  }

  // Encuentra el primer puerto libre a partir de startPort
  async findAvailablePort(startPort = 8080, maxAttempts = 20) {
    for (let port = startPort; port < startPort + maxAttempts; port++) {
      if (await this.isPortAvailable(port)) {
        return port;
      }
    }
    return startPort;
  }

  // Prepara el directorio de datos
  setupDataDirectory() {
    const { app } = require('electron');
    const baseConfigDir = path.resolve(__dirname, '../../');

    // 1. Si está empaquetado en producción con electron-builder o NSIS (resources/backend)
    if (process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, 'backend'))) {
      const appInstallDir = path.resolve(process.resourcesPath, '..');
      const isPortable = fs.existsSync(path.join(appInstallDir, 'portable.flag')) || process.env.SSCP_PORTABLE === '1';

      if (isPortable) {
        const portableDataDir = path.join(appInstallDir, 'data');
        if (!fs.existsSync(portableDataDir)) {
          fs.mkdirSync(portableDataDir, { recursive: true });
        }
        console.log(`[ServerManager] Modo portátil activo: ${portableDataDir}`);
        return portableDataDir;
      }

      // En Windows instalado (e.g. C:\Program Files\SSCP Desktop), los datos DEBEN residir en
      // %APPDATA%\SSCP Desktop\data para garantizar permisos completos de lectura/escritura en SQLite y logs
      // sin requerir privilegios de Administrador.
      const userAppDir = path.join(app.getPath('userData'), 'data');
      if (!fs.existsSync(userAppDir)) {
        fs.mkdirSync(userAppDir, { recursive: true });
      }

      // Migrar base de datos o licencias previas si existen en otras ubicaciones
      const candidateSourceDirs = [
        path.join(appInstallDir, 'data'),
        path.join(app.getPath('appData'), 'sscp-electron', 'data'),
        path.join(app.getPath('appData'), 'SSCP', 'data'),
        path.join(process.env.LOCALAPPDATA || '', 'SSCP', 'data')
      ];

      const filesToMigrate = ['sscp.db', 'sscp_local.db', 'license_mode.txt', '.secret_key'];
      for (const file of filesToMigrate) {
        const dst = path.join(userAppDir, file);
        if (!fs.existsSync(dst)) {
          for (const srcDir of candidateSourceDirs) {
            const src = path.join(srcDir, file);
            if (fs.existsSync(src)) {
              try {
                fs.copyFileSync(src, dst);
                console.log(`[ServerManager] Archivo migrado exitosamente a AppData: ${file} (desde ${src})`);
                break;
              } catch (migErr) {
                console.warn(`[ServerManager] No se pudo migrar ${file} desde ${src}:`, migErr.message);
              }
            }
          }
        }
      }

      console.log(`[ServerManager] Directorio de datos en AppData del usuario: ${userAppDir}`);
      return userAppDir;
    }

    const backendDir = path.isAbsolute(this.config.backendDir)
      ? this.config.backendDir
      : path.resolve(baseConfigDir, this.config.backendDir);

    if (!this.config.useIsolatedData) {
      console.log('[ServerManager] Usando base de datos original compartida.');
      return path.resolve(backendDir, 'data');
    }

    const isolatedDir = path.resolve(__dirname, '../../data');
    if (!fs.existsSync(isolatedDir)) {
      fs.mkdirSync(isolatedDir, { recursive: true });
    }

    const originalDataDir = path.resolve(backendDir, 'data');
    const dbFile = 'sscp.db';
    const secretKeyFile = '.secret_key';

    const targetDb = path.join(isolatedDir, dbFile);
    const sourceDb = path.join(originalDataDir, dbFile);

    if (!fs.existsSync(targetDb) && fs.existsSync(sourceDb)) {
      console.log(`[ServerManager] Copiando base de datos inicial a entorno aislado: ${targetDb}...`);
      try {
        fs.copyFileSync(sourceDb, targetDb);
        console.log('[ServerManager] Base de datos clonada exitosamente para modo seguro.');
      } catch (err) {
        console.error('[ServerManager] Error clonando base de datos:', err);
      }
    }

    const targetKey = path.join(isolatedDir, secretKeyFile);
    const sourceKey = path.join(originalDataDir, secretKeyFile);
    if (!fs.existsSync(targetKey) && fs.existsSync(sourceKey)) {
      try {
        fs.copyFileSync(sourceKey, targetKey);
      } catch (err) {
        console.warn('[ServerManager] Advertencia al copiar .secret_key:', err);
      }
    }

    return isolatedDir;
  }

  // Comprueba si el servidor web responde en el puerto dado
  async pingServer(port) {
    return new Promise((resolve) => {
      const req = http.get(
        {
          host: '127.0.0.1',
          port: port,
          path: '/',
          timeout: 1000
        },
        (res) => {
          // Si responde con cualquier código (200, 302, 307, 401, etc.), está activo
          resolve(true);
        }
      );

      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    });
  }

  // Espera a que el servidor esté listo
  async waitForServer(port, timeoutMs = 30000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeoutMs) {
      const isAlive = await this.pingServer(port);
      if (isAlive) {
        return true;
      }
      await new Promise((r) => setTimeout(r, 400));
    }
    return false;
  }

  // Inicia el backend de FastAPI
  async start() {
    this.port = await this.findAvailablePort(this.config.defaultPort || 8080);
    this.baseUrl = `http://127.0.0.1:${this.port}`;

    const isAlreadyRunning = await this.pingServer(this.port);
    if (isAlreadyRunning) {
      console.log(`[ServerManager] Servidor ya activo en ${this.baseUrl}`);
      return this.baseUrl;
    }

    const baseConfigDir = path.resolve(__dirname, '../../');
    const backendDir = path.isAbsolute(this.config.backendDir)
      ? this.config.backendDir
      : path.resolve(baseConfigDir, this.config.backendDir);

    const isWindows = process.platform === 'win32';
    const exeName = isWindows ? 'SSCP-Desktop.exe' : 'SSCP-Desktop';
    const fallbackPyExe = isWindows ? 'venv/Scripts/python.exe' : 'venv/bin/python';

    const rawPyConfig = this.config.pythonExe || fallbackPyExe;
    const pythonExe = path.isAbsolute(rawPyConfig)
      ? rawPyConfig
      : path.resolve(backendDir, rawPyConfig);

    const dataDir = this.setupDataDirectory();

    // Detección inteligente del ejecutable del backend (Windows / macOS / Linux):
    // 1. Recursos empaquetados por electron-builder (process.resourcesPath/backend/SSCP-Desktop[.exe])
    // 2. Ejecutable local en dist/SSCP-Desktop/SSCP-Desktop[.exe]
    // 3. Intérprete Python en entorno virtual (desarrollo)
    const packagedExe = process.resourcesPath ? path.join(process.resourcesPath, 'backend', exeName) : null;
    const localDistExe = path.resolve(baseConfigDir, `../dist/SSCP-Desktop/${exeName}`);

    let exeToRun = pythonExe;
    let args = [
      '-m',
      'uvicorn',
      'main:app',
      '--host',
      '127.0.0.1',
      '--port',
      String(this.port),
      '--log-level',
      'warning'
    ];
    let cwdToUse = backendDir;

    if (packagedExe && fs.existsSync(packagedExe)) {
      exeToRun = packagedExe;
      args = ['--server-only'];
      cwdToUse = path.dirname(packagedExe);
      console.log(`[ServerManager] Ejecutando backend empaquetado en producción: ${exeToRun}`);
    } else if (fs.existsSync(pythonExe)) {
      exeToRun = pythonExe;
      console.log(`[ServerManager] Ejecutando backend en modo desarrollo con Python: ${pythonExe}`);
    } else if (fs.existsSync(localDistExe)) {
      exeToRun = localDistExe;
      args = ['--server-only'];
      cwdToUse = path.dirname(localDistExe);
      console.log(`[ServerManager] Ejecutando backend compilado local: ${exeToRun}`);
    }

    console.log(`[ServerManager] Levantando backend en puerto ${this.port}...`);
    console.log(`[ServerManager] Comando: ${exeToRun} ${args.join(' ')}`);
    console.log(`[ServerManager] CWD: ${cwdToUse}`);
    console.log(`[ServerManager] SSCP_DATA_DIR: ${dataDir}`);

    const env = {
      ...process.env,
      SSCP_DATA_DIR: dataDir,
      SSCP_HOST: '127.0.0.1',
      SSCP_PORT: String(this.port),
      PYTHONIOENCODING: 'utf-8',
      PYTHONUNBUFFERED: '1'
    };

    this.process = spawn(exeToRun, args, {
      cwd: cwdToUse,
      env: env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true
    });

    const logFile = path.resolve(dataDir, 'backend.log');
    let logStream = null;
    try {
      logStream = fs.createWriteStream(logFile, { flags: 'a' });
      logStream.on('error', (err) => {
        console.warn(`[ServerManager] Advertencia en stream de log: ${err.message}`);
      });
    } catch (logErr) {
      console.warn(`[ServerManager] No se pudo abrir logStream en ${logFile}:`, logErr.message);
    }

    this.process.stdout.on('data', (data) => {
      const msg = data.toString();
      if (logStream && logStream.writable) {
        try { logStream.write(`[STDOUT] ${msg}`); } catch (e) {}
      }
    });

    this.process.stderr.on('data', (data) => {
      const msg = data.toString();
      if (logStream && logStream.writable) {
        try { logStream.write(`[STDERR] ${msg}`); } catch (e) {}
      }
      // Solo advertir en consola si es un error grave
      if (msg.toLowerCase().includes('error') || msg.toLowerCase().includes('critical')) {
        console.error(`[Python Backend Error] ${msg}`);
      }
    });

    this.process.on('close', (code) => {
      console.log(`[ServerManager] Proceso de Python finalizado con código: ${code}`);
      this.process = null;
    });

    // Esperar a que el servidor responda
    const ready = await this.waitForServer(this.port, 30000);
    if (!ready) {
      throw new Error(`El servidor FastAPI no respondió en http://127.0.0.1:${this.port} dentro del tiempo límite.`);
    }

    console.log(`[ServerManager] Servidor FastAPI listo y conectado en ${this.baseUrl}`);
    return this.baseUrl;
  }

  // Detiene el proceso limpiamente en Windows
  stop() {
    if (this.process && this.process.pid) {
      console.log(`[ServerManager] Cerrando subproceso Python (PID: ${this.process.pid})...`);
      const pid = this.process.pid;
      this.process = null;

      if (process.platform === 'win32') {
        try {
          exec(`taskkill /pid ${pid} /T /F`, (err) => {
            if (err) {
              console.warn(`[ServerManager] Nota al terminar proceso: ${err.message}`);
            } else {
              console.log('[ServerManager] Proceso terminado limpiamente.');
            }
          });
        } catch (e) {
          console.error('[ServerManager] Error en taskkill:', e);
        }
      } else {
        try {
          process.kill(pid, 'SIGTERM');
        } catch (e) {
          // Ignorado
        }
      }
    }
  }
}

module.exports = ServerManager;
