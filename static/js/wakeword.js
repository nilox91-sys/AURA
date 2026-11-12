(function (root) {
    'use strict';
    function extractCommand(transcript, phrase) {
        const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const words = String(phrase).trim().split(/\s+/).filter(Boolean).map(escape);
        if (!words.length) return null;
        const pattern = new RegExp('(?:^|[^\\p{L}\\p{N}])(' + words.join('[\\s,.;:!?]+') + ')(?=$|[^\\p{L}\\p{N}])', 'iu');
        const match = pattern.exec(String(transcript));
        if (!match) return null;
        const end = match.index + match[0].length;
        return String(transcript).slice(end).replace(/^[\s,.;:!?]+/, '').trim();
    }
    const api = {extractCommand};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.AuraWake = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
