const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

test('main.js enforces contextIsolation, nodeIntegration: false and sandbox: true', () => {
  const mainPath = path.resolve(__dirname, '../src/main/main.js');
  const content = fs.readFileSync(mainPath, 'utf8');

  assert.match(content, /contextIsolation:\s*true/, 'contextIsolation must be enabled in main.js');
  assert.match(content, /nodeIntegration:\s*false/, 'nodeIntegration must be disabled in main.js');
  assert.match(content, /sandbox:\s*true/, 'sandbox must be enabled in main.js');
});

test('main.js registers will-navigate defensive security listener', () => {
  const mainPath = path.resolve(__dirname, '../src/main/main.js');
  const content = fs.readFileSync(mainPath, 'utf8');

  assert.match(content, /webContents\.on\(\s*['"]will-navigate['"]/, 'will-navigate listener must be registered on webContents');
  assert.match(content, /event\.preventDefault\(\)/, 'will-navigate must prevent unauthorized default navigation');
});

test('print-configurator.js enforces secure webPreferences', () => {
  const pcPath = path.resolve(__dirname, '../src/main/print-configurator.js');
  const content = fs.readFileSync(pcPath, 'utf8');

  assert.match(content, /contextIsolation:\s*true/, 'contextIsolation must be enabled in print-configurator');
  assert.match(content, /nodeIntegration:\s*false/, 'nodeIntegration must be disabled in print-configurator');
  assert.match(content, /sandbox:\s*true/, 'sandbox must be enabled in print-configurator');
});

test('config.json version is synchronized with package.json', () => {
  const pkgPath = path.resolve(__dirname, '../package.json');
  const cfgPath = path.resolve(__dirname, '../config/config.json');

  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));

  assert.strictEqual(cfg.version, pkg.version, 'config.json version must match package.json version');
});
