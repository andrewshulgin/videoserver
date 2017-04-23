import logging
import smtplib
from email.mime.text import MIMEText

from notifier import *


class SMTP(Notifier):
    def send(self, message, stream=None, status=None):
        if message is None:
            return
        server = self.config.get_smtp_server()
        port = self.config.get_smtp_port()
        login = self.config.get_smtp_login()
        password = self.config.get_smtp_password()
        subject = self.config.get_smtp_subject()
        recipient = self.config.get_smtp_recipient()
        security = self.config.get_smtp_security()
        if security != 'ssl' and security != 'starttls':
            security = None

        message = MIMEText(message)
        message['Subject'] = subject
        message['From'] = login
        message['To'] = recipient

        try:
            if security == 'starttls':
                with smtplib.SMTP(server, port) as smtp:
                    smtp.starttls()
                    smtp.login(login, password)
                    smtp.send_message(message)
            elif security == 'ssl':
                with smtplib.SMTP_SSL(server, port) as smtp:
                    smtp.login(login, password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(server, port) as smtp:
                    smtp.login(login, password)
                    smtp.send_message(message)
            logging.info('Sent Email successfully')
        except smtplib.SMTPException as e:
            logging.error('Failed to send Email: {}'.format(str(e)))
