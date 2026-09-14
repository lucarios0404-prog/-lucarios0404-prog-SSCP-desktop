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
});
