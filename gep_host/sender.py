import smtplib
from email.message import EmailMessage

# Create a new email message
msg = EmailMessage()
msg.set_content('This is the email body.')
msg['Subject'] = 'Test Email'
msg['From'] = 'sender@example.com'
msg['To'] = 'tuzesdanie@gmail.com'

# Connect to the local SMTP server
server = smtplib.SMTP('localhost')
server.send_message(msg)
server.quit()
