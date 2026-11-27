// Typesets the math the markdown transpiler marked (.md-math: $..$, $$..$$, \(..\), \[..\], ```latex blocks) with KaTeX from /static/js/katex (base.html and public_shell.html load it).
// Runs on the first page and on every piece of content htmx swaps in later (wiki pages, chat replies, tabs). A formula KaTeX cannot read is shown as its source in red.
// Only marked elements are typeset: a page-wide $...$ search would also turn amounts like "$5 and $10" (Finance, Books) into math.
(function () {
    function run(root) {
        if (!root.querySelectorAll) return;
        var els = root.querySelectorAll('.md-math:not([data-done])');
        if (!els.length) return;
        if (!window.katex) return setTimeout(function () { run(root); }, 100);   // the deferred katex script is still loading
        els.forEach(function (el) { el.dataset.done = 1; katex.render(el.textContent, el, {displayMode: el.dataset.display === '1', throwOnError: false}); });
    }
    if (window.htmx) htmx.onLoad(run); else document.addEventListener('DOMContentLoaded', function () { run(document.body); });   // pages without htmx (the public wiki) are typeset once
})();
