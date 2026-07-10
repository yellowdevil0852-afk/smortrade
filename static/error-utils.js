/**
 * SmorTrade Error Management Utility
 */
const ErrorHandler = {
    // 1. Core logger that routes errors based on environment
    log(context, error) {
        console.error(`[SmorTrade Error] Context: ${context} | Message:`, error.message || error);
    },

    // 2. Safe API parsing wrapper with fallbacks
    safeString(value, fallback = '$--.--') {
        return value !== undefined && value !== null ? value : fallback;
    },

    // 3. Safe numeric array conversion
    safeNumericArray(arr) {
        if (!Array.isArray(arr)) return [];
        return arr.map(p => {
            const parsed = parseFloat(p);
            return isNaN(parsed) ? 0 : parsed;
        });
    },

    // 4. Fallback UI feedback for the user (optional visual alert)
    notifyUser(message) {
        // You can link this to a temporary toast alert on the dashboard later
        console.warn(`[UI Notice]: ${message}`);
    }
};

// Make it globally accessible across your app templates
window.ErrorHandler = ErrorHandler;