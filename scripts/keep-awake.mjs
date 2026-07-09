/**
 * Keep-alive del Cazador de Leads (E-Auto Global · Gecko EV48).
 *
 * La app corre en Streamlit Community Cloud, que HIBERNA las apps tras varios días
 * sin visitas ("Zzzz — This app has gone to sleep due to inactivity"). Cuando eso pasa,
 * la sección «Cazador de Leads» del CRM (que la embebe en un iframe) queda en blanco con
 * el spinner "taking longer than normal".
 *
 * Un ping HTTP NO sirve: la URL responde 200 incluso dormida. Hay que abrir la página con
 * un navegador real y, si aparece el botón de despertar, clickearlo. Además, cada visita
 * resetea el contador de inactividad, así que correr esto en cron la mantiene despierta.
 *
 * Este script:
 *   1. Abre la URL embebida (200 directo, sin el bucle de auth de Streamlit Cloud).
 *   2. Si detecta el botón "Yes, get this app back up!", lo clickea y espera el arranque.
 *   3. Verifica que la app quedó viva (renderiza su pantalla de acceso).
 *   4. Deja un screenshot como evidencia (artifact del workflow).
 *
 * Sale con código 0 si la app quedó despierta; 1 si no se pudo confirmar.
 */
import { chromium } from 'playwright';

const URL =
  process.env.CAZADOR_URL ||
  'https://eauto-cazador.streamlit.app/?embed=true&embed_options=show_toolbar';

// Marcadores de que la app REAL (no la pantalla de sueño) está renderizada.
const ALIVE_MARKERS = [
  'acceso restringido',
  'Contraseña de acceso',
  'Lead Hunter',
  'E-Auto Global',
];

const WAKE_BUTTON = /get this app back up|wake it back up|Yes, get this app/i;

const log = (...a) => console.log(new Date().toISOString(), ...a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function isAlive(page) {
  // OJO: Streamlit Community Cloud mete la app REAL en un iframe interno; el contenido no
  // está en el frame principal (ahí solo vive el shell "Built with Streamlit"). Hay que
  // recorrer TODOS los frames. Playwright lee frames cross-origin sin problema.
  for (const frame of page.frames()) {
    for (const m of ALIVE_MARKERS) {
      const found = await frame
        .getByText(m, { exact: false })
        .first()
        .isVisible()
        .catch(() => false);
      if (found) return m;
    }
    // Fallback: el input de contraseña de la app.
    const pw = await frame
      .locator('input[type="password"]')
      .first()
      .isVisible()
      .catch(() => false);
    if (pw) return 'password-input';
  }
  return null;
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36 eauto-keepalive/1.0',
  });
  const page = await ctx.newPage();
  let ok = false;

  try {
    log('Abriendo', URL);
    await page.goto(URL, { waitUntil: 'load', timeout: 60_000 });

    // ¿Está dormida? Dale un momento a que pinte la pantalla de sueño.
    await sleep(4000);
    const wake = page.getByRole('button', { name: WAKE_BUTTON }).first();
    const wasAsleep = await wake.isVisible().catch(() => false);

    if (wasAsleep) {
      log('Estado: DORMIDA — clickeando "despertar".');
      await wake.click({ timeout: 10_000 }).catch(async () => {
        // Fallback por texto si el rol no matchea.
        await page.locator(`text=/${WAKE_BUTTON.source}/i`).first().click({ timeout: 10_000 });
      });
    } else {
      log('Estado: ya despierta (o cargando) — la visita cuenta como actividad.');
    }

    // Espera a que la app real renderice (hasta ~2 min: el cold-start de Streamlit es lento).
    const deadline = Date.now() + 120_000;
    let marker = null;
    while (Date.now() < deadline) {
      marker = await isAlive(page);
      if (marker) break;
      await sleep(3000);
    }

    if (marker) {
      ok = true;
      log(`OK — app viva (marcador: "${marker}").`);
    } else {
      log('FALLO — no se confirmó que la app renderizara tras esperar.');
    }
  } catch (err) {
    log('ERROR:', err?.message || err);
  } finally {
    await page.screenshot({ path: 'keepalive-screenshot.png', fullPage: false }).catch(() => {});
    await browser.close().catch(() => {});
  }

  process.exit(ok ? 0 : 1);
}

run();
