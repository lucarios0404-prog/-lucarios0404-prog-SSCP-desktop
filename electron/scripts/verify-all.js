const path = require('path');
const fs = require('fs');
const http = require('http');
const ServerManager = require('../src/main/server-manager');

function request(url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          data: data
        });
      });
    });
    req.on('error', reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

async function runFullVerification() {
  console.log('====================================================');
  console.log('🚀 SSCP ELECTRON DESKTOP - VERIFICACIÓN END-TO-END');
  console.log('====================================================\n');

  // 1. Verificar archivos esenciales
  console.log('1️⃣  Verificando estructura de archivos...');
  const files = [
    '../config/config.json',
    '../src/main/main.js',
    '../src/main/server-manager.js',
    '../src/main/menu.js',
    '../src/main/notifications.js',
    '../src/main/print-configurator.js',
    '../src/preload/preload.js',
    '../src/renderer/print-configurator.html',
    '../src/splash/splash.html'
  ];

  for (const f of files) {
    const full = path.resolve(__dirname, f);
    if (!fs.existsSync(full)) {
      throw new Error(`Archivo no encontrado: ${f}`);
    }
  }
  console.log('   ✅ Todos los archivos de Electron existen y están en su lugar.\n');

  // 2. Levantar ServerManager
  console.log('2️⃣  Iniciando ServerManager (FastAPI Backend)...');
  const raw = fs.readFileSync(path.resolve(__dirname, '../config/config.json'), 'utf-8').replace(/^\uFEFF/, '');
  const config = JSON.parse(raw);
  const server = new ServerManager(config);

  try {
    const baseUrl = await server.start();
    console.log(`   ✅ Servidor FastAPI activo en: ${baseUrl}\n`);

    // 3. Probar endpoint /appointments/waiting-count
    console.log('3️⃣  Probando Módulo 2: Endpoint /appointments/waiting-count...');
    const waitingRes = await request(`${baseUrl}/appointments/waiting-count`);
    console.log(`   Status: ${waitingRes.statusCode}`);
    const waitingJson = JSON.parse(waitingRes.data);
    console.log(`   Respuesta:`, waitingJson);
    if (waitingRes.statusCode !== 200 || typeof waitingJson.count !== 'number') {
      throw new Error('Endpoint /appointments/waiting-count no devolvió el formato esperado.');
    }
    console.log('   ✅ Endpoint de sala de espera verificado con éxito.\n');

    // 4. Probar endpoint /settings/print-config (GET)
    console.log('4️⃣  Probando Módulo 3: Endpoint /settings/print-config (GET)...');
    const printGetRes = await request(`${baseUrl}/settings/print-config`);
    console.log(`   Status: ${printGetRes.statusCode}`);
    const printGetJson = JSON.parse(printGetRes.data);
    console.log(`   Márgenes actuales:`, printGetJson);
    if (printGetRes.statusCode !== 200 || !printGetJson.success) {
      throw new Error('Endpoint /settings/print-config GET falló.');
    }
    console.log('   ✅ Lectura de configuración de márgenes verificada.\n');

    // 5. Probar endpoint /settings/print-config (POST)
    console.log('5️⃣  Probando Módulo 3: Guardar nuevos márgenes (POST)...');
    const updatePayload = JSON.stringify({
      print_margin_top: 25.0,
      print_margin_bottom: 18.0,
      print_margin_left: 22.0,
      print_margin_right: 15.0,
      print_paper_size: 'Letter'
    });
    const printPostRes = await request(`${baseUrl}/settings/print-config`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(updatePayload)
      },
      body: updatePayload
    });
    console.log(`   Status: ${printPostRes.statusCode}`);
    const printPostJson = JSON.parse(printPostRes.data);
    console.log(`   Respuesta actualización:`, printPostJson);
    if (printPostRes.statusCode !== 200 || !printPostJson.success) {
      throw new Error('Endpoint /settings/print-config POST falló.');
    }

    // Comprobar persistencia
    const verifyGetRes = await request(`${baseUrl}/settings/print-config`);
    const verifyGetJson = JSON.parse(verifyGetRes.data);
    if (verifyGetJson.print_margin_top !== 25.0) {
      throw new Error('Los márgenes no se persistieron correctamente.');
    }
    console.log('   ✅ Persistencia de márgenes clínicos comprobada.\n');

    // Restaurar margen estándar (15mm)
    const restorePayload = JSON.stringify({
      print_margin_top: 15.0,
      print_margin_bottom: 15.0,
      print_margin_left: 20.0,
      print_margin_right: 15.0,
      print_paper_size: 'Letter'
    });
    await request(`${baseUrl}/settings/print-config`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(restorePayload)
      },
      body: restorePayload
    });

    // 6. Detener servidor limpiamente
    console.log('6️⃣  Deteniendo servidor limpiamente...');
    server.stop();
    console.log('   ✅ Proceso finalizado sin procesos huérfanos.\n');

    console.log('====================================================');
    console.log('🎉 TODAS LAS VERIFICACIONES COMPLETADAS CON ÉXITO');
    console.log('====================================================');
    process.exit(0);
  } catch (err) {
    console.error('❌ Error durante la verificación:', err);
    if (server) server.stop();
    process.exit(1);
  }
}

runFullVerification();
