/**
 * SSCP Desktop - Global JavaScript & Dark/Light Mode Switcher
 */

function syncThemeUI() {
    const isDark = document.documentElement.classList.contains('dark');
    const sunIcon = document.getElementById('theme-icon-sun');
    const moonIcon = document.getElementById('theme-icon-moon');
    const label = document.getElementById('theme-label');
    const btn = document.getElementById('theme-toggle-btn');

    if (sunIcon && moonIcon) {
        if (isDark) {
            sunIcon.classList.add('hidden');
            moonIcon.classList.remove('hidden');
        } else {
            sunIcon.classList.remove('hidden');
            moonIcon.classList.add('hidden');
        }
    }

    if (label) {
        label.textContent = isDark ? 'Oscuro' : 'Claro';
    }

    if (btn) {
        btn.setAttribute('title', isDark ? 'Cambiar a Modo Claro' : 'Cambiar a Modo Oscuro');
    }
}

function toggleDarkMode() {
    // Añadir transición suave
    document.documentElement.classList.add('theme-transition');

    const isCurrentlyDark = document.documentElement.classList.contains('dark');
    if (isCurrentlyDark) {
        document.documentElement.classList.remove('dark');
        localStorage.setItem('theme', 'light');
    } else {
        document.documentElement.classList.add('dark');
        localStorage.setItem('theme', 'dark');
    }

    syncThemeUI();

    setTimeout(() => {
        document.documentElement.classList.remove('theme-transition');
    }, 250);
}

// Inicializar al cargar la página
document.addEventListener('DOMContentLoaded', () => {
    syncThemeUI();
    // Auto-inicializar buscadores de pacientes que tengan la clase .patient-live-search-auto
    document.querySelectorAll('.patient-live-search-container').forEach(container => {
        initPatientLiveSearch({
            container: container,
            input: container.querySelector('.patient-search-input'),
            select: container.querySelector('.patient-target-select'),
            dropdown: container.querySelector('.patient-search-dropdown'),
            results: container.querySelector('.patient-search-results'),
            clearBtn: container.querySelector('.patient-search-clear')
        });
    });
});

/**
 * Buscador en Vivo de Pacientes con Autocompletado (Live Patient Search).
 * Permite buscar al escribir por Nombre, Apellidos, Cédula o Teléfono.
 * Se sincroniza bidireccionalmente con el <select> original para mantener
 * compatibilidad total con validaciones y envíos de formularios.
 */
function initPatientLiveSearch(config) {
    if (!config) return;
    const input = typeof config.input === 'string' ? document.getElementById(config.input) : config.input;
    const select = typeof config.select === 'string' ? document.getElementById(config.select) : config.select;
    const dropdown = typeof config.dropdown === 'string' ? document.getElementById(config.dropdown) : config.dropdown;
    const resultsContainer = typeof config.results === 'string' ? document.getElementById(config.results) : config.results;
    const clearBtn = typeof config.clearBtn === 'string' ? document.getElementById(config.clearBtn) : config.clearBtn;
    const onSelect = config.onSelect || null;

    if (!input || !select) return;

    let timer = null;
    let selectedIndex = -1;
    let currentPatients = [];

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Inicializar texto inicial si el select ya tiene un paciente preseleccionado
    function syncInitialValue() {
        if (select.value && select.selectedIndex >= 0) {
            const opt = select.options[select.selectedIndex];
            if (opt && opt.value) {
                const doc = opt.getAttribute('data-doc') || '';
                const name = opt.getAttribute('data-name') || opt.textContent.trim().split('(')[0].trim();
                input.value = name + (doc && doc !== 'Sin DNI' && doc !== 'N/D' ? ` (Cédula: ${doc})` : '');
                if (clearBtn) clearBtn.classList.remove('hidden');
            }
        }
    }
    syncInitialValue();

    async function doSearch(q) {
        if (!q || q.length < 1) {
            if (dropdown) dropdown.classList.add('hidden');
            return;
        }
        try {
            const res = await fetch(`/patients/autocomplete?q=${encodeURIComponent(q)}&limit=12`);
            if (!res.ok) return;
            const data = await res.json();
            currentPatients = data || [];
            selectedIndex = -1;
            renderResults(currentPatients, q);
        } catch (e) {
            console.error('Error buscando pacientes:', e);
        }
    }

    function renderResults(patients, query) {
        if (!resultsContainer || !dropdown) return;
        resultsContainer.innerHTML = '';

        if (!patients || patients.length === 0) {
            resultsContainer.innerHTML = `
                <div class="p-3 text-center text-xs text-slate-500">
                    <i class="fas fa-user-slash text-slate-300 text-lg mb-1 block"></i>
                    No se encontraron pacientes para "<strong>${escapeHtml(query)}</strong>"
                </div>
            `;
            dropdown.classList.remove('hidden');
            return;
        }

        patients.forEach((p, idx) => {
            const row = document.createElement('div');
            row.className = "px-3.5 py-2.5 hover:bg-teal-50 cursor-pointer rounded-xl transition-all flex items-center justify-between group border border-transparent hover:border-teal-100";
            row.dataset.index = idx;

            const initials = ((p.first_name ? p.first_name[0] : '') + (p.last_name ? p.last_name[0] : '')).toUpperCase();
            const ageBadge = p.age ? `<span class="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-medium">${p.age} años</span>` : '';
            const allergyBadge = (p.allergies && p.allergies.trim()) ? `<span class="text-[10px] bg-rose-50 text-rose-700 border border-rose-200 px-1.5 py-0.5 rounded font-bold"><i class="fas fa-triangle-exclamation mr-0.5"></i> Alergia: ${escapeHtml(p.allergies)}</span>` : '';
            const insuranceBadge = p.insurance_name ? `<span class="text-slate-600 font-medium">${escapeHtml(p.insurance_name)}</span>` : '';
            const phoneText = p.phone ? `<span class="text-slate-400">&bull;</span> <span class="text-slate-600 font-mono">${escapeHtml(p.phone)}</span>` : '';
            const docText = p.document_id ? `<strong class="font-mono text-slate-800 font-bold">${escapeHtml(p.document_id)}</strong>` : '<span class="text-slate-400">Sin cédula</span>';

            row.innerHTML = `
                <div class="flex-1 min-w-0 pr-3">
                    <div class="flex items-center space-x-2">
                        <span class="w-6 h-6 rounded-full bg-teal-100 text-teal-800 flex items-center justify-center font-bold text-[10px] shrink-0">
                            ${initials || 'P'}
                        </span>
                        <span class="text-xs font-bold text-slate-900 group-hover:text-teal-700 truncate">${escapeHtml(p.name)}</span>
                        ${ageBadge}
                        ${allergyBadge}
                    </div>
                    <div class="mt-1 flex items-center space-x-2 text-[11px] text-slate-500">
                        <span>Cédula: ${docText}</span>
                        ${phoneText}
                        ${insuranceBadge ? `<span class="text-slate-400">&bull;</span> ${insuranceBadge}` : ''}
                    </div>
                </div>
                <button type="button" class="text-xs text-teal-600 opacity-0 group-hover:opacity-100 font-bold px-2.5 py-1 rounded-lg bg-white shadow-2xs shrink-0 border border-teal-200 transition-opacity">
                    Seleccionar &rarr;
                </button>
            `;

            row.addEventListener('click', () => {
                selectPatient(p);
            });

            resultsContainer.appendChild(row);
        });

        dropdown.classList.remove('hidden');
    }

    function selectPatient(p) {
        let opt = select.querySelector(`option[value="${p.id}"]`);
        if (!opt) {
            opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = `${p.name} (${p.document_id || 'Sin Cédula'})`;
            select.appendChild(opt);
        }
        opt.setAttribute('data-name', p.name);
        opt.setAttribute('data-doc', p.document_id || '');
        opt.setAttribute('data-age', p.age || '');
        opt.setAttribute('data-gender', p.gender || '');
        opt.setAttribute('data-phone', p.phone || '');
        opt.setAttribute('data-insurance', p.insurance_name || '');
        opt.setAttribute('data-insurance-num', p.insurance_number || '');
        opt.setAttribute('data-allergies', p.allergies || '');

        select.value = p.id;

        input.value = `${p.name} (Cédula: ${p.document_id || 'Sin Cédula'})`;
        if (clearBtn) clearBtn.classList.remove('hidden');
        if (dropdown) dropdown.classList.add('hidden');

        select.dispatchEvent(new Event('change', { bubbles: true }));

        if (typeof onSelect === 'function') {
            onSelect(p, opt);
        }
    }

    input.addEventListener('input', function() {
        const val = this.value.trim();
        if (clearBtn) clearBtn.classList.toggle('hidden', !val);

        clearTimeout(timer);
        if (val.length >= 1) {
            timer = setTimeout(() => doSearch(val), 180);
        } else {
            if (dropdown) dropdown.classList.add('hidden');
            select.value = '';
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });

    input.addEventListener('focus', function() {
        const val = this.value.trim();
        if (val.length >= 1 && currentPatients.length > 0) {
            renderResults(currentPatients, val);
        }
    });

    input.addEventListener('keydown', function(e) {
        if (!dropdown || dropdown.classList.contains('hidden') || currentPatients.length === 0) return;

        const items = resultsContainer.querySelectorAll('[data-index]');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = (selectedIndex + 1) % items.length;
            highlightItem(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = (selectedIndex - 1 + items.length) % items.length;
            highlightItem(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (selectedIndex >= 0 && selectedIndex < currentPatients.length) {
                selectPatient(currentPatients[selectedIndex]);
            }
        } else if (e.key === 'Escape') {
            dropdown.classList.add('hidden');
        }
    });

    function highlightItem(items) {
        items.forEach((it, idx) => {
            if (idx === selectedIndex) {
                it.classList.add('bg-teal-100', 'border-teal-300');
                it.scrollIntoView({ block: 'nearest' });
            } else {
                it.classList.remove('bg-teal-100', 'border-teal-300');
            }
        });
    }

    document.addEventListener('click', function(e) {
        if (dropdown && !input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.add('hidden');
        }
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            input.value = '';
            clearBtn.classList.add('hidden');
            if (dropdown) dropdown.classList.add('hidden');
            select.value = '';
            select.dispatchEvent(new Event('change', { bubbles: true }));
            input.focus();
        });
    }

    select.addEventListener('change', function() {
        if (this.value && this.selectedIndex >= 0) {
            const opt = this.options[this.selectedIndex];
            const doc = opt.getAttribute('data-doc') || '';
            const name = opt.getAttribute('data-name') || opt.textContent.trim().split('(')[0].trim();
            input.value = name + (doc && doc !== 'Sin DNI' && doc !== 'N/D' ? ` (Cédula: ${doc})` : '');
            if (clearBtn) clearBtn.classList.remove('hidden');
        } else if (!this.value) {
            input.value = '';
            if (clearBtn) clearBtn.classList.add('hidden');
        }
    });
}

/**
 * Auto-Sincronizador Silencioso de Buzón Relay (Doctor PC & Recepción)
 * Se ejecuta en segundo plano cada 30 segundos.
 * Descarga citas y llegadas de pacientes registradas por la secretaria en la tablet
 * sin interrumpir el trabajo del doctor.
 */
(function initRelayAutoSync() {
    let isSyncing = false;

    async function checkRelayUpdates() {
        if (isSyncing) return;
        isSyncing = true;
        try {
            const res = await fetch('/api/relay/sync-local', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (res.ok) {
                const data = await res.json();
                const totalMerged = (data.total_appointments_merged || 0) + (data.total_patients_merged || 0);
                if (totalMerged > 0) {
                    showRelayNotification(`Recepción: ${totalMerged} actualización(es) sincronizada(s) desde la tablet.`);
                    // Si estamos en la página del dashboard o citas, recargar datos en 2s para mostrar el nuevo turno
                    if (window.location.pathname === '/' || window.location.pathname.includes('/appointments') || window.location.pathname.includes('/dashboard')) {
                        setTimeout(() => {
                            window.location.reload();
                        }, 2500);
                    }
                }
            }
        } catch (e) {
            // Falla silenciosa si está desconectado
        } finally {
            isSyncing = false;
        }
    }

    function showRelayNotification(msg) {
        let toast = document.getElementById('relay-toast-notification');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'relay-toast-notification';
            toast.className = 'fixed bottom-5 right-5 z-50 flex items-center gap-2.5 px-4 py-3 bg-emerald-900 text-white text-xs font-semibold rounded-2xl shadow-2xl border border-emerald-500/40 transition-all duration-300 transform translate-y-12 opacity-0';
            document.body.appendChild(toast);
        }
        toast.innerHTML = `<span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span><span>${msg}</span>`;
        toast.classList.remove('translate-y-12', 'opacity-0');
        setTimeout(() => {
            toast.classList.add('translate-y-12', 'opacity-0');
        }, 4500);
    }

    // Iniciar 3 segundos después de cargar la página, luego verificar cada 30 segundos
    window.addEventListener('load', () => {
        setTimeout(checkRelayUpdates, 3000);
        setInterval(checkRelayUpdates, 30000);
    });
})();


