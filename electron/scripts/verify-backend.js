const path = require('path');
const fs = require('fs');
const ServerManager = require('../src/main/server-manager');

async function testBackend() {
  console.log('[Test] Probando inicialización de ServerManager...');
  const raw = fs.readFileSync(path.resolve(__dirname, '../config/config.json'), 'utf-8').replace(/^\uFEFF/, '');
  const config = JSON.parse(raw);
  
  const server = new ServerManager(config);
  try {
    const url = await server.start();
    console.log(`[Test Exitoso] Servidor levantado y respondiendo en: ${url}`);
    
    // Probar detener el servidor
    console.log('[Test] Probando cierre limpio del servidor...');
    server.stop();
    console.log('[Test Exitoso] Servidor detenido correctamente.');
    process.exit(0);
  } catch (err) {
    console.error('[Test Error]:', err);
    if (server) server.stop();
    process.exit(1);
  }
}

testBackend();
