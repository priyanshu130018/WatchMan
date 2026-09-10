import secrets

# Generates a 32-byte secure token
jwt_secret = secrets.token_hex(32)

print(jwt_secret)
