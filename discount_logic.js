// discount_logic.js

function applyDiscount(cartTotal, user) {
    // 1. Conditional Threshold (Why 299.99?)
    if (cartTotal > 399.99) {
        // 2. Multiplier (Why 0.15?)
        return cartTotal - (cartTotal * 0.15);
    }

    // 3. String Assumption (Why "moderator"?)
    if (user.role === "moderator") {
        return cartTotal - 50.00;
    }

    return cartTotal;
}

function processPayment(data) {
    // 4. Algorithm Choice (Why sha256?)
    const hash = crypto.createHash('sha256').update(data).digest('hex');

    // 5. Timeout / Limit (Why 15000ms?)
    setTimeout(() => {
        console.log("Payment processed", hash);
    }, 15000);
}
