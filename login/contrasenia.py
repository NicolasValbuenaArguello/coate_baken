import bcrypt

password = "admin123".encode("utf-8")

# generar hash
hashed = bcrypt.hashpw(password, bcrypt.gensalt())

print(hashed.decode())

"""
UPDATE usuarios
SET password_hash = '$2b$12$FE15whjzDoCcoroKuhSi6.gyayl6sXAjEr8rxTmqNckuijIk1N4vi'
WHERE usuario = 'admin';
"""