// Run once the page is loaded
// Use tom-select for all <select> elements
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('select').forEach(select => {
        new TomSelect(select, {
            // allow empty option when original element is not required
            allowEmptyOption: !select.hasAttribute('required'),
        });
    })
    // if #wizard-select exists, add images
    if (document.getElementById('wizard-edition')) {
        // for each label, get the input value and prepend the image to the label
        document.querySelectorAll('#id_edition-edition_selection label').forEach(label => {
            const input = label.querySelector('input');
            const img = document.createElement('img');
            img.src = `https://covers.openlibrary.org/b/olid/${input.value}-S.jpg`;
            img.alt = input.value;
            label.prepend(img);
        })
    }
});
