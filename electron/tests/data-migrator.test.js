const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { migrateLegacyData, protectDataOnUpgrade, listBackups } = require('../src/main/data-migrator');

function makeSandbox() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sscp-migr-'));
  const dataDir = path.join(root, 'userData', 'data');
  fs.mkdirSync(dataDir, { recursive: true });
  return { root, dataDir, backupsDir: path.join(root, 'userData', 'backups') };
}

const CUSTOM_CONFIG = JSON.stringify({ standard_margins: { top: 33, bottom: 22, left: 11, right: 44 } });

test('upgrade keeps customized margins untouched and creates a backup', () => {
  const { dataDir, backupsDir } = makeSandbox();
  fs.writeFileSync(path.join(dataDir, 'print_config.json'), CUSTOM_CONFIG);
  fs.writeFileSync(path.join(dataDir, '.data_version'), '1.2.8');

  const result = protectDataOnUpgrade(dataDir, '1.2.9', { backupsDir });

  assert.strictEqual(fs.readFileSync(path.join(dataDir, 'print_config.json'), 'utf8'), CUSTOM_CONFIG);
  assert.ok(result.backedUp);
  assert.strictEqual(fs.readFileSync(path.join(dataDir, '.data_version'), 'utf8'), '1.2.9');
  assert.strictEqual(listBackups(backupsDir).length, 1);
});

test('same version does not create another backup', () => {
  const { dataDir, backupsDir } = makeSandbox();
  fs.writeFileSync(path.join(dataDir, 'print_config.json'), CUSTOM_CONFIG);
  protectDataOnUpgrade(dataDir, '1.2.9', { backupsDir });

  const second = protectDataOnUpgrade(dataDir, '1.2.9', { backupsDir });

  assert.strictEqual(second.backedUp, null);
  assert.strictEqual(listBackups(backupsDir).length, 1);
});

test('lost config is restored from the latest backup', () => {
  const { dataDir, backupsDir } = makeSandbox();
  fs.writeFileSync(path.join(dataDir, 'print_config.json'), CUSTOM_CONFIG);
  protectDataOnUpgrade(dataDir, '1.2.9', { backupsDir });
  fs.rmSync(path.join(dataDir, 'print_config.json'));
  fs.writeFileSync(path.join(dataDir, 'sscp.db'), 'db');

  const result = protectDataOnUpgrade(dataDir, '1.3.0', { backupsDir });

  assert.ok(result.restored >= 1);
  assert.strictEqual(fs.readFileSync(path.join(dataDir, 'print_config.json'), 'utf8'), CUSTOM_CONFIG);
});

test('legacy migration copies every file but never overwrites existing ones', () => {
  const { root, dataDir } = makeSandbox();
  const legacy = path.join(root, 'legacy');
  fs.mkdirSync(path.join(legacy, 'uploads'), { recursive: true });
  fs.writeFileSync(path.join(legacy, 'print_config.json'), 'legacy-config');
  fs.writeFileSync(path.join(legacy, 'sscp.db'), 'legacy-db');
  fs.writeFileSync(path.join(legacy, 'uploads', 'logo.png'), 'logo');
  fs.writeFileSync(path.join(dataDir, 'sscp.db'), 'current-db');

  migrateLegacyData(dataDir, [legacy]);

  assert.strictEqual(fs.readFileSync(path.join(dataDir, 'sscp.db'), 'utf8'), 'current-db');
  assert.strictEqual(fs.readFileSync(path.join(dataDir, 'print_config.json'), 'utf8'), 'legacy-config');
  assert.ok(fs.existsSync(path.join(dataDir, 'uploads', 'logo.png')));
});

test('legacy migration ignores empty 0-byte db files from legacy locations', () => {
  const { root, dataDir } = makeSandbox();
  const legacy = path.join(root, 'legacy-empty');
  fs.mkdirSync(legacy, { recursive: true });
  fs.writeFileSync(path.join(legacy, 'sscp.db'), ''); // 0 bytes dummy

  migrateLegacyData(dataDir, [legacy]);

  assert.strictEqual(fs.existsSync(path.join(dataDir, 'sscp.db')), false);
});

test('only the 5 most recent backups are kept', () => {
  const { dataDir, backupsDir } = makeSandbox();
  fs.writeFileSync(path.join(dataDir, 'sscp.db'), 'db');
  for (let i = 1; i <= 8; i++) protectDataOnUpgrade(dataDir, `1.0.${i}`, { backupsDir });

  assert.strictEqual(listBackups(backupsDir).length, 5);
});
