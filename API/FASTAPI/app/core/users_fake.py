from app.core.security import hash_password

FAKE_USERS = {
    "admin": {
        "username": "admin",
        "password_hash": hash_password("admin123"),  # troque
        "role": "admin",
    }
}
