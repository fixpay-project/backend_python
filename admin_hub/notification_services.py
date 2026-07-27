# Third-Party Library Imports
import requests

# Django Core Imports
from django.conf import settings
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives

def mobicomm_submit_sms(contact_no, code):
    # Prepare the SMS content
    message = f"{code} is your One-Time Password (OTP) for logging into Fixpay. This code is valid for the next 1 minute"

    # Replace the placeholders with actual values
    URL = "http://web.shreesms.net/API/SendSMS.aspx"
    sms_params = {
        'UserID': 'FIXPAY',
        'Password':'FIXPAY@123',
        'SMSType': 2,
        'SenderID':'FIXPAY',
        'Mobile': f"+91{contact_no}",
        'MsgText': message,
        'Entityid': '1701174488531252757',
        'Templateid': '1707174540345315232'
    }

    # Send the SMS using a GET request
    response = requests.get(URL, params=sms_params)
    return response


def mobicomm_submit_sms_register(contact_no, code):
    # Prepare the SMS content
    message = f"{code} is your One-Time Password (OTP) for logging into Fixpay. This code is valid for the next 1 minute"

    # Replace the placeholders with actual values
    URL = "http://web.shreesms.net/API/SendSMS.aspx"
    sms_params = {
        'UserID': 'FIXPAY',
        'Password':'FIXPAY@123',
        'SMSType': 2,
        'SenderID':'FIXPAY',
        'Mobile': f"+91{contact_no}",
        'MsgText': message,
        'Entityid': '1701174488531252757',
        'Templateid': '1707174540345315232'
    }

    # Send the SMS using a GET request
    response = requests.get(URL, params=sms_params)
    return response

# def mobicomm_submit_sms(contact_no, code):
#     # Prepare the SMS content
#     message = f"Your One Time Verification Code for SSEPL login is {code}. Please do not share it with anyone. Thank you, SSEPL."

#     # Replace the placeholders with actual values
#     sms_url = "https://mobicomm.dove-sms.com/submitsms.jsp"
#     sms_params = {
#         'user': 'TAPICASH',
#         'key': '66a1621a84XX',
#         'mobile': f"+91{contact_no}",
#         'message': message,
#         'senderid': 'TAPICL',
#         'accusage': '1',
#         'entityid': '1701172165114242200',
#         'tempid': '1707172206814737429'
#     }

#     # Send the SMS using a GET request
#     response = requests.get(sms_url, params=sms_params)

#     return response
# def mobicomm_submit_sms_register(contact_no, code):
#     # Prepare the SMS content
#     message = f"Your One Time Verification Code for SSEPL login is {code}. Please do not share it with anyone. Thank you, SSEPL."

#     # Replace the placeholders with actual values
#     sms_url = "https://mobicomm.dove-sms.com/submitsms.jsp"
#     sms_params = {
#         'user': 'TAPICASH',
#         'key': '66a1621a84XX',
#         'mobile': f"+91{contact_no}",
#         'message': message,
#         'senderid': 'TAPICL',
#         'accusage': '1',
#         'entityid': '1701172165114242200',
#         'tempid': '1707172206814737429'
#     }

#     # Send the SMS using a GET request
#     response = requests.post(sms_url, params=sms_params)

#     return response

# def send_email_otp(email, otp, role): #CHanges Foramat of OTP
#     # Prepare HTML content for email
#     subject = 'Verify Code for Email Verification'

#     # HTML content 
#     html_content = f"""
#             <html>
#             <head>
#                 <style>
#                     body {{
#                         font-family: Arial, sans-serif;
#                         background-color: #f4f4f4;
#                         padding: 20px;
#                     }}
#                     .container {{
#                         background-color: #ffffff;
#                         border-radius: 5px;
#                         padding: 20px;
#                         box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
#                         padding: 20px;
#                     }}
#                     p {{
#                         color: #555;
#                         line-height: 1.6;
#                     }}
#                     .otp {{
#                         font-size: 15px;
#                         font-weight: bold;
#                         color: #000000;
#                     }}
#                     .footer {{
#                         margin-top: 20px;
#                         font-size: 0.8em;
#                         color: #999;
#                         text-align: center;
#                     }}
#                 </style>
#             </head>
#             <body>
#                 <div class="container">
#                     <p>We hope this message finds you well!</p>
#                     <p>Your OTP for email verification is: <span class="otp">{otp}</span></p>
#                     <p>Please make sure to keep it confidential and do not share it with anyone.</p>
#                     <p>If you did not request this, please disregard this email.</p>
#                     <p>If you have any questions or need further assistance, feel free to contact our support team.</p>
#                     <p>Best regards,<br><strong>SSEPL</strong></p>
#                 </div>
#                 <div class="footer">
#                     <p>This email is generated automatically, please do not reply.</p>
#                 </div>
#             </body>
#             </html>
#         """


#     # Create a plain text version by stripping HTML tags (for email clients that don't support HTML)
#     text_content = strip_tags(html_content)
#     # Create the email object
#     email_message = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [email])
#     # Attach the HTML version of the email
#     email_message.attach_alternative(html_content, "text/html")
#     email_message.send(fail_silently=False)


def send_user_credentials(email, name, username, password):
    # Prepare email subject and content
    subject = "Welcome to <b>FIXPAY</b> - Your Account Details"
    html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    padding: 20px;
                }}
                .container {{
                    background-color: #ffffff;
                    border-radius: 5px;
                    padding: 20px;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                }}
                h4 {{
                    color: #333;
                }}
                p {{
                    color: #555;
                    margin: 10px 0;
                }}
                b {{
                    font-weight: bold;
                }}
                .footer {{
                    margin-top: 20px;
                    font-size: 0.8em;
                    color: #999;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <p>Dear <b>{name}</b>,</p>
                <p>Welcome to <b>Fixpay</b>! We are excited to have you onboard and look forward to a successful partnership.</p>
                <p>Below are your account details to access the <b>Fixpay Portal</b>:</p>
                <p>User ID: <b>{username}</b></p>
                <p>Password: <b>{password}</b></p>
                <p><b>Important:</b><br>For your security, we strongly recommend <b>changing your default password</b> upon your first login.</p>
                <p><b>Note</b>: This is a system-generated email. Please do not reply to this message. If you need assistance, contact our support team at <b>(+91) 99999 99999</b>.</p>
                <p>Warm regards,<br>FIXPAY SERVE PRIVATE LIMITED</p>
            </div>
            <div class="footer">
                <p>This email is generated automatically, please do not reply.</p>
            </div>
        </body>
        </html>
    """
    text_content = strip_tags(html_content)
    email_message = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [email])
    email_message.attach_alternative(html_content, "text/html")
    email_message.send(fail_silently=False)


# bbps service mail format
def bbps_email_send(username, wallet_current, service_name,bbps_balance):

    # admin mail id
    receiver_emails = ["kunal@ssepl.live"]

    # receiver_emails = ["Nilkanth.koffeekodes@gmail.com", "Divya.koffeekodes@gmail.com"]

    subject = "Retailer Wallet Balance Update"

    # Properly formatted HTML email body
    email_body = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
            }}
            .footer {{
                margin-top: 20px;
                font-size: 0.8em;
            }}
            .header {{
                font-size: 1.2em;
                font-weight: bold;
                margin-bottom: 20px;
            }}
            .balance {{
                font-weight: bold;
                color: #007BFF;
            }}
        </style>
    </head>
    <body>
        <div class="header">Retailer Wallet Balance Update</div>
        <p>Dear Admin,</p>
        <p>The retailer <strong>{username}</strong> has successfully used the <strong>{service_name}</strong> service.</p>
        <p>The current user servive account balance is: <span class="balance">{wallet_current}</span></p>
        <p>The current bbps balance is: <span class="balance">{bbps_balance}</span></p>
        <p>Please ensure the retailer has sufficient balance for future transactions.</p>
        <br>
        <div class="footer">
            <p>This email is automatically generated. Please do not reply.</p>
        </div>
        <br>
        <p>Best Regards,</p>
        <p><strong>FIXPAY SERVE PRIVATE LIMITED</strong></p>
    </body>
    </html>
    """

    # Convert HTML to plain text for email clients that don't support HTML
    text_content = strip_tags(email_body)

    # Sending email to all recipients
    for email in receiver_emails:
        email_message = EmailMultiAlternatives(
            subject, text_content, settings.EMAIL_HOST_USER, [email]
        )
        email_message.attach_alternative(email_body, "text/html")
        email_message.send(fail_silently=False)
