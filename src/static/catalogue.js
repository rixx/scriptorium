// Run once the page is loaded
// Use tom-select for all <select> elements
document.addEventListener('DOMContentLoaded', () => {
    for (name of ['tags']) {
        document.querySelectorAll(`select#id_${name}`).forEach(select => {
            new TomSelect(select, {
                allowEmptyOption: true,
                closeAfterSelect: true,
            });
        })
    }
    // if #wizard-select exists, add images
});
