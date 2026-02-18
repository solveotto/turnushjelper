// Shift Classifier Module
// Single source of truth for shift type classification.
// Used by shift-colors.js and color-adjustment.js for consistent categorization.
//
// Classification rules (start + end time):
//   night-early : start before 06:00
//   morning     : start 06:00–07:59
//   midday      : start 08:00–11:59
//   afternoon   : start 12:00+ (kveldsvakt — evening shifts, including those ending shortly after midnight)
//   evening     : crosses midnight AND ends 02:00+ next day (nattevakt — true night shifts)
//
// NOTE: The Python equivalent lives in app/utils/shift_stats.py — keep in sync.

const SHIFT_TYPES = {
    NIGHT_EARLY: 'night-early',
    MORNING:     'morning',
    MIDDAY:      'midday',
    AFTERNOON:   'afternoon',
    EVENING:     'evening',
    DAY_OFF:     'day_off',
    HOLIDAY:     'h-dag'
};

// Boundaries used as fallback for shifts not caught by the start+end rules.
// Only applies to shifts starting before 12:00.
const START_TIME_BOUNDARIES = [
    { maxMinutes: 6 * 60,   type: SHIFT_TYPES.NIGHT_EARLY },
    { maxMinutes: 8 * 60,   type: SHIFT_TYPES.MORNING },
    { maxMinutes: 12 * 60,  type: SHIFT_TYPES.MIDDAY },
    { maxMinutes: 17 * 60,  type: SHIFT_TYPES.AFTERNOON },
    { maxMinutes: Infinity,  type: SHIFT_TYPES.EVENING }
];

// Threshold for distinguishing kveldsvakt from nattevakt (in minutes past midnight)
const NIGHT_END_THRESHOLD = 2 * 60; // 02:00

/**
 * Classify a shift based on start and end time strings.
 * @param {string} startTime - "HH:MM" format
 * @param {string} endTime   - "HH:MM" format
 * @returns {string} One of the SHIFT_TYPES values
 */
function classifyShift(startTime, endTime) {
    const [startH, startM] = startTime.split(':').map(Number);
    const [endH, endM] = endTime.split(':').map(Number);
    const startTotal = startH * 60 + startM;
    const endTotal = endH * 60 + endM;

    const crossesMidnight = endTotal < startTotal;

    // Night shift (nattevakt): crosses midnight AND ends deep into next day (02:00+)
    if (crossesMidnight && endTotal >= NIGHT_END_THRESHOLD) {
        return SHIFT_TYPES.EVENING;
    }

    // Evening shift (kveldsvakt): starts 12:00+ and ends same day,
    // or crosses midnight but ends before 02:00
    if (startTotal >= 12 * 60 && (crossesMidnight || endTotal > startTotal)) {
        return SHIFT_TYPES.AFTERNOON;
    }

    // Fallback: use start-time-only boundaries (morning/midday/etc.)
    for (const { maxMinutes, type } of START_TIME_BOUNDARIES) {
        if (startTotal < maxMinutes) {
            return type;
        }
    }

    return SHIFT_TYPES.EVENING;
}

/**
 * Parse a time-text cell and return the shift type.
 * Handles day-off codes and holiday markers.
 * @param {string} timeText    - Full cell text, e.g. "06:30 - 14:30" or "XX"
 * @param {string} customText  - The dagsverk/custom text, used to detect holidays
 * @returns {string|null} A SHIFT_TYPES value, or null if unrecognizable
 */
function classifyCell(timeText, customText) {
    const cleaned = timeText.replace(/\s+/g, ' ').trim();

    // Holiday check
    if (customText && customText.trim().endsWith('H')) {
        return SHIFT_TYPES.HOLIDAY;
    }

    const times = cleaned.split(' - ').map(t => t.trim());

    if (times.length > 1) {
        return classifyShift(times[0], times[1]);
    }

    // Day-off codes
    const dayOffCodes = ['X', 'O', 'T', ''];
    if (dayOffCodes.includes(times[0])) {
        return SHIFT_TYPES.DAY_OFF;
    }

    return null;
}

export { SHIFT_TYPES, START_TIME_BOUNDARIES, classifyShift, classifyCell };
