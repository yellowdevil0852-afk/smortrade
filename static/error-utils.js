/**
 * SmorTrade Error Management Utility
 */
const ErrorHandler = {
    log(context, error) {
        console.error(`[SmorTrade Error] Context: ${context} | Message:`, error.message || error);
    },

    safeString(value, fallback = '$--.--') {
        return value !== undefined && value !== null ? value : fallback;
    },

    safeNumericArray(arr) {
        if (!Array.isArray(arr)) return [];
        return arr.map(p => {
            const parsed = parseFloat(p);
            return isNaN(parsed) ? 0 : parsed;
        });
    },

    notifyUser(message) {
        const container = document.getElementById('toast-container');
        if (!container) {
            console.warn("Toast container element missing from layout.");
            return;
        }

        // Create the toast element box
        const toast = document.createElement('div');
        toast.className = 'trade-error-toast';
        
        // Inline styles to match your clean, minimalist beige/earth layout elements
        toast.style.cssText = `
            background-color: #fef2f2;
            color: #991b1b;
            border-left: 4px solid var(--negative-red, #ef4444);
            padding: 12px 16px;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
            font-size: 14px;
            font-weight: 500;
            min-width: 280px;
            max-width: 400px;
            opacity: 0;
            transform: translateX(50px);
            transition: transform 0.2s ease-out, opacity 0.2s ease-out;
        `;

        // Error message text content
        toast.innerHTML = `⚠️ &nbsp; ${message}`;

        container.appendChild(toast);

        // Animate incoming slide
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        });

        // Trigger exit and removal sequence
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(50px)';
            setTimeout(() => {
                toast.remove();
            }, 200);
        }, 4000);
    },

    // NEW: Trade Execution Portfolio Validation Engine
    validateOrder(action, ticker, quantityRequested, portfolioHoldings) {
        const qty = parseInt(quantityRequested);
        if (isNaN(qty) || qty <= 0) {
            this.notifyUser("Please enter a valid quantity greater than 0.");
            return false;
        }

        // Only enforce holdings restrictions on SELL actions
        if (action.toUpperCase() === 'SELL') {
            const sharesOwned = portfolioHoldings[ticker.toUpperCase()] || 0;

            // Error 1: Selling a stock not present in portfolio array
            if (sharesOwned === 0) {
                this.notifyUser(`You cannot sell ${ticker}. You do not own any shares of this asset.`);
                return false;
            }

            // Error 2: Selling an amount that exceeds actual holdings
            if (qty > sharesOwned) {
                this.notifyUser(`Insufficient shares. You are trying to sell ${qty} shares of ${ticker}, but you only hold ${sharesOwned}.`);
                return false;
            }
        }
        return true;
    }
};

window.ErrorHandler = ErrorHandler;