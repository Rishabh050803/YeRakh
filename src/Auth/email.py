import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.config import Config
import logging
import uuid
from sqlmodel.ext.asyncio.session import AsyncSession
from src.config import Config


class EmailSender:
    @staticmethod
    async def send_verification_email(email: str, token: str):
        """Send verification email to user"""
     
        try:
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
            with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
                server.starttls()
                server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
                server.send_message(message)
                
            return True
        except Exception as e:
            return False
        

    @staticmethod
    async def alert_user_about_token_reuse(user,user_id: uuid.UUID, session: AsyncSession):
        """Alert user about possible token theft via refresh token reuse"""
        try:
            if not user:
                logging.warning(f"Token reuse alert skipped: No user found for ID {user_id}")
                return False

            # Create the email message
            message = MIMEMultipart()
            message["From"] = Config.EMAIL_FROM
            message["To"] = user.email
            message["Subject"] = "⚠️ Security Alert: Suspicious Login Activity"

            # Email body
            body = f"""
            <html>
            <body>
                <h2>Security Alert</h2>
                <p>Hi {user.first_name or 'User'},</p>
                <p>We detected that one of your login tokens was used more than once, which may indicate someone else is trying to access your account.</p>
                <p>If this was not you, we recommend the following:</p>
                <ul>
                    <li>Change your password immediately.</li>
                    <li>Revoke other sessions by logging out and back in.</li>
                    <li>Enable two-factor authentication (2FA) if supported.</li>
                </ul>
                <p>Stay safe,</p>
                <p><b>YeRakh Security Team</b></p>
            </body>
            </html>
            """

            message.attach(MIMEText(body, "html"))

            # Send the email
            with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
                server.starttls()
                server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
                server.send_message(message)

            logging.info(f"Security alert email successfully sent to {user.email}")
            return True

        except Exception as e:
            logging.error(f"Failed to send token reuse alert to user {user_id}: {e}")
            return False