// Run once the page is loaded
// Use tom-select for all <select> elements
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('select').forEach(select => {
        new TomSelect(select, {
            // allow empty option when original element is not required
            allowEmptyOption: !select.hasAttribute('required'),
        });
    })
});
