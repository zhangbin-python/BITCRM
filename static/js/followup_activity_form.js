(function () {
    'use strict';

    function localTodayIso() {
        const now = new Date();
        const offset = now.getTimezoneOffset() * 60000;
        return new Date(now.getTime() - offset).toISOString().slice(0, 10);
    }

    function setRequired(container, selector, required) {
        container.querySelectorAll(selector).forEach(function (input) {
            input.required = required;
        });
    }

    function updateSection(formRoot, prefix) {
        const text = formRoot.querySelector('[data-activity-text="' + prefix + '"]');
        const type = formRoot.querySelector('[data-activity-type="' + prefix + '"]');
        if (!text || !type) return;

        const hasText = text.value.trim().length > 0;
        const selectedType = type.value;
        const isRemote = selectedType === 'Remote Engagement';
        const remoteFields = formRoot.querySelector('[data-activity-fields="' + prefix + '-remote"]');
        const requiredMark = type.closest('.col-md-6')?.querySelector('.activity-required-mark');

        type.required = hasText;
        if (requiredMark) requiredMark.classList.toggle('d-none', !hasText);
        if (remoteFields) remoteFields.classList.toggle('d-none', !(hasText && isRemote));

        setRequired(formRoot, '[data-activity-fields="' + prefix + '-remote"] input', hasText && isRemote);
    }

    function updateExistingVisit(root) {
        const select = root.querySelector('[data-existing-visit-select]');
        const notes = root.querySelector('[data-existing-visit-notes]');
        if (!select || !notes) return;
        notes.required = Boolean(select.value);
        notes.closest('.card')?.classList.toggle('border-danger', Boolean(select.value) && !notes.value.trim());
    }

    window.initializeFollowupActivityForms = function (container) {
        const scope = container || document;
        const roots = [];
        if (scope.matches && scope.matches('[data-followup-activity-form]')) roots.push(scope);
        scope.querySelectorAll('[data-followup-activity-form]').forEach(function (root) { roots.push(root); });

        roots.forEach(function (root) {
            // Reapply defaults every time a modal is opened. A form.reset() clears
            // dynamically assigned values even though the listeners remain initialized.
            root.querySelectorAll('[data-default-today]').forEach(function (input) {
                if (!input.value) input.value = localTodayIso();
            });
            if (root.dataset.followupActivityInitialized === 'true') {
                updateSection(root, 'followup');
                updateSection(root, 'todo');
                updateExistingVisit(root);
                return;
            }
            root.dataset.followupActivityInitialized = 'true';
            ['followup', 'todo'].forEach(function (prefix) {
                const text = root.querySelector('[data-activity-text="' + prefix + '"]');
                const type = root.querySelector('[data-activity-type="' + prefix + '"]');
                if (text) text.addEventListener('input', function () { updateSection(root, prefix); });
                if (type) type.addEventListener('change', function () { updateSection(root, prefix); });
                updateSection(root, prefix);
            });
            const visitSelect = root.querySelector('[data-existing-visit-select]');
            const visitNotes = root.querySelector('[data-existing-visit-notes]');
            if (visitSelect) visitSelect.addEventListener('change', function () { updateExistingVisit(root); });
            if (visitNotes) visitNotes.addEventListener('input', function () { updateExistingVisit(root); });
            updateExistingVisit(root);
        });
    };

    document.addEventListener('DOMContentLoaded', function () {
        window.initializeFollowupActivityForms(document);
    });
})();
