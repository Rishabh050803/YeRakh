import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.config import Config
import logging

class EmailSender:
    @staticmethod
    async def send_verification_email(email: str, token: str):
        """Send verification email to user"""
        print("Config.APP_URL:", Config.APP_URL)
        print("Config.SMTP_SERVER:", Config.SMTP_SERVER)
        print("Config.SMTP_PORT:", Config.SMTP_PORT)
        print("Config.SMTP_USERNAME:", Config.SMTP_USERNAME)
        print("Config.SMTP_PASSWORD:", Config.SMTP_PASSWORD)
        print("Config.EMAIL_FROM:", Config.EMAIL_FROM)
        try:
            print(f"Attempting to send verification email to {email}")
            # Create verification URL
            verification_url = f"{Config.APP_URL}/verify-email?token={token}"
            
            # Create email
            message = MIMEMultipart()
            message["From"] = Config.EMAIL_FROM
            message["To"] = email
            message["Subject"] = "Verify Your Email Address"
            
            # Email body
            body = f"""
            <html>
            <body>
                <h2>Welcome to YeRakh!</h2>
                <p>Please click the link below to verify your email address:</p>
                <p><a href="{verification_url}">Verify Email</a></p>
            </body>
            </html>
            """
            
            # Attach HTML content
            message.attach(MIMEText(body, "html"))
            
            # Send email
            print(f"Connecting to SMTP server {Config.SMTP_SERVER}:{Config.SMTP_PORT}")
            with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
                server.starttls()
                server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
                server.send_message(message)
                
            print(f"Verification email successfully sent to {email}")
            return True
        except Exception as e:
            print(f"Failed to send verification email: {e}")
            return False