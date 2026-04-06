// Immediately apply the theme to prevent FOUC (Flash of Unstyled Content)
(function() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = savedTheme === 'dark' || (!savedTheme && prefersDark);

    if (isDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
    }
})();

// Initialize toggle button when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const toggleBtns = document.querySelectorAll('.theme-toggle-btn');

    // Set initial button text/icon
    function updateBtnState() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        toggleBtns.forEach(btn => {
            btn.innerHTML = isDark ? '☀️ Light Mode' : '🌙 Dark Mode';
        });
    }

    updateBtnState();

    toggleBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const newTheme = isDark ? 'light' : 'dark';

            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateBtnState();
        });
    });

    // Listen for system theme changes if no preference is saved
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        if (!localStorage.getItem('theme')) {
            const newTheme = e.matches ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            updateBtnState();
        }
    });
});
