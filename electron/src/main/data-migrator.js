const fs = require('fs');
const path = require('path');

const VERSION_FILE = '.data_version';
const SKIPPED_DIRS = new Set(['logs', 'cache', 'tmp']);
const DEFAULT_KEEP_BACKUPS = 5;

function hasContent(dir) {
  return fs.existsSync(dir) && fs.readdirSync(dir).some((name) => name !== VERSION_FILE);
}

// Verifica si un archivo es una BD válida con tamaño mayor a 0 bytes
function isValidFileToCopy(filePath, fileName) {
  try {
    const stat = fs.statSync(filePath);
    if (fileName.endsWith('.db') && stat.size === 0) {
      return false; // Previene copiar DBs vacías de 0 bytes o placeholders
    }
    return true;
  } catch {
    return false;
  }
}

// Copia archivos/carpetas desde src a dst sin sobrescribir nunca lo que ya existe en dst.
function copyMissing(src, dst) {
  if (!fs.existsSync(src)) return 0;
  fs.mkdirSync(dst, { recursive: true });
  let copied = 0;
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (entry.name === VERSION_FILE) continue;
    const from = path.join(src, entry.name);
    const to = path.join(dst, entry.name);
    if (entry.isDirectory()) {
      if (SKIPPED_DIRS.has(entry.name)) continue;
      copied += copyMissing(from, to);
    } else if (!fs.existsSync(to)) {
      if (!isValidFileToCopy(from, entry.name)) continue;
      try {
        fs.copyFileSync(from, to);
        copied++;
      } catch (err) {
        console.warn(`[DataMigrator] No se pudo copiar ${from}:`, err.message);
      }
    }
  }
  return copied;
}

// Detecta si en otros perfiles de usuario de Windows existen datos válidos (p. ej. si un técnico instaló con cuenta admin)
function findOtherUserProfilesDataDirs(currentDataDir) {
  const dirs = [];
  try {
    const userProfile = process.env.USERPROFILE;
    if (!userProfile) return dirs;
    const usersRoot = path.dirname(userProfile);
    if (!fs.existsSync(usersRoot)) return dirs;

    const entries = fs.readdirSync(usersRoot, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const otherProfile = path.join(usersRoot, entry.name);
      if (path.resolve(otherProfile) === path.resolve(userProfile)) continue;

      const candidates = [
        path.join(otherProfile, 'AppData', 'Roaming', 'SSCP Desktop', 'data'),
        path.join(otherProfile, 'AppData', 'Roaming', 'sscp-desktop', 'data'),
        path.join(otherProfile, 'AppData', 'Local', 'SSCP', 'data')
      ];

      for (const cand of candidates) {
        if (path.resolve(cand) !== path.resolve(currentDataDir) && fs.existsSync(cand)) {
          const dbPath = path.join(cand, 'sscp.db');
          if (fs.existsSync(dbPath) && fs.statSync(dbPath).size > 0) {
            dirs.push(cand);
          }
        }
      }
    }
  } catch (err) {
    // Modo seguro sin detener ejecución
  }
  return dirs;
}

// Completa lo que falte en dataDir a partir de las ubicaciones legadas o alternativas
function migrateLegacyData(dataDir, legacyDirs) {
  let total = 0;
  const allSources = [...(legacyDirs || [])];

  // Si dataDir no tiene la base de datos sscp.db, buscar en otros perfiles del sistema
  const targetDb = path.join(dataDir, 'sscp.db');
  if (!fs.existsSync(targetDb) || fs.statSync(targetDb).size === 0) {
    const otherDirs = findOtherUserProfilesDataDirs(dataDir);
    allSources.push(...otherDirs);
  }

  for (const legacyDir of allSources) {
    if (!legacyDir || path.resolve(legacyDir) === path.resolve(dataDir)) continue;
    if (hasContent(legacyDir)) {
      total += copyMissing(legacyDir, dataDir);
    }
  }
  return total;
}

function listBackups(backupsDir) {
  if (!fs.existsSync(backupsDir)) return [];
  return fs.readdirSync(backupsDir, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => ({ name: e.name, mtime: fs.statSync(path.join(backupsDir, e.name)).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime)
    .map((b) => b.name);
}

function pruneBackups(backupsDir, keep) {
  for (const old of listBackups(backupsDir).slice(keep)) {
    fs.rmSync(path.join(backupsDir, old), { recursive: true, force: true });
  }
}

/**
 * Se ejecuta al detectar cambio de versión:
 * 1. Crea un respaldo íntegro de la carpeta de datos en backups/vX.Y.Z_timestamp
 * 2. Si falta algún archivo crítico (márgenes, configuración, base de datos) lo restaura desde el respaldo más reciente.
 * 3. Nunca sobreescribe datos existentes del usuario.
 */
function protectDataOnUpgrade(dataDir, currentVersion, options = {}) {
  const keep = options.keep || DEFAULT_KEEP_BACKUPS;
  const backupsDir = options.backupsDir || path.join(dataDir, '..', 'backups');
  const versionFile = path.join(dataDir, VERSION_FILE);
  const previousVersion = fs.existsSync(versionFile) ? fs.readFileSync(versionFile, 'utf8').trim() : null;

  const result = { previousVersion, currentVersion, backedUp: null, restored: 0 };

  if (previousVersion === currentVersion) return result;

  const existingBackups = listBackups(backupsDir);

  if (hasContent(dataDir)) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupName = `v${previousVersion || 'desconocida'}_${stamp}`;
    copyMissing(dataDir, path.join(backupsDir, backupName));
    result.backedUp = backupName;
    pruneBackups(backupsDir, keep);
  }

  // Si a la carpeta actual le falta información previa, restaurar desde los backups disponibles
  const backupsToScan = existingBackups.length > 0 ? existingBackups : listBackups(backupsDir);
  for (const bName of backupsToScan) {
    const bPath = path.join(backupsDir, bName);
    result.restored += copyMissing(bPath, dataDir);
  }

  fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(versionFile, currentVersion);
  return result;
}

module.exports = {
  copyMissing,
  migrateLegacyData,
  protectDataOnUpgrade,
  listBackups,
  findOtherUserProfilesDataDirs,
  VERSION_FILE
};
