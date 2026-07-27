from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from admin_hub.models import (
    PortalUser, PortalUserDetails, PortalUserLoginLogs,
    PgServiceTrn, PosServiceTrn, BBPSBillPayment, DistributorHierarchy
)


class DailyLoginReminderView(APIView):
    """
    Send daily login reminder emails to distributors about retailers who:
    1. Did not login today
    2. Logged in but did not perform any transaction today
    
    Uses created_by chain instead of dh hierarchy
    """
    
    def get(self, request):
        return self._handle_request(request)
    
    def post(self, request):
        return self._handle_request(request)

    def _handle_request(self, request):
        try:
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            print(f"🕐 Today start time: {today_start}")
            
            # Get all retailers
            retailers = PortalUser.objects.filter(
                pu_role='RETAILER',
                is_deleted=False,
                is_deactive=False,
                pu_status='APPROVED'
            )
            print(f"👥 Total retailers found: {retailers.count()}")
            
            # Get today's login logs (use distinct to avoid duplicates)
            today_logins = set(PortalUserLoginLogs.objects.filter(
                created_at__gte=today_start,
                pu_user_role='RETAILER'
            ).values_list('pu_user_id', flat=True))
            print(f"🔐 Retailers who logged in today: {today_logins}")
            
            # Get today's transactions
            today_pg_transactions = set(PgServiceTrn.objects.filter(
                created_at__gte=today_start
            ).values_list('created_by', flat=True))
            print(f"💳 PG transactions today (user IDs): {today_pg_transactions}")
            
            today_pos_transactions = set(PosServiceTrn.objects.filter(
                created_at__gte=today_start
            ).values_list('created_by', flat=True))
            print(f"🏪 POS transactions today (user IDs): {today_pos_transactions}")
            
            today_bbps_transactions = set(BBPSBillPayment.objects.filter(
                created_at__gte=today_start
            ).values_list('created_by', flat=True))
            print(f"📱 BBPS transactions today (user IDs): {today_bbps_transactions}")
            
            # Combine all transaction user IDs
            transaction_users = today_pg_transactions | today_pos_transactions | today_bbps_transactions
            print(f"✅ All transaction users combined: {transaction_users}")
            
            # Dictionary to store distributor-wise retailers
            distributor_retailers_map = {}
            
            for retailer in retailers:
                print(f"\n👤 Processing retailer: {retailer.id} - {retailer.pu_name}")
                
                try:
                    # Get PortalUserDetails to find created_by
                    retailer_detail = PortalUserDetails.objects.filter(pu=retailer).first()
                    
                    if not retailer_detail or not retailer_detail.created_by:
                        print(f"❌ No created_by found for retailer {retailer.id}")
                        continue
                    
                    print(f"✅ Retailer created_by: {retailer_detail.created_by}")
                    
                    # Check if retailer didn't login OR logged in but no transaction
                    should_notify = False
                    status_type = ""
                    
                    if retailer.id not in today_logins:
                        should_notify = True
                        status_type = "Not Logged In"
                        print(f"⚠️ Retailer {retailer.id} did NOT login today")
                    elif retailer.id not in transaction_users:
                        should_notify = True
                        status_type = "No Transaction"
                        print(f"⚠️ Retailer {retailer.id} logged in but NO transaction")
                    else:
                        print(f"✅ Retailer {retailer.id} is active with transactions")
                    
                    if should_notify:
                        print(f"📧 Should notify for retailer {retailer.id} - Status: {status_type}")
                        
                        # Get distributor chain using created_by
                        distributor_chain = self._get_distributor_chain_by_created_by(retailer_detail.created_by)
                        print(f"🔗 Distributor chain for retailer {retailer.id}: {distributor_chain}")
                        
                        retailer_info = {
                            'id': retailer.id,
                            'name': retailer.pu_name,
                            'username': retailer.username,
                            'contact': retailer.pu_contact_no,
                            'email': retailer.pu_email,
                            'status': status_type
                        }
                        
                        # Add retailer to all distributors in chain
                        for dist_id in distributor_chain:
                            if dist_id not in distributor_retailers_map:
                                distributor_retailers_map[dist_id] = []
                            distributor_retailers_map[dist_id].append(retailer_info)
                            print(f"➕ Added retailer {retailer.id} to distributor {dist_id}")
                
                except Exception as e:
                    print(f"❌ Error processing retailer {retailer.id}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"\n📊 Final distributor_retailers_map: {distributor_retailers_map}")
            print(f"📧 Total distributors to notify: {len(distributor_retailers_map)}")
            
            # Send emails to distributors
            emails_sent = self._send_emails_to_distributors(distributor_retailers_map)
            
            return Response({
                "status": True,
                "message": "Daily reminder emails sent successfully",
                "data": {
                    "distributors_notified": len(emails_sent),
                    "total_retailers": sum(len(retailers) for retailers in distributor_retailers_map.values()),
                    "emails_sent": emails_sent
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print("❌ Error in daily login reminder:", str(e))
            import traceback
            traceback.print_exc()
            return Response({
                "status": False,
                "message": f"Error sending daily reminders: {str(e)}",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_distributor_chain_by_created_by(self, created_by_id):
        """
        Get all distributor IDs in the hierarchy chain using created_by
        Example: Retailer created_by=2 → User 2's created_by=1 → User 1's created_by=Admin
        Returns list of distributor user IDs
        """
        print(f"\n🔗 Starting created_by chain lookup from user ID: {created_by_id}")
        distributor_chain = []
        current_user_id = created_by_id
        level = 1
        max_levels = 10  # Safety limit to prevent infinite loops
        
        while current_user_id and level <= max_levels:
            print(f"  Level {level}: Checking user ID {current_user_id}")
            
            try:
                # Get the user
                user = PortalUser.objects.filter(
                    id=current_user_id,
                    is_deleted=False,
                    is_deactive=False
                ).first()
                
                if not user:
                    print(f"  ❌ User {current_user_id} not found or inactive")
                    break
                
                print(f"  Found user: {user.id} - {user.pu_name} (Role: {user.pu_role})")
                
                # Add to chain if Distributor or Admin
                if user.pu_role in ['DISTRIBUTOR', 'ADMIN']:
                    distributor_chain.append(user.id)
                    print(f"  ✅ Added to chain: {user.id} ({user.pu_role})")
                    
                    # If Admin, stop the chain
                    if user.pu_role == 'ADMIN':
                        print(f"  🛑 Reached Admin, stopping chain")
                        break
                else:
                    print(f"  ⚠️ User role is {user.pu_role}, not Distributor/Admin")
                
                # Get this user's creator (parent in hierarchy)
                user_detail = PortalUserDetails.objects.filter(pu=user).first()
                
                if user_detail and user_detail.created_by:
                    current_user_id = user_detail.created_by
                    print(f"  Moving to parent user (created_by): {current_user_id}")
                    level += 1
                else:
                    print(f"  🛑 No created_by found, stopping chain")
                    break
                    
            except Exception as e:
                print(f"  ❌ Error at level {level}: {str(e)}")
                import traceback
                traceback.print_exc()
                break
        
        print(f"🔗 Final distributor chain: {distributor_chain}\n")
        return distributor_chain

    def _send_emails_to_distributors(self, distributor_retailers_map):
        """
        Send consolidated email to each distributor using SendEmailView API
        """
        import requests
        import json
        
        print(f"\n📧 Starting email sending process...")
        emails_sent = []
        
        for dist_id, retailers in distributor_retailers_map.items():
            print(f"\n📬 Processing distributor {dist_id} with {len(retailers)} retailers")
            try:
                distributor = PortalUser.objects.get(id=dist_id)
                print(f"  Distributor: {distributor.pu_name} ({distributor.pu_email})")
                
                if not distributor.pu_email:
                    print(f"  ❌ No email found for distributor {dist_id}")
                    continue
                
                # Group retailers by status
                not_logged_in = [r for r in retailers if r['status'] == 'Not Logged In']
                no_transaction = [r for r in retailers if r['status'] == 'No Transaction']
                
                print(f"  Not logged in: {len(not_logged_in)}")
                print(f"  No transaction: {len(no_transaction)}")
                
                # Prepare retailers list as HTML table rows for email
                retailers_html = ""
                
                if not_logged_in:
                    retailers_html += "<h3 style='color: #dc3545;'>❌ Did Not Login Today ({0})</h3>".format(len(not_logged_in))
                    retailers_html += """
                    <table style='width: 100%; border-collapse: collapse; margin-bottom: 20px;'>
                        <thead>
                            <tr style='background-color: #f8d7da;'>
                                <th style='border: 1px solid #ddd; padding: 8px;'>Name</th>
                                <th style='border: 1px solid #ddd; padding: 8px;'>Username</th>
                                <th style='border: 1px solid #ddd; padding: 8px;'>Contact</th>
                                <th style='border: 1px solid #ddd; padding: 8px;'>Email</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
                    for r in not_logged_in:
                        retailers_html += f"""
                            <tr>
                                <td style='border: 1px solid #ddd; padding: 8px;'>{r['name']}</td>
                                <td style='border: 1px solid #ddd; padding: 8px;'>{r['username']}</td>
                                <td style='border: 1px solid #ddd; padding: 8px;'>{r['contact']}</td>
                                <td style='border: 1px solid #ddd; padding: 8px;'>{r['email']}</td>
                            </tr>
                        """
                    retailers_html += "</tbody></table>"
                
                if no_transaction:
                    retailers_html += "<h3 style='color: #ffc107;'>⚠️ Logged In But No Transaction ({0})</h3>".format(len(no_transaction))
                    retailers_html += """
                    <table style='width: 100%; border-collapse: collapse; margin-bottom: 20px;'>
                        <thead>
                            <tr style='background-color: #fff3cd;'>
                                <th style='border: 1px solid #ddd; padding: 8px;'>Name</th>
                                <th style='border: 1px solid #ddd; padding: 8px;'>Username</th>
                                <th style='border: 1px solid #ddd; padding: 8px;'>Contact</th>
                                <th style='border: 1px solid #ddd; padding: 8px;'>Email</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
                    for r in no_transaction:
                        retailers_html += f"""
                            <tr>
                                <td style='border: 1px solid #ddd; padding: 8px;'>{r['name']}</td>
                                <td style='border: 1px solid #ddd; padding: 8px;'>{r['username']}</td>
                                <td style='border: 1px solid #ddd; padding: 8px;'>{r['contact']}</td>
                                <td style='border: 1px solid #ddd; padding: 8px;'>{r['email']}</td>
                            </tr>
                        """
                    retailers_html += "</tbody></table>"
                
                # Prepare message for email
                from datetime import datetime
                today_date = datetime.now().strftime('%d %B %Y')
                today_day = datetime.now().strftime('%A')
                
                message_content = f"""
                <div style='font-family: Arial, sans-serif;'>
                    <h2 style='color: #333;'>🔔 Daily Login Reminder</h2>
                    <p><strong>Date:</strong> {today_day}, {today_date}</p>
                    <p>Dear <strong>{distributor.pu_name}</strong>,</p>
                    <p>This is your daily security reminder for retailers under your hierarchy.</p>
                    
                    <div style='background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;'>
                        <p style='margin: 5px 0;'><strong>Total Retailers Needing Attention:</strong> {len(retailers)}</p>
                        <p style='margin: 5px 0;'><strong>Not Logged In:</strong> {len(not_logged_in)}</p>
                        <p style='margin: 5px 0;'><strong>No Transaction:</strong> {len(no_transaction)}</p>
                    </div>
                    
                    {retailers_html}
                    
                    <p style='color: #666; margin-top: 30px;'>Please follow up with these retailers for security purposes.</p>
                    <p style='color: #999; font-size: 12px;'>This is an automated email. Please do not reply.</p>
                </div>
                """
                
                # Call SendEmailView API
                email_api_data = {
                    "subject": f"🔔 Daily Login Reminder - {today_date}",
                    "recipient_list": [distributor.pu_email],
                    "name": distributor.pu_name,
                    "timestamp": today_date,
                    "message": message_content
                }
                
                send_email_url = "http://127.0.0.1:8000/admin_hub/send-email/"
                print(f"  📤 Calling SendEmailView API...")
                
                response = requests.post(send_email_url, json=email_api_data)
                
                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get('status') == 'success':
                        print(f"  ✅ Email sent successfully via API!")
                        emails_sent.append({
                            'distributor_id': dist_id,
                            'distributor_name': distributor.pu_name,
                            'distributor_email': distributor.pu_email,
                            'retailers_count': len(retailers),
                            'not_logged_in': len(not_logged_in),
                            'no_transaction': len(no_transaction)
                        })
                    else:
                        print(f"  ⚠️ API returned error: {response_data.get('message')}")
                else:
                    print(f"  ❌ API call failed with status {response.status_code}: {response.text}")
                    
            except Exception as e:
                print(f"  ❌ Error sending email to distributor {dist_id}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n✅ Email sending complete. Total emails sent: {len(emails_sent)}")
        return emails_sent
        