/* No API endpoints or server credentials are exposed to the browser. */
document.querySelectorAll('.lab-air-action').forEach(function (form) {
    form.addEventListener('submit', function (event) {
        if (form.dataset.submitting) { event.preventDefault(); return; }
        form.dataset.submitting = '1';
        form.setAttribute('aria-busy', 'true');
        var action = form.querySelector('[name="lab_action"]').value;
        form.querySelectorAll('button[type="submit"]').forEach(function (button) {
            button.disabled = true;
            button.textContent = action === 'propose' ? 'Generating proposal…' :
                (action === 'apply' ? 'Applying approved changes…' : 'Processing…');
        });
    });
});

// LAB_AI_REVIEW_POLISH_UI
(() => {
    'use strict';

    const translations = new Map([
        ['AI Content Review', 'Weryfikacja treści AI'],
        ['Human-in-the-loop product content workflow', 'Treści produktowe AI z ręczną akceptacją'],
        ['BIURKO / LAB · AUTOMATION', 'BIURKO / LAB · AUTOMATYZACJA'],

        ['STAGE 4', 'ETAP 4'],

        ['Products', 'Produkty'],
        ['Selected proposal', 'Wybrana propozycja'],
        ['Provider', 'Dostawca AI'],
        ['Backend', 'Backend'],
        ['CONNECTED', 'POŁĄCZONY'],

        ['Generate', 'Generowanie'],
        ['Review', 'Weryfikacja'],
        ['Plan', 'PLAN'],
        ['Apply', 'Zastosowanie'],

        ['AI proposes. Human approves. WooCommerce applies.',
         'AI proponuje. Człowiek zatwierdza. WooCommerce wprowadza zmiany.'],

        ['Product', 'Produkt'],
        ['Open review', 'Otwórz weryfikację'],
        ['Local llama.cpp', 'Lokalny llama.cpp'],
        ['Generate AI Proposal', 'Wygeneruj propozycję AI'],
        ['Generating proposal…', 'Generowanie propozycji…'],
        ['Generating proposal...', 'Generowanie propozycji…'],

        ['Content review', 'Weryfikacja treści'],
        ['CURRENT SOURCE', 'OBECNA TREŚĆ'],
        ['Current source', 'Obecna treść'],
        ['AI PROPOSAL', 'PROPOZYCJA AI'],
        ['AI Proposal', 'Propozycja AI'],

        ['Description', 'Opis'],
        ['Short description', 'Krótki opis'],
        ['Image ALT', 'ALT obrazu'],
        ['Image / ALT', 'Obraz / ALT'],

        ['PROPOSED', 'PROPONOWANE'],
        ['UNCHANGED', 'BEZ ZMIAN'],
        ['PENDING', 'DO WERYFIKACJI'],
        ['APPROVED', 'ZATWIERDZONE'],
        ['REJECTED', 'ODRZUCONE'],
        ['LOCKED', 'ZABLOKOWANE'],

        ['Reject', 'Odrzuć'],
        ['Approve', 'Zatwierdź'],

        ['Verify every factual claim. Generating again replaces this proposal and resets review.',
         'Zweryfikuj wszystkie informacje. Ponowne wygenerowanie zastąpi tę propozycję i wyzeruje jej zatwierdzenie.'],

        ['Preview WooCommerce PLAN', 'Podejrzyj PLAN WooCommerce'],

        ['AI BOUNDARY', 'ZAKRES AI'],
        ['Protected product fields', 'Chronione pola produktu'],
        ['Name', 'Nazwa'],
        ['Price', 'Cena'],
        ['Stock', 'Stan magazynowy'],
        ['Status', 'Status'],

        ['AI cannot modify these fields.',
         'AI nie może modyfikować tych pól.'],

        ['The full catalog planner can reconcile source-owned fields. LOCKED describes the AI boundary, not a content-only synchronization mode. Inspect all changes before APPLY.',
         'Pełny plan synchronizacji katalogu może uwzględnić również pola zarządzane przez źródło danych. ZABLOKOWANE określa wyłącznie zakres działania AI. Przed zastosowaniem zmian sprawdź cały PLAN.'],

        ['Review safeguards', 'Zabezpieczenia weryfikacji'],
        ['Approval binds exact content', 'Zatwierdzenie jest powiązane z dokładną treścią'],
        ['Changed source blocks APPLY', 'Zmiana danych źródłowych blokuje zastosowanie zmian'],
        ['Existing store stock is preserved', 'Stan magazynowy istniejących produktów pozostaje po stronie WooCommerce'],
        ['Every write needs a separate action', 'Każdy zapis wymaga osobnej akcji'],

        ['WooCommerce PLAN', 'PLAN WooCommerce'],
        ['READ ONLY', 'TYLKO ODCZYT'],

        ['CREATE', 'UTWORZENIE'],
        ['UPDATE', 'AKTUALIZACJA'],
        ['SKIP', 'BEZ ZMIAN'],
        ['ERROR', 'BŁĘDY'],

        ['ACTION', 'AKCJA'],
        ['Action', 'Akcja'],
        ['CHANGES', 'ZMIANY'],
        ['Changes', 'Zmiany'],

        ['Inspect all planned field values',
         'Sprawdź wszystkie zaplanowane wartości pól'],

        ['EXPLICIT WRITE', 'JAWNY ZAPIS'],
        ['NO WRITE NEEDED', 'BRAK ZAPISU'],
        ['No changes to apply', 'Brak zmian do zastosowania'],
        ['The current store already matches the approved proposal and catalog plan.',
         'Aktualny sklep jest już zgodny z zatwierdzoną propozycją i PLAN-em katalogu.'],
        ['No WooCommerce write is needed.',
         'Nie jest wymagany żaden zapis do WooCommerce.'],
        ['Ready to apply', 'Gotowe do zastosowania'],

        ['The approved content passed validation and WooCommerce preflight.',
         'Zatwierdzona treść przeszła walidację i kontrolę wstępną WooCommerce.'],

        ['Applying will recheck the source and write the newly planned changes to the local store. The previous PLAN is not a frozen transaction.',
         'Zastosowanie ponownie sprawdzi źródło i zapisze nowo zaplanowane zmiany w lokalnym sklepie. Poprzedni PLAN nie jest zamrożoną transakcją.'],

        ['Apply approved changes', 'Zastosuj zatwierdzone zmiany'],

        ['Review every row, including possible source-owned field updates. Writes are not transactional.',
         'Sprawdź każdy wiersz, w tym możliwe aktualizacje pól zarządzanych przez źródło. Zapisy nie są transakcyjne.'],

        ['Applied successfully', 'Zmiany zastosowano pomyślnie'],

        ['Backend Connected', 'Backend połączony'],
        ['Backend Unavailable', 'Backend niedostępny']
    ]);

    function getTranslation(value) {
        if (!value) {
            return null;
        }

        if (translations.has(value)) {
            return translations.get(value);
        }

        const requestMatch = value.match(/^Requests:\s*(.*)$/);
        if (requestMatch) {
            return 'Żądania: ' + requestMatch[1];
        }

        const fieldsMatch = value.match(/^(\d+)\s+fields?$/);
        if (fieldsMatch) {
            const count = Number(fieldsMatch[1]);
            let word = 'pól';

            if (count === 1) {
                word = 'pole';
            } else if (
                count % 10 >= 2 &&
                count % 10 <= 4 &&
                (count % 100 < 12 || count % 100 > 14)
            ) {
                word = 'pola';
            }

            return String(count) + ' ' + word;
        }

        return null;
    }

    function translateTextNode(node) {
        const original = node.nodeValue;
        const trimmed = original.trim();

        if (!trimmed) {
            return;
        }

        const translated = getTranslation(trimmed);

        if (translated && translated !== trimmed) {
            node.nodeValue = original.replace(trimmed, translated);
        }
    }

    function translateAttributes(element) {
        for (const attribute of ['placeholder', 'title', 'aria-label']) {
            if (!element.hasAttribute(attribute)) {
                continue;
            }

            const value = element.getAttribute(attribute);
            const translated = getTranslation(value);

            if (translated) {
                element.setAttribute(attribute, translated);
            }
        }
    }

    function translateTree(root) {
        if (!root) {
            return;
        }

        if (root.nodeType === Node.TEXT_NODE) {
            translateTextNode(root);
            return;
        }

        if (
            root.nodeType !== Node.ELEMENT_NODE &&
            root.nodeType !== Node.DOCUMENT_NODE
        ) {
            return;
        }

        if (root.nodeType === Node.ELEMENT_NODE) {
            translateAttributes(root);
        }

        const walker = document.createTreeWalker(
            root,
            NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT
        );

        let node;

        while ((node = walker.nextNode())) {
            if (node.nodeType === Node.TEXT_NODE) {
                translateTextNode(node);
            } else {
                translateAttributes(node);
            }
        }
    }

    function startPolishUI() {
        translateTree(document.body);

        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                if (mutation.type === 'characterData') {
                    translateTextNode(mutation.target);
                }

                for (const node of mutation.addedNodes) {
                    translateTree(node);
                }
            }
        });

        observer.observe(document.body, {
            subtree: true,
            childList: true,
            characterData: true
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener(
            'DOMContentLoaded',
            startPolishUI,
            { once: true }
        );
    } else {
        startPolishUI();
    }
})();
