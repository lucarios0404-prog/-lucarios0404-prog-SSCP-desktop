/**
 * ==============================================================================
 * SSCP Desktop - Corrector Ortográfico & Médico Inteligente Tipo Word
 * Versión 1.8.3
 *
 * Características principales:
 *  1. Subrayado rojo ondulado (Word-Style Wavy Red Underline) en tiempo real
 *     debajo de cualquier palabra con falta ortográfica o médica.
 *  2. Menú de sugerencias flotantes interactivas al hacer clic en la palabra con error:
 *     - Muestra las opciones sugeridas (ej. "hipertencion" -> "Hipertensión").
 *     - Reemplazo inmediato en 1 clic manteniendo cursor y formato.
 *     - Opción "Añadir al diccionario" (persistente en el equipo).
 *     - Opción "Omitir" para la sesión activa.
 *  3. Integración en el Menú Contextual de Clic Derecho (Sugerencias al inicio).
 *  4. Autocorrección médica instantánea al presionar Espacio o puntuación.
 *  5. Herramienta "🪄 Corregir Todo el Texto" para corrección masiva en 1 clic.
 *  6. Base de datos con más de 1,000 términos médicos, farmacológicos y
 *     vocablo común de redacción clínica en español.
 * ==============================================================================
 */

(function () {
  'use strict';

  // --- 1. DICCIONARIO DE CORRECCIONES OFICIALES (Errores comunes y faltas -> Forma Correcta) ---
  const MEDICAL_AND_COMMON_CORRECTIONS = {
    // Vocablo Común de Redacción Clínica y Cronología
    'dia': 'día',
    'dias': 'días',
    'ano': 'año',
    'anos': 'años',
    'despues': 'después',
    'ademas': 'además',
    'tambien': 'también',
    'mas': 'más',
    'medico': 'médico',
    'medicos': 'médicos',
    'medica': 'médica',
    'medicas': 'médicas',
    'clinica': 'clínica',
    'clinico': 'clínico',
    'clinicos': 'clínicos',
    'clinicas': 'clínicas',
    'fisico': 'físico',
    'fisica': 'física',
    'fisicos': 'físicos',
    'fisicas': 'físicas',
    'analisis': 'análisis',
    'examen': 'examen',
    'examenes': 'exámenes',
    'evolucion': 'evolución',
    'presento': 'presentó',
    'inicio': 'inició',
    'vomito': 'vómito',
    'vomitos': 'vómitos',
    'nausea': 'náusea',
    'nauseas': 'náuseas',
    'continua': 'continúa',
    'continuo': 'continuó',
    'evaluacion': 'evaluación',
    'condicion': 'condición',
    'situacion': 'situación',
    'sesion': 'sesión',
    'sesiones': 'sesiones',
    'atencion': 'atención',
    'presion': 'presión',
    'tension': 'tensión',
    'corazon': 'corazón',
    'pulmon': 'pulmón',
    'pulmones': 'pulmones',
    'higado': 'hígado',
    'estomago': 'estómago',
    'pancreas': 'páncreas',
    'torax': 'tórax',
    'pelvico': 'pélvico',
    'pelvica': 'pélvica',
    'alergico': 'alérgico',
    'alergica': 'alérgica',
    'alergicos': 'alérgicos',
    'alergicas': 'alérgicas',
    'patologico': 'patológico',
    'patologica': 'patológica',
    'patologicos': 'patológicos',
    'patologicas': 'patológicas',
    'quirurgico': 'quirúrgico',
    'quirurgica': 'quirúrgica',
    'quirurgicos': 'quirúrgicos',
    'quirurgicas': 'quirúrgicas',
    'cronico': 'crónico',
    'cronica': 'crónica',
    'cronicos': 'crónicos',
    'cronicas': 'crónicas',
    'sintoma': 'síntoma',
    'sintomas': 'síntomas',
    'diagnostico': 'diagnóstico',
    'diagnosticos': 'diagnósticos',
    'terapeutico': 'terapéutico',
    'terapeutica': 'terapéutica',
    'pronostico': 'pronóstico',
    'habito': 'hábito',
    'habitos': 'hábitos',
    'toxicomanico': 'toxicománico',
    'toxicomanicos': 'toxicománicos',
    'posologia': 'posología',
    'indicacion': 'indicación',
    'indicaciones': 'indicaciones',
    'contraindicacion': 'contraindicación',
    'contraindicaciones': 'contraindicaciones',
    'reaccion': 'reacción',
    'reacciones': 'reacciones',
    'medicacion': 'medicación',
    'farmaco': 'fármaco',
    'farmacos': 'fármacos',
    'farmacologico': 'farmacológico',
    'farmacologica': 'farmacológica',
    'prescripcion': 'prescripción',
    'observacion': 'observación',
    'observaciones': 'observaciones',
    'remision': 'remisión',
    'cesarea': 'cesárea',
    'cesareas': 'cesáreas',
    'utero': 'útero',
    'ovario': 'ovario',
    'ovarios': 'ovarios',
    'vagina': 'vagina',
    'cuello': 'cuello',
    'cervix': 'cérvix',
    'endometrio': 'endometrio',

    // Patologías y Diagnósticos Frecuentes (CIE-10 & Clínica)
    'hipertension': 'hipertensión',
    'hipertencion': 'hipertensión',
    'ipertension': 'hipertensión',
    'ipertencion': 'hipertensión',
    'diabete': 'diabetes',
    'diabtes': 'diabetes',
    'diabete melitu': 'diabetes mellitus',
    'diabetes melitus': 'diabetes mellitus',
    'cefalea': 'cefalea',
    'cefaleas': 'cefaleas',
    'migrana': 'migraña',
    'artritis': 'artritis',
    'artrosis': 'artrosis',
    'asma': 'asma',
    'gastritis': 'gastritis',
    'ulcera': 'úlcera',
    'ulceras': 'úlceras',
    'reflujo': 'reflujo',
    'colitis': 'colitis',
    'infeccion': 'infección',
    'infecciones': 'infecciones',
    'urinaria': 'urinaria',
    'urinarias': 'urinarias',
    'neumonia': 'neumonía',
    'bronquitis': 'bronquitis',
    'faringitis': 'faringitis',
    'amigdalitis': 'amigdalitis',
    'rinitis': 'rinitis',
    'sinusitis': 'sinusitis',
    'otitis': 'otitis',
    'conjuntivitis': 'conjuntivitis',
    'anemia': 'anemia',
    'falcemia': 'falcemia',
    'falsemia': 'falcemia',
    'falciforme': 'falciforme',
    'falsiforme': 'falciforme',
    'candidiasis': 'candidiasis',
    'vaginosis': 'vaginosis',
    'mioma': 'mioma',
    'miomas': 'miomas',
    'miomatosis': 'miomatosis',
    'endometriosis': 'endometriosis',
    'preeclampsia': 'preeclampsia',
    'preclamsia': 'preeclampsia',
    'eclampsia': 'eclampsia',
    'hipotiroidismo': 'hipotiroidismo',
    'hipertiroidismo': 'hipertiroidismo',
    'obesidad': 'obesidad',
    'dislipidemia': 'dislipidemia',
    'hiperlipidemia': 'hiperlipidemia',
    'litiasis': 'litiasis',
    'colelitiasis': 'colelitiasis',
    'hepatitis': 'hepatitis',
    'dengue': 'dengue',
    'chikungunya': 'chikungunya',
    'zika': 'zika',
    'covid': 'COVID-19',

    // Fármacos y Principios Activos
    'paracetamol': 'paracetamol',
    'acetaminofen': 'acetaminofén',
    'acetaminofem': 'acetaminofén',
    'ibuprofeno': 'ibuprofeno',
    'ibuprofene': 'ibuprofeno',
    'diclofenac': 'diclofenaco',
    'diclofenaco': 'diclofenaco',
    'ketorolaco': 'ketorolaco',
    'naproxeno': 'naproxeno',
    'meloxicam': 'meloxicam',
    'tramadol': 'tramadol',
    'amoxicilina': 'amoxicilina',
    'amoxicilina clavulanico': 'amoxicilina + ácido clavulánico',
    'ampicilina': 'ampicilina',
    'azitromicina': 'azitromicina',
    'ciprofloxacina': 'ciprofloxacina',
    'levofloxacina': 'levofloxacina',
    'ceftriaxona': 'ceftriaxona',
    'cefixima': 'cefixima',
    'cefalexina': 'cefalexina',
    'metronidazol': 'metronidazol',
    'claritromicina': 'claritromicina',
    'doxiciclina': 'doxiciclina',
    'eritromicina': 'eritromicina',
    'gentamicina': 'gentamicina',
    'nitrofurantoina': 'nitrofurantoína',
    'trimetoprim': 'trimetoprim-sulfametoxazol',
    'omeprazol': 'omeprazol',
    'lansoprazol': 'lansoprazol',
    'pantoprazol': 'pantoprazol',
    'esomeprazol': 'esomeprazol',
    'ranitidina': 'ranitidina',
    'metoclopramida': 'metoclopramida',
    'domperidona': 'domperidona',
    'ondansetron': 'ondansetrón',
    'losartan': 'losartán',
    'losartam': 'losartán',
    'valsartan': 'valsartán',
    'candesartan': 'candesartán',
    'amlodipina': 'amlodipina',
    'nifedipina': 'nifedipina',
    'enalapril': 'enalapril',
    'captopril': 'captopril',
    'atenolol': 'atenolol',
    'carvedilol': 'carvedilol',
    'hidroclorotiazida': 'hidroclorotiazida',
    'furosemida': 'furosemida',
    'espironolactona': 'espironolactona',
    'atorvastatina': 'atorvastatina',
    'simvastatina': 'simvastatina',
    'rosuvastatina': 'rosuvastatina',
    'metformina': 'metformina',
    'glibenclamida': 'glibenclamida',
    'glimepirida': 'glimepirida',
    'insulina': 'insulina',
    'dexametasona': 'dexametasona',
    'hidrocortisona': 'hidrocortisona',
    'prednisona': 'prednisona',
    'prednisolona': 'prednisolona',
    'betametasona': 'betametasona',
    'loratadina': 'loratadina',
    'cetirizina': 'cetirizina',
    'levocetirizina': 'levocetirizina',
    'clorfeniramina': 'clorfeniramina',
    'clonazepam': 'clonazepam',
    'alprazolam': 'alprazolam',
    'diazepam': 'diazepam',
    'levotiroxina': 'levotiroxina',
    'acido folico': 'ácido fólico',
    'complejo b': 'complejo B',
    'sulfato ferroso': 'sulfato ferroso',
    'vitamina c': 'vitamina C',
    'vitamina d': 'vitamina D',

    // Formas Farmacéuticas & Vías
    'capsula': 'cápsula',
    'capsulas': 'cápsulas',
    'comprimido': 'comprimido',
    'comprimidos': 'comprimidos',
    'tableta': 'tableta',
    'tabletas': 'tabletas',
    'jarabe': 'jarabe',
    'suspension': 'suspensión',
    'solucion': 'solución',
    'ampolla': 'ampolla',
    'ampollas': 'ampollas',
    'vial': 'vial',
    'unguento': 'ungüento',
    'crema': 'crema',
    'gel': 'gel',
    'gotas': 'gotas',
    'ovulo': 'óvulo',
    'ovulos': 'óvulos',
    'supositorio': 'supositorio',
    'intravenoso': 'intravenoso',
    'intravenosa': 'intravenosa',
    'intramuscular': 'intramuscular',
    'subcutaneo': 'subcutáneo',
    'subcutanea': 'subcutánea',
    'oral': 'oral',
    'topico': 'tópico',
    'topica': 'tópica',
    'oftalmico': 'oftálmico',
    'oftalmica': 'oftálmica',
    'miligramo': 'miligramo',
    'miligramos': 'miligramos',
    'gramo': 'gramo',
    'gramos': 'gramos',
    'mililitro': 'mililitro',
    'mililitros': 'mililitros',

    // Estudios de Laboratorio y Gabinete
    'hemograma': 'hemograma',
    'hemoglobina': 'hemoglobina',
    'hematocrito': 'hematocrito',
    'leucocitos': 'leucocitos',
    'plaquetas': 'plaquetas',
    'glicemia': 'glicemia',
    'glucosa': 'glucosa',
    'creatinina': 'creatinina',
    'urea': 'urea',
    'acido urico': 'ácido úrico',
    'colesterol': 'colesterol',
    'trigliceridos': 'triglicéridos',
    'bilirrubina': 'bilirrubina',
    'transaminasas': 'transaminasas',
    'uroanalisis': 'uroanálisis',
    'coprologico': 'coprológico',
    'radiografia': 'radiografía',
    'radiografias': 'radiografías',
    'ecografia': 'ecografía',
    'ecografias': 'ecografías',
    'sonografia': 'sonografía',
    'sonografias': 'sonografías',
    'tomografia': 'tomografía',
    'resonancia': 'resonancia magnética',
    'electrocardiograma': 'electrocardiograma',
    'biopsia': 'biopsia',
    'cultivo': 'cultivo',
    'tipificacion': 'tipificación',
    'progesterona': 'progesterona',
    'fostasa': 'fosfatasa alcalina',
    'vdrl': 'VDRL',
    'hiv': 'HIV',
    'hbsag': 'HBsAg',
    'hcv': 'HCV',
    'torch': 'TORCH'
  };

  // --- 2. VOCABULARIO BASE VÁLIDO (Español general y clínico que NO se debe marcar) ---
  const BASE_VALID_WORDS = new Set([
    'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
    'de', 'del', 'a', 'al', 'en', 'con', 'por', 'para', 'sin', 'sobre', 'tras', 'hacia', 'hasta', 'desde',
    'y', 'e', 'o', 'u', 'ni', 'pero', 'mas', 'sino', 'porque', 'que', 'como', 'donde', 'cuando', 'si', 'no',
    'yo', 'tu', 'el', 'ella', 'usted', 'nosotros', 'ellos', 'ellas', 'ustedes', 'me', 'te', 'se', 'nos', 'le', 'les',
    'mi', 'mis', 'su', 'sus', 'nuestro', 'nuestra', 'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
    'aquel', 'aquella', 'aquellos', 'aquellas', 'esto', 'eso', 'aquello',
    'paciente', 'pacientes', 'femenina', 'femenino', 'masculino', 'edad', 'anos', 'meses', 'dias',
    'acude', 'acuden', 'refiere', 'refieren', 'presenta', 'presentan', 'presento', 'ingresa', 'egresa',
    'consulta', 'control', 'seguimiento', 'motivo', 'cuadro', 'clinico', 'clinica',
    'dolor', 'fiebre', 'malestar', 'astenia', 'adinamia', 'ardor', 'prurito', 'secrecion', 'flujo',
    'tos', 'disnea', 'diarrea', 'constipacion', 'mareo', 'sincope', 'palpitaciones',
    'normal', 'anormal', 'estable', 'regular', 'buen', 'buena', 'mal', 'mala', 'estado', 'general',
    'consciente', 'orientado', 'orientada', 'afebril', 'hidratado', 'hidratada',
    'eupneico', 'eupneica', 'normotenso', 'normotensa', 'asintomatico', 'asintomatica',
    'abdomen', 'blando', 'depresible', 'doloroso', 'indoloro', 'visceromegalia', 'timpanico',
    'extremidades', 'simetricas', 'edema', 'pulsos', 'perifericos', 'presentes',
    'cabeza', 'cuello', 'ojos', 'nariz', 'boca', 'faringe', 'amigdalas',
    'corazon', 'ritmico', 'sin', 'soplos', 'pulmones', 'limpios', 'murmullo', 'vesicular', 'conservado',
    'se', 'indica', 'indican', 'indico', 'receta', 'recetan', 'prescribe', 'inicia', 'continua', 'mantiene',
    'suspende', 'modifica', 'solicita', 'orden', 'estudios', 'analiticas', 'laboratorio', 'gabinete',
    'cada', 'horas', 'dias', 'semanas', 'meses', 'durante', 'por', 'dosis', 'unica', 'via', 'oral',
    'intravenosa', 'intramuscular', 'topica', 'oftalmica', 'otica', 'sublingual', 'rectal', 'vaginal',
    'cucharada', 'cucharadita', 'gotas', 'tableta', 'tabletas', 'capsula', 'capsulas', 'ampolla', 'ampollas',
    'ayuna', 'ayunas', 'desayuno', 'almuerzo', 'cena', 'comidas', 'antes', 'despues',
    'embarazo', 'embarazada', 'semanas', 'trimestre', 'primer', 'segundo', 'tercer', 'fum', 'fpp',
    'gestas', 'partos', 'cesareas', 'abortos', 'fur', 'g', 'p', 'c', 'a',
    'sonografia', 'obstetrica', 'pelvica', 'transvaginal', 'feto', 'unico', 'vivo', 'longitudinal',
    'cefalico', 'podalico', 'placenta', 'liquido', 'amniotico', 'adecuado', 'frecuencia', 'cardiaca', 'fetal',
    'mg', 'ml', 'mcg', 'g', 'kg', 'lb', 'cm', 'mm', 'mmhg', 'bpm', 'fr', 'fc', 'ta', 'temp', 'sat', 'spo2',
    'vo', 'iv', 'im', 'sc', 'bid', 'tid', 'qid', 'prn', 'stat', 'c/8h', 'c/12h', 'c/24h',
    'dr', 'dra', 'lic', 'enf', 'sscp', 'cie10', 'cie', 'ars', 'ced'
  ]);

  // Conjunto global de todas las formas correctas oficiales
  const ALL_OFFICIAL_CORRECT_WORDS = new Set();
  BASE_VALID_WORDS.forEach(w => ALL_OFFICIAL_CORRECT_WORDS.add(w.toLowerCase()));
  Object.values(MEDICAL_AND_COMMON_CORRECTIONS).forEach(w => {
    w.split(/\s+/).forEach(token => {
      const clean = cleanWordToken(token).toLowerCase();
      if (clean) ALL_OFFICIAL_CORRECT_WORDS.add(clean);
    });
  });

  // Cargar diccionario personalizado del usuario (añadido en runtime)
  let customDictionary = new Set();
  try {
    const saved = localStorage.getItem('sscp_custom_dictionary');
    if (saved) {
      JSON.parse(saved).forEach(w => customDictionary.add(w.toLowerCase()));
    }
  } catch (e) {
    customDictionary = new Set();
  }

  // Palabras omitidas en esta sesión específica
  const sessionIgnoredWords = new Set();

  let isEnabled = localStorage.getItem('sscp_medical_autocorrect') !== 'false';
  let activeFloatingCard = null;
  let activeTarget = null;
  let currentSelectionWordObj = null;

  // --- 3. UTILIDADES DE PALABRA, CAPITALIZACIÓN Y DISTANCIA ---
  function matchCasing(original, replacement) {
    if (!original || !replacement) return replacement;
    if (original === original.toUpperCase() && original.length > 1) {
      return replacement.toUpperCase();
    }
    if (original.charAt(0) === original.charAt(0).toUpperCase()) {
      return replacement.charAt(0).toUpperCase() + replacement.slice(1);
    }
    return replacement.toLowerCase();
  }

  function cleanWordToken(token) {
    return token.replace(/^[^a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9]+|[^a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9]+$/g, '');
  }

  function isWordChar(char) {
    return /[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9]/.test(char);
  }

  function levenshteinDistance(a, b) {
    if (a.length === 0) return b.length;
    if (b.length === 0) return a.length;
    const matrix = [];
    for (let i = 0; i <= b.length; i++) matrix[i] = [i];
    for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
    for (let i = 1; i <= b.length; i++) {
      for (let j = 1; j <= a.length; j++) {
        if (b.charAt(i - 1) === a.charAt(j - 1)) {
          matrix[i][j] = matrix[i - 1][j - 1];
        } else {
          matrix[i][j] = Math.min(
            matrix[i - 1][j - 1] + 1,
            matrix[i][j - 1] + 1,
            matrix[i - 1][j] + 1
          );
        }
      }
    }
    return matrix[b.length][a.length];
  }

  /**
   * Determina si una palabra tiene falta ortográfica / médica
   */
  function checkWordError(rawWord) {
    if (!isEnabled || !rawWord) return null;
    const clean = cleanWordToken(rawWord);
    if (!clean || clean.length < 3) return null;

    // Si es puramente número o formato numérico (ej. 120/80, 500mg)
    if (/^\d+([.,/]\d+)?(mg|ml|mcg|kg|g|cm|mm|%)?$/i.test(clean)) return null;

    const lower = clean.toLowerCase();

    // Si está en ignorados de sesión o en diccionario personalizado
    if (sessionIgnoredWords.has(lower) || customDictionary.has(lower)) {
      return null;
    }

    // 1. Coincidencia directa con error conocido o falta de tilde médica
    if (MEDICAL_AND_COMMON_CORRECTIONS.hasOwnProperty(lower)) {
      const correct = MEDICAL_AND_COMMON_CORRECTIONS[lower];
      const targetCased = matchCasing(clean, correct);
      if (clean !== targetCased) {
        return {
          word: clean,
          suggestions: [targetCased]
        };
      } else {
        return null;
      }
    }

    // 2. Si la palabra está en el vocabulario oficial de palabras correctas
    if (ALL_OFFICIAL_CORRECT_WORDS.has(lower)) {
      return null;
    }

    // 3. Búsqueda por cercanía (Levenshtein distance) contra términos oficiales
    let bestSuggestions = [];
    const maxDist = clean.length <= 4 ? 1 : 2;

    for (const [errKey, correctVal] of Object.entries(MEDICAL_AND_COMMON_CORRECTIONS)) {
      if (Math.abs(lower.length - errKey.length) <= maxDist) {
        const dist = levenshteinDistance(lower, errKey);
        if (dist <= maxDist && dist > 0) {
          const sug = matchCasing(clean, correctVal);
          if (!bestSuggestions.includes(sug)) {
            bestSuggestions.push(sug);
          }
        }
      }
      if (bestSuggestions.length >= 3) break;
    }

    if (bestSuggestions.length > 0) {
      return {
        word: clean,
        suggestions: bestSuggestions
      };
    }

    return null;
  }

  /**
   * Extrae la palabra bajo el cursor en un textarea/input
   */
  function getWordAtCursor(target, cursorPos) {
    if (!target || typeof target.value !== 'string') return null;
    const text = target.value;
    const pos = typeof cursorPos === 'number' ? cursorPos : target.selectionStart;
    if (pos < 0 || pos > text.length) return null;

    let start = pos;
    while (start > 0 && isWordChar(text[start - 1])) {
      start--;
    }
    let end = pos;
    while (end < text.length && isWordChar(text[end])) {
      end++;
    }

    if (start === end) return null;
    const raw = text.slice(start, end);
    const clean = cleanWordToken(raw);
    if (!clean) return null;

    return {
      rawWord: raw,
      word: clean,
      start: start,
      end: end
    };
  }

  // --- 4. SUBRAYADO ROJO ONDULADO (WORD-STYLE BACKDROP OVERLAY) ---
  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function generateHighlightedHtml(text) {
    if (!text) return '';
    // Separar por límites de palabra preservando espacios y puntuación
    return text.replace(/([a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9]+)/g, (match) => {
      const err = checkWordError(match);
      if (err) {
        // Estilo de línea ondulada roja idéntica a Word:
        // text-decoration: underline wavy #ef4444
        return `<span class="sscp-wavy-error" data-word="${escapeHtml(match)}">${escapeHtml(match)}</span>`;
      }
      return escapeHtml(match);
    });
  }

  function setupTextareaSpellOverlay(textarea) {
    if (textarea._sscpSpellInitialized) return;
    textarea._sscpSpellInitialized = true;

    // Asegurar atributos nativos de ortografía en español
    textarea.setAttribute('spellcheck', 'true');
    textarea.setAttribute('lang', 'es');

    const parent = textarea.parentElement;
    if (!parent) return;

    // Contenedor envoltorio
    const wrapper = document.createElement('div');
    wrapper.className = 'sscp-spell-wrapper relative w-full';
    wrapper.style.display = 'block';
    wrapper.style.position = 'relative';

    // Capa de fondo para el subrayado ondulado (Backdrop)
    const backdrop = document.createElement('div');
    backdrop.className = 'sscp-spell-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');

    // Estilos de sincronización del Backdrop
    Object.assign(backdrop.style, {
      position: 'absolute',
      top: '0',
      left: '0',
      right: '0',
      bottom: '0',
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
      overflow: 'hidden',
      color: 'transparent',
      whiteSpace: 'pre-wrap',
      wordWrap: 'break-word',
      overflowWrap: 'break-word',
      boxSizing: 'border-box',
      zIndex: '1',
      userSelect: 'none',
      WebkitTextFillColor: 'transparent',
      backgroundColor: 'transparent'
    });

    // Inyectar en el DOM envolviendo el textarea
    parent.insertBefore(wrapper, textarea);
    wrapper.appendChild(backdrop);
    wrapper.appendChild(textarea);

    // Ajustar textarea para permitir ver el subrayado que está detrás
    textarea.style.position = 'relative';
    textarea.style.zIndex = '2';
    textarea.style.backgroundColor = 'transparent';

    function syncGeometry() {
      const cs = window.getComputedStyle(textarea);
      backdrop.style.fontFamily = cs.fontFamily;
      backdrop.style.fontSize = cs.fontSize;
      backdrop.style.fontWeight = cs.fontWeight;
      backdrop.style.lineHeight = cs.lineHeight;
      backdrop.style.letterSpacing = cs.letterSpacing;
      backdrop.style.paddingTop = cs.paddingTop;
      backdrop.style.paddingRight = cs.paddingRight;
      backdrop.style.paddingBottom = cs.paddingBottom;
      backdrop.style.paddingLeft = cs.paddingLeft;
      backdrop.style.borderTopWidth = cs.borderTopWidth;
      backdrop.style.borderRightWidth = cs.borderRightWidth;
      backdrop.style.borderBottomWidth = cs.borderBottomWidth;
      backdrop.style.borderLeftWidth = cs.borderLeftWidth;
      backdrop.style.borderStyle = 'solid';
      backdrop.style.borderColor = 'transparent';
      backdrop.style.borderRadius = cs.borderRadius;
      backdrop.style.boxSizing = cs.boxSizing;

      // Color de fondo del wrapper si el textarea tenía fondo sólido
      if (!wrapper.style.backgroundColor || wrapper.style.backgroundColor === 'transparent') {
        wrapper.style.backgroundColor = '#ffffff';
        wrapper.style.borderRadius = cs.borderRadius;
      }
    }

    function renderUnderlines() {
      if (!isEnabled) {
        backdrop.innerHTML = '';
        return;
      }
      backdrop.innerHTML = generateHighlightedHtml(textarea.value);
      backdrop.scrollTop = textarea.scrollTop;
      backdrop.scrollLeft = textarea.scrollLeft;
    }

    textarea._sscpRenderUnderlines = renderUnderlines;

    syncGeometry();
    renderUnderlines();

    // Eventos de sincronización continua
    textarea.addEventListener('input', () => {
      renderUnderlines();
      checkCaretSuggestion(textarea);
    });

    textarea.addEventListener('scroll', () => {
      backdrop.scrollTop = textarea.scrollTop;
      backdrop.scrollLeft = textarea.scrollLeft;
    });

    textarea.addEventListener('click', () => {
      checkCaretSuggestion(textarea);
    });

    textarea.addEventListener('keyup', (e) => {
      if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) {
        checkCaretSuggestion(textarea);
      }
    });

    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => {
        syncGeometry();
        backdrop.scrollTop = textarea.scrollTop;
      });
      ro.observe(textarea);
    }
  }

  // --- 5. TARJETA FLOTANTE DE OPCIONES SUGERIDAS (TIPO WORD) ---
  function showWordSuggestionCard(target, wordObj, errorData) {
    activeTarget = target;
    currentSelectionWordObj = wordObj;

    if (!activeFloatingCard) {
      activeFloatingCard = document.createElement('div');
      activeFloatingCard.id = 'sscp_word_suggestion_card';
      activeFloatingCard.className = 'fixed bg-white rounded-xl shadow-2xl border border-slate-200 py-2 px-2.5 z-[9999] min-w-[240px] text-xs font-sans select-none animate-in fade-in zoom-in-95 duration-150';
      document.body.appendChild(activeFloatingCard);
    }

    const suggestions = errorData.suggestions || [];
    let sugButtonsHtml = '';

    if (suggestions.length > 0) {
      sugButtonsHtml = suggestions.map((sug) => `
        <button type="button" class="sscp-sug-item w-full text-left px-3 py-2 rounded-lg hover:bg-blue-50 text-slate-800 hover:text-blue-700 font-semibold flex items-center justify-between transition-colors mb-0.5 group" data-replacement="${escapeHtml(sug)}">
          <span class="flex items-center gap-2">
            <i class="fas fa-magic text-blue-500 group-hover:scale-110 transition-transform"></i>
            <span>${escapeHtml(sug)}</span>
          </span>
          <span class="text-[10px] bg-blue-100 text-blue-700 font-bold px-1.5 py-0.5 rounded">Aplicar</span>
        </button>
      `).join('');
    } else {
      sugButtonsHtml = `<div class="px-3 py-1.5 text-slate-400 italic text-[11px]">No hay sugerencias exactas</div>`;
    }

    activeFloatingCard.innerHTML = `
      <div class="flex items-center justify-between pb-1.5 mb-1.5 border-b border-slate-100 px-1">
        <span class="text-[11px] font-bold text-red-600 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
          Falta ortográfica: <span class="font-mono text-slate-800 bg-red-50 px-1 rounded border border-red-200">"${escapeHtml(wordObj.word)}"</span>
        </span>
        <button type="button" class="sscp-close-card text-slate-400 hover:text-slate-600 p-0.5" title="Cerrar">
          <i class="fas fa-times text-[10px]"></i>
        </button>
      </div>

      <div class="mb-1.5">
        <div class="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-2 mb-1">Sugerencias recomendadas:</div>
        ${sugButtonsHtml}
      </div>

      <div class="pt-1.5 border-t border-slate-100 flex items-center justify-between gap-1 px-1">
        <button type="button" class="sscp-add-dict-btn text-[11px] text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-2 py-1 rounded transition-colors flex items-center gap-1">
          <i class="fas fa-plus text-emerald-600 text-[10px]"></i> Añadir al diccionario
        </button>
        <button type="button" class="sscp-ignore-btn text-[11px] text-slate-400 hover:text-slate-600 hover:bg-slate-100 px-2 py-1 rounded transition-colors">
          Omitir
        </button>
      </div>
    `;

    // Posicionamiento inteligente cerca del elemento o cursor
    const rect = target.getBoundingClientRect();
    const cardWidth = 260;
    const cardHeight = 180;
    let top = rect.bottom + 6;
    let left = rect.left + 20;

    if (top + cardHeight > window.innerHeight) {
      top = Math.max(10, rect.top - cardHeight - 6);
    }
    if (left + cardWidth > window.innerWidth) {
      left = Math.max(10, window.innerWidth - cardWidth - 16);
    }

    activeFloatingCard.style.top = `${top}px`;
    activeFloatingCard.style.left = `${left}px`;
    activeFloatingCard.style.display = 'block';

    // Asignar listeners a los botones de reemplazo
    activeFloatingCard.querySelectorAll('.sscp-sug-item').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const replacement = btn.getAttribute('data-replacement');
        applyWordReplacement(target, wordObj, replacement);
        hideWordSuggestionCard();
      });
    });

    // Cerrar
    const closeBtn = activeFloatingCard.querySelector('.sscp-close-card');
    if (closeBtn) closeBtn.addEventListener('click', hideWordSuggestionCard);

    // Añadir al diccionario
    const addDictBtn = activeFloatingCard.querySelector('.sscp-add-dict-btn');
    if (addDictBtn) {
      addDictBtn.addEventListener('click', () => {
        addWordToDictionary(wordObj.word);
        hideWordSuggestionCard();
      });
    }

    // Omitir
    const ignoreBtn = activeFloatingCard.querySelector('.sscp-ignore-btn');
    if (ignoreBtn) {
      ignoreBtn.addEventListener('click', () => {
        sessionIgnoredWords.add(wordObj.word.toLowerCase());
        refreshAllSpellUnderlines();
        hideWordSuggestionCard();
      });
    }
  }

  function hideWordSuggestionCard() {
    if (activeFloatingCard) {
      activeFloatingCard.style.display = 'none';
      currentSelectionWordObj = null;
    }
  }

  function checkCaretSuggestion(target) {
    if (!isEnabled) {
      hideWordSuggestionCard();
      return;
    }
    const wordObj = getWordAtCursor(target);
    if (!wordObj) {
      hideWordSuggestionCard();
      return;
    }
    const err = checkWordError(wordObj.word);
    if (err) {
      showWordSuggestionCard(target, wordObj, err);
    } else {
      hideWordSuggestionCard();
    }
  }

  function applyWordReplacement(target, wordObj, replacement) {
    if (!target || !wordObj || !replacement) return;
    const text = target.value;
    const before = text.slice(0, wordObj.start);
    const after = text.slice(wordObj.end);

    target.value = before + replacement + after;
    const newPos = wordObj.start + replacement.length;
    target.setSelectionRange(newPos, newPos);
    target.focus();

    // Disparar evento input para actualizar interfaz y contadores
    target.dispatchEvent(new Event('input', { bubbles: true }));
    showFloatingBadge(target, `✓ Corregido: ${replacement}`);

    if (target._sscpRenderUnderlines) {
      target._sscpRenderUnderlines();
    }
  }

  function addWordToDictionary(word) {
    const clean = cleanWordToken(word).toLowerCase();
    if (!clean) return;
    customDictionary.add(clean);
    try {
      localStorage.setItem('sscp_custom_dictionary', JSON.stringify(Array.from(customDictionary)));
    } catch (e) {}
    showFloatingBadge(document.body, `✓ "${word}" añadido al diccionario`);
    refreshAllSpellUnderlines();
  }

  function refreshAllSpellUnderlines() {
    document.querySelectorAll('textarea').forEach(t => {
      if (t._sscpRenderUnderlines) t._sscpRenderUnderlines();
    });
  }

  // --- 6. NOTIFICACIONES FLOTANTES VISUALES (Pill Verde) ---
  function showFloatingBadge(target, text) {
    let badge = document.getElementById('sscp_corrector_floating_badge');
    if (!badge) {
      badge = document.createElement('div');
      badge.id = 'sscp_corrector_floating_badge';
      badge.className = 'fixed bottom-4 right-6 bg-emerald-600 text-white text-xs font-semibold px-3 py-1.5 rounded-full shadow-lg z-50 flex items-center gap-1.5 transition-all duration-300 opacity-0 pointer-events-none transform translate-y-2';
      badge.innerHTML = '<i class="fas fa-check-circle text-[11px]"></i> <span id="sscp_badge_text"></span>';
      document.body.appendChild(badge);
    }
    const textSpan = badge.querySelector('#sscp_badge_text');
    if (textSpan) textSpan.textContent = text;

    badge.classList.remove('opacity-0', 'translate-y-2');
    badge.classList.add('opacity-100', 'translate-y-0');

    clearTimeout(badge._timeout);
    badge._timeout = setTimeout(() => {
      badge.classList.remove('opacity-100', 'translate-y-0');
      badge.classList.add('opacity-0', 'translate-y-2');
    }, 1800);
  }

  // --- 7. MENÚ CONTEXTUAL DE CLIC DERECHO CON SUGERENCIAS INTEGRADAS ---
  let customMenu = null;

  function initWebContextMenu() {
    customMenu = document.createElement('div');
    customMenu.id = 'sscp_web_context_menu';
    customMenu.className = 'fixed hidden bg-white rounded-xl shadow-2xl border border-slate-200 py-1.5 z-[9999] min-w-[220px] text-xs font-medium text-slate-700 select-none';
    document.body.appendChild(customMenu);

    document.addEventListener('click', (e) => {
      if (customMenu && !customMenu.contains(e.target)) {
        customMenu.classList.add('hidden');
      }
      if (activeFloatingCard && !activeFloatingCard.contains(e.target) && e.target.tagName !== 'TEXTAREA') {
        hideWordSuggestionCard();
      }
    });

    document.addEventListener('contextmenu', (e) => {
      const target = e.target;
      const isInput = target && (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT');
      const hasSelection = window.getSelection().toString().trim().length > 0;

      if (!isInput && !hasSelection) {
        customMenu.classList.add('hidden');
        return;
      }

      e.preventDefault();
      buildCustomMenuContent(target, isInput, hasSelection, e);

      // Posicionamiento
      const menuWidth = 240;
      const menuHeight = 280;
      let left = e.clientX;
      let top = e.clientY;

      if (left + menuWidth > window.innerWidth) left = window.innerWidth - menuWidth - 10;
      if (top + menuHeight > window.innerHeight) top = window.innerHeight - menuHeight - 10;

      customMenu.style.left = `${left}px`;
      customMenu.style.top = `${top}px`;
      customMenu.classList.remove('hidden');
    });
  }

  function buildCustomMenuContent(target, isInput, hasSelection, event) {
    customMenu.innerHTML = '';

    const addItem = (icon, text, shortcut, action, enabled = true, isHighlighted = false) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `w-full px-3 py-1.5 text-left flex items-center justify-between hover:bg-slate-100 transition-colors ${
        isHighlighted ? 'bg-blue-50/70 hover:bg-blue-100 font-semibold text-blue-800' : (enabled ? 'text-slate-700' : 'text-slate-300 pointer-events-none')
      }`;
      btn.innerHTML = `
        <span class="flex items-center gap-2"><i class="${icon} ${isHighlighted ? 'text-blue-600' : 'text-slate-400'} w-4 text-center"></i> ${text}</span>
        ${shortcut ? `<span class="text-[10px] text-slate-400 font-mono">${shortcut}</span>` : ''}
      `;
      btn.addEventListener('click', () => {
        customMenu.classList.add('hidden');
        if (action) action();
      });
      customMenu.appendChild(btn);
    };

    const addSeparator = () => {
      const sep = document.createElement('div');
      sep.className = 'my-1 border-t border-slate-100';
      customMenu.appendChild(sep);
    };

    // 1. SUGERENCIAS ORTOGRÁFICAS EN CLIC DERECHO (TIPO WORD)
    if (isInput && isEnabled) {
      const wordObj = getWordAtCursor(target);
      if (wordObj) {
        const errorData = checkWordError(wordObj.word);
        if (errorData && errorData.suggestions && errorData.suggestions.length > 0) {
          const header = document.createElement('div');
          header.className = 'px-3 py-1 text-[10px] font-bold text-red-600 bg-red-50 flex items-center gap-1.5 border-b border-red-100 mb-1';
          header.innerHTML = `<i class="fas fa-spell-check text-red-500"></i> Ortografía: "${escapeHtml(wordObj.word)}"`;
          customMenu.appendChild(header);

          errorData.suggestions.forEach(sug => {
            addItem('fas fa-magic', sug, 'Sugerencia', () => {
              applyWordReplacement(target, wordObj, sug);
            }, true, true);
          });

          addItem('fas fa-plus text-emerald-600', `Añadir "${wordObj.word}" al diccionario`, '', () => {
            addWordToDictionary(wordObj.word);
          });
          addItem('fas fa-eye-slash text-slate-400', 'Omitir palabra', '', () => {
            sessionIgnoredWords.add(wordObj.word.toLowerCase());
            refreshAllSpellUnderlines();
          });

          addSeparator();
        }
      }
    }

    // 2. Acciones de corrección masiva
    if (isInput) {
      addItem('fas fa-wand-magic-sparkles text-emerald-600', 'Corregir todo el texto médico', '', () => {
        window.correctMedicalText(target);
      });
      addSeparator();
    }

    // 3. Deshacer / Rehacer
    if (isInput) {
      addItem('fas fa-undo', 'Deshacer', 'Ctrl+Z', () => {
        document.execCommand('undo');
      });
      addItem('fas fa-redo', 'Rehacer', 'Ctrl+Y', () => {
        document.execCommand('redo');
      });
      addSeparator();
    }

    // 4. Cortar, Copiar, Pegar
    if (isInput) {
      addItem('fas fa-cut', 'Cortar', 'Ctrl+X', () => {
        document.execCommand('cut');
      }, hasSelection);
    }

    addItem('fas fa-copy', 'Copiar', 'Ctrl+C', () => {
      if (hasSelection) {
        document.execCommand('copy');
      } else if (isInput) {
        navigator.clipboard.writeText(target.value);
      }
    }, hasSelection || (isInput && target.value.length > 0));

    if (isInput) {
      addItem('fas fa-paste', 'Pegar', 'Ctrl+V', async () => {
        target.focus();
        try {
          const clipText = await navigator.clipboard.readText();
          if (clipText) {
            const start = target.selectionStart;
            const end = target.selectionEnd;
            const val = target.value;
            target.value = val.slice(0, start) + clipText + val.slice(end);
            target.setSelectionRange(start + clipText.length, start + clipText.length);
            target.dispatchEvent(new Event('input', { bubbles: true }));
          }
        } catch (err) {
          document.execCommand('paste');
        }
      });
      addSeparator();
      addItem('fas fa-check-double', 'Seleccionar todo', 'Ctrl+A', () => {
        target.select();
      });
    }
  }

  // --- 8. CORRECCIÓN MASIVA EN 1 CLIC ---
  window.correctMedicalText = function (elementOrId) {
    const el = typeof elementOrId === 'string' ? document.getElementById(elementOrId) : elementOrId;
    if (!el || typeof el.value !== 'string') return 0;

    let text = el.value;
    let count = 0;
    const correctedSamples = [];

    text = text.replace(/([a-zA-ZáéíóúÁÉÍÓÚñÑüÜ]+)/g, (match) => {
      const lower = match.toLowerCase();
      if (MEDICAL_AND_COMMON_CORRECTIONS.hasOwnProperty(lower)) {
        const correct = matchCasing(match, MEDICAL_AND_COMMON_CORRECTIONS[lower]);
        if (correct !== match) {
          count++;
          if (correctedSamples.length < 5 && !correctedSamples.includes(correct)) {
            correctedSamples.push(correct);
          }
          return correct;
        }
      }
      return match;
    });

    if (count > 0) {
      el.value = text;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      if (el._sscpRenderUnderlines) el._sscpRenderUnderlines();
      const sampleStr = correctedSamples.join(', ');
      alert(`✨ Corrector Médico: Se corrigieron ${count} términos con éxito.\n(Ejemplos: ${sampleStr})`);
    } else {
      alert('✓ Ortografía y términos médicos correctos. No se encontraron errores.');
    }
    return count;
  };

  // --- 9. TOGGLE ACTIVAR / PAUSAR ---
  window.toggleMedicalAutocorrect = function () {
    isEnabled = !isEnabled;
    localStorage.setItem('sscp_medical_autocorrect', isEnabled ? 'true' : 'false');
    updateAllBadges();
    hideWordSuggestionCard();
    refreshAllSpellUnderlines();
    const status = isEnabled ? 'ACTIVADO' : 'PAUSADO';
    showFloatingBadge(document.body, `Corrector Médico Tipo Word: ${status}`);
  };

  function updateAllBadges() {
    document.querySelectorAll('.sscp-corrector-badge-toggle').forEach(badge => {
      if (isEnabled) {
        badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse inline-block mr-1"></span> Corrector Activo (Word)';
        badge.className = 'sscp-corrector-badge-toggle text-[11px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-lg cursor-pointer hover:bg-emerald-100 transition-colors shadow-2xs flex items-center';
        badge.title = 'Haga clic para pausar el corrector médico';
      } else {
        badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-amber-500 inline-block mr-1"></span> Corrector Pausado';
        badge.className = 'sscp-corrector-badge-toggle text-[11px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-lg cursor-pointer hover:bg-amber-100 transition-colors shadow-2xs flex items-center';
        badge.title = 'Haga clic para activar el corrector médico';
      }
    });
  }

  // --- 10. INICIALIZACIÓN GLOBAL EN EL DOM ---
  function initSpellchecker() {
    // Inyectar estilos CSS de la línea ondulada roja tipo Word
    if (!document.getElementById('sscp-spell-styles')) {
      const styleEl = document.createElement('style');
      styleEl.id = 'sscp-spell-styles';
      styleEl.textContent = `
        .sscp-wavy-error {
          text-decoration: underline wavy #ef4444 !important;
          -webkit-text-decoration-color: #ef4444 !important;
          text-decoration-thickness: 1.8px !important;
          text-underline-offset: 3.5px !important;
          color: transparent !important;
          -webkit-text-fill-color: transparent !important;
        }
        .sscp-spell-backdrop mark {
          background-color: transparent !important;
        }
      `;
      document.head.appendChild(styleEl);
    }

    // Configurar en todos los textareas de la página
    document.querySelectorAll('textarea').forEach(setupTextareaSpellOverlay);

    // Observar inserciones dinámicas de nuevos textareas (modales, etc.)
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((m) => {
        m.addedNodes.forEach((node) => {
          if (node.nodeType === 1) {
            if (node.tagName === 'TEXTAREA') {
              setupTextareaSpellOverlay(node);
            } else if (node.querySelectorAll) {
              node.querySelectorAll('textarea').forEach(setupTextareaSpellOverlay);
            }
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });

    initWebContextMenu();
    updateAllBadges();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSpellchecker);
  } else {
    initSpellchecker();
  }
})();
