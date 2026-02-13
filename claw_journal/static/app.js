// Minimal JS for Claw Journal UI
document.addEventListener('DOMContentLoaded', function() {
    // Auto-focus search input on search page
    const searchInput = document.querySelector('input[type="search"]');
    if (searchInput && !searchInput.value) {
        searchInput.focus();
    }
});
