const updateCatalogueLink = () => {
    const link = document.querySelector('nav #catalogue-link')
    // Intercept clicks, show a search input instead, and focus it
    link.addEventListener('click', (e) => {
        e.preventDefault()
        // Hide main nav, show search input
        const nav = document.querySelector('nav#nav-links')
        nav.classList.add('hidden')
        const input = document.querySelector('nav#catalogue-form')
        input.classList.remove('hidden')
        input.querySelector('input').focus()

        // But on blur, hide the input and show the nav again
        input.querySelector('input').addEventListener('blur', (e) => {
            nav.classList.toggle('hidden')
            input.classList.toggle('hidden')
        })
    })

}


document.addEventListener('DOMContentLoaded', updateCatalogueLink)
