(function () {
    'use strict';

    const VISIT_TYPES = ['Customer Visit', 'DC Site Visit'];

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
        const isVisit = VISIT_TYPES.includes(selectedType);
        const isRemote = selectedType === 'Remote Engagement';
        const remoteFields = formRoot.querySelector('[data-activity-fields="' + prefix + '-remote"]');
        const visitFields = formRoot.querySelector('[data-activity-fields="' + prefix + '-visit"]');
        const requiredMark = type.closest('.col-md-6')?.querySelector('.activity-required-mark');

        type.required = hasText;
        if (requiredMark) requiredMark.classList.toggle('d-none', !hasText);
        if (remoteFields) remoteFields.classList.toggle('d-none', !(hasText && isRemote));
        if (visitFields) visitFields.classList.toggle('d-none', !(hasText && isVisit));

        setRequired(formRoot, '[data-activity-fields="' + prefix + '-remote"] input', hasText && isRemote);
        setRequired(
            formRoot,
            '[data-activity-fields="' + prefix + '-visit"] input[type="date"], [data-activity-fields="' + prefix + '-visit"] input[type="time"]',
            hasText && isVisit
        );
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
        });
    };

    document.addEventListener('DOMContentLoaded', function () {
        window.initializeFollowupActivityForms(document);
    });
})();
