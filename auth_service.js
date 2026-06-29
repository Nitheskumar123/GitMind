// auth_service.js
// We are migrating away from legacy session cookies.
// All authentication now exclusively uses JWT tokens passed in the Authorization header.

function authenticateUser(req) {
    const token = req.headers.authorization;
    if (!token || !token.startsWith("Bearer ")) {
        throw new Error("Unauthorized: Missing JWT Token");
    }
    return verifyJWT(token);
}
