const updateCatalogueLink = () => {
    const link = document.querySelector('nav #catalogue-link')
    const nav = document.querySelector('nav#nav-links')
    const form = document.querySelector('nav#catalogue-form')
    const input = form.querySelector('input')
    // Intercept clicks, show a search input instead, and focus it
    link.addEventListener('click', (e) => {
        e.preventDefault()
        // Hide main nav, show search input
        nav.classList.add('hidden')
        form.classList.remove('hidden')
        input.focus()
    })
    // But on blur, hide the input and show the nav again
    input.addEventListener('blur', () => {
        nav.classList.remove('hidden')
        form.classList.add('hidden')
    })

}


document.addEventListener('DOMContentLoaded', updateCatalogueLink)

document.addEventListener('submit', (e) => {
    const message = e.target.dataset.confirm
    if (message && !window.confirm(message)) e.preventDefault()
})
