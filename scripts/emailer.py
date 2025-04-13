#!/usr/bin/env python3
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Content, Email, TrackingSettings, ClickTracking

# SendGrid API key (you'll need to set this as an environment variable)
# export SENDGRID_API_KEY='your_api_key'

def send_email():
    # Setup the sender and recipient
    from_email = Email("cedric@askcrystal.info")
    to_email = "soulcedric2@gmail.com"
    subject = "Your early access to improved data.gov search"
    
    # Create the email content with plain text formatting
    content = Content(
        "text/plain",
        """
        Hi [Name]! Ari and Cedric here from Crystal, a new tool for searching public datasets. Thanks for providing the public with access to your data. As regular Data.gov users, we found a few problems with search today that may resonate with you:
        
        - Keyword search is imprecise and often yields irrelevant results
        - Difficult to filter geographically and temporally
        - Many resources have inconsistent formats or are unavailable (linkrot).
        
        We'd love to get your feedback on Crystal (askcrystal.info), which we built to fix these issues. Here's early feedback from researchers we've received:
        
        - More accurate results
        - Better interface
        - One-click downloads
        
        If you have any suggestions at all as we build out the tool further, please reply to us directly here, or submit feedback using the green button on our site. 
        We also have a Discord community you can join here: discord.gg/ngKpsdKEyD
        
        Would love to hear your insights,
        Ari & Cedric
        """
    )
    
    # Construct the Mail object
    message = Mail(from_email, to_email, subject, content)
    
    # Disable click tracking to prevent link rewriting
    tracking_settings = TrackingSettings()
    click_tracking = ClickTracking(enable=False, enable_text=False)
    tracking_settings.click_tracking = click_tracking
    message.tracking_settings = tracking_settings
    
    try:
        # Send the email
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        response = sg.send(message)
        print(f"Email sent! Status code: {response.status_code}")
        print(f"Response body: {response.body}")
        print(f"Response headers: {response.headers}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

if __name__ == "__main__":
    success = send_email()
    if success:
        print("Email sent successfully!")
    else:
        print("Failed to send email. Check the error message above.")