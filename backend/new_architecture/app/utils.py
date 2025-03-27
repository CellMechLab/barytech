
import string
import random

def generate_token(length=16):
    """Generates a unique token string with letters and numbers."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))