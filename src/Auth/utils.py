from passlib.context import CryptContext
from datetime import timedelta,datetime
from src.config import Config
import  jwt
import uuid
import logging
from google.oauth2 import id_token
from google.auth.transport import requests

poassword_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_EXPIRE_MINUTES = Config.ACCESS_TOKEN_EXPIRE_MINUTES

def generate_password_hash(password: str) -> str:
    """Generate a hashed password."""
    return poassword_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return poassword_context.verify(plain_password, hashed_password)


def create_access_token(user_data:dict, expiry: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), refresh:bool = False) -> str:
    """Create a JWT access token."""
    # Convert to Unix timestamp for JWT standard
    expiration_time = datetime.now() + expiry
    expiration_timestamp = int(expiration_time.timestamp())
    
    payload = {
        "sub": user_data.get("sub", ""),
        "email": user_data.get("email", ""),
        "exp": expiration_timestamp,  # Using standard Unix timestamp
        "jti": str(uuid.uuid4())
    }
    
    print(f"Creating access token that expires at: {expiration_time}")
    token = jwt.encode(
        payload = payload,
        key = Config.JWT_SECRET,
        algorithm = Config.JWT_ALGORITHM
    )

    return token


def decode_access_token(token: str) -> dict:
    """Decode a JWT access token."""
    try:
        payload = jwt.decode(
            jwt = token,
            key = Config.JWT_SECRET,
            algorithms = [Config.JWT_ALGORITHM]
        )
        print("paylod ---->  ",payload)
        return {"status": "valid", "payload": payload}
    except jwt.ExpiredSignatureError:
        print("Token has expired")
        return {"status": "expired", "payload": {}}
    except jwt.InvalidTokenError:
        print("Invalid token")
        return {"status": "invalid", "payload": {}}
    except Exception as e:
        print(f"An error occurred while decoding the token: {e}")
        return {"status": "error", "payload": {}}
    


def create_verification_token(user_id: uuid.UUID) -> str:
    """
    Generate a verification token which is sent to email with a link
    """
    payload = {
        "sub": str(user_id),
        "type": "email_verification",
        "exp": datetime.now() + timedelta(hours=24)
    }
    token = jwt.encode(
        payload=payload,
        key=Config.JWT_SECRET,
        algorithm=Config.JWT_ALGORITHM
    )
    return token

def verify_token(token: str) -> dict:
    """Verify a token (verification or password reset)"""
    try:
        payload = jwt.decode(
            jwt=token,
            key=Config.JWT_SECRET,
            algorithms=[Config.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        logging.error("Token has expired")
        return {}
    except jwt.InvalidTokenError:
        logging.error("Invalid token")
        return {}
    except Exception as e:
        logging.error(f"An error occurred while verifying the token: {e}")
        return {}

async def verify_google_token(token: str) -> dict:
    """
    Verify a Google ID token and return user information
    """
    try:
        # Specify the CLIENT_ID of your app
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), Config.GOOGLE_CLIENT_ID)
        
        # Verify the issuer
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
            
        # ID token is valid
        return {
            "email": idinfo['email'],
            "first_name": idinfo.get('given_name', ''),
            "last_name": idinfo.get('family_name', ''),
            "provider_id": idinfo['sub'],  # Google user ID
            "picture": idinfo.get('picture', '')
        }
    except ValueError as e:
        # Invalid token
        logging.error(f"Invalid Google token: {e}")
        return {}
