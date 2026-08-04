
# Standard Library Imports
import json
import os
import random
import string
import re
import ast
from datetime import timedelta
from datetime import datetime, timedelta
from urllib3 import request
from dateutil import parser
from django.db import IntegrityError
from .bbps_service import *
# Django Core Imports
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail, EmailMultiAlternatives
from django.core.paginator import Paginator, EmptyPage
from django.forms import ValidationError
from django.db.models import ProtectedError
from django.db import transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.html import strip_tags
from .db_model_for_raw_query import *
from .commission_calculations import *
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils.dateparse import parse_datetime
# Third-Party Library Imports
from dotenv import load_dotenv, set_key
from user_agents import parse

# Django REST Framework Imports
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.db.models import Sum, Count
from .authentication import BearerTokenAuthentication  # Import your custom authentication class

# Custom Utility Imports
from validation.custom_validation import *
from .notification_services import *
from .verfication_suite import *

# Local Application Imports
from .models import *
from .serializers import *
from .utilies import *
from ssepl_backend.custom_jwt_auth import get_tokens_for_user, IsAdmin, IsRetailer, IsDistributor, \
    CustomJWTAuthentication
import traceback
import pytz

from django.views.decorators.http import require_POST

def get_ist_time():
    """Get current time in IST"""
    return timezone.now().astimezone(pytz.timezone('Asia/Kolkata'))


def post_test(request):
    return render(request, 'POS_Test.html')

def mask_aadhaar(aadhaar):
    if not aadhaar:
        return "Not Provided"

    # Extract only digits
    digits = ''.join(filter(str.isdigit, str(aadhaar)))

    if len(digits) < 8:
        return "Invalid Aadhaar"

    return f"{digits[:4]} XXXX XXXX {digits[-4:]}"


def get_formatted_date():
    today = datetime.datetime.today()
    day = today.day
    suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return today.strftime(f"%A, {day}{suffix} %B, %Y")


class GeolocationGetApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer | IsAdmin]

    def post(self, request):
        user = PortalUser.objects.get(id=request.user.id)
        latitude = request.data.get('get_latitude')
        longitude = request.data.get('get_longitude')

        # Optional: validate if both values are present and are valid floats
        if latitude is None or longitude is None:
            return Response(
                {'status': 'error', 'message': 'Latitude and Longitude are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user.latitude = float(latitude)
            user.longitude = float(longitude)
            user.save()
        except ValueError:
            return Response(
                {'status': 'error', 'message': 'Invalid latitude or longitude values.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {'status': 'success', 'message': 'Location Added successfully.'},
            status=status.HTTP_200_OK
        )

class HooksView(APIView):
    authentication_classes = [BearerTokenAuthentication]

    def post(self, request):
        """
        Handles POST requests to create a new hook entry.
        """
        try:
            response_data = json.loads(request.body)

            if not response_data:
                return Response({"status": "error", "message": "responsedata is required"},
                                status=status.HTTP_400_BAD_REQUEST)

            # Fetch user based on `tid`
            txnId = response_data.get("txnId")
            if not txnId:
                return Response({"status": "error", "message": "Transaction id is required in the request data"},
                                status=status.HTTP_400_BAD_REQUEST)

            if hooks_details.objects.filter(txn_id=txnId).exists():  # ADD CONDTION 
                return Response({"status": "fail", "message": "txnId already stored"},
                                status=status.HTTP_400_BAD_REQUEST)

            # Save hooks details
            hooks_details.objects.create(response_data=response_data, txn_id=txnId)

            self.add_pos_trn(request, response_data)

            return Response({"status": "success", "message": "Data successfully saved."},
                            status=status.HTTP_201_CREATED)

        except json.JSONDecodeError:
            return Response({"status": "error", "message": "Invalid JSON format "}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print('create hooks', str(e))
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        """
        Handles GET requests to fetch all hook entries.
        """
        try:
            hooks = hooks_details.objects.all()

            response_data = []
            for hook in hooks:
                hook_data = {
                    "id": hook.id,
                    "response_data": hook.response_data,
                    "created_at": hook.created_at
                }
                response_data.append(hook_data)

            return Response({"status": "success", "message": "Data successfully fetched", "data": response_data},
                            status=status.HTTP_200_OK)

        except hooks_details.DoesNotExist:
            return Response({"status": "error", "message": "No data found", "data": []},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def add_pos_trn(self, request, response_data):
        if not response_data:
            return Response({"status": "error", "message": "responsedata is required"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Fetch user based on `tid`
        tid = response_data.get("tid")
        if not tid:
            return Response({"status": "error", "message": "tid is required in the request data"},
                            status=status.HTTP_400_BAD_REQUEST)
        
        card_no = response_data.get('formattedPan')
        extracted_value = re.sub(r"[^0-9]", "", card_no)[:6]

        try:
            user_mapping = PosDevice.objects.get(terminal=tid)
            user = user_mapping.pu  # Assuming TidUserMapping has a ForeignKey to the User model
        except PosDevice.DoesNotExist:
            user = None
        
        bin_response = fetch_bin_details(extracted_value, user.id if user else None)
        posting_date_str = response_data.get("postingDate")
        pos_trn_dt = parse_datetime(posting_date_str) if posting_date_str else timezone.now()
        if pos_trn_dt is None:
            # If parsing fails, fallback to timezone.now()
            pos_trn_dt = timezone.now()
        
        with transaction.atomic():

            # Create PosServiceTrn entry
            sp = AdServiceProvider.objects.get(sp_id=1)
            service_trn = PosServiceTrn.objects.create(
                sp_id=1,
                trn_unique_id=response_data.get('txnId'),
                terminal_id=tid,
                trn_amount=response_data.get("amount"),
                customer_name=response_data.get("customerName"),
                trn_response=response_data,
                trn_status='COMPLETED',
                pos_trn_dt=pos_trn_dt,
                pos_charge_type=bin_response.get('charge_type'),
                created_by=user.id if user else None
            )


class RetailerTransactionSettlementAPIView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def get(self, request):
        try:
            pos_trn = PosServiceTrn.objects.filter(created_by__isnull=False, is_settled=False)[:5]

            for trn in pos_trn:
                print('fetch pos trn', trn.trn_amount)
                portal_user_details = PortalUserDetails.objects.get(pu_id=trn.created_by)
                rtl_wallet = PortalUserWallet.objects.get(pu_id=trn.created_by)
                # for retailer
                rt_gl = GlTrn.objects.create(
                    service_trn_id=trn.pk,
                    pu_id=trn.created_by,
                    gl_trn_amt=trn.trn_amount,
                    effectvie_wallet='pg_wallet',
                    effectvie_amt=trn.trn_amount,
                    service_trn_table='ad_pos_service_transaction',
                    effective_type='CR',
                    gl_trn_dt=now(),
                )

                WalletTrn.objects.create(
                    action_id=rt_gl.pk,
                    action_type='Service',
                    pu_id=trn.created_by,
                    wl_label=f"POS_by_{portal_user_details.pud_unique_id}_of_amount_{trn.trn_amount}_with_tx_id_{trn.trn_unique_id}",
                    effectvie_wallet='pg_wallet',
                    effectvie_amt=trn.trn_amount,
                    effective_type='CR',
                    current_balance=float(rtl_wallet.pg_wallet) + float(trn.trn_amount),
                    wl_trn_dt=now()
                )

                rtl_wallet.pg_wallet = float(rtl_wallet.pg_wallet) + float(trn.trn_amount)
                rtl_wallet.updated_at = now()
                rtl_wallet.save()

                # Prepare data for after_tx_cal
                data = {
                    'order_amount': trn.trn_amount,
                    'id': trn.created_by,
                    'sp_id': trn.sp_id,
                    'customer_contact_no': None,
                    'customer_name': trn.customer_name,
                    'trn_response': trn.trn_response,
                    'service_trn': trn.pk,
                    'label': AdServiceProvider.objects.get(sp_id=trn.sp_id).label,
                    'charge_level': trn.pos_charge_type
                }

                # Call after_tx_cal function
                after_tx_cal(request, data)

                trn.trn_status = "SETTLED"
                trn.is_settled = True
                trn.save()
            return Response({"status": "success", "message": "Transaction settled successfully"},
                            status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Manualy Admin
@api_view(['POST'])
def admin(request):
    try:
        data = request.data
        required_fields = ["pu_name", "pu_email", "pu_contact_no", "password"]

        for field in required_fields:
            if not data.get(field):
                return Response({"status": "fail", "message": f"{field} is required."},
                                status=status.HTTP_400_BAD_REQUEST)

        existing_admin = PortalUser.objects.filter(pu_role="ADMIN", is_deleted=False).first()
        if existing_admin:
            return Response(
                {
                    "status": "fail",
                    "message": "An admin already exists.",
                    "admin_details": {
                        "pu_name": existing_admin.pu_name,
                        "pu_email": existing_admin.pu_email,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        new_admin = PortalUser.objects.create(
            pu_name=data["pu_name"],
            pu_email=data["pu_email"],
            username=data["username"],
            pu_contact_no=data["pu_contact_no"],
            password=make_password(data["password"]),
            pu_role="ADMIN",
            is_verify=data.get("is_verify", False),
            is_kyc_verify=data.get("is_kyc_verify", False),
            is_deactive=data.get("is_deactive", False),
            is_deleted=False,
        )

        return Response(
            {
                "status": "success",
                "message": "Admin created successfully.",
                "admin_details": {
                    "pu_name": new_admin.pu_name,
                    "pu_email": new_admin.pu_email,
                    "pu_contact_no": new_admin.pu_contact_no,
                }
            },
            status=status.HTTP_201_CREATED
        )
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# START CODE =======>

# File Path
# def handle_uploaded_file(file, upload_folder):
#     media_root = settings.MEDIA_ROOT
#     upload_dir = os.path.join(media_root, upload_folder)
#     os.makedirs(upload_dir, exist_ok=True)

#     file_name = file.name.replace(" ", "_")

#     file_path = os.path.join(upload_dir, file_name)
#     relative_file_path = os.path.join(upload_folder, file_name)

#     try:
#         with open(file_path, 'wb') as destination:
#             for chunk in file.chunks():
#                 destination.write(chunk)
#     except Exception as e:
#         print(f"Error saving file: {e}")
#         return None

#     relative_file_path = relative_file_path.replace("\\", "/")

#     return relative_file_path
# def handle_uploaded_file(file, upload_folder):
#     media_root = settings.MEDIA_ROOT
#     upload_dir = os.path.join(media_root, upload_folder)
#     os.makedirs(upload_dir, exist_ok=True)

#     # Generate a timestamp-based filename
#     timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
#     extension = os.path.splitext(file.name)[1]  # Keep the original extension
#     file_name = f"{timestamp}{extension}"

#     file_path = os.path.join(upload_dir, file_name)
#     relative_file_path = os.path.join(upload_folder, file_name)

#     try:
#         with open(file_path, 'wb') as destination:
#             for chunk in file.chunks():
#                 destination.write(chunk)
#     except Exception as e:
#         print(f"Error saving file: {e}")
#         return None

#     return relative_file_path.replace("\\", "/")


def handle_uploaded_file(file, upload_folder, identifier):  # Add identifier
    media_root = settings.MEDIA_ROOT
    upload_dir = os.path.join(media_root, upload_folder)
    os.makedirs(upload_dir, exist_ok=True)

    safe_identifier = str(identifier).replace(" ", "_")
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    extension = os.path.splitext(file.name)[1]
    file_name = f"{timestamp}_{safe_identifier}{extension}"

    file_path = os.path.join(upload_dir, file_name)
    relative_file_path = os.path.join(upload_folder, file_name)

    try:
        with open(file_path, 'wb') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
    except Exception as e:
        print(f"Error saving file: {e}")
        return None

    return relative_file_path.replace("\\", "/")

def handle_uploaded_file_fund(file, upload_folder, identifier):  # identifier can be id or username
    media_root = settings.MEDIA_ROOT
    upload_dir = os.path.join(media_root, upload_folder)
    os.makedirs(upload_dir, exist_ok=True)

    # Sanitize identifier (remove spaces or problematic characters)
    safe_identifier = str(identifier).replace(" ", "_")

    # Generate a timestamp-based filename with identifier
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    extension = os.path.splitext(file.name)[1]  # Keep the original extension
    file_name = f"{timestamp}_{safe_identifier}{extension}"

    file_path = os.path.join(upload_dir, file_name)
    relative_file_path = os.path.join(upload_folder, file_name)

    try:
        with open(file_path, 'wb') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
    except Exception as e:
        print(f"Error saving file: {e}")
        return None

    return relative_file_path.replace("\\", "/")


# File Path - Get path
def get_full_image_url(request, image_path):
    """Function to convert image path into full URL"""
    if image_path:
        return f'http://{request.META["HTTP_HOST"]}/media/{image_path}'
    return None


# RANDOME PASSWORD GANRATED FUNCTION
def random_password(*, nchars=8, min_nupper=2, ndigits=2, nspecial=2, special=string.punctuation):
    if min_nupper + ndigits + nspecial > nchars:
        raise ValueError("Total of min_nupper, ndigits, and nspecial cannot exceed nchars.")

    nlower = nchars - (min_nupper + ndigits + nspecial)

    letters = random.choices(string.ascii_lowercase, k=nlower)
    letters_upper = random.choices(string.ascii_uppercase, k=min_nupper)
    digits = random.choices(string.digits, k=ndigits)
    specials = random.choices(special, k=nspecial)

    password_chars = letters + letters_upper + digits + specials
    random.shuffle(password_chars)

    return ''.join(password_chars)


# HSN/SAC Module
class HsnSacAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        if 'page_number' in request.data or 'page_size' in request.data:
            return self.fetch_hsnsac(request)
        elif 'hsnsac_code' in request.data and 'tax_rate' in request.data:
            return self.create_hsnsac(request)
        else:
            return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)

    def fetch_hsnsac(self, request):
        hsnsac_id = request.data.get('hsnsac_id')
        search_txt = request.data.get('search')
        page_number = int(request.data.get('page_numbr', 1))
        page_size = int(request.data.get('page_size', 10))

        try:
            if not page_size:
                return Response({'status': 'fail', 'message': 'page_size is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if isnumber(page_size) == False:
                return Response({'status': 'fail', 'message': 'page_size must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if isnumber(page_number) == False:
                    return Response({'status': 'fail', 'message': 'page_number must contain only digits.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if hsnsac_id:
                if isnumber(hsnsac_id) == False:
                    return Response({'status': 'fail', 'message': 'hsnsac_id must contain only digits.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            queryset = AdHSNSAC.objects.filter(is_deleted=False).order_by('-pk')

            if hsnsac_id:
                queryset = queryset.filter(pk=hsnsac_id)
            if search_txt:
                queryset = queryset.filter(
                    Q(hsnsac_code__icontains=search_txt) |
                    Q(tax_rate__icontains=search_txt)
                )

            queryset = queryset.order_by('-pk')

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            if page_obj is not None:
                if not queryset.exists():
                    paginated_response_data = {
                        'total_pages': 0,
                        'current_page': 0,
                        'total_items': 0,
                        'results': []
                    }
                    response_data = {
                        'status': 'success',
                        'message': 'HSNSAC Data not found.',
                        'data': paginated_response_data
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                serializer = HSNSACSerializer(page_obj.object_list, many=True, context={'request': request,
                                                                                        'exclude_fields': ["created_at",
                                                                                                           "updated_at",
                                                                                                           "is_deleted"]})
                paginated_response_data = {
                    'total_pages': paginator.num_pages,
                    'current_page': page_obj.number,
                    'total_items': paginator.count,
                    'results': serializer.data
                }
                return Response({
                    'status': 'success',
                    'message': 'HSNSAC Data',
                    'data': paginated_response_data
                }, status=status.HTTP_200_OK)

            serializer = HSNSACSerializer(queryset, many=True, context={'request': request,
                                                                        'exclude_fields': ["created_at", "updated_at",
                                                                                           "is_deleted"]})
            response_data = {
                'status': 'success',
                'message': 'HSNSAC Data',
                'data': serializer.data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create_hsnsac(self, request):
        request_data = request.data.copy()
        hsnsac_code = request.data.get('hsnsac_code')
        tax_rate = request.data.get('tax_rate')
        description = request.data.get('description')

        if 'hsnsac_code' not in request_data and 'tax_rate' not in request_data:
            return Response({"status": "fail", "message": "HSNSAC Code and Tax Rate is required"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            if isfloat(tax_rate) == False:
                return Response({"status": "fail", "message": "tax_rate must contain decimal value"},
                                status=status.HTTP_400_BAD_REQUEST)

            hsnsac_queryset = AdHSNSAC.objects.get(hsnsac_code=hsnsac_code, is_deleted=False)

            response_data = {
                "status": "fail",
                "message": "HSNSAC Code already exists"
            }

            if hsnsac_queryset.tax_rate == float(tax_rate):
                response_data['message'] = "Same HSNSAC code and tax rate already exists."

            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

        except AdHSNSAC.DoesNotExist:
            hsnsac_query = AdHSNSAC.objects.create(
                hsnsac_code=hsnsac_code,
                tax_rate=float(tax_rate),
                description=description if description else None,
                created_at=timezone.now(),
                created_by=request.user
            )

            user_activity = {
                "table_id": hsnsac_query.pk,
                "table_name": 'ad_hsn_sac_code',
                "ua_action": 'Create',  # Action performed
                "ua_description": 'HSNSAC Entry Created Successfully.',  # Action description
                "created_by": request.user,  # Current user performing the action
                "request_data": dict(request.data),  # Request data
                "response_data": model_to_dict(hsnsac_query)
            }

            add_user_activity(user_activity)

            response_data = {
                'status': 'success',
                'message': 'HSNSAC Entry Created Successfully'
            }
            # Return a success response with status code 201 (Created)
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            # Handle any exceptions and return an error response
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        hsnsac_id = request.data.get('hsnsac_id')
        hsnsac_code = request.data.get('hsnsac_code')
        tax_rate = request.data.get('tax_rate')
        description = request.data.get('description')

        if not hsnsac_id:
            return Response(
                {"status": "fail", "message": "HSNSAC ID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isnumber(hsnsac_id):
            return Response(
                {'status': 'fail', 'message': 'HSNSAC ID must contain only digits.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            hsnsac_queryset = AdHSNSAC.objects.get(hsnsac_id=hsnsac_id, is_deleted=False)

            # Case 1: Toggle activation/deactivation
            if not any([hsnsac_code, tax_rate, description]):
                active_hsnsac_count = AdHSNSAC.objects.filter(is_deactive=False).count()
                if active_hsnsac_count <= 1 and not hsnsac_queryset.is_deactive:
                    return Response(
                        {'status': 'fail',
                         'message': 'You cannot deactivate this HSNSAC entry. At least one active entry is required.'},
                        status=status.HTTP_200_OK
                    )

                hsnsac_queryset.is_deactive = not hsnsac_queryset.is_deactive
                hsnsac_queryset.updated_at = timezone.now()
                hsnsac_queryset.save()

                message = 'HSNSAC Entry Activated Successfully' if not hsnsac_queryset.is_deactive else 'HSNSAC Entry Deactivated Successfully'

                return Response({"status": "success", "message": message}, status=status.HTTP_200_OK)

            # Case 2: Update HSNSAC fields
            if hsnsac_code or tax_rate or description:
                duplicate_hsnsac = AdHSNSAC.objects.filter(
                    hsnsac_code=hsnsac_code
                ).exclude(hsnsac_id=hsnsac_id).first()

                if duplicate_hsnsac:
                    return Response(
                        {"status": "fail", "message": "HSNSAC code already exists."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if hsnsac_code:
                    hsnsac_queryset.hsnsac_code = hsnsac_code

                if tax_rate:
                    hsnsac_queryset.tax_rate = float(tax_rate)

                if description:
                    hsnsac_queryset.description = description

                hsnsac_queryset.updated_at = timezone.now()
                hsnsac_queryset.save()

                # Log user activity
                user_activity = {
                    "table_id": hsnsac_queryset.pk,
                    "table_name": 'ad_hsn_sac_code',
                    "ua_action": 'Update',
                    "ua_description": 'HSNSAC Entry Updated Successfully.',
                    "created_by": request.user,
                    "request_data": dict(request.data),
                    "response_data": model_to_dict(hsnsac_queryset)
                }
                add_user_activity(user_activity)

                return Response(
                    {"status": "success", "message": "HSNSAC Entry Updated Successfully"},
                    status=status.HTTP_200_OK
                )

        except AdHSNSAC.DoesNotExist:
            return Response(
                {'status': 'fail', 'message': "HSNSAC entry not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            return Response(
                {"status": "error", "message": f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request):
        hsnsac_id = request.data.get("hsnsac_id")

        if not hsnsac_id:
            return Response(
                {'status': 'fail', 'message': "hsnsac_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not hsnsac_id.isdigit():
            return Response(
                {'status': 'fail', 'message': 'hsnsac_id must contain only digits.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            hsnsac = AdHSNSAC.objects.get(hsnsac_id=hsnsac_id, is_deleted=False)

            active_count = AdHSNSAC.objects.filter(is_deactive=False, is_deleted=False).count()
            if active_count <= 1 and not hsnsac.is_deactive:
                return Response(
                    {'status': 'fail', 'message': 'You need to have at least one active HSNSAC.'},
                    status=status.HTTP_200_OK
                )

            with transaction.atomic():
                hsnsac.is_deleted = True
                hsnsac.save()

            return Response(
                {'status': 'success', 'message': 'HSNSAC Deleted Successfully'},
                status=status.HTTP_200_OK
            )

        except AdHSNSAC.DoesNotExist:
            return Response(
                {'status': 'fail', 'message': 'HSNSAC not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        except ProtectedError as e:
            return Response(
                {'status': 'fail', 'message': 'Cannot delete the record because it is referenced in other tables.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            return Response(
                {'status': 'error', 'message': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# SERVICE
class ServiceAPIView(APIView):
    """
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        service_id = request.data.get('service_id')
        search_txt = request.data.get('search')
        page_number = int(request.data.get('page_numbr', 1))
        page_size = int(request.data.get('page_size', 10))

        try:
            if not page_size: return Response({'status': 'fail', 'message': 'page_size is required.'},
                                              status=status.HTTP_400_BAD_REQUEST)
            if isnumber(page_size) == False: return Response(
                {'status': 'fail', 'message': 'page_size must contain only digits.'},
                status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if isnumber(page_number) == False: return Response(
                    {'status': 'fail', 'message': 'page_number must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if service_id:
                if isnumber(service_id) == False: return Response(
                    {'status': 'fail', 'message': 'service_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            queryset = AdService.objects.filter(is_deleted=False).order_by('-pk')

            if service_id:
                queryset = queryset.filter(pk=service_id)
            if search_txt:
                queryset = queryset.filter(
                    Q(service_name__icontains=search_txt) |
                    Q(description__icontains=search_txt)
                )

            queryset = queryset.order_by('-pk')

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            if page_obj is not None:
                if not queryset.exists():
                    paginated_response_data = {
                        'total_pages': 0,
                        'current_page': 0,
                        'total_items': 0,
                        'results': []
                    }
                    response_data = {
                        'status': 'Sucsess',
                        'message': 'HSNSAC Data not found.',
                        'data': paginated_response_data
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                serializer = ServiceSerializer(page_obj.object_list, many=True, context={'request': request,
                                                                                         'exclude_fields': [
                                                                                             "created_at", "updated_at",
                                                                                             "is_deleted"]})
                paginated_response_data = {
                    'total_pages': paginator.num_pages,
                    'current_page': page_obj.number,
                    'total_items': paginator.count,
                    'results': serializer.data
                }
                return Response({
                    'status': 'success',
                    'message': 'Service Data',
                    'data': paginated_response_data
                }, status=status.HTTP_200_OK)

            serializer = ServiceSerializer(queryset, many=True, context={'request': request,
                                                                         'exclude_fields': ["created_at", "updated_at",
                                                                                            "is_deleted"]})
            response_data = {
                'status': 'success',
                'message': 'Service Data',
                'data': serializer.data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            with transaction.atomic():
                savepoint = transaction.savepoint()
                service_id = request.data.get('service_id')
                service_name = request.data.get('service_name', None)
                service_description = request.data.get('service_description', None)

                if not service_id:
                    return Response({
                        'status': 'fail',
                        'message': 'Service ID is required'
                    }, status=status.HTTP_400_BAD_REQUEST)

                service_instance = AdService.objects.get(service_id=service_id, is_deleted=False)

                service_provider_instance = AdServiceProvider.objects.filter(service=service_instance)

                if not any([service_name, service_description]):
                    active_services_count = AdService.objects.filter(is_deactive=False, is_deleted=False).count()
                    # if active_services_count <= 1 and not service_instance.is_deactive:
                    #     return Response({
                    #         'status': 'fail',
                    #         'message': 'You cannot deactivate this service. At least one active service is required.'
                    #     }, status=status.HTTP_200_OK)

                    if service_instance.is_deactive:
                        service_instance.is_deactive = False
                        message = "Service activated successfully"
                    else:
                        service_instance.is_deactive = True
                        message = "Service deactivated successfully"

                    service_instance.updated_at = datetime.datetime.now()

                    for sp_instance in service_provider_instance:
                        sp_instance.is_deactive = service_instance.is_deactive
                        commission_charges = AdCommissionCharges.objects.filter(service_provider=sp_instance.pk,
                                                                                is_deleted=False)
                        hierarchy_charges = HierarchyCharges.objects.filter(sp=sp_instance.pk, is_deleted=False)
                        service_transaction_charges = PortalUserCharges.objects.filter(sp=sp_instance.pk)

                        for charges in commission_charges:
                            charges.is_deactive = service_instance.is_deactive
                            charges.save()
                        for charges in hierarchy_charges:
                            charges.is_deactive = service_instance.is_deactive
                            charges.save()
                        for charges in service_transaction_charges:
                            charges.is_deactive = service_instance.is_deactive
                            charges.save()

                        sp_instance.save()

                    service_instance.save()
                    transaction.savepoint_commit(savepoint)

                    return Response({
                        'status': 'success',
                        'message': message
                    }, status=status.HTTP_200_OK)

                if service_name:
                    service_instance.service_name = service_name
                if service_description:
                    service_instance.description = service_description

                service_instance.updated_at = timezone.now()
                service_instance.save()
                transaction.savepoint_commit(savepoint)

                return Response({
                    'status': 'success',
                    'message': 'Service updated successfully'
                }, status=status.HTTP_200_OK)

        except AdService.DoesNotExist:
            return Response({
                'status': 'fail',
                'message': f'Service with ID {service_id} does not exist'
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# SERVICE PROVIDERS
class ServiceProviderAPIView(APIView):
    """
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        try:
            if 'page_number' in request.data and 'page_size' in request.data:
                return self.fetch_service_provider(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_service_provider(self, request):
        sp_id = request.data.get('sp_id')
        service_id = request.data.get('service_id')
        hsn_sac_id = request.data.get('hsn_sac_id')
        search_txt = request.data.get('search')
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size')
        is_common_settlement = request.data.get('is_common_settlement')

        try:
            if not page_size: return Response({'status': 'fail', 'message': 'page_size is required.'},
                                              status=status.HTTP_400_BAD_REQUEST)
            if isnumber(page_size) == False: return Response(
                {'status': 'fail', 'message': 'page_size must contain only digits.'},
                status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if isnumber(page_number) == False: return Response(
                    {'status': 'fail', 'message': 'page_number must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if sp_id:
                if isnumber(sp_id) == False: return Response(
                    {'status': 'fail', 'message': 'sp_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if service_id:
                if isnumber(service_id) == False: return Response(
                    {'status': 'fail', 'message': 'service_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if hsn_sac_id:
                if isnumber(hsn_sac_id) == False: return Response(
                    {'status': 'fail', 'message': 'hsn_sac_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)
            
            user = PortalUser.objects.get(id=request.user.pk)

            queryset = AdServiceProvider.objects.filter(is_deleted=False, sa_provided=True)

            if is_common_settlement != "yes":
                blocked_sp_ids = AdServiceProvider.objects.filter(
                    for_instant__isnull=False
                ).values_list('for_instant', flat=True).distinct()
                queryset = queryset.exclude(sp_id__in=blocked_sp_ids)

            if sp_id:
                queryset = queryset.filter(pk=sp_id)
            if service_id:
                queryset = queryset.filter(service_id=service_id)
            if hsn_sac_id:
                queryset = queryset.filter(hsn_sac_id=hsn_sac_id)
            if search_txt:
                queryset = queryset.filter(
                    Q(service__service_name__icontains=search_txt) |
                    Q(sp_name__icontains=search_txt) |
                    Q(label__icontains=search_txt) |
                    Q(hsn_sac__hsnsac_code__icontains=search_txt)
                )

            queryset = queryset.order_by('-pk')

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            # If no data found, return an empty result with pagination metadata
            if not queryset.exists():
                return Response({
                    'status': 'fail',
                    'message': 'Service Provider Data not found.',
                    'data': {
                        'total_pages': 0,
                        'current_page': 0,
                        'total_items': 0,
                        'results': []
                    }
                }, status=status.HTTP_200_OK)

            # For each service provider, fetch related charges
            service_provider_data = []
            regular_rate = 0.00
            premium_rate = 0.00
            is_premium = False
            # Initialize a dictionary to group providers by their sub_service_provider
            sub_service_provider_mapping = {}

            for provider in page_obj:
                # Fetch related charges (assuming 'to_provide' charges category)
                to_us_charges = AdCharges.objects.filter(service_provider=provider, charge_category='to_us')
                service = AdService.objects.get(service_id=provider.service_id)
                if service.is_global ==True and service.is_table_config ==False:
                    regular_rate = 0.00
                    premium_rate = 0.00
                    is_premium = True
                if len(to_us_charges) > 0:
                    charge_serializer = ChargeSerializer(to_us_charges, many=True, context={'request': request})
                    charge_type = to_us_charges.first().charges_type if to_us_charges.exists() else None
                    charge_serializer_update = charge_serializer.data
                    for charge in charge_serializer_update:
                        charge['regular_rate'] = charge.get('rate')
                        charge['premium_rate'] = charge.get('rate')
                        
                        charge.pop("created_at")
                        charge.pop("updated_at")
                        charge.pop("is_deactive")
                        charge.pop("is_deleted")
                        charge.pop("created_by")

                        if charge.get("minimum") == "0.00" and charge.get("maximum") == "0.00":
                            charge.update({"is_slab": False})
                        else:
                            charge.update({"is_slab": True})
                else:
                    charge_serializer_update = []
                    charge_type = None

                ad_commission_queryset = AdCommissionCharges.objects.filter(service_provider=provider, is_deleted=False)
                if len(ad_commission_queryset) > 0:
                    global_commission_list = [
                        {
                            "commission_charges_id": commission_value.commission_charges_id,
                            "service_provider": commission_value.service_provider.pk,
                            "rate_type": commission_value.rate_type,
                            "minimum": commission_value.minimum,
                            "maximum": commission_value.maximum,
                            "is_slab": commission_value.is_slab
                        }
                        for commission_value in ad_commission_queryset
                    ]
                else:
                    global_commission_list = []

                service_name = AdService.objects.get(service_id=provider.service_id)

                # if provider.parent_name is None:
                service_provider_data.append({
                    'parent_name': None,
                    'sub_service_provider': [],
                    'sp_id': provider.sp_id,
                    'service_id': service_name.service_id,
                    'service_name': service_name.service_name,
                    'is_global': service_name.is_global,
                    'is_table_config': service_name.is_table_config,
                    'provider_name': provider.sp_name,
                    'provider_label': provider.label,
                    'tds_rate': provider.tds_rate,
                    'hsn_sac': provider.hsn_sac.hsnsac_id if provider.hsn_sac else None,
                    'hsn_sac_code': provider.hsn_sac.hsnsac_code if provider.hsn_sac else None,
                    'tax_rate': provider.hsn_sac.tax_rate if provider.hsn_sac else None,
                    'charge_type': charge_type,
                    'is_deactive': provider.is_deactive,
                    'to_us_charges': charge_serializer_update, 
                    'global_commission': global_commission_list,
                    'credentials_json': provider.credentials_json,
                    'regular_rate': regular_rate,  #ADD
                    'premium_rate': premium_rate,  #ADD
                    'is_premium': is_premium
                })
                # else:
                #     # sub_service_provider = AdSubServiceProvider.objects.filter(ssp_id=provider.parent_id.ssp_id).first()
                #     if provider.parent_name != None:
                #         if provider.parent_name not in sub_service_provider_mapping:
                #             sub_service_provider_mapping[provider.parent_name] = {
                #                 'parent_name': provider.parent_name,
                #                 'sub_service_provider': []
                #             }

                #         sub_service_provider_mapping[provider.parent_name]['sub_service_provider'].append({
                #             'sp_id': provider.sp_id,
                #             'service_id': service_name.service_id,
                #             'service_name': service_name,
                #             'is_global': service_name.is_global,
                #             'provider_name': provider.sp_name,
                #             'provider_label': provider.label,
                #             'tds_rate': provider.tds_rate,
                #             'hsn_sac': provider.hsn_sac.hsnsac_id if provider.hsn_sac else None,
                #             'hsn_sac_code': provider.hsn_sac.hsnsac_code if provider.hsn_sac else None,
                #             'tax_rate': provider.hsn_sac.tax_rate if provider.hsn_sac else None,
                #             'charge_type': charge_type,
                #             'is_deactive': provider.is_deactive,
                #             'to_us_charges': charge_serializer_update,
                #             'global_commission': global_commission_list,
                #             'credentials_json': provider.credentials_json,
                #         })

            for ssp_id, data in sub_service_provider_mapping.items():
                service_provider_data.append(data) 
 
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': service_provider_data
            }

            return Response({
                'status': 'success',
                'message': 'Service Provider Data with Charges',
                'data': paginated_response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def add_commission_structure(self, request):
        sp_id = request.data.get('sp_id')
        global_commission = request.data.get('global_commission')
        commission_value = request.data.get('commissions')

        try:
            global_commission_list = self._parse_json(global_commission, "Invalid JSON format for global commission")
            commission_list = self._parse_json(commission_value, "Invalid JSON format for commission value")
            
            service_provider = self._get_service_provider(sp_id)
            
            with transaction.atomic():
                hierarchy_charges = HierarchyCharges.objects.filter(sp=service_provider, is_deleted=False)
                
                if hierarchy_charges.exists():
                    print('if', hierarchy_charges)
                    self._update_global_commission(hierarchy_charges[0], global_commission_list, request)
                    self._update_hierarchy_commission(commission_list, service_provider, request)
                else:
                    print('else', hierarchy_charges)
                    self._create_global_commission(global_commission_list, service_provider, request)
                    self._create_hierarchy_commission(commission_list, service_provider, request)

                self._log_user_activity(request, 'Create', 'Service provider commission updated successfully.')
                
            data = {'status': 'success', 'message': 'Service provider commission updated successfully.'}
            return data
        
        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _parse_json(self, json_string, error_message):
        try:
            return json.loads(json_string)
        except json.JSONDecodeError:
            raise ValidationError(error_message)

    def _get_service_provider(self, sp_id):
        try:
            return AdServiceProvider.objects.get(sp_id=sp_id, is_deleted=False)
        except AdServiceProvider.DoesNotExist:
            raise ValidationError("Service Provider not found")

    def _update_global_commission(self, hierarchy_charge, global_commission_list, request):
        for index, commission_data in enumerate(global_commission_list):
            if index == 0:
                adcommission = AdCommissionCharges.objects.get(commission_charges_id=hierarchy_charge.pk)
                self._update_adcommission(adcommission, commission_data)
            else:
                AdCommissionCharges.objects.create(
                    service_provider=hierarchy_charge.sp,
                    rate_type=commission_data["rate_type"],
                    minimum=commission_data["minimum"],
                    maximum=commission_data["maximum"],
                    rate=commission_data["rate"],
                    is_slab=bool(commission_data.get("is_slab")),
                    created_by=request.user
                )
    
    def _update_hierarchy_commission(self, commission_list, service_provider, request):
        for value in commission_list:
            
            dh_id = value['dh_id'] if value['dh_id'] != 0 else None
            
            hierarchy_charge = HierarchyCharges.objects.get(dh_id=dh_id, sp=service_provider)
            
            hierarchy_charge.hc_charges = value.get('commission')
            hierarchy_charge.updated_at = timezone.now()
            hierarchy_charge.save()

            portal_user_charges = PortalUserCharges.objects.filter(dh_id=dh_id, sp=service_provider)

            if portal_user_charges.exists():
            
                for puc in portal_user_charges:
                    
                    puc.puc_charges = hierarchy_charge.hc_charges  # Update charges from hierarchy charges
                    puc.is_deactive = hierarchy_charge.is_deactive  # Sync active/deactive status
                    puc.updated_at = timezone.now()
                    puc.save()

    def _create_global_commission(self, global_commission_list, service_provider, request):
        for commission_data in global_commission_list:
            AdCommissionCharges.objects.create(
                service_provider=service_provider,
                charges_type=commission_data.get("charges_type"),
                rate_type=commission_data["rate_type"],
                minimum=commission_data["minimum"],
                maximum=commission_data["maximum"],
                rate=commission_data["rate"],
                is_slab=bool(commission_data.get("is_slab")),
                created_by=request.user
            )

    def _create_hierarchy_commission(self, commission_list, service_provider, request):
        for value in commission_list:
            dh = self._get_distributor_hierarchy(value['dh_id'])
            HierarchyCharges.objects.create(
                hc_charges=value['commission'],
                dh=dh,
                sp=service_provider,
                created_by=request.user
            )
    
    def _get_distributor_hierarchy(self, dh_id):
        if dh_id != 0:
            try:
                return DistributorHierarchy.objects.get(dh_id=dh_id, is_deleted=False)
            except DistributorHierarchy.DoesNotExist:
                raise ValidationError("Distributor Hierarchy ID does not exist")
        return None

    def _update_adcommission(self, adcommission, commission_data):
        adcommission.rate_type = commission_data.get("rate_type")
        adcommission.minimum = commission_data.get("minimum")
        adcommission.maximum = commission_data.get("maximum")
        adcommission.rate = commission_data.get("rate")
        adcommission.is_slab = bool(commission_data.get("is_slab"))
        adcommission.updated_at = timezone.now()
        adcommission.save()

    def _log_user_activity(self, request, action, description):
        user_activity = {
            "table_id": 0,
            "table_name": 'ad_commission_charges',
            "ua_action": action,
            "ua_description": description,
            "created_by": request.user,
            "request_data": dict(request.data),
            "response_data": None
        }
        add_user_activity(user_activity)

    def put(self, request):
        try:
            with transaction.atomic():
                savepoint_1 = transaction.savepoint()
                
                sp_id = request.data.get('sp_id')
                charges_type = request.data.get('charges_type')
                tds_rate = request.data.get('tds_rate')

                if not sp_id:
                    return Response({'status': 'fail', 'message': 'Service Provider ID is required'},
                                    status=status.HTTP_400_BAD_REQUEST)
                
                if not sp_id.isdigit():
                    return Response({'status': 'fail', 'message': 'sp_id must contain only digits.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                try:
                    service_provider = AdServiceProvider.objects.get(sp_id=sp_id, is_deleted=False)
                except AdServiceProvider.DoesNotExist:
                    return Response({'status': 'fail', 'message': 'Service Provider not found'},
                                    status=status.HTTP_404_NOT_FOUND)

                # Activation or deactivation
                if not charges_type and not tds_rate:
                    return self.handle_activation_deactivation(service_provider, savepoint_1)

                # Update TDS Rate and Commission Structure
                return self.update_tds_and_commission(request, service_provider, tds_rate, charges_type)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    # for old using of active service provider -> is_instant -> True & for_instant -> id

    # def handle_activation_deactivation(self, service_provider, savepoint_1):
    #     try:
    #         if not service_provider.service.is_global and not HierarchyCharges.objects.filter(sp_id=service_provider.sp_id).exists():
    #             return Response({'status': 'fail', 
    #                             'message': 'The service provider commission structure must be set up to activate this service.'},
    #                             status=status.HTTP_400_BAD_REQUEST)

    #         if service_provider.service.service_name == 'BBPS' and not BBPSBillerCategory.objects.filter(is_deactive=False).exists():
    #             return Response({'status': 'fail', 'message': 'Please update the category rate before activating the service provider.'},
    #                             status=status.HTTP_400_BAD_REQUEST)

    #         if service_provider.service.service_name == 'Recharge' and not Oprators.objects.filter(is_deactive=False).exists():
    #             return Response({'status': 'fail', 'message': 'Please update the category rate before activating the service provider.'},
    #                             status=status.HTTP_400_BAD_REQUEST)

    #         service_provider.is_deactive = not service_provider.is_deactive
    #         service_provider.updated_at = timezone.now()

    #         related_objects = [HierarchyCharges.objects.filter(sp=service_provider, is_deleted=False),
    #                         PortalUserCharges.objects.filter(sp=service_provider),
    #                         AdCommissionCharges.objects.filter(service_provider=service_provider, is_deleted=False)]
            
    #         for obj_list in related_objects:
    #             obj_list.update(is_deactive=service_provider.is_deactive)

    #         service_provider.save()
    #         transaction.savepoint_commit(savepoint_1)

    #         return Response({'status': 'success', 
    #                         'message': f'Service Provider {"Activated" if not service_provider.is_deactive else "Deactivated"} Successfully.'})

    #     except Exception as e:
    #         transaction.savepoint_rollback(savepoint_1)
    #         return Response({'status': 'error', 'message': f'Error processing Service Provider: {str(e)}'},
    #                         status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def handle_activation_deactivation(self, service_provider, savepoint_1):
        try:
            if not service_provider.service.is_global and not HierarchyCharges.objects.filter(sp_id=service_provider.sp_id).exists():
                return Response({'status': 'fail', 
                                'message': 'The service provider commission structure must be set up to activate this service.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if service_provider.service.service_name == 'BBPS' and not BBPSBillerCategory.objects.filter(is_deactive=False).exists():
                return Response({'status': 'fail', 'message': 'Please update the category rate before activating the service provider.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if service_provider.service.service_name == 'Recharge' and not Oprators.objects.filter(is_deactive=False).exists():
                return Response({'status': 'fail', 'message': 'Please update the category rate before activating the service provider.'},
                                status=status.HTTP_400_BAD_REQUEST)

            service_provider.is_deactive = not service_provider.is_deactive
            service_provider.updated_at = timezone.now()

            related_objects = [
                HierarchyCharges.objects.filter(sp=service_provider, is_deleted=False),
                PortalUserCharges.objects.filter(sp=service_provider),
                AdCommissionCharges.objects.filter(service_provider=service_provider, is_deleted=False)
            ]
            
            for obj_list in related_objects:
                obj_list.update(is_deactive=service_provider.is_deactive)

            service_provider.save()
         
            if service_provider.is_instant and service_provider.for_instant:
                instant_provider = service_provider.for_instant
                
                instant_provider.is_deactive = service_provider.is_deactive
                instant_provider.updated_at = timezone.now()
                instant_provider.save()
                
                instant_related_objects = [
                    HierarchyCharges.objects.filter(sp=instant_provider, is_deleted=False),
                    PortalUserCharges.objects.filter(sp=instant_provider),
                    AdCommissionCharges.objects.filter(service_provider=instant_provider, is_deleted=False)
                ]
                
                for obj_list in instant_related_objects:
                    obj_list.update(is_deactive=service_provider.is_deactive)
            else:
                print(f"Condition not met: is_instant={service_provider.is_instant}, for_instant={service_provider.for_instant}")

            transaction.savepoint_commit(savepoint_1)

            return Response({
                'status': 'success', 
                'message': f'Service Provider {"Activated" if not service_provider.is_deactive else "Deactivated"} Successfully.'
            })

        except Exception as e:
            transaction.savepoint_rollback(savepoint_1)
            return Response({
                'status': 'error', 
                'message': f'Error processing Service Provider: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update_tds_and_commission(self, request, service_provider, tds_rate, charges_type):
        if tds_rate is None:
            return Response({'status': 'fail', 'message': 'TDS rate is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tds_rate = float(tds_rate)
            if not (0 <= tds_rate <= 100):
                return Response({'status': 'fail', 'message': 'TDS rate must be between 0 and 100.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if service_provider.sp_id in [3, 4, 6,10]:
                rupay_mdr = request.data.get('rupay_mdr')
                mastercard_mdr = request.data.get('mastercard_mdr')
                visa_mdr = request.data.get('visa_mdr')
                gst_percentage = request.data.get('gst_percentage')
                
                # Validate MDR values
                for field_name, field_value in [
                    ('rupay_mdr', rupay_mdr),
                    ('mastercard_mdr', mastercard_mdr),
                    ('visa_mdr', visa_mdr),
                    ('gst_percentage', gst_percentage)
                ]:
                    if field_value is not None and field_value != '':
                        try:
                            value = float(field_value)
                            if not (0 <= value <= 100):
                                return Response({
                                    'status': 'fail', 
                                    'message': f'{field_name} must be between 0 and 100.'
                                }, status=status.HTTP_400_BAD_REQUEST)
                        except ValueError:
                            return Response({
                                'status': 'fail', 
                                'message': f'Invalid value for {field_name}.'
                            }, status=status.HTTP_400_BAD_REQUEST)

            

            savepoint_2 = transaction.savepoint()

            serializer = ServiceProviderSerializer(service_provider, data=request.data, partial=True,
                                                context={'request': request})
            if serializer.is_valid():
                service_provider_instance = serializer.save(updated_at=timezone.now(), updated_by=request.user)

                add_user_activity({
                    "table_id": service_provider_instance.pk,
                    "table_name": 'ad_service_provider',
                    "ua_action": 'Update',
                    "ua_description": 'Service Provider updated successfully.',
                    "created_by": request.user,
                    "request_data": dict(request.data),
                    "response_data": serializer.data
                })

                service_data = AdService.objects.get(service_id=service_provider.service_id)

                if 'to_us_charges' in request.data:
                    to_us_charges_str = request.data.get('to_us_charges', '[]')
                    self.process_charges(to_us_charges_str, service_provider_instance, request, 'to_us', charges_type)

                if not service_data.is_table_config:
                    self.add_commission_structure(request)

                transaction.savepoint_commit(savepoint_2)
                return Response({'status': 'success', 'message': 'Service Provider updated successfully'})

            transaction.savepoint_rollback(savepoint_2)
            return Response({'status': 'fail', 'message': 'Failed to update Service Provider', 'data': serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            transaction.savepoint_rollback(savepoint_2)
            return Response({'status': 'error', 'message': f'Error updating TDS rate: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# DEVICE
class DeviceAPIView(APIView):

    def post(self, request):
        if 'device_active' in request.data and 'number' in request.data:
            return self.add_device_number(request)
        else:
            return self.get_device_number(request)

    def add_device_number(self, request):
        load_dotenv()

        device_active = request.data.get('device_active')
        number = request.data.get('number')

        if not device_active or not number:
            return Response({"error": "Both device_active and number are required"}, status=status.HTTP_400_BAD_REQUEST)

        env_path = os.path.join(os.path.dirname(__file__), '../.env')

        set_key(env_path, device_active, number)

        return Response({"message": f"'{device_active}' saved successfully"}, status=status.HTTP_200_OK)

    def get_device_number(self, request):

        device_active = request.data.get('device_active')

        load_dotenv()

        number = os.getenv(device_active)

        if number:
            return Response({device_active: number}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Key not found"}, status=status.HTTP_404_NOT_FOUND)


# PARTNER CATEGORY CREATE
class PartnerCategoryAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        try:
            if 'is_service_provider' in request.data and 'dh_id' in request.data:
                return self.fetch_hirarchy_service_provider(request)
            elif 'page_number' in request.data and 'page_size' in request.data:
                return self.fetch_data(request)
            elif 'name' in request.data and 'partner_prefix' in request.data:
                return self.create_hierarchy(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create_hierarchy(self, request):
        try:
            with transaction.atomic():
                name = request.data.get('name')
                parent_id = request.data.get('parent_id', 0)
                description = request.data.get('description')
                partner_prefix = request.data.get('partner_prefix')
                service_provider_str = request.data.get('service_provider', '[]')
                service_provider = json.loads(service_provider_str)

                if parent_id:
                    try:
                        dh_obj = DistributorHierarchy.objects.get(dh_id=parent_id)

                        if dh_obj.is_used:
                            response_data = {
                                'status': 'success',
                                'message': 'Parent id is already used'
                            }
                            # Return a success response with status code 201 (Created)
                            return Response(response_data, status=status.HTTP_201_CREATED)
                        else:
                            dh_obj.is_used = True
                            dh_obj.save()
                    except DistributorHierarchy.DoesNotExist:
                        response_data = {
                            'status': 'fail',
                            'message': 'Parent id does not exist'
                        }
                        # Return a success response with status code 201 (Created)
                        return Response(response_data, status=status.HTTP_404_NOT_FOUND)

                if len(partner_prefix) >= 4:
                    return Response({'status': 'fail', 'message': 'Partner prefix must be fewer than 4 characters.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                # Assuming DistributorHierarchy is created here
                hierarchy = DistributorHierarchy.objects.create(
                    dh_name=name, dh_parent_id=parent_id if parent_id else None, dh_description=description,
                    dh_prefix=partner_prefix
                )
                for provider in service_provider:
                    sp_id = provider.get('sp_id')
                    mark_type = provider.get('charge_type')
                    mark_value = provider.get('mark_value')
                    is_deactive = provider.get('is_deactive')
                    rate_type = provider.get('rate_type')

                    charges = AdCharges.objects.filter(service_provider=sp_id)
                    # Prepare charges data
                    charges_list = []
                    for charge in charges:
                        rate = charge.rate
                        minimum = charge.minimum
                        maximum = charge.maximum

                        # Apply markup based on the type
                        updated_rate = float(rate) + mark_value

                        charges_list.append({
                            'rate': updated_rate,
                            'minimum': float(minimum) if minimum != "0.00" else minimum,
                            'maximum': float(maximum) if maximum != "0.00" else maximum,
                            'charge_type': mark_type,
                            'rate_type': rate_type,
                            'is_slab': True if (str(minimum) != "0.00" and str(maximum) != "0.00") else False,
                            'mark_value': mark_value
                        })
                    # Store the charges data in HierarchyCharges model
                    HierarchyCharges.objects.create(
                        hc_charges=charges_list,
                        sp_id=sp_id,
                        dh_id=hierarchy.dh_id,
                        mark_type=mark_type,
                        is_deactive=is_deactive
                    )

                user_activity = {
                    "table_id": hierarchy.pk,
                    "table_name": 'ad_distributor_hierarchy',
                    "ua_action": 'Create',  # Action performed
                    "ua_description": 'Partner Category Created Successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(hierarchy)
                }

                add_user_activity(user_activity)

                response_data = {
                    'status': 'success',
                    'message': 'Partner Category Created Successfully'
                }
                # Return a success response with status code 201 (Created)
                return Response(response_data, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            response_data = {
                'status': 'fail',
                'message': f'{str(e)}'
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Handle any exceptions and return an error response
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_data(self, request):
        user_id = request.user.id
        user_role = request.user.pu_role

        dh_id = request.data.get('dh_id')
        search_txt = request.data.get('search')
        in_retailer = request.data.get('in_retailer', None)
        in_partner = request.data.get('in_partner', None)
        page_number = int(request.data.get('page_numbr', 1))
        page_size = int(request.data.get('page_size', 10))
        data = {
            "dh_id": 0,
            "parent_category_name": None,
            "hc_charges": [],
            "dh_name": "Retailer",
            "dh_parent_id": None,
            "dh_description": "retailer",
            "dh_prefix": "RT",
            "is_used": False,
            "is_deactive": False,
            "is_deleted": False,
            "created_at": "2024-10-16T12:31:48.621432Z",
            "updated_at": None,
            "updated_by": None,
            "created_by": None
        }
        try:
            if user_role == 'ADMIN':
                queryset = DistributorHierarchy.objects.filter(
                    is_deleted=False
                ).order_by('pk')
                # if in_parent:
                #     queryset = queryset.filter(is_used=False)
                if in_partner:
                    queryset = queryset.filter(dh_parent_id=None)
            else:
                # Fetch the distributor hierarchy ID of the user
                user_hierarchy = PortalUserDetails.objects.filter(pu_id=user_id).first()
                # Check if user has an associated hierarchy
                if not user_hierarchy:
                    return Response({
                        'status': 'fail',
                        'message': 'No associated partner category found for this user.',
                        'data': {}
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Get the hierarchy ID to filter with
                user_dh_id = user_hierarchy.dh.dh_id
                if user_dh_id == 1:
                    queryset = DistributorHierarchy.objects.filter(
                        is_deleted=False).order_by('pk')[1:3]
                else:
                    queryset = DistributorHierarchy.objects.filter(
                        is_deleted=False, dh_parent_id=user_dh_id
                    ).order_by('pk')
            # Apply additional filters if provided
            if dh_id:
                queryset = queryset.filter(pk=dh_id)
            if search_txt:
                queryset = queryset.filter(
                    Q(service_name__icontains=search_txt) |
                    Q(description__icontains=search_txt)
                )

            # Paginator setup
            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            # Return paginated response if data exists
            if page_obj is not None:
                if not queryset.exists():
                    paginated_response_data = {
                        'total_pages': 1,
                        'current_page': 1,
                        'total_items': 1,
                        'results': []
                    }
                    paginated_response_data['results'].append(data)
                    response_data = {
                        'status': 'success',
                        'message': 'Partner Category Data.',
                        'data': paginated_response_data
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                serializer = DistributorHierarchySerializer(page_obj.object_list, many=True,
                                                            context={'request': request,
                                                                     'exclude_fields': ["created_at", "updated_at",
                                                                                        "is_deleted"]})

                paginated_response_data = {
                    'total_pages': paginator.num_pages,
                    'current_page': page_obj.number,
                    'total_items': paginator.count,
                    'results': serializer.data
                }
                if request.data.get('sp_id'):
                    sp_id = request.data.get('sp_id')

                    retailer_charges = HierarchyCharges.objects.filter(dh=None, sp=request.data.get('sp_id')).first()
                    if retailer_charges == None:
                        data['hc_charges'] = []
                    else:
                        data['hc_charges'] = retailer_charges.hc_charges

                    if int(sp_id) in [3, 4, 6,10]:
                        try:
                            service_provider = AdServiceProvider.objects.get(sp_id=sp_id)
                            paginated_response_data['rupay_mdr'] = float(service_provider.rupay_mdr) if service_provider.rupay_mdr else 0
                            paginated_response_data['mastercard_mdr'] = float(service_provider.mastercard_mdr) if service_provider.mastercard_mdr else 0
                            paginated_response_data['visa_mdr'] = float(service_provider.visa_mdr) if service_provider.visa_mdr else 0
                            paginated_response_data['gst_percentage'] = float(service_provider.gst_percentage) if service_provider.gst_percentage else 0
                        except AdServiceProvider.DoesNotExist:
                            pass
                    

                # paginated_response_data = {
                #     'total_pages': paginator.num_pages,
                #     'current_page': page_obj.number,
                #     'total_items': paginator.count,
                #     'results': serializer.data
                # }

                if page_number and page_size and in_partner or in_retailer:
                    if not in_partner:
                        paginated_response_data['results'].append(data)
                        paginated_response_data['total_items'] += 1
                return Response({
                    'status': 'success',
                    'message': 'Partner Cateogry Data',
                    'data': paginated_response_data
                }, status=status.HTTP_200_OK)

            # Non-paginated response if page object is None
            serializer = DistributorHierarchySerializer(queryset, many=True, context={'request': request,
                                                                                      'exclude_fields': ["created_at",
                                                                                                         "updated_at",
                                                                                                         "is_deleted"]})

            response_data = {
                'status': 'success',
                'message': 'Partner Category Data',
                'data': serializer.data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'fail',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_hirarchy_service_provider(self, request):
        is_service_provider = request.data.get("is_service_provider")
        page_size = request.data.get('page_size')
        page_number = request.data.get('page_number', 1)
        dh_id = request.data.get("dh_id")

        try:
            if not dh_id: return Response({"status": "fail", "message": "dh_id is required"},
                                          status=status.HTTP_400_BAD_REQUEST)
            if not is_service_provider: return Response(
                {"status": "fail", "message": "is_service_provider is required"}, status=status.HTTP_400_BAD_REQUEST)
            if not page_size: return Response({"status": "fail", "message": "page_size is required"},
                                              status=status.HTTP_400_BAD_REQUEST)

            if isboolean(is_service_provider) is None: return Response(
                {'status': 'fail', 'message': 'Invalid is_service_provider value.'}, status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(dh_id): return Response({'status': 'fail', 'message': 'dh_id must be only digit.'},
                                                    status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(page_size): return Response({'status': 'fail', 'message': 'page_size must be only digit.'},
                                                        status=status.HTTP_400_BAD_REQUEST)

            hierachy_charge_queryset = HierarchyCharges.objects.filter(dh=dh_id, is_deleted=False).order_by('sp')
            hierachy_serializer = HierarchyChargesSerializer(hierachy_charge_queryset, many=True,
                                                             context={'request': request,
                                                                      'exclude_fields': ["created_at", "updated_at",
                                                                                         "is_deleted", "updated_by",
                                                                                         "created_by"]})
            hierachy_serializer_data = hierachy_serializer.data

            response_data = []
            sp_ids = []

            if hierachy_serializer_data:
                for hierachy_data in hierachy_serializer_data:
                    sp_id = hierachy_data.get('sp')
                    if sp_id:
                        service_provider_queryset = AdServiceProvider.objects.get(sp_id=sp_id)
                        hierachy_data.update({
                            'sp_id': sp_id,
                            'service_name': service_provider_queryset.service.service_name,
                            'provider_name': service_provider_queryset.sp_name,
                            'provider_label': service_provider_queryset.label,
                            'hsn_sac_code': service_provider_queryset.hsn_sac.hsnsac_code,
                            'charges': hierachy_data.get('hc_charges')
                        })

                        hierachy_data.pop("dh", None)
                        hierachy_data.pop("mark_type", None)
                        hierachy_data.pop("hc_charges", None)

                        response_data.append(hierachy_data)
                        sp_ids.append(sp_id)

            ad_service_provider_queryset = AdServiceProvider.objects.filter(is_deleted=False).exclude(
                sp_id__in=sp_ids).order_by('sp_id')
            print('===', ad_service_provider_queryset)
            for sp_data in ad_service_provider_queryset:
                to_us_charges = AdCharges.objects.filter(service_provider=sp_data, charge_category='to_us')
                if len(to_us_charges) > 0:
                    charge_serializer = ChargeSerializer(to_us_charges, many=True, context={'request': request})
                    charge_type = to_us_charges.first().charges_type if to_us_charges.exists() else None

                    charge_serializer_update = charge_serializer.data
                    for charge in charge_serializer_update:
                        charge.pop("created_at")
                        charge.pop("updated_at")
                        charge.pop("is_deactive")
                        charge.pop("is_deleted")
                        charge.pop("created_by")

                        if charge.get("minimum") == "0.00" and charge.get("maximum") == "0.00":
                            charge.update({"is_slab": False})
                        else:
                            charge.update({"is_slab": True})
                else:
                    charge_serializer_update = []
                    charge_type = None

                response_data.append({
                    'sp_id': sp_data.sp_id,
                    'service_name': sp_data.service.service_name,
                    'provider_name': sp_data.sp_name,
                    'provider_label': sp_data.label,
                    'hsn_sac_code': sp_data.hsn_sac.hsnsac_code,
                    'is_deactive': sp_data.is_deactive,
                    'charges': charge_serializer_update
                })

            paginator = Paginator(response_data, page_size)
            if not response_data:
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                response_data_dict = {
                    'status': 'fail',
                    'message': 'ServiceProvider Data not found.',
                    'data': paginated_response_data
                }
                return Response(response_data_dict, status=status.HTTP_200_OK)

            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': page_obj.object_list
            }

            response_data_dict = {
                'status': 'success',
                'message': 'ServiceProvider Data',
                'data': paginated_response_data
            }

            return Response(response_data_dict, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            dh_id = request.data.get('dh_id')
            prefix = request.data.get('prefix', None)
            description = request.data.get('description', None)

            if prefix:
                prefix_validation = isstring(prefix)
                if prefix_validation == False:
                    return Response({'status': 'fail', 'message': 'Invalid input: prefix must be a string.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(prefix) > 4:
                    return Response({'status': 'fail', 'message': 'Partner prefix must be fewer than 4 characters.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            distributor_hierachy = DistributorHierarchy.objects.get(dh_id=dh_id)

            if prefix:
                distributor_hierachy.dh_prefix = prefix

            if description:
                distributor_hierachy.dh_description = description

            distributor_hierachy.save()

            return Response({'status': 'success', 'message': 'Distributor hierarchy updated successfully..'},
                            status=status.HTTP_200_OK)

        except DistributorHierarchy.DoesNotExist:
            return Response({'status': 'fail', 'message': 'distributor hierarchy dose not exists.'},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# USERS API CREATE -- UPDATE
class UserAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsAdmin | IsRetailer]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        try:
            if 'aadhaar_card' in request.data and 'pan_card' in request.data and 'name' in request.data and 'email' in request.data and 'contact_no' in request.data:
                return self.add_users(request)

            elif 'aadhaar_card' in request.data:
                return self.verify_aadhaar(request)

            elif ('ref_id' in request.data and 'aadhaar_otp' in request.data) or (
                    'email' in request.data and 'email_otp' in request.data) or (
                    'contact_no' in request.data and 'contact_otp' in request.data):
                return self.verify_otp(request)

            elif 'pan_card' in request.data:
                return self.verify_pan(request)

            elif 'email' in request.data:
                return self.verify_email(request)

            elif 'contact_no' in request.data:
                return self.verify_contact(request)

            elif 'user_id' in request.data and 'is_service' in request.data:
                return self.fetch_service_providers(request)

            elif 'user_id' in request.data and 'amount' in request.data and 'debit_from' in request.data and 'label' in request.data and 'description' in request.data:
                return self.manual_debit(request)

            # elif 'page_number' in request.data and 'page_size' in request.data or 'request_user_id' in request.data:
            #     return self.fetch_users(request)

            elif 'page_number' in request.data and 'page_size' in request.data or 'request_user_id' in request.data or 'noPagination' in request.data:
                return self.fetch_users(request)

            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def verify_aadhaar(self, request):
        aadhaar_card = request.data.get('aadhaar_card')
        if not aadhaar_card:
            return Response({"status": "fail", "message": "Aadhaar card is required."},
                            status=status.HTTP_400_BAD_REQUEST)

        if not isnumber(aadhaar_card):
            return Response({"status": "fail", "message": "Aadhaar card number must contain only digits."},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(aadhaar_card) != 12:
            return Response({"status": "fail", "message": "Aadhaar card number must be exactly 12 digits long."},
                            status=status.HTTP_400_BAD_REQUEST)

        # if PortalUserDetails.objects.filter(aadhaar_card=aadhaar_card).exists(): #===> ADHAR CHECk ALREDY RAGISTER 
        #     return Response({
        #         'status': 'fail',
        #         'message': 'This Aadhar number is already registered, use a different Aadhar number.'
        #     }, status=status.HTTP_400_BAD_REQUEST)

        aadhaar_response = aadhaar_verify(aadhaar_card)
        return Response(aadhaar_response['data'], status=aadhaar_response['status'])

    def verify_otp(self, request):
        if 'ref_id' in request.data and 'aadhaar_otp' in request.data:
            ref_id = request.data.get('ref_id')
            aadhaar_otp = request.data.get('aadhaar_otp')
            fwdp = request.data.get('fwdp')
            codeVerifier = request.data.get('codeVerifier')

            if not ref_id:
                return Response({"status": "fail", "message": "Referance id is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not aadhaar_otp:
                return Response({"status": "fail", "message": "Aadhaar OTP is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(aadhaar_otp):
                return Response({"status": "fail", "message": "Aadhaar OTP must contain only digits."},
                                status=status.HTTP_400_BAD_REQUEST)
            if len(aadhaar_otp) != 6:
                return Response({"status": "fail", "message": "OTP code must be exactly 6 digits long."},
                                status=status.HTTP_400_BAD_REQUEST)

            aadhaar_otp_response = aadhaar_otp_verify(aadhaar_otp, ref_id, fwdp, codeVerifier)
            return Response(aadhaar_otp_response['data'], status=aadhaar_otp_response['status'])

        elif 'email' in request.data and 'email_otp' in request.data:
            email = request.data.get('email')
            email_otp = request.data.get('email_otp')

            try:
                if not email:
                    return Response({"status": "fail", "message": "Email is required."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not email_otp:
                    return Response({"status": "fail", "message": "Email OTP is required."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not validation_email_address(email):
                    return Response({"status": "fail", "message": "Invalid email address format."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(email_otp):
                    return Response({"status": "fail", "message": "OTP code must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(email_otp) != 6:
                    return Response({"status": "fail", "message": "OTP code must be exactly 6 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)

                user = UserCodeVerification.objects.get(ucv_data=email)

                if user.verify_code == email_otp and user.verify_code_expire_at > timezone.now():
                    user.verify_code = None
                    user.verify_code_expire_at = None
                    user.is_verify = True
                    user.save()

                    response_data = {
                        'status': 'success',
                        'message': 'Email verification code verified successfully.',
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                else:
                    response_data = {
                        'status': 'fail',
                        'message': 'Invalid or expired verification code.'
                    }
                    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

            except UserCodeVerification.DoesNotExist:
                response_data = {
                    'status': 'error',
                    'message': 'User with this email does not exist.'
                }
                return Response(response_data, status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                response_data = {
                    'status': 'error',
                    'message': f'Internal server error: {str(e)}'
                }
                # Return a success response with status code 200
                return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


        else:
            contact_no = request.data.get('contact_no')
            contact_otp = request.data.get('contact_otp')

            try:
                if not contact_no:
                    return Response({"status": "fail", "message": "Contact number is required."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not contact_otp:
                    return Response({"status": "fail", "message": "OTP code is required."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(contact_no):
                    return Response({"status": "fail", "message": "Contact number must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(contact_no) != 10:
                    return Response({"status": "fail", "message": "Contact number must be exactly 10 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(contact_otp):
                    return Response({"status": "fail", "message": "OTP code must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(contact_otp) != 6:
                    return Response({"status": "fail", "message": "OTP code must be exactly 6 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)

                user = UserCodeVerification.objects.get(ucv_data=contact_no)

                if user.verify_code == contact_otp and user.verify_code_expire_at > timezone.now():
                    user.verify_code = None
                    user.verify_code_expire_at = None
                    user.is_verify = True
                    user.save()

                    response_data = {
                        'status': 'success',
                        'message': 'Contact verification code verified successfully.',
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                else:
                    response_data = {
                        'status': 'fail',
                        'message': 'Invalid or expired verification code.'
                    }
                    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

            except UserCodeVerification.DoesNotExist:
                response_data = {
                    'status': 'error',
                    'message': 'User with this contact no does not exist.'
                }
                return Response(response_data, status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                response_data = {
                    'status': 'error',
                    'message': f'Internal server error: {str(e)}'
                }
                # Return a success response with status code 200
                return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def verify_pan(self, request):
        pan_card = request.data.get('pan_card')
        if not pan_card:
            return Response({"status": "fail", "message": "Pan card is required."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not checkpancardvalidation(pan_card):
            return Response({"status": "fail", "message": "Invalid PAN card format."},
                            status=status.HTTP_400_BAD_REQUEST)

        # if PortalUserDetails.objects.filter(pan_card=pan_card).exists(): #===> PAN ENTRY CHECK 
        #     return Response({
        #         'status': 'fail',
        #         'message': 'This Pan number is already registered, use a different Pan number.'
        #     }, status=status.HTTP_400_BAD_REQUEST)

        pan_card_response = verify_pan_card(pan_card)
        return Response(pan_card_response['data'], status=pan_card_response['status'])

    def verify_email(self, request):
        email = request.data.get('email')
        otp = get_random_string(length=6, allowed_chars='0123456789')
        try:
            if not email:
                return Response({"status": "fail", "message": "Email is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not validation_email_address(email):
                return Response({"status": "fail", "message": "Invalid email address format."},
                                status=status.HTTP_400_BAD_REQUEST)

            if PortalUser.objects.filter(pu_email=email, is_deleted=False).exists():
                return Response({
                    'status': 'fail',
                    'message': 'This Email is already registered, use a different Email.'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                pu_obj = UserCodeVerification.objects.get(ucv_data=email)
                pu_obj.verify_code = otp
                pu_obj.verify_code_expire_at = timezone.now() + timedelta(minutes=10)
                pu_obj.save()
            except UserCodeVerification.DoesNotExist:
                UserCodeVerification.objects.create(ucv_data=email, verify_code=otp,
                                                    verify_code_expire_at=timezone.now() + timedelta(minutes=10))

            with transaction.atomic():
                # send_email = send_email_otp(email, otp, 'Distributor')
                send_email_subject = "OTP for Email Verification"

                email_data = {
                    "subject": send_email_subject,
                    "recipient_list": [email],
                    "otp": otp,
                    "role": "Distributor"
                }

                # Sending HTTP request to Project A's API to trigger the email sending
                send_email_url = "https://qaapi.fixpay.in/admin_hub/send-email/"
                response = requests.post(send_email_url, json=email_data)

            response_data = {
                'status': 'success',
                'message': 'Email sent successfully', }
            # Return a success response with status code 200
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            # Return a success response with status code 200
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def verify_contact(self, request):
        contact_no = request.data.get('contact_no')
        otp = get_random_string(length=6, allowed_chars='0123456789')
        try:
            if not contact_no:
                return Response({"status": "fail", "message": "Contact number is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(contact_no):
                return Response({"status": "fail", "message": "Contact number must contain only digits."},
                                status=status.HTTP_400_BAD_REQUEST)
            if len(contact_no) != 10:
                return Response({"status": "fail", "message": "Contact number must be exactly 10 digits long."},
                                status=status.HTTP_400_BAD_REQUEST)

            if PortalUser.objects.filter(pu_contact_no=contact_no, is_deleted=False).exists():
                return Response({
                    'status': 'fail',
                    'message': 'This contact number is already registered, use a different contact number.'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                pu_obj = UserCodeVerification.objects.get(ucv_data=contact_no)
                pu_obj.verify_code = otp
                pu_obj.verify_code_expire_at = timezone.now() + timedelta(minutes=10)
                pu_obj.save()
            except UserCodeVerification.DoesNotExist:
                UserCodeVerification.objects.create(ucv_data=contact_no, verify_code=otp,
                                                    verify_code_expire_at=timezone.now() + timedelta(minutes=10))

            # Prepare the SMS content
            response = mobicomm_submit_sms(contact_no, otp)

            # Check the SMS API response status
            if response.status_code == 200:
                response_data = {
                    'status': 'success',
                    'message': 'OTP has been sent via SMS.',
                    'data': {'contact_otp': otp}
                }
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                response_data = {
                    'status': 'error',
                    'message': 'Failed to send the OTP via SMS.',
                    'details': response.text  # Include the response for debugging
                }
                return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            # Return a success response with status code 200
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def add_users(self, request):
        print('add_users', request.data)
        aadhaar_card = request.data.get('aadhaar_card')
        pan_card = request.data.get('pan_card')
        pan_response = request.data.get('pan_response')
        pu_name = request.data.get('name')
        pu_email = request.data.get('email')
        pu_contact_no = request.data.get('contact_no')
        alternate_contact_no = request.data.get('alternate_contact_no')
        address = request.data.get('address')
        state = request.data.get('state')
        city = request.data.get('city')
        zip_code = request.data.get('zip_code')
        partner_category = request.data.get('partner_category')
        profile_image = request.FILES.get('profile_image')
        shop_name = request.data.get('shop_name')
        shop_address = request.data.get('shop_address')
        shop_images = request.FILES.get('shop_images')
        shop_gst_number = request.data.get('shop_gst_number')
        aadhar_front_image = request.FILES.get('aadhar_image_front')
        aadhar_back_image = request.FILES.get('aadhar_image_back')
        pan_images = request.FILES.get('pan_image')
        print(state)
        



        try:
            with transaction.atomic():
                prefix_value = ""
                required_fields = ['aadhaar_card', 'pan_card', 'pan_response', 'name', 'email',
                                   'contact_no', 'alternate_contact_no', 'address', 'state', 'city', 'zip_code',
                                   'partner_category', 'shop_name', 'shop_address', 'shop_images', "aadhar_image_front",
                                   "aadhar_image_back", "pan_image"]

                missing_fields = [field for field in required_fields if not request.data.get(field)]

                if missing_fields:
                    return Response(
                        {'status': 'fail',
                         'message': f'Required fields are empty: {", ".join(missing_fields)}. provide all required fields and try again'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if PortalUser.objects.filter(pu_contact_no=pu_contact_no, is_deleted=False).exists():
                    return Response({
                        'status': 'fail',
                        'message': 'This contact number is already registered, use a different contact number.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if not isnumber(aadhaar_card):
                    return Response({"status": "fail", "message": "Aadhaar card number must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(aadhaar_card) != 12:
                    return Response(
                        {"status": "fail", "message": "Aadhaar card number must be exactly 12 digits long."},
                        status=status.HTTP_400_BAD_REQUEST)
                if not checkpancardvalidation(pan_card):
                    return Response({"status": "fail", "message": "Invalid PAN card format."},
                                    status=status.HTTP_400_BAD_REQUEST)

                try:
                    parsed_data = json.loads(pan_response)
                except json.JSONDecodeError:
                    return Response({"status": "fail", "message": "PAN response must be valid JSON."},
                                    status=status.HTTP_400_BAD_REQUEST)

                if not validation_email_address(pu_email):
                    return Response({"status": "fail", "message": "Invalid email address format."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(pu_contact_no):
                    return Response({"status": "fail", "message": "Contact number must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(pu_contact_no) != 10:
                    return Response({"status": "fail", "message": "Contact number must be exactly 10 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(alternate_contact_no):
                    return Response({"status": "fail", "message": "Alternate contact number must be digit."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(alternate_contact_no) != 10:
                    return Response(
                        {"status": "fail", "message": "Alternate contact number must be exactly 10 digits long."},
                        status=status.HTTP_400_BAD_REQUEST)
                # if shop_gst_number:
                    # if not is_valid_gst_number(shop_gst_number):
                        # return Response(
                            # {"status": "fail", "message": "Invalid GST number format."},
                            # status=status.HTTP_400_BAD_REQUEST
                        # )
                state = state.strip()
                state_obj = State.objects.filter(state_name__icontains=state).first()
                print(state_obj)
                

                if not state_obj:
                    return Response({'status': 'fail', 'message': 'State not found.'}, status=status.HTTP_404_NOT_FOUND)

                state_id = state_obj.state_id
                print('state_id==================>', state_id)
                short_name = state_obj.short_name
                print('short_name==================>', short_name)

                city_obj = City.objects.filter(city_name__icontains=city).first()
                if not city_obj:
                    return Response({'status': 'fail', 'message': 'City not found.'}, status=status.HTTP_404_NOT_FOUND)

                city_id = city_obj.city_id

                if not isnumber(zip_code):
                    return Response({"status": "fail", "message": "Zip code must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)

                if len(zip_code) != 6:
                    return Response({"status": "fail", "message": "Zip code must be exactly 6 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)

                user = PortalUser.objects.get(id=request.user.id, is_deleted=False)

                # masked_aadhaar_number = parsed_data.get('masked_aadhaar_number')[-4:]
                #
                # if masked_aadhaar_number != aadhaar_card[-4:]:
                #     return Response({'status': 'fail', 'message': 'Aadhaar number mismatch. Please verify the Aadhaar details.'},
                #                     status=status.HTTP_400_BAD_REQUEST)
                #
                #
                # if parsed_data.get('aadhaar_linked') == False:
                #     return Response({'status': 'fail', 'message': 'Aadhaar is not linked to the provided PAN card.'},
                #                     status=status.HTTP_400_BAD_REQUEST)

                if int(partner_category) != 0:
                    # Fetch DistributorHierarchy
                    try:
                        distributor_hierarchy = DistributorHierarchy.objects.get(pk=partner_category)
                        print(distributor_hierarchy, distributor_hierarchy.dh_prefix)
                        prefix_value = distributor_hierarchy.dh_prefix
                    except DistributorHierarchy.DoesNotExist:
                        return Response({
                            'status': 'fail',
                            'message': 'Partner Category Does Not Exist'
                        }, status=status.HTTP_404_NOT_FOUND)
                else:
                    distributor_hierarchy = None
                    prefix_value = "RT"

                unique_user_id = generate_userid(prefix_value, short_name)

                username = unique_user_id
                password = get_random_string(8)

                # if shop_images:
                #     file_path2 = handle_uploaded_file(shop_images, 'shopimages') if shop_images else None
                if shop_images:
                    if isinstance(shop_images, list):
                        file_path2 = [handle_uploaded_file(file, 'shopimages',username) for file in shop_images]
                    else:
                        file_path2 = [handle_uploaded_file(shop_images, 'shopimages',username)]
                else:
                    file_path2 = []
                


                if int(partner_category) != 0:
                    file_path1 = handle_uploaded_file(profile_image, 'Distributor/Docs',username) if profile_image else None
                    pan_images = handle_uploaded_file(pan_images, 'Distributor/pan_card',username) if pan_images else None
                    aadhar_front_image = handle_uploaded_file(aadhar_front_image,
                                                              'Distributor/aadhar_front',username) if aadhar_front_image else None
                    aadhar_back_image = handle_uploaded_file(aadhar_back_image,
                                                             'Distributor/aadhar_back',username) if aadhar_back_image else None

                    pu_obj = PortalUser.objects.create(
                        pu_name=pu_name,
                        pu_email=pu_email,
                        pu_contact_no=pu_contact_no,
                        username=username,
                        password=make_password(password),
                        pu_role="DISTRIBUTOR",
                        is_kyc_verify=True
                    )

                    PortalUserWallet.objects.create(
                        main_wallet=0.00,
                        pu=pu_obj
                    )
                else:
                    file_path1 = handle_uploaded_file(profile_image, 'Retailer/Docs',username) if profile_image else None
                    pan_images = handle_uploaded_file(pan_images, 'Retailer/pan_card',username) if pan_images else None
                    aadhar_front_image = handle_uploaded_file(aadhar_front_image,
                                                              'Retailer/aadhar_front',username) if aadhar_front_image else None
                    aadhar_back_image = handle_uploaded_file(aadhar_back_image,
                                                             'Retailer/aadhar_back',username) if aadhar_back_image else None

                    pu_obj = PortalUser.objects.create(
                        pu_name=pu_name,
                        pu_email=pu_email,
                        pu_contact_no=pu_contact_no,
                        username=username,
                        password=make_password(password),
                        pu_role="RETAILER",
                        is_kyc_verify=True
                    )

                    PortalUserWallet.objects.create(
                        main_wallet=0.00,
                        cashin_wallet=0.00,
                        pg_wallet=0.00,
                        pu=pu_obj
                    )

                # Email sendd
                # send_user_credentials(pu_email, pu_name, username, password)
                send_email_subject = "Welcome to Fixpay!"
        
                email_data = {
                    "subject": send_email_subject,
                    "recipient_list": [pu_email],
                    "username": username,
                    "password": password,
                    "name": pu_name
                }

                # Sending HTTP request to Project A's API to trigger the welcome email
                send_email_url = "https://qaapi.fixpay.in/admin_hub/send-email/"
                response = requests.post(send_email_url, json=email_data)

                # Combine all paths into a single dictionary
                file_paths = {
                    'profile_image': file_path1,
                    'shop_images': file_path2,
                    'aadhar_front_image': aadhar_front_image,
                    'aadhar_back_image': aadhar_back_image,
                    'pan_images': pan_images
                }
                print('file_paths=================>', file_paths)
                if shop_gst_number == '':
                    shop_gst_number = None
                # Create PortalUserDetails
                PortalUserDetails.objects.create(
                    pu=pu_obj,
                    dh=distributor_hierarchy,
                    pud_unique_id=unique_user_id,
                    alternate_contact_no=alternate_contact_no,
                    address=address,
                    doc_images=file_paths,
                    state_id=state_id,
                    city_id=city_id,
                    zip_code=zip_code,
                    aadhaar_card=aadhaar_card,
                    pan_card=pan_card,
                    pan_response=pan_response,
                    created_by=request.user.id,
                    shop_name=shop_name,
                    shop_address=shop_address,
                    shop_gst_number=shop_gst_number,

                )

                # for charge in hierarchy_charges:
                #     PortalUserCharges.objects.create(
                #         sp=charge.sp,
                #         dh=charge.dh,
                #         pu_id=pu_obj.id,  # Assuming pu_id refers to the primary key of PortalUser
                #         parent_id=request.user.id,
                #         mark_type=charge.mark_type,
                #         puc_charges=charge.hc_charges,
                #         created_by=request.user
                #     )

                user_activity = {
                    "table_id": pu_obj.pk,
                    "table_name": 'ad_portal_user',
                    "ua_action": 'Create',  # Action performed
                    "ua_description": 'User Created Successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(pu_obj)
                }

                add_user_activity(user_activity)

                return Response({
                    'status': 'success',
                    'message': 'User Created Successfully'
                }, status=status.HTTP_201_CREATED)
            

        
        
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    def fetch_users(self, request):
        user_id = request.user.id
        try:
            no_pagination_value = request.data.get('noPagination', False)
            if isinstance(no_pagination_value, str):
                no_pagination = no_pagination_value.lower() in ['true', '1', 'yes']
            else:
                no_pagination = bool(no_pagination_value)
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            filter_by = request.data.get('filter_by', None)
            search = request.data.get('search', None)
            start_date = request.data.get('start_date', None)
            request_user_id = request.data.get('request_user_id', None)
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            portal_users = PortalUser.objects.filter(is_deleted=False).order_by('-pk')

            if request.user.pu_role == "ADMIN":
                if request_user_id:
                    portal_users = portal_users.filter(id=request_user_id)
                else:
                    portal_users = portal_users.filter(pu_role__in=["DISTRIBUTOR", "RETAILER"])
            else:
                if request_user_id:
                    portal_users = portal_users.filter(id=request_user_id)
                else:
                    portal_users = portal_users.filter(portaluserdetails__created_by=user_id)

            if filter_by:
                allowed_filters = ['ALL USERS', 'ALL DISTRIBUTORS', 'SUPER DISTRIBUTOR', 'MASTER DISTRIBUTOR',
                                   'DISTRIBUTOR', 'RETAILER']
                if filter_by not in allowed_filters:
                    return Response({'status': 'fail',
                                     'message': f'Invalid filter_by value. Only allowed values are {", ".join(allowed_filters)}'},
                                    status=status.HTTP_400_BAD_REQUEST)

                if filter_by == 'RETAILER':
                    portal_users = portal_users.filter(portaluserdetails__dh__isnull=True)
                else:
                    if filter_by == 'ALL DISTRIBUTORS':
                        portal_users = portal_users.filter(pu_role='DISTRIBUTOR')
                    elif filter_by == 'ALL USERS':
                        portal_users = portal_users
                    else:
                        dh = DistributorHierarchy.objects.filter(dh_name=filter_by, is_deleted=False).first()
                        if not dh:
                            return Response({'status': 'fail', 'message': f'Hierarchy "{filter_by}" not found.'},
                                            status=status.HTTP_404_NOT_FOUND)
                        portal_users = portal_users.filter(portaluserdetails__dh=dh)

            if search:
                portal_users = portal_users.filter(
                    Q(pu_name__icontains=search) |
                    Q(pu_email__icontains=search) |
                    Q(pu_contact_no__icontains=search) |
                    Q(portaluserdetails__aadhaar_card__icontains=search) |
                    Q(portaluserdetails__pan_card__icontains=search)
                )

            if start_date:
                portal_users = portal_users.filter(created_at__date__range=[start_date, end_date])
            # paginator = Paginator(portal_users, page_size)
            # page_obj = paginator.page(page_number)

            if no_pagination:
                page_obj = portal_users  
                total_items = portal_users.count()
                total_pages = 1
                current_page = 1
            else:
                paginator = Paginator(portal_users, page_size)
                page_obj = paginator.page(page_number)
                total_items = paginator.count
                total_pages = paginator.num_pages
                current_page = page_obj.number

            users_data = []
            for user in page_obj:
                # Fetch the related PortalUserDetails object, if it exists
                portal_user_details = PortalUserDetails.objects.filter(pu=user).first()

                # Check if portal_user_details is None
                if portal_user_details:
                    if portal_user_details.dh:
                        dh = DistributorHierarchy.objects.filter(dh_id=portal_user_details.dh.dh_id).first()
                        user_category = dh.dh_name if dh else 'UNKNOWN'
                    else:
                        user_category = 'RETAILER'

                    # Safely access 'created_by' attribute
                    p_user = PortalUser.objects.filter(id=portal_user_details.created_by).first()

                    doc_images = portal_user_details.doc_images if portal_user_details.doc_images else {}
                    image_urls = {key: get_full_image_url(request, value) for key, value in doc_images.items()}
                    wallet_data = self.get_wallet_data(user.id)  

                    user_data = {
                        'user': {
                            'id': user.id,
                            'name': user.pu_name,
                            'email': user.pu_email,
                            'contact_no': user.pu_contact_no,
                            'is_deactive':user.is_deactive,
                            'unique_id': portal_user_details.pud_unique_id,
                            'user_category': user_category,
                            'user_status': user.pu_status,
                            'created_by': portal_user_details.created_by if portal_user_details.created_by else 'N/A',  # Default value if None
                            'parent_user_id': p_user.username if p_user else 'N/A',  # Default value if None
                            'parent_user_name': p_user.pu_name if p_user else 'N/A',  # Default value if None
                            'profile_image': image_urls.get("profile_image"),
                            'pan_images': image_urls.get("pan_images"),
                            'aadhar_front_image': image_urls.get("aadhar_front_image"),
                            'aadhar_back_image': image_urls.get("aadhar_back_image")
                        },

                        'shop_info': {
                            'shop_name': portal_user_details.shop_name,
                            'shop_images': image_urls.get("shop_images"),
                            'shop_gst_number': portal_user_details.shop_gst_number,
                            'shop_address': portal_user_details.shop_address,
                        },

                        'wallet_info': wallet_data
                    }
                    print(user_data,'-----)))))))))))))))))))))))))))))2634')

                    users_data.append(user_data)
                else:
                    # Handle the case where portal_user_details is None
                    users_data.append({
                        'user': {
                            'id': user.id,
                            'name': user.pu_name,
                            'email': user.pu_email,
                            'contact_no': user.pu_contact_no,
                            'user_category': 'UNKNOWN',  # Default value if portal_user_details is None
                            'user_status': user.pu_status,
                            'created_by': 'N/A',  # Default value if None
                            'parent_user_id': 'N/A',  # Default value if None
                            'parent_user_name': 'N/A',  # Default value if None
                        },
                        'shop_info': {},
                        'wallet_info': {}
                    })

            # Continue with pagination and response as usual


            # paginated_response_data = {
            #     'total_pages': paginator.num_pages,
            #     'current_page': page_obj.number,
            #     'total_items': paginator.count,
            #     'results': users_data
            # }
            paginated_response_data = {
                'total_pages': total_pages,      
                'current_page': current_page,    
                'total_items': total_items,      
                'results': users_data
            }

            return Response({'status': 'success', 'message': 'Portal User Data', 'data': paginated_response_data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e),'-----ggg')
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_wallet_data(self, user_id):
        print(user_id)
        """
        Fetch wallet data (main, cashin, pg) for the user.
        Assumes a related `PortalUserWallet` model.
        """
        try:
            wallet = PortalUserWallet.objects.filter(pu_id=user_id).first()
            if wallet:
                return {
                    'main_wallet': wallet.main_wallet,
                    'cashin_wallet': wallet.cashin_wallet,
                    'pg_wallet': wallet.pg_wallet
                }
            return {'main_wallet': 0, 'cashin_wallet': 0, 'pg_wallet': 0}
        except Exception as e:
            print(f"Error fetching wallet data for user {user_id}: {str(e)}")
            return {'main_wallet': 0, 'cashin_wallet': 0, 'pg_wallet': 0}

    def fetch_service_providers(self, request):
        sp_id = request.data.get('sp_id')
        user_id = request.data.get('user_id')
        is_service = request.data.get('is_service')
        service_id = request.data.get('service_id')
        hsn_sac_id = request.data.get('hsn_sac_id')
        search_txt = request.data.get('search')
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size')

        try:
            if not page_size: return Response({'status': 'fail', 'message': 'page_size is required.'},
                                              status=status.HTTP_400_BAD_REQUEST)
            if isnumber(page_size) == False: return Response(
                {'status': 'fail', 'message': 'page_size must contain only digits.'},
                status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if isnumber(page_number) == False: return Response(
                    {'status': 'fail', 'message': 'page_number must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if sp_id:
                if isnumber(sp_id) == False: return Response(
                    {'status': 'fail', 'message': 'sp_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if service_id:
                if isnumber(service_id) == False: return Response(
                    {'status': 'fail', 'message': 'service_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if hsn_sac_id:
                if isnumber(hsn_sac_id) == False: return Response(
                    {'status': 'fail', 'message': 'hsn_sac_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            user = PortalUser.objects.get(id=request.user.pk)

            queryset = AdServiceProvider.objects.filter(is_deleted=False)

            if sp_id:
                queryset = queryset.filter(pk=sp_id)
            if service_id:
                queryset = queryset.filter(service_id=service_id)
            if hsn_sac_id:
                queryset = queryset.filter(hsn_sac_id=hsn_sac_id)
            if search_txt:
                queryset = queryset.filter(
                    Q(service__service_name__icontains=search_txt) |
                    Q(sp_name__icontains=search_txt) |
                    Q(label__icontains=search_txt) |
                    Q(hsn_sac__hsnsac_code__icontains=search_txt)
                )

            queryset = queryset.order_by('-pk')

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            # If no data found, return an empty result with pagination metadata
            if not queryset.exists():
                return Response({
                    'status': 'fail',
                    'message': 'Service Provider Data not found.',
                    'data': {
                        'total_pages': 0,
                        'current_page': 0,
                        'total_items': 0,
                        'results': []
                    }
                }, status=status.HTTP_200_OK)

            # For each service provider, fetch related charges
            service_provider_data = []
            # Initialize a dictionary to group providers by their sub_service_provider
            sub_service_provider_mapping = {}

            for provider in page_obj:
                # Fetch related charges (assuming 'to_provide' charges category)
                to_us_charges = AdCharges.objects.filter(service_provider=provider, charge_category='to_us')

                if len(to_us_charges) > 0:
                    charge_serializer = ChargeSerializer(to_us_charges, many=True, context={'request': request})
                    charge_type = to_us_charges.first().charges_type if to_us_charges.exists() else None
                    charge_serializer_update = charge_serializer.data
                    for charge in charge_serializer_update:
                        charge.pop("created_at")
                        charge.pop("updated_at")
                        charge.pop("is_deactive")
                        charge.pop("is_deleted")
                        charge.pop("created_by")

                        if charge.get("minimum") == "0.00" and charge.get("maximum") == "0.00":
                            charge.update({"is_slab": False})
                        else:
                            charge.update({"is_slab": True})
                else:
                    charge_serializer_update = []
                    charge_type = None

                ad_commission_queryset = AdCommissionCharges.objects.filter(service_provider=provider, is_deleted=False)
                if len(ad_commission_queryset) > 0:
                    global_commission_list = [
                        {
                            "commission_charges_id": commission_value.commission_charges_id,
                            "service_provider": commission_value.service_provider.pk,
                            "rate_type": commission_value.rate_type,
                            "minimum": commission_value.minimum,
                            "maximum": commission_value.maximum,
                            "is_slab": commission_value.is_slab
                        }
                        for commission_value in ad_commission_queryset
                    ]
                else:
                    global_commission_list = []

                service_name = AdService.objects.get(service_id=provider.service_id).service_name

                if provider.parent_name is None:
                    service_provider_data.append({
                        'parent_name': None,
                        'is_user_service_provider': True if PortalUserCharges.objects.filter(pu_id=int(user_id),
                                                                                             sp_id=provider.sp_id).exists() else False,
                        'sub_service_provider': [],
                        'sp_id': provider.sp_id,
                        'service_name': service_name,
                        'provider_name': provider.sp_name,
                        'provider_label': provider.label,
                        'tds_rate': provider.tds_rate,
                        'hsn_sac': provider.hsn_sac.hsnsac_id if provider.hsn_sac else None,
                        'hsn_sac_code': provider.hsn_sac.hsnsac_code if provider.hsn_sac else None,
                        'tax_rate': provider.hsn_sac.tax_rate if provider.hsn_sac else None,
                        'charge_type': charge_type,
                        'is_deactive': False,
                        'to_provide_charges': charge_serializer_update,
                        'global_commission': global_commission_list,
                    })
                else:
                    # sub_service_provider = AdSubServiceProvider.objects.filter(ssp_id=provider.parent_id.ssp_id).first()
                    print('user.id', user.id)
                    if provider.parent_name:
                        if provider.parent_name not in sub_service_provider_mapping:
                            sub_service_provider_mapping[provider.parent_name] = {
                                'parent_name': provider.parent_name,
                                'is_user_service_provider': True if PortalUserCharges.objects.filter(pu_id=int(user_id),
                                                                                                     sp_id=provider.sp_id).exists() else False,
                                'sub_service_provider': []
                            }

                        sub_service_provider_mapping[provider.parent_name]['sub_service_provider'].append({
                            'sp_id': provider.sp_id,
                            'service_name': service_name,
                            'provider_name': provider.sp_name,
                            'provider_label': provider.label,
                            'tds_rate': provider.tds_rate,
                            'hsn_sac': provider.hsn_sac.hsnsac_id if provider.hsn_sac else None,
                            'hsn_sac_code': provider.hsn_sac.hsnsac_code if provider.hsn_sac else None,
                            'tax_rate': provider.hsn_sac.tax_rate if provider.hsn_sac else None,
                            'charge_type': charge_type,
                            'is_deactive': False,
                            'to_provide_charges': charge_serializer_update,
                            'global_commission': global_commission_list,
                        })

            for ssp_id, data in sub_service_provider_mapping.items():
                service_provider_data.append(data)

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': service_provider_data
            }

            return Response({
                'status': 'success',
                'message': 'Service Provider Data with Charges',
                'data': paginated_response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def manual_debit(self, request):
        user_id = request.data.get('user_id')
        amount = request.data.get('amount')
        debit_from = request.data.get('debit_from')
        wallet_type = debit_from
        action_type = request.data.get('action_type', 'Manual Debit')
        label = request.data.get('label')
        description = request.data.get('description', '')

        if label == 'others':
            label = request.data.get('other_reason', '')

        # Validate required fields
        if not user_id or not amount or not debit_from:
            return Response({'status': 'error', 'message': 'Missing required fields.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = float(amount)
            if amount <= 0:
                return Response({'status': 'error', 'message': 'Invalid amount.'},
                                status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({'status': 'error', 'message': 'Amount must be a number.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            portal_user_instance = PortalUser.objects.get(id=user_id)
            wallet = PortalUserWallet.objects.get(pu=portal_user_instance)
        except PortalUser.DoesNotExist:
            return Response({'status': 'error', 'message': 'User not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        except PortalUserWallet.DoesNotExist:
            return Response({'status': 'error', 'message': 'Wallet not found for this user.'},
                            status=status.HTTP_404_NOT_FOUND)

        # Check balance before debiting
        if action_type == "Manual Debit":
            current_wallet_balance = getattr(wallet, debit_from, None)
            if current_wallet_balance is None:
                return Response({'status': 'error', 'message': 'Invalid wallet type.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if float(current_wallet_balance) < amount:
                return Response({'status': 'error', 'message': f'Insufficient funds in {debit_from.replace("_", " ")}.'},
                                status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                current_balance = float(getattr(wallet, debit_from))

                if action_type == "Manual Debit":
                    updated_balance = current_balance - amount
                else:  # Manual Credit
                    updated_balance = current_balance + amount

                setattr(wallet, debit_from, updated_balance)
                wallet.updated_at = now()
                wallet.save()

                WalletTrn.objects.create(
                    action_id=portal_user_instance.pk,
                    action_type=action_type,
                    pu_id=portal_user_instance.pk,
                    wl_label=label,
                    effectvie_wallet=debit_from,
                    effectvie_amt=amount,
                    effective_type='DR' if action_type == "Manual Debit" else 'CR',
                    current_balance=updated_balance,  # **Use updated balance of the right wallet**
                    wl_trn_dt=now(),
                )

            response_message = "Manual debit successful." if action_type == "Manual Debit" else "Manual Credit successful."
            return Response({'status': 'success', 'message': response_message},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            user_id = request.data.get('user_id')
            service_provider = request.data.get('service_provider')

            try:
                convert_service_provider = json.loads(service_provider)
            except json.JSONDecodeError:
                return Response({"status": "fail", "message": "service_provider must be valid JSON."},
                                status=status.HTTP_400_BAD_REQUEST)

            if not user_id:
                return Response({'status': 'fail', 'message': 'Distributor ID is required.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not service_provider:
                return Response({'status': 'fail', 'message': 'Service provider data is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # distributor = PortalUser.objects.get(pu_role='DISTRIBUTOR', id=distributor_id)
            users = PortalUser.objects.get(id=user_id)

            if not users:
                return Response({'status': 'fail', 'message': 'Users does not exist.'},
                                status=status.HTTP_404_NOT_FOUND)

            for data in convert_service_provider:
                if data['sp_id'] == '':
                    return Response({'status': 'fail', 'message': 'service provider ID is requried.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                service_provider_data = AdServiceProvider.objects.get(sp_id=data['sp_id'])
                distributor_charges = PortalUserCharges.objects.get(pu_id=users.id, sp=service_provider_data)
                for i in distributor_charges.puc_charges:
                    user_charge_data = i
                for i in convert_service_provider:
                    mark_value = i
                if not distributor_charges:
                    return Response({'status': 'fail', 'message': 'Users charges do not exist.'},
                                    status=status.HTTP_404_NOT_FOUND)

                if data['mark_value'] in ['', 'None']:
                    return Response({'status': 'fail', 'message': 'mark value are required.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                user_charge_data['rate'] = float(user_charge_data['rate'])
                mark_value['mark_value'] = float(mark_value['mark_value'])

                user_charge_data['rate'] += mark_value['mark_value']

                user_charge_data['rate'] = format(user_charge_data['rate'], ".2f")
                distributor_charges.puc_charges = [user_charge_data]
                distributor_charges.save()

            user_activity = {
                "table_id": distributor_charges.pk,
                "table_name": 'ad_portal_user_charges',
                "ua_action": 'Update',  # Action performed
                "ua_description": 'Users charges updated successfully.',  # Action description
                "created_by": request.user,  # Current user performing the action
                "request_data": dict(request.data),  # Request data
                "response_data": model_to_dict(distributor_charges)
            }

            add_user_activity(user_activity)

            return Response({'status': 'success', 'message': 'Users charges updated successfully.'},
                            status=status.HTTP_200_OK)

        except AdServiceProvider.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Service provider does not exist.'},
                            status=status.HTTP_404_NOT_FOUND)

        except PortalUserCharges.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Users charges do not exist.'},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserServicesChargesAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        sp_id = request.data.get('sp_id')
        user_id = request.data.get('user_id')
        service_id = request.data.get('service_id')
        hsn_sac_id = request.data.get('hsn_sac_id')
        search_txt = request.data.get('search')
        start_date = request.data.get('start_date', None)
        end_date = request.data.get('end_date', datetime.datetime.now().date())
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)

        try:
            if not page_size: return Response({'status': 'fail', 'message': 'page_size is required.'},
                                              status=status.HTTP_400_BAD_REQUEST)
            if not user_id: return Response({'status': 'fail', 'message': 'user_id is required.'},
                                            status=status.HTTP_400_BAD_REQUEST)
            if isnumber(page_size) == False: return Response(
                {'status': 'fail', 'message': 'page_size must contain only digits.'},
                status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if isnumber(page_number) == False: return Response(
                    {'status': 'fail', 'message': 'page_number must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if sp_id:
                if isnumber(sp_id) == False: return Response(
                    {'status': 'fail', 'message': 'sp_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if service_id:
                if isnumber(service_id) == False: return Response(
                    {'status': 'fail', 'message': 'service_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if hsn_sac_id:
                if isnumber(hsn_sac_id) == False: return Response(
                    {'status': 'fail', 'message': 'hsn_sac_id must contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            user = PortalUser.objects.get(id=user_id)

            queryset = AdServiceProvider.objects.filter(is_deleted=False, sa_provided=True, is_deactive=False)

            
            blocked_sp_ids = AdServiceProvider.objects.filter(
                for_instant__isnull=False
            ).values_list('for_instant', flat=True).distinct()

            queryset = queryset.exclude(sp_id__in=blocked_sp_ids)

            if start_date:
                queryset = queryset.filter(created_at__date__range=[start_date, end_date])
            if sp_id:
                queryset = queryset.filter(pk=sp_id)
            if service_id:
                queryset = queryset.filter(service_id=service_id)
            if hsn_sac_id:
                queryset = queryset.filter(hsn_sac_id=hsn_sac_id)
            if search_txt:
                queryset = queryset.filter(
                    Q(service__service_name__icontains=search_txt) |
                    Q(sp_name__icontains=search_txt) |
                    Q(label__icontains=search_txt) |
                    Q(hsn_sac__hsnsac_code__icontains=search_txt)
                )

            queryset = queryset.order_by('-pk')

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            # If no data found, return an empty result with pagination metadata
            if not queryset.exists():
                return Response({
                    'status': 'fail',
                    'message': 'Service Provider Data not found.',
                    'data': {
                        'total_pages': 0,
                        'current_page': 0,
                        'total_items': 0,
                        'results': []
                    }
                }, status=status.HTTP_200_OK)

            # For each service provider, fetch related charges
            service_provider_data = []
            # Initialize a dictionary to group providers by their sub_service_provider
            sub_service_provider_mapping = {}
            for provider in page_obj:

                service_name = AdService.objects.get(service_id=provider.service.service_id).service_name
                portal_user_charges = PortalUserCharges.objects.filter(pu_id=user_id, sp=provider)

                charges = None
                hierarchy_charges = None
                terminal_with_role = PosDevice.objects.filter(pu=user).values_list('terminal', flat=True)  # change

                # if service_name != 'BBPS':
                if portal_user_charges.exists():
                    if portal_user_charges:
                        charges = portal_user_charges.first().puc_charges  # Convert the queryset to a list
                    else:
                        charges = []

                else:
                    # Fetch user details
                    user_details = PortalUserDetails.objects.filter(pu_id=user_id).first()

                    if user_details and user_details.dh:
                        # Fetch distributor hierarchy data
                        if portal_user_charges.exists():
                            hierarchy_charges = portal_user_charges.first().puc_charges

                        else:
                            dh_data = user_details.dh
                            if dh_data:
                                pass
                            else:
                                dh_data = None
                            if provider.service.is_global == True and provider.service.is_table_config == False:
                                hierarchy_charges_obj = HierarchyCharges.objects.filter(dh=dh_data, sp=provider).first()
                                if hierarchy_charges_obj:
                                    hierarchy_charges = hierarchy_charges_obj.hc_charges  # Access the `hc_charges` field directly
                                else:
                                    hierarchy_charges = None  # Default value if no records found
                            else:
                                hierarchy_charges = None

                    if hierarchy_charges:
                        charges = hierarchy_charges  # Convert the queryset to a list
                    else:
                        charges = []

                portal_charges = PortalUserCharges.objects.filter(pu_id=int(user_id), sp_id=provider.sp_id).first()
                if portal_charges:
                    if portal_charges.is_deactive == True:
                        is_user_service_provider = True
                    else:
                        is_user_service_provider = False
                else:
                    is_user_service_provider = True
                service_provider_data.append({
                    'parent_name': None,
                    'is_user_service_provider': is_user_service_provider,
                    'sub_service_provider': [],
                    'sp_id': provider.sp_id,
                    'service_name': service_name,
                    'is_global': provider.service.is_global,
                    'is_table_config': provider.service.is_table_config,
                    'provider_name': provider.sp_name,
                    'provider_label': provider.label,
                    'tds_rate': provider.tds_rate,
                    'hsn_sac': provider.hsn_sac.hsnsac_id if provider.hsn_sac else None,
                    'hsn_sac_code': provider.hsn_sac.hsnsac_code if provider.hsn_sac else None,
                    'tax_rate': provider.hsn_sac.tax_rate if provider.hsn_sac else None,
                    'charges': charges,
                    'terminal': terminal_with_role,
                    'roles': user.pu_role,
                    'is_instant': provider.is_instant,
                    'for_instant_id': provider.for_instant.sp_id if provider.for_instant else None,
                    'is_instant_deactive': False,  # Default value
                })

                if provider.is_instant and provider.for_instant:
                    instant_charges = PortalUserCharges.objects.filter(
                        pu_id=user_id,
                        sp=provider.for_instant
                    ).first()
                    
                    if instant_charges:
                        # Update the last appended item
                        service_provider_data[-1]['is_instant_deactive'] = instant_charges.is_deactive

            for ssp_id, data in sub_service_provider_mapping.items():
                service_provider_data.append(data)

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': service_provider_data
            }

            return Response(
                {'status': 'success', 'message': 'Service Provider Data with Charges', 'data': paginated_response_data},
                status=status.HTTP_200_OK)

        except AdService.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Service not found.', 'data': {}},
                            status=status.HTTP_404_NOT_FOUND)

        except DistributorHierarchy.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Distributor Hierarchy not found.', 'data': {}},
                            status=status.HTTP_404_NOT_FOUND)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User not found.', 'data': {}},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # def toggle_activation(self, instance, activate, success_message, deactivate_message):
    #     print('activate', activate)
    #     if activate:
    #         instance.is_deactive = False
    #         instance.save()
    #         return {'status': 'success', 'message': success_message}
    #     else:
    #         instance.is_deactive = True
    #         instance.save()
    #         return {'status': 'success', 'message': deactivate_message}


    def toggle_activation(self, instance, activate, success_message, deactivate_message, service_provider, portal_user):
        print('activate', activate)
        if activate:
            instance.is_deactive = False
            instance.save()
            message = success_message
        else:
            instance.is_deactive = True
            instance.save()
            message = deactivate_message
        
        
        
        # Instant provider logic
        if service_provider.is_instant and service_provider.for_instant:
            instant_provider = service_provider.for_instant
            
            instant_charges = PortalUserCharges.objects.filter(
                pu_id=portal_user.pk,
                sp=instant_provider
            ).first()
            
            
            if instant_charges:
                instant_charges.is_deactive = instance.is_deactive
                instant_charges.save()
            else:
                try:
                    user_details = PortalUserDetails.objects.filter(pu=portal_user).first()
                    dh_id = user_details.dh.dh_id if user_details and user_details.dh else None
                    
                    PortalUserCharges.objects.create(
                        sp_id=instant_provider.sp_id,
                        dh_id=dh_id,
                        pu_id=portal_user.pk,
                        parent_id=user_details.created_by if user_details else None,
                        puc_charges=[], 
                        is_deactive=instance.is_deactive,  
                        created_by=portal_user
                    )
                except Exception as e:
                    print(f"Error creating instant provider: {e}")
        else:
            print(f"Condition not met: is_instant={service_provider.is_instant}, for_instant={service_provider.for_instant}")
        
        return {'status': 'success', 'message': message}

    @transaction.atomic
    def put(self, request):
        sp_id = request.data.get('sp_id')
        user_id = request.data.get('user_id')

        if not sp_id or not user_id:
            return Response({'status': 'fail', 'message': 'Missing required parameters: sp_id or user_id.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            # Fetch user hierarchy
            users_list = fetch_user_hierarchy(user_id)

            # Fetch service provider and service details
            service_provider = AdServiceProvider.objects.get(sp_id=sp_id)
            service_data = service_provider.service

            def create_or_toggle_charges(portal_user, dh_id, service_provider, service_data, dh_value):
                # Check if charges exist
                portal_user_charges = PortalUserCharges.objects.filter(pu_id=portal_user.pk,
                                                                       sp=service_provider).first()

                if not portal_user_charges:
                    # Assign charges
                    if service_data.is_global and not service_data.is_table_config:
                        hierarchy_charges = HierarchyCharges.objects.filter(
                            dh=dh_id, sp=service_provider.sp_id, is_deleted=False
                        )
                        for charges in hierarchy_charges:
                            PortalUserCharges.objects.create(
                                sp_id=sp_id,
                                dh_id=dh_id,
                                pu_id=portal_user.pk,
                                parent_id=dh_value.created_by if dh_value else None,
                                puc_charges=charges.hc_charges,
                                is_deactive=False,
                                created_by=portal_user
                            )
                    else:
                        def ensure_user_charge_with_hierarchy(user_id, visited_ids=None):
                            if visited_ids is None:
                                visited_ids = set()
                            
                            if user_id in visited_ids:
                                return
                            visited_ids.add(user_id)

                            try:
                                user = PortalUser.objects.get(id=user_id)
                            except PortalUser.DoesNotExist:
                                print(f"User {user_id} does not exist")
                                return

                            # user_charge_exists = UserCharge.objects.filter(user_id=user_id).exists()
                            # if not user_charge_exists:
                            #     print(f"[CREATE] Creating UserCharge for user {user_id} ({user.pu_role})")
                            #     base_charges = PGBaseCharge.objects.filter(role__iexact=user.pu_role)

                            #     if base_charges.exists():
                            #         with transaction.atomic():
                            #             for base_charge in base_charges:
                            #                 exists = UserCharge.objects.filter(
                            #                     user_id=user_id,
                            #                     pg=base_charge.pg,
                            #                     card_type=base_charge.card_type
                            #                 ).exists()
                            #                 if not exists:
                            #                     UserCharge.objects.create(
                            #                         user_id=user,
                            #                         pg=base_charge.pg,
                            #                         card_type=base_charge.card_type,
                            #                         charge_percent=base_charge.charge_percent
                            #                     )
                            #     else:
                            #         print(f"[SKIP] No base charges for role {user.pu_role}")
                            
                            user_charge_exists = UserCharge.objects.filter(user_id=user_id).exists()
                            if not user_charge_exists:
                                print(f"[CREATE] Creating UserCharge for user {user_id} ({user.pu_role})")

                                # Map username prefix to role
                                username_prefix = user.username[:2].upper()
                                prefix_role_map = {
                                    "SD": "SUPER DISTRIBUTOR",
                                    "MD": "MASTER DISTRIBUTOR",
                                    "DT": "DISTRIBUTOR",
                                    "RT": "RETAILER",
                                }

                                if username_prefix in prefix_role_map:
                                    mapped_role = prefix_role_map[username_prefix]
                                else:
                                    # Get admin user's role as fallback
                                    admin_user = PortalUser.objects.filter(pu_role__iexact="ADMIN").first()
                                    if admin_user:
                                        mapped_role = admin_user.pu_role.upper()
                                    else:
                                        # If no admin user found, fallback to user’s own role
                                        mapped_role = user.pu_role.upper()

                                base_charges = PGBaseCharge.objects.filter(role__iexact=mapped_role)

                                if base_charges.exists():
                                    with transaction.atomic():
                                        for base_charge in base_charges:
                                            exists = UserCharge.objects.filter(
                                                user_id=user_id,
                                                pg=base_charge.pg,
                                                card_type=base_charge.card_type
                                            ).exists()
                                            if not exists:
                                                UserCharge.objects.create(
                                                    user=user,
                                                    pg=base_charge.pg,
                                                    card_type=base_charge.card_type,
                                                    charge_percent=base_charge.charge_percent
                                                )
                                else:
                                    print(f"[SKIP] No base charges for role {mapped_role}")

                            try:
                                user_details = PortalUserDetails.objects.get(pu=user)
                                parent_id = user_details.created_by
                                if parent_id:
                                    ensure_user_charge_with_hierarchy(parent_id, visited_ids)
                            except PortalUserDetails.DoesNotExist:
                                print(f"[SKIP] No user details for user {user_id}")
                        ensure_user_charge_with_hierarchy(user_id)
                        PortalUserCharges.objects.create(
                            sp_id=sp_id,
                            dh_id=dh_id,
                            pu_id=portal_user.pk,
                            parent_id=dh_value.created_by if dh_value else None,
                            puc_charges=[],
                            is_deactive=False,
                            created_by=portal_user
                        )
                    

                    if service_provider.is_instant and service_provider.for_instant:
                        instant_provider = service_provider.for_instant
                        
                        instant_exists = PortalUserCharges.objects.filter(
                            pu_id=portal_user.pk,
                            sp=instant_provider
                        ).exists()
                        
                        if not instant_exists:
                            PortalUserCharges.objects.create(
                                sp_id=instant_provider.sp_id,
                                dh_id=dh_id,
                                pu_id=portal_user.pk,
                                parent_id=dh_value.created_by if dh_value else None,
                                puc_charges=[],  
                                is_deactive=False,  
                                created_by=portal_user
                            )
                        else:
                            instant_charges = PortalUserCharges.objects.filter(
                                pu_id=portal_user.pk,
                                sp=instant_provider
                            ).first()
                            instant_charges.is_deactive = False
                            instant_charges.save()

                    return {'status': 'success', 'message': 'Service Provider Activated Successfully.'}
                else:
                    # Toggle activation
                    # return self.toggle_activation(
                    #     portal_user_charges, portal_user_charges.is_deactive,
                    #     'Service Provider Activated Successfully.',
                    #     'Service Provider Deactivated Successfully.'
                    # )

                    result = self.toggle_activation(
                        portal_user_charges, 
                        portal_user_charges.is_deactive,
                        'Service Provider Deactivated Successfully.',
                        'Service Provider Activated Successfully.',
                        service_provider,  
                        portal_user        
                    )
                    
                    return result  

            # Process each user in the hierarchy
            for user in users_list:
                portal_user = PortalUser.objects.get(id=user['user_id'])
                dh_value = PortalUserDetails.objects.filter(pu=portal_user).select_related('dh').first()
                dh_id = dh_value.dh.dh_id if dh_value and dh_value.dh else None

                # Create or toggle charges
                message = create_or_toggle_charges(portal_user, dh_id, service_provider, service_data, dh_value)

            return Response(message, status=status.HTTP_200_OK)

        except AdServiceProvider.DoesNotExist:
            return Response({'status': 'error', 'message': 'Service Provider not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        except PortalUser.DoesNotExist:
            return Response({'status': 'error', 'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @transaction.atomic
    def patch(self, request):
        sp_id = request.data.get('sp_id')
        user_id = request.data.get('user_id')
        
        if not sp_id or not user_id:
            return Response(
                {'status': 'fail', 'message': 'Missing required parameters: sp_id or user_id.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service_provider = AdServiceProvider.objects.get(sp_id=sp_id)
            
            # Check if this service has an instant provider
            if not service_provider.is_instant or not service_provider.for_instant:
                return Response(
                    {'status': 'fail', 'message': 'This service does not have an instant provider.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            instant_provider = service_provider.for_instant
            users_list = fetch_user_hierarchy(user_id)
            
            for user in users_list:
                portal_user = PortalUser.objects.get(id=user['user_id'])
                
                # Find instant provider charges
                instant_charges = PortalUserCharges.objects.filter(
                    pu_id=portal_user.pk,
                    sp=instant_provider
                ).first()
                
                if instant_charges:
                    # Toggle instant provider
                    instant_charges.is_deactive = not instant_charges.is_deactive
                    instant_charges.save()
                    print(f"{'🔴 Deactivated' if instant_charges.is_deactive else '🟢 Activated'} instant provider for user {portal_user.pk}")
            
            # Check final status for message
            sample_charges = PortalUserCharges.objects.filter(
                pu_id=user_id,
                sp=instant_provider
            ).first()
            
            if sample_charges and sample_charges.is_deactive:
                message = 'Instant Provider Deactivated Successfully.'
            else:
                message = 'Instant Provider Activated Successfully.'
            
            return Response(
                {'status': 'success', 'message': message},
                status=status.HTTP_200_OK
            )
            
        except AdServiceProvider.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'Service Provider not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'status': 'error', 'message': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# 1PARTNERS CHANGE USERNAME AND PASSWORD
class CredentialForgotAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        if 'email' in request.data and 'code' in request.data:
            return self.set_password_email(request)
        elif 'pu_contact_no' in request.data and 'code' in request.data:
            return self.set_password_mobile(request)
        elif 'email' in request.data:
            return self.email_send_otp(request)
        elif 'pu_contact_no' in request.data:
            return self.mobile_send_otp(request)

        return Response({
            "status": "error",
            "message": "Please provide valid input: 'email' or 'pu_contact_no' with optional 'code'."
        }, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    def email_send_otp(self, request):
        pu_email = request.data.get('email')

        portal_user = PortalUser.objects.filter(pu_email=pu_email).first()
        if not portal_user:
            return Response({
                "status": "error",
                "message": "No user found with the provided email."
            }, status=status.HTTP_404_NOT_FOUND)

        # Generate and save OTP
        code = get_random_string(length=6, allowed_chars='0123456789')
        portal_user.verify_code = code
        portal_user.verify_code_expire_at = timezone.now() + timedelta(minutes=10)
        portal_user.save()

        # Send OTP via email
        subject = "Your OTP for Password Reset"
        html_content = f"""
            <p>Hello,</p>
            <p>Your One-Time Password (OTP) is <strong>{code}</strong>.</p>
            <p>This OTP will expire in 10 minutes.</p>
        """
        email_message = EmailMultiAlternatives(
            subject, strip_tags(html_content), settings.EMAIL_HOST_USER, [pu_email]
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.send()

        return Response({
            "status": "success",
            "message": "OTP sent successfully to the provided email.",
            "data": {"otp": code}
        }, status=status.HTTP_200_OK)

    @transaction.atomic
    def mobile_send_otp(self, request):
        pu_contact_no = request.data.get('pu_contact_no')

        portal_user = PortalUser.objects.filter(pu_contact_no=pu_contact_no).first()
        if not portal_user:
            return Response({
                "status": "error",
                "message": "No user found with the provided contact number."
            }, status=status.HTTP_404_NOT_FOUND)

        # Generate and save OTP
        code = get_random_string(length=6, allowed_chars='0123456789')
        portal_user.verify_code = code
        portal_user.verify_code_expire_at = timezone.now() + timedelta(minutes=10)
        portal_user.save()

        sms_response = mobicomm_submit_sms(pu_contact_no, code)
        if sms_response.status_code == 200:
            return Response({
                "status": "success",
                "message": "OTP sent successfully to the provided contact number.",
                "data": {"otp": code}
            }, status=status.HTTP_200_OK)

        return Response({
            "status": "error",
            "message": "Failed to send OTP to the provided contact number."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @transaction.atomic
    def set_password_email(self, request):
        pu_email = request.data.get('email')
        code = request.data.get('code')

        portal_user = PortalUser.objects.filter(pu_email=pu_email).first()
        if not portal_user or portal_user.verify_code != code:
            return Response({
                "status": "error",
                "message": "Invalid email or OTP."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Reset verify code and generate token
        portal_user.verify_code = None
        portal_user.verify_code_expire_at = None
        portal_user.save()

        access_token = get_tokens_for_user(portal_user, timedelta(minutes=30))

        return Response({
            "status": "success",
            "message": "Email and OTP verified. Token generated.",
            'data': {'user_role': portal_user.pu_role, 'is_generated': False, 'token': str(access_token)}
        }, status=status.HTTP_200_OK)

    @transaction.atomic
    def set_password_mobile(self, request):
        pu_contact_no = request.data.get('pu_contact_no')
        code = request.data.get('code')

        portal_user = PortalUser.objects.filter(pu_contact_no=pu_contact_no).first()
        if not portal_user or portal_user.verify_code != code:
            return Response({
                "status": "error",
                "message": "Invalid contact number or OTP."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Reset verify code and generate token
        portal_user.verify_code = None
        portal_user.verify_code_expire_at = None
        portal_user.save()

        access_token = get_tokens_for_user(portal_user, timedelta(minutes=30))

        return Response({
            "status": "success",
            "message": "Mobile number and OTP verified. Token generated.",
            'data': {'user_role': portal_user.pu_role, 'is_generated': False, 'token': str(access_token)}
        }, status=status.HTTP_200_OK)


# 2PARTNERS SET USER PASS
class ChangePasswordAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]
    parser_classes = (MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request):
        try:
            is_forgot = request.data.get('is_forgot', False)
            new_password = request.data.get('password')

            if not new_password:
                return Response(
                    {"status": "error", "message": "New password is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if new_password:
                if len(new_password) < 8:
                    return Response(
                        {"status": "fail", "message": "Password must be at least 8 characters long."},
                        status=status.HTTP_400_BAD_REQUEST)

                if len(new_password) > 12:
                    return Response({"status": "fail", "message": "Password cannot be longer than 12 characters."},
                                    status=status.HTTP_400_BAD_REQUEST)

            user = PortalUser.objects.get(id=request.user.id)

            user.password = make_password(new_password)
            user.is_default_change = True
            user.save()

            user_activity = {
                "table_id": user.pk,
                "table_name": 'ad_portal_user',
                "ua_action": 'Change Password',  # Action performed
                "ua_description": 'User Change Password Successfully.',  # Action description
                "created_by": request.user,  # Current user performing the action
                "request_data": dict(request.data),  # Request data
                "response_data": model_to_dict(user)
            }

            add_user_activity(user_activity)

            return Response(
                {"status": "success", "message": "Password reset successfully."}, status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response(
                {"status": "error", "message": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def put(self, request):
        try:
            username = request.data.get('username')
            password = request.data.get('password')

            user = PortalUser.objects.get(id=request.user.id)

            if not username and not password:
                return Response({"status": "error", "message": "At least one of username or password is required."},
                                status=status.HTTP_400_BAD_REQUEST)

            if username:
                user.username = username

            if password:
                if len(password) < 8:
                    return Response(
                        {"status": "fail", "message": "Password must be at least 8 characters long."},
                        status=status.HTTP_400_BAD_REQUEST)

                if len(password) > 12:
                    return Response({"status": "fail", "message": "Password cannot be longer than 12 characters."},
                                    status=status.HTTP_400_BAD_REQUEST)
                user.password = make_password(password)

            user.save()

            return Response({"status": "success", "message": "User details updated successfully"},
                            status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response({"status": "error", "message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class SetMpinAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]
    parser_classes = (MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request):
        try:
            # Get the input data from the request
            is_forgot = request.data.get('is_forgot', False)
            new_mpin = request.data.get('mpin')

            # Validate new MPIN input
            if not new_mpin:
                return Response(
                    {"status": "error", "message": "New MPIN is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate MPIN length
            if len(new_mpin) < 4:
                return Response(
                    {"status": "fail", "message": "MPIN must be at least 4 digits long."},
                    status=status.HTTP_400_BAD_REQUEST)

            if len(new_mpin) > 6:
                return Response(
                    {"status": "fail", "message": "MPIN cannot be longer than 6 digits."},
                    status=status.HTTP_400_BAD_REQUEST)

            if not new_mpin.isdigit():
                return Response(
                    {"status": "fail", "message": "MPIN must be numeric."},
                    status=status.HTTP_400_BAD_REQUEST)

            # Get the user and update their MPIN
            user = PortalUser.objects.get(id=request.user.id)

            user.mpin = new_mpin  # Assuming there's a field `mpin` in the `PortalUser` model.
            user.is_default_change = True  # Set to True, similar to the password change process
            user.save()

            # Log the activity for the user
            user_activity = {
                "table_id": user.pk,
                "table_name": 'ad_portal_user',
                "ua_action": 'Change MPIN',  # Action performed
                "ua_description": 'User changed their MPIN successfully.',  # Action description
                "created_by": request.user,  # Current user performing the action
                "request_data": dict(request.data),  # Request data
                "response_data": model_to_dict(user)
            }

            add_user_activity(user_activity)

            return Response(
                {"status": "success", "message": "MPIN changed successfully."},
                status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response(
                {"status": "error", "message": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def put(self, request):
        try:
            mpin = request.data.get('mpin')

            user = PortalUser.objects.get(id=request.user.id)

            if not mpin:
                return Response({"status": "error", "message": "MPIN is required."},
                                status=status.HTTP_400_BAD_REQUEST)

            if len(mpin) < 4:
                return Response(
                    {"status": "fail", "message": "MPIN must be at least 4 digits long."},
                    status=status.HTTP_400_BAD_REQUEST)

            if len(mpin) > 6:
                return Response(
                    {"status": "fail", "message": "MPIN cannot be longer than 6 digits."},
                    status=status.HTTP_400_BAD_REQUEST)

            if not mpin.isdigit():
                return Response(
                    {"status": "fail", "message": "MPIN must be numeric."},
                    status=status.HTTP_400_BAD_REQUEST)

            # Update the user's MPIN
            user.mpin = mpin
            user.save()

            return Response({"status": "success", "message": "User MPIN updated successfully"},
                            status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response({"status": "error", "message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# PARTNERS LOGIN
class UserLoginAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        is_app = request.data.get('is_app', False)

        # Static testing bypass (does not hit database)
        if username == 'test_static' and password == 'test_pass':
            return Response({
                'status': 'success',
                'message': 'Static login test successful without DB.',
                'user_role': 'TEST_ADMIN',
                'user_id': 999
            }, status=status.HTTP_200_OK)

        # Validate input
        if not username or not password:
            return Response({'status': 'fail', 'message': 'Missing username or password.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            # Retrieve user based on username
            user = PortalUser.objects.get(username=username)

            # Prevent admin from logging in via the app if `is_app` is true
            if is_app and user.pu_role == 'ADMIN':
                return Response({'status': 'fail', 'message': 'Admin users cannot log in through the app.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if user.pu_role == 'RETAILER':
                last_login_log = PortalUserLoginLogs.objects.filter(pu_user=user).order_by('-created_at').first()
                cutoff_date = timezone.now() - timedelta(days=30)

                if last_login_log:
                    if last_login_log.created_at < cutoff_date:
                        if not user.is_deactive:
                            user.is_deactive = True
                            user.pu_status = 'INACTIVE'
                            user.save(update_fields=['is_deactive', 'pu_status'])
                        return Response({
                            'status': 'fail',
                            'message': 'Your Account is locked due to inactivity. Please contact admin.'
                        }, status=status.HTTP_403_FORBIDDEN)
                    else:
                        # Reactivate if previously deactivated
                        if user.is_deactive:
                            user.is_deactive = False
                            user.pu_status = 'APPROVED'
                            user.save(update_fields=['is_deactive', 'pu_status'])

                


            if user.pu_status in ['REJECT'] and user.pu_role != 'ADMIN':
                return Response(
                    {
                        'status': 'fail',
                        'message': 'We noticed your account status is not approved yet. It is either pending or has been rejected. Please reach out to our support team to resolve this quickly.'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verify password
            if check_password(password, user.password):
                access_token = get_tokens_for_user(user, timedelta(days=1))
                load_dotenv()
                device_active = 'device_number'
                number = os.getenv(device_active, '1')
                get_user_log = PortalUserLoginLogs.objects.filter(pu_user=user, is_expire=False)
                if len(get_user_log) == int(number):
                    if get_user_log[0].expire_datetime <= timezone.now():
                        old_log = get_user_log[0]
                        old_log.is_expire = True
                        old_log.save()
                    else:
                        old_log = get_user_log[0]
                        old_log.is_expire = True
                        old_log.save()

                # Create new login log
                PortalUserLoginLogs.objects.create(
                    pu_user=user,
                    pu_user_role=user.pu_role,
                    pu_token=str(access_token),
                    browser_type=request.META.get('HTTP_USER_AGENT', 'Unknown'),
                    expire_datetime=timezone.now() + timedelta(hours=24)
                )
                is_default_mpin = None
                if user.mpin == 0:
                    is_default_mpin = True
                else:
                    is_default_mpin = False
                # Successful login response
                response_data = {
                    'status': 'success',
                    'message': 'Login successful.',
                    'user_role': user.pu_role,
                    'user_id': user.pk,
                    'is_kyc_verify': user.is_kyc_verify,
                    'is_default_change': user.is_default_change,
                    'is_mpin':is_default_mpin,
                    'access_token': str(access_token)
                }
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                return Response({'status': 'fail', 'message': 'Invalid password.'}, status=status.HTTP_401_UNAUTHORIZED)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User with this username does not exist.'},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserProfileAPIView(APIView):
    """
    API view to handle the user profile.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        """
        API endpoint for retrieving the authenticated user's details.

        This endpoint requires authentication with a JWT token.
        """

        try:
            users = PortalUser.objects.get(id=request.user.id)

            if users.pu_role == "ADMIN":
                serializer = PortalUserSerializer(users, context={'request': request})
                user_data = serializer.data

                response_data = {
                    'status': 'success',
                    'message': 'Admin user data retrieved successfully',
                    'data': user_data
                }
                return Response(response_data, status=status.HTTP_200_OK)

            # Fetch user details and wallet for other roles
            user_details = PortalUserDetails.objects.filter(pu=users).first()
            wallet = PortalUserWallet.objects.filter(pu=users).first()

            wallet_serializer = PortalUserWalletSerializer(wallet, context={'request': request})
            serializer = PortalUserSerializer(users, context={'request': request})

            user_data = serializer.data
            wallet_data = wallet_serializer.data
            user_data['wallet'] = wallet_data

            if users.pu_role == "DISTRIBUTOR":
                try:
                    puc_obj = PortalUserCharges.objects.filter(pu_id=request.user.id).first()
                    distributor_hierarchy = DistributorHierarchy.objects.get(dh_id=user_details.dh_id)

                    if distributor_hierarchy.dh_name == 'SUPER DISTRIBUTOR':
                        partner_category = "SUPER DISTRIBUTOR"
                    elif distributor_hierarchy.dh_name == 'MASTER DISTRIBUTOR':
                        partner_category = "MASTER DISTRIBUTOR"
                    else:
                        partner_category = "DISTRIBUTOR"

                    user_data['partner_category'] = partner_category
                    user_data['distributor_wallet'] = {
                        'main_wallet': wallet.main_wallet,
                        'cashin_wallet': wallet.cashin_wallet
                    }
                    user_data['aadhaar_card'] = user_details.aadhaar_card
                    user_data['pan_card'] = user_details.pan_card
                    user_data['is_kyc_verified'] = users.is_kyc_verify
                    user_data['shop_gst_number'] = user_details.shop_gst_number
                    user_data['shop_address'] = user_details.shop_address
                    user_data['shop_name'] = user_details.shop_name
                    user_data['gst_type'] = user_details.busniess_type
                    user_data['is_under_review'] = users.under_review
                    user_data['upload_status'] = user_details.upload_status
                    user_data['security_upload_status'] = user_details.security_upload_status
                    user_data['pdf_upload_status'] = user_details.pdf_upload_status
                    user_data['onboarding_check_num'] = user_details.onboarding_check_num
                    user_data['security_check_num'] = user_details.security_check_num
                    user_data['created_at'] = user_details.created_at.strftime("%d-%m-%Y")
                    user_data['profile_image'] = (
                        request.build_absolute_uri(f"{settings.MEDIA_URL}{user_details.doc_images.get('profile_image')}")
                        .replace("\\", "/")
                        if user_details.doc_images and user_details.doc_images.get('profile_image')
                        else None
                    )


                except DistributorHierarchy.DoesNotExist:
                    return Response({
                        'status': 'fail',
                        'message': 'Partner Category Does Not Exist'
                    }, status=status.HTTP_404_NOT_FOUND)

            # Handle logic for RETAILER role
            if users.pu_role == 'RETAILER':
                user_data['partner_category'] = "RETAILER"
                user_data['retailer_wallet'] = {
                    'main_wallet': wallet.main_wallet,
                    'cashin_wallet': wallet.cashin_wallet,
                    'pg_wallet': wallet.pg_wallet
                }
                user_data['aadhaar_card'] = user_details.aadhaar_card
                user_data['pan_card'] = user_details.pan_card
                user_data['is_kyc_verified'] = users.is_kyc_verify
                user_data['shop_gst_number'] = user_details.shop_gst_number
                user_data['shop_address'] = user_details.shop_address
                user_data['shop_name'] = user_details.shop_name
                user_data['gst_type'] = user_details.busniess_type
                user_data['is_under_review'] = users.under_review
                user_data['upload_status'] = user_details.upload_status
                user_data['security_upload_status'] = user_details.security_upload_status
                user_data['pdf_upload_status'] = user_details.pdf_upload_status
                user_data['created_at'] = user_details.created_at.strftime("%d-%m-%Y")
                user_data['profile_image'] = (
                        request.build_absolute_uri(f"{settings.MEDIA_URL}{user_details.doc_images.get('profile_image')}")
                        .replace("\\", "/")
                        if user_details.doc_images and user_details.doc_images.get('profile_image')
                        else None
                )



            response_data = {
                'status': 'success',
                'message': 'User data retrieved successfully',
                'data': user_data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            response_error = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_error, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserStatusChangeAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        user_id = request.data.get('user_id')
        pu_status = request.data.get('status')
        reason = request.data.get('reason', None)

        if not user_id:
            return Response({"status": "fail", "message": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not pu_status:
            return Response({"status": "fail", "message": "Status is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not reason:
            return Response({"status": "fail", "message": "Reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        if pu_status not in ['APPROVED', 'REJECTED']:
            return Response({
                "status": "fail",
                "message": "Invalid status. Allowed values are 'APPROVED' or 'REJECTED'."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                portal_user = PortalUser.objects.get(id=user_id)

                if portal_user.pu_status != "PENDING":
                    return Response({
                        "status": "fail",
                        "message": "Status can only be updated is PENDING."
                    }, status=status.HTTP_400_BAD_REQUEST)

                portal_user.pu_status = pu_status
                portal_user.pu_reason = reason
                portal_user.updated_at = timezone.now()

                if pu_status == 'APPROVED':
                    portal_user.under_review = False
                portal_user.save()

            return Response({"status": "success", "message": "User status successfully updated.", },
                            status=status.HTTP_200_OK)

        except PortalUser.DoesNotExist:
            return Response({"status": "fail", "message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({
                "status": "error",
                "message": f"Internal server error:  {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BankDetailsAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        try:
            if 'deposite_category' in request.data and 'bank_name' in request.data and 'ifsc_code' in request.data and 'branch_name' in request.data and 'account_type' in request.data and 'account_number' in request.data:
                return self.add_bank_details(request)
            elif 'page_size' in request.data or 'page_size' in request.data:
                return self.get_bank_details(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid request'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def add_bank_details(self, request):
        try:
            deposite_category = request.data.get('deposite_category')
            bank_name = request.data.get('bank_name')
            ifsc_code = request.data.get('ifsc_code')
            branch_name = request.data.get('branch_name')
            account_type = request.data.get('account_type')
            account_number = request.data.get('account_number')


            required_fields = ['deposite_category', 'bank_name', 'ifsc_code', 'branch_name', 'account_type',
                               'account_number']

            missing_fields = [field for field in required_fields if not request.data.get(field)]

            if missing_fields:
                return Response(
                    {'status': 'fail',
                     'message': f'Required fields are empty: {", ".join(missing_fields)}. provide all required fields and try again'},
                    status=status.HTTP_400_BAD_REQUEST)


            bank_name_validation = isstring(bank_name)
            print('bank_name_validation----->>>>',bank_name_validation)
            if bank_name_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid bank name. It should be a string.'},
                                status=status.HTTP_400_BAD_REQUEST)

            ifsc_code_validation = is_valid_ifsc(ifsc_code)
            if ifsc_code_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid IFSC code. Please check the format.'},
                                status=status.HTTP_400_BAD_REQUEST)

            branch_name_validation = isstring(branch_name)
            if branch_name_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid branch name. It should be a string.'},
                                status=status.HTTP_400_BAD_REQUEST)

            account_type_validation = isstring(account_type)
            if account_type_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid account type. It should be a string.'},
                                status=status.HTTP_400_BAD_REQUEST)

            account_number_validation = isnumber(account_number)
            if account_number_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid account number. It should contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)

            validation_account_number = validate_account_number(account_number)
            if validation_account_number == False:
                return Response({'status': 'fail',
                                 'message': 'Invalid account number. It should contain only digits and be between 11 and 16 characters long.'},
                                status=status.HTTP_400_BAD_REQUEST)

            deposite = json.loads(deposite_category)
            get_exists_bank = BankDetails.objects.filter(bank_name=bank_name, ifsc_code=ifsc_code,
                                                         account_number=account_number, is_delete=False).first()
            if get_exists_bank:
                return Response({'status': 'fail', 'message': 'Bank details already exist.'},
                                status.HTTP_400_BAD_REQUEST)

            user = PortalUser.objects.get(id=request.user.id)
            BankDetails.objects.create(
                deposite_category=deposite,
                bank_name=bank_name,
                branch_name=branch_name,
                ifsc_code=ifsc_code,
                account_type=account_type,
                account_number=account_number,
                created_by=user
            )
            return Response({'status': 'success', 'message': 'Bank details added successfully.'},
                            status=status.HTTP_200_OK)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User dose not exists.'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_bank_details(self, request):
        try:
            data = {
                'total_pages': 0,
                'current_page': 0,
                'total_items': 0,
                'results': []
            }
            deposite = {}
            get_bank_details = []
            page_size = int(request.data.get('page_size', 10))
            page_number = int(request.data.get('page_number', 1))
            bank_details_id = request.data.get('bank_details_id', None)
            search = request.data.get('search', None)
            depostie_category = request.data.get('depostie_category', None)
            if not page_size:
                return Response({'status': 'fail', 'message': 'Page size is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            get_bank_details = BankDetails.objects.filter(is_delete=False)

            if search is not None:
                get_bank_details = get_bank_details.filter(
                    Q(bank_name__icontains=search) |
                    Q(ifsc_code__icontains=search) |
                    # Q(branch_name__icontains=search) |
                    # Q(account_type__icontains=search) |
                    Q(account_number__icontains=search))

            if bank_details_id is not None:
                if not bank_details_id:
                    return Response({'status': 'fail', 'message': 'bank details ID is required.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                bank_id_validation = isnumber(bank_details_id)
                if bank_id_validation == False:
                    return Response(
                        {'status': 'fail', 'message': 'Invalid bank details ID. It should contain only digits.'}
                        , status=status.HTTP_400_BAD_REQUEST)

                get_bank_detail = get_bank_details.filter(bd_id=bank_details_id).first()

                if get_bank_detail:
                    for key, value in get_bank_detail.deposite_category.items():
                        if value is True:
                            deposite[key] = value

                    result = {
                        'bank_details_id': get_bank_detail.bd_id,
                        'deposite_category': deposite,
                        'bank_name': get_bank_detail.bank_name,
                        'ifsc_code': get_bank_detail.ifsc_code,
                        'branch_name': get_bank_detail.branch_name,
                        'account_type': get_bank_detail.account_type,
                        'account_number': get_bank_detail.account_number
                    }

                    return Response({'status': 'success', 'data': result}, status=status.HTTP_200_OK)
                else:
                    return Response({'status': 'fail', 'message': 'Bank detail not found.'},
                                    status=status.HTTP_404_NOT_FOUND)

            if depostie_category is not None:
                if not depostie_category:
                    return Response({'status': 'fail', 'message': 'depostie category is required.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                filtered_bank_details = []

                for bank_details in get_bank_details:
                    keys = bank_details.deposite_category.items()
                    for key, value in keys:
                        if key == depostie_category and value == True:
                            filtered_bank_details.append(bank_details)

                get_bank_details = filtered_bank_details

            paginator = Paginator(get_bank_details, page_size)

            if page_number > paginator.num_pages:
                return Response({
                    'status': 'success',
                    'data': data
                }, status=status.HTTP_200_OK)

            page_obj = paginator.get_page(page_number)

            for bank_details in page_obj:
                deposite = {}
                for key, value in bank_details.deposite_category.items():
                    if value is True:
                        deposite[key] = value

                results = {
                    'bank_details_id': bank_details.bd_id,
                    'deposite_category': deposite,
                    'bank_name': bank_details.bank_name,
                    'ifsc_code': bank_details.ifsc_code,
                    'branch_name': bank_details.branch_name,
                    'account_type': bank_details.account_type,
                    'account_number': bank_details.account_number
                }
                data['results'].append(results)

            data['total_pages'] = paginator.num_pages
            data['current_page'] = page_number
            data['total_items'] = paginator.count

            return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            bank_details_id = request.data.get('bank_details_id')

            if not bank_details_id:
                return Response({'status': 'fail', 'message': 'bank details ID is required,'},
                                status=status.HTTP_400_BAD_REQUEST)

            bank_id_validation = isnumber(bank_details_id)
            if bank_id_validation == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid bank details ID. It should contain only digits.'},
                    status=status.HTTP_400_BAD_REQUEST)

            bank_detail = BankDetails.objects.get(bd_id=bank_details_id, is_delete=False)
            bank_detail.is_delete = True
            bank_detail.save()
            return Response({'status': 'success', 'message': 'Bank Details deleted successfully.'},
                            status=status.HTTP_200_OK)

        except BankDetails.DoesNotExist:
            return Response({'status': 'fail', 'message': 'bank details dose not exists.'},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            bank_details_id = request.data.get('bank_details_id')
            bank_name = request.data.get('bank_name', None)
            deposite_category = request.data.get('deposite_category', None)
            ifsc_code = request.data.get('ifsc_code', None)
            branch_name = request.data.get('branch_name', None)
            account_type = request.data.get('account_type', None)
            account_number = request.data.get('account_number', None)

            if not bank_details_id:
                return Response({'status': 'fail', 'message': 'bank details ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

            bank_id_validation = isnumber(bank_details_id)
            if bank_id_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid bank details ID. It should contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)
            
            get_bank_details = BankDetails.objects.get(bd_id=bank_details_id, is_delete=False)
            print('get_bank_details-------------',get_bank_details)
            
            #as long as there is an active fund request (with a "PENDING" status), neither activation/deactivation nor updates should be allowed
            get_fund_request = FundRequest.objects.filter(deposite_bank=get_bank_details,request_status= 'PENDING', is_delete=False).first()
            if bank_details_id and not any([bank_name, deposite_category, ifsc_code, branch_name, account_type, account_number]):

                if get_fund_request:
                    return Response({'status': 'fail', 'message': 'Cannot deactivate bank details, there are active fund requests associated with it.'}, status=status.HTTP_400_BAD_REQUEST)

                if get_bank_details.is_deactive == True:
                    get_bank_details.is_deactive = False
                    message = 'Bank details activated Successfully.'

                else: 
                    get_bank_details.is_deactive = True
                    message = 'Bank details Deactivated Successfully.'

                get_bank_details.updated_at = timezone.now()
                get_bank_details.updated_by = request.user.id

                get_bank_details.save()
            else:
                if get_fund_request:
                    return Response(
                        {'status': 'fail', 'message': 'Cannot update bank details, as there are pending fund requests associated with it.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if bank_name:
                    if not bank_name:
                        return Response({'status': 'fail', 'message': 'bank name is required.'}, status=status.HTTP_400_BAD_REQUEST)   
                    bank_name_validation = isstring(bank_name)

                    if bank_name_validation == False:
                        return Response({'status': 'fail', 'message': 'Invalid bank name. It should be a string.'}, status=status.HTTP_400_BAD_REQUEST)
                    get_bank_details.bank_name = bank_name

                if deposite_category:
                    if not deposite_category:
                        return Response({'status': 'fail', 'message': 'deposite category is required.'}, status=status.HTTP_400_BAD_REQUEST)
                    deposite = json.loads(deposite_category)
                    get_bank_details.deposite_category = deposite

                if ifsc_code:
                    if not ifsc_code:
                        return Response({'status': 'fail', 'message': 'IFSC code is required.'}, status=status.HTTP_400_BAD_REQUEST)
                    ifsc_code_validation = is_valid_ifsc(ifsc_code)
                    if ifsc_code_validation == False:
                        return Response({'status': 'fail', 'message': 'Invalid IFSC code. Please check the format.'}, status=status.HTTP_400_BAD_REQUEST)
                    get_bank_details.ifsc_code = ifsc_code

                if branch_name:
                    if not branch_name:
                        return Response({'status': 'fail', 'message': 'branch name is required.'}, status=status.HTTP_400_BAD_REQUEST)
                    branch_name_validation = isstring(branch_name)
                    if branch_name_validation == False:
                        return Response({'status': 'fail', 'message': 'Invalid branch name. It should be a string.'}, status=status.HTTP_400_BAD_REQUEST)
                    get_bank_details.branch_name = branch_name

                if account_type:
                    if not account_type:
                        return Response({'status': 'fail', 'message': 'account type is required.'}, status=status.HTTP_400_BAD_REQUEST)
                    account_type_validation = isstring(account_type)

                    if account_type_validation == False:
                        return Response({'status': 'fail', 'message': 'Invalid account type. It should be a string.'}, status=status.HTTP_400_BAD_REQUEST)
                    get_bank_details.account_type = account_type

                if account_number:
                    if not account_number:
                        return Response({'status': 'fail', 'message': 'account number is required.'}, status=status.HTTP_400_BAD_REQUEST)
                    account_number_validation = isnumber(account_number)

                    if account_number_validation == False:
                        return Response({'status': 'fail', 'message': 'Invalid account number. It should contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)
                    get_bank_details.account_number = account_number

                get_bank_details.updated_at = timezone.now()
                get_bank_details.updated_by = request.user.id
                get_bank_details.save()

                message = 'Bank details updated Successfully.'

            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)

        except BankDetails.DoesNotExist:
            return Response({'status': 'fail', 'message': 'bank details dose not exists.'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class VerifyBankDetailsAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        ifsc_code = request.data.get('ifsc_code')
        account_number = request.data.get('account_number')

        # client_id = 61860316
        # client_secret = "OHQ7t2o4RAUM67J6vWQSTDMYCSXNvCE2"

        client_id = 76034597
        client_secret = "jIzkvvBkEFvIYjde8O7lini65ghUk5Yo"

        # callback_url = "https://apidemo.digitap.work/penny-drop/v2/check-valid"
        callback_url = "https://api.digitap.ai/penny-drop/v2/check-valid"

        try:
            if not ifsc_code:
                return Response({'status': 'fail', 'message': 'IFSC code is required.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not account_number:
                return Response({'status': 'fail', 'message': 'Account number is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            ifsc_code_validation = is_valid_ifsc(ifsc_code)
            if ifsc_code_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid IFSC code. Please check the format.'},
                                status=status.HTTP_400_BAD_REQUEST)

            account_number_validation = isnumber(account_number)
            if account_number_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid account number. It should contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)

            validation_account_number = validate_account_number(account_number)
            if not validation_account_number:
                # if len(account_number) < 6 or len(account_number) > 20:
                return Response({'status': 'fail',
                                 'message': 'Invalid account number. It should contain only digits and be between 6 and 20 characters long.'},
                                status=status.HTTP_400_BAD_REQUEST)

            auth_string = f"{client_id}:{client_secret}"

            encode_auth_string = base64.b64encode(bytes(auth_string, 'utf-8'))  # byte

            payload = {
                "accNo": account_number,
                "ifsc": ifsc_code,
            }
            headers = {
                "ent_authorization": encode_auth_string,
                "Content-Type": "application/json"
            }

            verify_bank_response = requests.post(callback_url, headers=headers, json=payload)

            if verify_bank_response.status_code == 200:
                verify_bank_response_json = verify_bank_response.json()

                if verify_bank_response_json.get("model").get("status") == "SUCCESS":
                    return Response({"status": "success", "message": "Bank verification completed successfully.",
                                     "data": verify_bank_response_json}, status=verify_bank_response.status_code)
                if verify_bank_response_json.get("model").get("status") == "PENDING":
                    return Response({"status": "pending",
                                     "message": "Bank verification is currently pending. Please check back later.",
                                     "data": verify_bank_response_json}, status=verify_bank_response.status_code)
                else:
                    return Response({"status": "fail",
                                     "message": "Bank verification failed. Please verify the details and try again.",
                                     "data": verify_bank_response_json}, status=verify_bank_response.status_code)
            elif verify_bank_response.status_code == 500:
                return Response({'status': 'error', 'data': verify_bank_response.text},
                                status=verify_bank_response.status_code)
            else:
                return Response({'status': 'error', 'data': verify_bank_response.json()},
                                status=verify_bank_response.status_code)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FundRequestAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        try:
            if 'deposit_bank_id' in request.data and 'deposit_amount' in request.data:
                return self.add_fund_request(request)
            elif 'page_number' in request.data or 'page_size' in request.data or 'fr_id' in request.data:
                return self.fetch_fund_request(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def add_fund_request(self, request):
        deposite_category = request.data.get('deposite_category')
        bd_id = request.data.get('deposit_bank_id')
        deposit_amount = request.data.get('deposit_amount')
        payment_proof = request.data.get('payment_proof')
        remark = request.data.get('remark')
        transaction_id = request.data.get('transaction_id')
        utr_number = request.data.get('utr_number')
        transaction_mode = request.data.get('transaction_mode')

        try:
            if not deposite_category: return Response({'status': 'fail','message': 'deposite_category is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not bd_id: return Response({'status': 'fail','message': 'bd_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not deposit_amount: return Response({'status': 'fail','message': 'deposit_amount is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not payment_proof: return Response({'status': 'fail','message': 'payment_proof is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not remark: return Response({'status': 'fail','message': 'remark is required.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                deposite_category_json = json.loads(deposite_category)
            except json.JSONDecodeError:
                return Response({'status': 'fail', 'message': 'Invalid deposite category format'}, status=status.HTTP_400_BAD_REQUEST)

            if isfloat(deposit_amount) == False: Response({'status': 'fail','message': 'Invalid desposit amount.'}, status=status.HTTP_400_BAD_REQUEST)
            if float(deposit_amount) < 0: Response({'status': 'fail','message': 'Desposit amount must be positive number.'}, status=status.HTTP_400_BAD_REQUEST)
            username = request.user.username
            file_path = handle_uploaded_file_fund(payment_proof, 'Retailer/PaymentProof',username) if payment_proof else None
            payment_proof_file_paths = {
                'payment_proof': file_path,
            }
            if FundRequest.objects.filter(transaction_id=transaction_id).exists():
                return Response({'status': 'fail', 'message': 'Transaction ID already exists.'}, status=status.HTTP_400_BAD_REQUEST)
            if deposite_category_json.get("counter_deposit") == True or deposite_category_json.get("cdm_deposit") == True:

                if not transaction_id: return Response({'status': 'fail','message': 'transaction_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    bank_detail = BankDetails.objects.get(bd_id=bd_id)
                except BankDetails.DoesNotExist:
                    return Response({'status': 'fail', 'message': 'Bank does not exists.'}, status=status.HTTP_400_BAD_REQUEST)

                # if len(transaction_id) < 12 or len(transaction_id) > 16: return Response({'status': 'fail', 'message': 'transaction_id length must be between 12 to 16.'}, status=status.HTTP_400_BAD_REQUEST)

                fund_request = FundRequest.objects.create(deposite_category=deposite_category_json, deposite_bank=bank_detail,
                                                          deposite_amount=deposit_amount, transaction_id=transaction_id, payment_proof=payment_proof_file_paths,
                                                          remark=remark, created_at=timezone.now(), created_by=request.user)
                
                user_activity = {
                    "table_id": fund_request.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Create',  # Action performed
                    "ua_description": 'Fund request generated successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(fund_request)
                }

                add_user_activity(user_activity)

                return Response({"status": "success", "message": "Fund request generated successfully."}, status=status.HTTP_201_CREATED)

            elif deposite_category_json.get("online_transaction") == True:
                if not utr_number: return Response({'status': 'fail','message': 'utr_number is required.'}, status=status.HTTP_400_BAD_REQUEST)
                if not transaction_mode: return Response({'status': 'fail','message': 'transaction_mode is required.'}, status=status.HTTP_400_BAD_REQUEST)

                transaction_mode_list = ["IMPS", "RTGS", "NEFT"]
                if transaction_mode not in transaction_mode_list:
                    return Response({'status': 'fail','message': 'transaction_mode values must be following: IMPS, RTGS and NEFT'}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    bank_detail = BankDetails.objects.get(bd_id=bd_id)
                except BankDetails.DoesNotExist:
                    return Response({'status': 'fail', 'message': 'Bank does not exists.'}, status=status.HTTP_400_BAD_REQUEST)

                # if len(utr_number) < 12 or len(utr_number) > 16: return  ({'status': 'fail', 'message': 'utr_number length must be between 12 to 16.'}, status=status.HTTP_400_BAD_REQUEST)

                fund_request = FundRequest.objects.create(deposite_category=deposite_category_json, deposite_bank=bank_detail,
                                                          deposite_amount=deposit_amount, utr_number=utr_number, payment_proof=payment_proof_file_paths,
                                                          transaction_mode=transaction_mode, remark=remark, created_at=timezone.now(),
                                                          created_by=request.user)
                user_activity = {
                    "table_id": fund_request.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Create',  # Action performed
                    "ua_description": 'Fund request generated successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(fund_request)
                }

                add_user_activity(user_activity)

                return Response({"status": "success", "message": "Fund request generated successfully."}, status=status.HTTP_201_CREATED)

            else:
                return Response({'status': 'fail', 'message': 'At least one deposite category must be true.'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_fund_request(self, request):
        fr_id = request.data.get("fr_id")
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size')

        try:
            if not page_size: return Response({'status': 'fail','message': 'page_size is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(page_size): return Response({'status': 'fail','message': 'page_size must contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if not isnumber(page_number): return Response({'status': 'fail','message': 'page_number must contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            if fr_id:
                if not isnumber(fr_id): return Response({'status': 'fail','message': 'fr_id must contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            if request.user.pu_role == "ADMIN":
                queryset = FundRequest.objects.filter(is_delete=False)
            else:
                queryset = FundRequest.objects.filter(is_delete=False, created_by=request.user.pk)

            if fr_id:
                queryset = queryset.filter(pk=fr_id)

            queryset = queryset.order_by('-pk')

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            if page_obj is not None:
                if not queryset.exists():
                    paginated_response_data = {
                        'total_pages': 0,
                        'current_page': 0,
                        'total_items': 0,
                        'results': []
                    }
                    response_data = {
                        'status': 'fail',
                        'message': 'Fund request Data not found.',
                        'data': paginated_response_data
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                serializer = FundRequestSerializer(page_obj.object_list, many=True, context={'request': request})
                paginated_response_data = {
                    'total_pages': paginator.num_pages,
                    'current_page': page_obj.number,
                    'total_items': paginator.count,
                    'results': serializer.data
                }
                return Response({
                    'status': 'success',
                    'message': 'Fund request data',
                    'data': paginated_response_data
                }, status=status.HTTP_200_OK)

            serializer = FundRequestSerializer(queryset, many=True, context={'request': request})
            response_data = {
                'status': 'success',
                'message': 'Fund request data',
                'data': serializer.data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'fail', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    
    def put(self, request):
        try:
            if 'fr_id' in request.data and 'request_status' in request.data or 'reason' in request.data:
                return self.fund_request_approve(request)
            elif 'fr_id' in request.data and 'deposit_bank_id' in request.data and 'deposite_category' in request.data:
                return self.fund_request_update(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'status': 'error', 'message': 'Internal server error.', 'data': str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fund_request_approve(self, request):
        try:
            fr_id = request.data.get("fr_id")
            request_status = request.data.get("request_status")
            reason = request.data.get("reason")

            if not fr_id: return Response({'status': 'fail', 'message': 'fr_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not request_status: return Response({'status': 'fail', 'message': 'request_status is required.'}, status=status.HTTP_400_BAD_REQUEST)

            get_fund_request = FundRequest.objects.get(fr_id=fr_id)
            # if get_fund_request.request_status == "REJECTED" or get_fund_request.request_status == "REVERSED":
            #     return Response({'status': 'fail', 'message': 'Fund request has already been processed.'}, status=status.HTTP_400_BAD_REQUEST)
            if get_fund_request.request_status == "REVERSED":
                return Response({'status': 'fail', 'message': 'Fund request has already been processed.'}, status=status.HTTP_400_BAD_REQUEST)

            if request_status == "APPROVED" and get_fund_request.request_status != "PENDING":
                return Response({'status': 'fail', 'message': 'Fund request has already been processed.'}, status=status.HTTP_400_BAD_REQUEST)

            # if request_status == "REVERSED" and get_fund_request.request_status != "APPROVED":
            #     return Response({'status': 'fail', 'message': 'Only requests with "APPROVED" status can be reversed.'}, status=status.HTTP_400_BAD_REQUEST)
            if request_status == "REVERSED" and get_fund_request.request_status not in ["APPROVED", "REJECTED"]:
                return Response({'status': 'fail', 'message': 'Only requests with "APPROVED" or "REJECTED" status can be reversed.'}, status=status.HTTP_400_BAD_REQUEST)

            deposit_amount = get_fund_request.deposite_amount
            request_user = get_fund_request.created_by

            try:
                get_portal_user_wallet = PortalUserWallet.objects.get(pu=request_user)
            except PortalUserWallet.DoesNotExist:
                return Response({'status': 'fail', 'message': 'PortalUser wallet not exists.'},
                            status=status.HTTP_404_NOT_FOUND)
            
            if request_status == "APPROVED" and get_fund_request.request_status == "PENDING":
                cashin_wallet_amount = get_portal_user_wallet.cashin_wallet or Decimal("0.00")

                # for retailer
                rt_gl = GlTrn.objects.create(
                    service_trn_id=get_fund_request.pk,
                    pu=request_user,
                    gl_trn_amt=cashin_wallet_amount,
                    effectvie_wallet='cashin_wallet',
                    effectvie_amt=deposit_amount,
                    service_trn_table='ad_fund_request',
                    effective_type='CR',
                    gl_trn_dt=now(),
                )

                WalletTrn.objects.create(
                    action_id=rt_gl.pk,
                    action_type='Fund Request',
                    pu=request_user,
                    wl_label=f"Fund_Request_Approve_by_admin_of_amount_{deposit_amount}",
                    effectvie_wallet='cashin_wallet',
                    effectvie_amt=deposit_amount,
                    effective_type='CR',
                    current_balance=cashin_wallet_amount + deposit_amount,
                    wl_trn_dt=now()
                )

                get_portal_user_wallet.cashin_wallet = cashin_wallet_amount + deposit_amount
                get_portal_user_wallet.save()

                get_fund_request.request_status = request_status
                get_fund_request.reasons = reason
                get_fund_request.save()

                user_activity = {
                    "table_id": get_fund_request.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Update',  # Action performed
                    "ua_description": 'Fund request approved successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(get_fund_request)
                }

                add_user_activity(user_activity)

                return Response({'status': 'success', 'message': 'Fund request approved successfully.'},
                            status=status.HTTP_200_OK)

            elif request_status == "REVERSED" and get_fund_request.request_status == "APPROVED":

                main_wallet_amount = get_portal_user_wallet.main_wallet or Decimal("0.00")
                get_portal_user_wallet.main_wallet = main_wallet_amount - deposit_amount
                get_portal_user_wallet.save()

                get_fund_request.request_status = request_status
                get_fund_request.reasons = reason
                get_fund_request.save()

                user_activity = {
                    "table_id": get_fund_request.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Update',  # Action performed
                    "ua_description": 'Fund request reversed successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(get_fund_request)
                }

                add_user_activity(user_activity)

                return Response({'status': 'success', 'message': 'Fund request reversed successfully.'},
                            status=status.HTTP_200_OK)
            

            elif request_status == "REVERSED" and get_fund_request.request_status == "REJECTED":
                get_fund_request.request_status = request_status
                get_fund_request.reasons = reason
                get_fund_request.save()

                user_activity = {
                    "table_id": get_fund_request.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Update',  # Action performed
                    "ua_description": 'Fund request reversed successfully',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(get_fund_request)
                }

                add_user_activity(user_activity)

                return Response({'status': 'success', 'message': 'Fund request reversed successfully.'},
                                status=status.HTTP_200_OK)

            elif request_status == "REJECTED":
                get_fund_request.request_status = request_status
                get_fund_request.reasons = reason
                get_fund_request.save()

                user_activity = {
                    "table_id": get_fund_request.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Update',  # Action performed
                    "ua_description": 'Fund request rejected successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(get_fund_request)
                }

                add_user_activity(user_activity)

                return Response({'status': 'success', 'message': 'Fund request rejected successfully.'},
                            status=status.HTTP_200_OK)
            
            else:
                return Response({'status': 'fail', 'message': 'Invalid request status.'},
                            status=status.HTTP_400_BAD_REQUEST) 

        except FundRequest.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Fund request record not exists.'},
                            status=status.HTTP_404_NOT_FOUND) 

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fund_request_update(self, request):
        fr_id = request.data.get('fr_id')
        deposite_category = request.data.get('deposite_category')
        bd_id = request.data.get('deposit_bank_id')
        deposit_amount = request.data.get('deposit_amount')
        payment_proof = request.data.get('payment_proof')
        remark = request.data.get('remark')
        transaction_id = request.data.get('transaction_id')
        utr_number = request.data.get('utr_number')
        transaction_mode = request.data.get('transaction_mode')

        try:
            if not fr_id: return Response({'status': 'fail','message': 'fr_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
            fund_request_queryset = FundRequest.objects.get(fr_id=fr_id, is_delete=False)
            if fund_request_queryset.created_by.pk != request.user.pk: return Response({"status": "fail", "message": "Unauthorized to update fund request."}, status=status.HTTP_401_UNAUTHORIZED)
            if fund_request_queryset.request_status != "PENDING": return Response({"status": "fail", "message": "Fund request has already been processed"}, status=status.HTTP_400_BAD_REQUEST)

            if not deposite_category: return Response({'status': 'fail','message': 'deposite_category is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not bd_id: return Response({'status': 'fail','message': 'bd_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not deposit_amount: return Response({'status': 'fail','message': 'deposit_amount is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not remark: return Response({'status': 'fail','message': 'remark is required.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                deposite_category_json = json.loads(deposite_category)
            except json.JSONDecodeError:
                return Response({'status': 'fail', 'message': 'Invalid deposite category format'}, status=status.HTTP_400_BAD_REQUEST)

            if not isfloat(deposit_amount): Response({'status': 'fail','message': 'Invalid desposit amount.'}, status=status.HTTP_400_BAD_REQUEST)
            if float(deposit_amount) < 0: Response({'status': 'fail','message': 'Desposit amount must be positive number.'}, status=status.HTTP_400_BAD_REQUEST)
            username=request.user.username
            if payment_proof:
                file_path = handle_uploaded_file_fund(payment_proof, 'Retailer/PaymentProof',username) if payment_proof else None
                payment_proof_file_paths = {'payment_proof': file_path}

            bank_detail = BankDetails.objects.get(bd_id=bd_id)

            

            if deposite_category_json.get("counter_deposit") == True or deposite_category_json.get("cdm_deposit") == True:
                if not transaction_id: return Response({'status': 'fail','message': 'transaction_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
                # if len(transaction_id) < 12 or len(transaction_id) > 16: return Response({'status': 'fail', 'message': 'transaction_id length must be between 12 to 16.'}, status=status.HTTP_400_BAD_REQUEST)

                fund_request_queryset.deposite_category = deposite_category_json
                fund_request_queryset.deposite_bank = bank_detail
                fund_request_queryset.deposite_amount = deposit_amount
                fund_request_queryset.transaction_id = transaction_id
                if payment_proof:
                    fund_request_queryset.payment_proof = payment_proof_file_paths
                fund_request_queryset.remark = remark
                fund_request_queryset.save()

                user_activity = {
                    "table_id": fund_request_queryset.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Update',
                    "ua_description": 'Fund request updated successfully.',
                    "created_by": request.user,
                    "request_data": dict(request.data),
                    "response_data": model_to_dict(fund_request_queryset)
                }

                add_user_activity(user_activity)

                return Response({"status": "success", "message": "Fund request updated successfully."}, status=status.HTTP_200_OK)

            elif deposite_category_json.get("online_transaction") == True:
                if not utr_number: return Response({'status': 'fail','message': 'utr_number is required.'}, status=status.HTTP_400_BAD_REQUEST)
                if not transaction_mode: return Response({'status': 'fail','message': 'transaction_mode is required.'}, status=status.HTTP_400_BAD_REQUEST)

                transaction_mode_list = ["IMPS", "RTGS", "NEFT"]
                if transaction_mode not in transaction_mode_list:
                    return Response({'status': 'fail','message': 'transaction_mode values must be following: IMPS, RTGS and NEFT'}, status=status.HTTP_400_BAD_REQUEST)

                # if len(utr_number) < 12 or len(utr_number) > 16: return  ({'status': 'fail', 'message': 'utr_number length must be between 12 to 16.'}, status=status.HTTP_400_BAD_REQUEST)

                fund_request_queryset.deposite_category = deposite_category_json
                fund_request_queryset.deposite_bank = bank_detail
                fund_request_queryset.deposite_amount = deposit_amount
                fund_request_queryset.utr_number = utr_number
                fund_request_queryset.transaction_mode = transaction_mode
                if payment_proof:
                    fund_request_queryset.payment_proof = payment_proof_file_paths
                fund_request_queryset.remark = remark
                fund_request_queryset.save()

                user_activity = {
                    "table_id": fund_request_queryset.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Update',  # Action performed
                    "ua_description": 'Fund request updated successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(fund_request_queryset)
                }

                add_user_activity(user_activity)

                return Response({"status": "success", "message": "Fund request updated successfully."}, status=status.HTTP_200_OK)
            else:
                return Response({'status': 'fail', 'message': 'At least one deposite category must be true.'}, status=status.HTTP_400_BAD_REQUEST)

        except BankDetails.DoesNotExist:
                return Response({'status': 'fail', 'message': 'Bank does not exists.'}, status=status.HTTP_404_NOT_FOUND)
        except FundRequest.DoesNotExist:
            return Response({"status": "fail", "message": "Fund request does not exist."},status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            fr_id = request.data.get('fr_id')

            if not fr_id: return Response({'status': 'fail', 'message': 'fr_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(fr_id): return Response({'status': 'fail','message': 'fr_id must contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            queryset = FundRequest.objects.get(fr_id=fr_id, is_delete=False)
            if queryset.created_by.pk != request.user.pk: return Response({"status": "fail", "message": "Unauthorized to delete fund request."}, status=status.HTTP_401_UNAUTHORIZED)

            if queryset.request_status == "PENDING":
                queryset.is_delete = True
                queryset.is_deactive = True
                queryset.save()

                user_activity = {
                    "table_id": queryset.pk,
                    "table_name": 'ad_fund_request',
                    "ua_action": 'Delete',  # Action performed
                    "ua_description": 'Fund request deleted successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(queryset)
                }

                add_user_activity(user_activity)

                return Response({'status': 'success', 'message': 'Fund request deleted successfully.'}, status=status.HTTP_200_OK)
            else:
                return Response({'status': 'fail', 'message': 'Only requests with a pending status can be deleted.'}, status=status.HTTP_400_BAD_REQUEST)

        except FundRequest.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Fund request dose not exists.'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': 'Internal server error.', 'data': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import decimal
class WalletAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer | IsDistributor]

    def post(self, request):
        try:
            if 'from_wallet' in request.data and 'amount' in request.data:
                print('if')
                return self.wallet_to_wallet(request)
            elif 'contact_no' in request.data and 'amount' in request.data and 'from_wallet' in request.data:
                print('if1')
                return self.wallet_to_other_wallet(request)
            elif 'contact_no' in request.data:
                print('if2')
                return self.get_data_contact_number(request)
            elif 'wallet' in request.data and 'page_number' in request.data or 'page_size' in request.data:
                print('if3')
                return self.all_wallet_transaction(request)
            elif 'page_number' in request.data or 'page_size' in request.data:
                print('if4')
                return self.get_wallet_transaction(request)
            else:
                return Response({'status': 'fail', 'message': 'Invalid request data.'},
                                status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def wallet_to_wallet(self, request):
        try:
            updated_to_wallet = request.data.get('updated_to_wallet')
            from_wallet = request.data.get('from_wallet')
            description = request.data.get('description', None)
            amount = request.data.get('amount')
            
            # Default to 'main_wallet' for the transfer, but allow the transfer to 'cashin_wallet'
            to_wallet = 'main_wallet'  

            if updated_to_wallet == 'cashin_wallet':
                to_wallet = 'cashin_wallet'  # if 'updated_to_wallet' is 'cashin_wallet', set to_wallet to 'cashin_wallet'
            
            main_wallet = 'main_wallet'

            # Validate required parameters
            if not from_wallet:
                return Response({'status': 'fail', 'message': 'from_wallet is required.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not amount:
                return Response({'status': 'fail', 'message': 'amount is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # validation_ammount = isnumber(amount)
            # if validation_ammount == False:
            #     return Response({'status': 'fail', 'message': 'Invalid amount. It must be a positive integer.'},
            #                     status=status.HTTP_400_BAD_REQUEST)

            from_wallet_validation = isstring(from_wallet)
            if from_wallet_validation == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid from wallet. It should contain only alphabetic characters.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if from_wallet not in ['cashin_wallet', 'pg_wallet']:
                return Response({'status': 'fail',
                                 'message': 'Invalid wallet name. Please choose from cashin_wallet or pg_wallet.'},
                                status=status.HTTP_400_BAD_REQUEST)

            amount = decimal.Decimal(amount)

            # Check if either 'from_wallet' or 'to_wallet' is the 'main_wallet'
            print(main_wallet,to_wallet)
            if main_wallet == to_wallet or main_wallet == from_wallet or to_wallet == 'cashin_wallet':
                
                if main_wallet == to_wallet and main_wallet == from_wallet:
                    return Response(
                        {'status': 'fail', 'message': f'Either from_wallet and to_wallet must be {main_wallet}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                # If transferring from 'pg_wallet' to 'cashin_wallet'
                if from_wallet == 'pg_wallet' and to_wallet == 'cashin_wallet':
                    print('----------------------5300')
                    user = request.user.id
                    retailer = PortalUser.objects.get(id=user, is_deleted=False)
                    retailer_details = PortalUserDetails.objects.get(pu=retailer)
                    user_wallet = PortalUserWallet.objects.get(pu=retailer)

                    if getattr(user_wallet, from_wallet) < amount:
                        return Response(
                            {'status': 'fail', 'message': f'Insufficient funds in {from_wallet}.', 'is_success': True},
                            status=status.HTTP_400_BAD_REQUEST)

                    # Debit from pg_wallet and Credit to cashin_wallet
                    setattr(user_wallet, from_wallet, getattr(user_wallet, from_wallet) - amount)
                    setattr(user_wallet, to_wallet, getattr(user_wallet, to_wallet) + amount)

                    user_wallet.save()

                    # Prepare transaction labels
                    from_wallet_name = 'Balance Account'
                    to_wallet_name = 'Cash Account'
                    main_wallet_name = 'Service Account'
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    from_label = f'{retailer_details.pud_unique_id}_DR_Internal{from_wallet_name}To{to_wallet_name}_{timestamp}'
                    to_label = f'{retailer_details.pud_unique_id}_CR_Internal{from_wallet_name}To{to_wallet_name}_{timestamp}'

                    # Record the transactions
                    wallet_transaction = {'CR': [to_wallet, to_label], 'DR': [from_wallet, from_label]}
                    for key, value in wallet_transaction.items():
                        global_transaction = GlTrn.objects.create(
                            pu=retailer,
                            effectvie_wallet=value[0],
                            effectvie_amt=amount,
                            effective_type=key,
                            service_trn_table='ad_wallet_trnasaction',
                            gl_trn_dt=timezone.now()
                        )

                        WalletTrn.objects.create(
                            action_id=global_transaction.gl_trn_id,
                            action_type=f'Internal_{from_wallet}_to_{to_wallet}',
                            pu=retailer,
                            wl_label=value[1],
                            effectvie_wallet=value[0],
                            effectvie_amt=amount,
                            effective_type=key,
                            wl_trn_des=description if description else None,
                            current_balance=getattr(user_wallet, value[0]),
                            wl_trn_dt=timezone.now()
                        )

                    return Response(
                        {'status': 'success', 'message': f'{amount} transferred from {from_wallet} to {to_wallet}.',
                        'is_success': True}, status=status.HTTP_200_OK)

                # Existing functionality for transferring to main_wallet (if applicable)
                user = request.user.id
                retailer = PortalUser.objects.get(id=user, is_deleted=False)
                retailer_details = PortalUserDetails.objects.get(pu=retailer)
                user_wallet = PortalUserWallet.objects.get(pu=retailer)

                if getattr(user_wallet, from_wallet) < amount:
                    return Response(
                        {'status': 'fail', 'message': f'Insufficient funds in {from_wallet}.', 'is_success': True},
                        status=status.HTTP_400_BAD_REQUEST)

                setattr(user_wallet, from_wallet, getattr(user_wallet, from_wallet) - amount)
                setattr(user_wallet, to_wallet, getattr(user_wallet, to_wallet) + amount)

                user_wallet.save()
                from_wallet_name = ''
                if from_wallet == 'cashin_wallet':
                    from_wallet_name = 'Cash Account'
                elif from_wallet == 'pg_wallet':
                    from_wallet_name = 'Balance Account'
                main_wallet_name = 'Service Account'
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                from_label = f'{retailer_details.pud_unique_id}_DR_Internal{from_wallet_name}To{main_wallet_name}_{timestamp}'
                to_label = f'{retailer_details.pud_unique_id}_CR_Internal{from_wallet_name}To{main_wallet_name}_{timestamp}'
                wallet_transaction = {'CR': [main_wallet, to_label], 'DR': [from_wallet, from_label]}
                for key, value in wallet_transaction.items():
                    global_transaction = GlTrn.objects.create(
                        pu=retailer,
                        effectvie_wallet=value[0],
                        effectvie_amt=amount,
                        effective_type=key,
                        service_trn_table='ad_wallet_trnasaction',
                        gl_trn_dt=timezone.now()
                    )

                    WalletTrn.objects.create(
                        action_id=global_transaction.gl_trn_id,
                        action_type=f'Internal_{from_wallet}_to_{main_wallet}',
                        pu=retailer,
                        wl_label=value[1],
                        effectvie_wallet=value[0],
                        effectvie_amt=amount,
                        effective_type=key,
                        wl_trn_des=description if description else None,
                        current_balance=getattr(user_wallet, value[0]),
                        wl_trn_dt=timezone.now()
                    )

                total_balances = PortalUserWallet.objects.filter(
                    pu__pu_role="RETAILER",
                    pu__pu_status="APPROVED"
                ).aggregate(
                    total_main_wallet=Sum('main_wallet', default=0),
                )

                    # Fetch BBPS Deposit Balance
                bbps_balance = get_bbps_deposit_balance()


                send_email_subject = "Wallet Transfer Alert - FIXPAY"

                # Convert Decimal values to float or string before sending them
                email_data = {
                    "subject": send_email_subject,
                    "recipient_list": ["gaurangkumar@ssepl.live", "kunal@ssepl.live"],
                    "username": request.user.username,
                    "amount": float(amount),  # Convert Decimal to float
                    "timestamp": timestamp,
                    "total_balance": float(total_balances['total_main_wallet']),  # Convert Decimal to float
                    "bbps_balance": float(bbps_balance),  # Convert Decimal to float
                }

                # Sending HTTP request to Project A's API to trigger the email sending
                send_email_url = "https://qaapi.fixpay.in/admin_hub/send-email/"
                response = requests.post(send_email_url, json=email_data)

                return Response(
                    {'status': 'success', 'message': f'{amount} transferred from {from_wallet} to {to_wallet}.',
                     'is_success': True}, status=status.HTTP_200_OK)

            else:
                return Response(
                    {'status': 'fail', 'message': f'Either from_wallet or to_wallet must be {main_wallet}.'},
                    status=status.HTTP_400_BAD_REQUEST)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)
        except PortalUserWallet.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Wallet not found for the user.'},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_data_contact_number(self, request):
        try:
            contact_number = request.data.get('contact_no')

            if not contact_number: return Response({'status': 'fail', 'message': 'contact number is required.'},
                                                   status=status.HTTP_400_BAD_REQUEST)

            validation_contact_number = validate_mobile_number(contact_number)
            if validation_contact_number == False:
                return Response({'status': 'fail', 'message': 'Invalid Mobile Number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            get_data = PortalUser.objects.get(pu_contact_no=contact_number, is_deleted=False)
            UserSerializer = PortalUserSerializer(get_data)

            return Response(
                {'status': 'success', 'message': 'user data get successfully.', 'data': UserSerializer.data},
                status=status.HTTP_200_OK)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'user dose not exists.', 'data': []},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def wallet_to_other_wallet(self, request):
        try:
            contact_no = request.data.get('contact_no')
            amount = request.data.get('amount')
            from_wallet = request.data.get('from_wallet')

            if not contact_no: return Response({'status': 'fail', 'message': 'contact no is required.'},
                                               status=status.HTTP_400_BAD_REQUEST)
            if not amount: return Response({'status': 'fail', 'message': 'amount is required.'},
                                           status=status.HTTP_400_BAD_REQUEST)
            if not from_wallet: return Response({'status': 'fail', 'message': 'from wallet is required.'},
                                                status=status.HTTP_400_BAD_REQUEST)

            validation_contact_number = validate_mobile_number(contact_no)
            if validation_contact_number == False:
                return Response({'status': 'fail', 'message': 'Invalid Mobile Number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            validation_amount = isnumber(amount)
            if validation_amount == False:
                return Response({'status': 'fail', 'message': 'Invalid amount. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            from_Wallet_validation = isstring(from_wallet)
            if from_Wallet_validation == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid from wallet. It should contain only alphabetic characters.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if from_wallet not in 'main_wallet':
                return Response({'status': 'fail', 'message': 'Invalid wallet name. Please choose from main_wallet.'},
                                status=status.HTTP_400_BAD_REQUEST)

            amount = Decimal(amount)
            main_wallet = 'main_wallet'

            user = PortalUser.objects.get(id=request.user.id, is_deleted=False)
            get_user = PortalUser.objects.get(pu_contact_no=contact_no, is_deleted=False)
            to_user_details = PortalUserDetails.objects.get(pu=user)
            from_user_details = PortalUserDetails.objects.get(pu=get_user)
            if get_user.pu_role not in ['RETAILER', 'DISTRIBUTOR']:
                return Response({'status': 'fail',
                                 'message': 'Only Retailers and Distributors are authorized to perform this action.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if request.user.id == get_user.id:
                return Response({'status': 'fail',
                                 'message': 'Self-transfer is not allowed. You cannot transfer funds to your own wallet.',
                                 'is_success': True}, status=status.HTTP_400_BAD_REQUEST)

            from_user_wallet = PortalUserWallet.objects.get(pu=get_user)
            to_user_wallet = PortalUserWallet.objects.get(pu=request.user.id)
            from_wallet_balance = Decimal(getattr(to_user_wallet, from_wallet))

            if from_wallet_balance < amount:
                return Response(
                    {'status': 'fail', 'message': f'Insufficient funds in {from_wallet}.', 'is_success': True},
                    status=status.HTTP_400_BAD_REQUEST)

            setattr(from_user_wallet, main_wallet, Decimal(getattr(from_user_wallet, main_wallet)) + amount)
            setattr(to_user_wallet, from_wallet, from_wallet_balance - amount)

            from_user_wallet.save()
            to_user_wallet.save()
            from_wallet_name = ''
            if from_wallet == 'cashin_wallet':
                from_wallet_name = 'CashIn'
            elif from_wallet == 'pg_wallet':
                from_wallet_name = 'Pg'
            main_wallet_name = 'Main'

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            from_label = f'{from_user_details.pud_unique_id}_CR_{from_wallet}_Internal{from_wallet_name}To{main_wallet_name}_{timestamp}'
            to_label = f'{to_user_details.pud_unique_id}_DR_{main_wallet}_Internal{from_wallet_name}To{main_wallet_name}_{timestamp}'
            wallet_transaction = {'CR': [from_wallet, from_label], 'DR': [main_wallet, to_label]}
            for key, value in wallet_transaction.items():
                global_transaction = GlTrn.objects.create(
                    pu=user,
                    effectvie_wallet=value[0],
                    effectvie_amt=amount,
                    effective_type=key,
                    service_trn_table='ad_wallet_trnsaction',
                    gl_trn_dt=timezone.now()
                )

                WalletTrn.objects.create(
                    action_id=global_transaction.gl_trn_id,
                    action_type=f'Internal{from_wallet}_to_{main_wallet}',
                    pu=get_user,
                    wl_label=value[1],
                    effectvie_wallet=value[0],
                    effectvie_amt=amount,
                    effective_type=key,
                    wl_trn_des=f"{user.pu_name} transferred {amount} from their wallet to {get_user.pu_name} ",
                    current_balance=from_wallet_balance.main_wallet,
                    wl_trn_dt=timezone.now()
                )

            return Response({
                'status': 'success',
                'message': f'{amount} transferred from {from_wallet} of to_user_wallet to {main_wallet} of from_user_wallet.',
                'is_success': True
            }, status=status.HTTP_200_OK)

        except PortalUserWallet.DoesNotExist:
            return Response({'status': 'fail', 'message': 'user wallet dose not exists'},
                            status=status.HTTP_404_NOT_FOUND)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'user dose not exists.'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_wallet_transaction(self, request):
        data = {
            "total_pages": 0,
            "current_page": 0,
            "total_items": 0,
            "results": []
        }
        print('request.data', request.data)
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        wallet_name = request.data.get('wallet', None)
        page_size = int(page_size)
        page_number = int(page_number)
        all_wl_data = 'Wallet'
        user = request.user.id
        try:
            retailer = PortalUser.objects.get(id=user, is_deleted=False)
            if not wallet_name:
                filter_wallet_transaction = WalletTrn.objects.filter(pu=retailer)
            else:
                wallet_name_validation = isstring(wallet_name)
                if wallet_name_validation == False:
                    return Response({'status': 'fail',
                                     'message': 'Invalid wallet name. It should contain only alphabetic characters.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                if wallet_name not in ['main_wallet', 'cashin_wallet', 'pg_wallet']:
                    return Response({'status': 'fail',
                                     'message': 'Invalid wallet name. Please choose from main_wallet, cashin_wallet or pg_wallet'},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not wallet_name:
                    return Response({'status': 'fail', 'message': 'wallet name is required.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                filter_wallet_transaction = WalletTrn.objects.filter(pu=retailer, effectvie_wallet=wallet_name)
            print(filter_wallet_transaction, 'wallet trn')
            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size
            paginated_wallet_transaction = filter_wallet_transaction[start_index:end_index]
            total_items = filter_wallet_transaction.count()
            total_pages = (len(filter_wallet_transaction) + page_size - 1) // page_size
            serializer = WalletTrnSerializer(paginated_wallet_transaction, many=True)
            print(serializer.data, 'wallet trn serializer')
            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serializer.data
            }

            return Response(
                {'status': 'success', 'message': f'Get all {wallet_name if wallet_name else all_wl_data} transaction.',
                 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def all_wallet_transaction(self, request):
        data = {
            "total_pages": 0,
            "current_page": 0,
            "total_items": 0,
            "results": []
        }
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        consolidation_wallet = request.data.get('wallet', None)
        page_size = int(page_size)
        page_number = int(page_number)
        user = request.user.id
        try:
            user = PortalUser.objects.get(id=user, is_deleted=False)
            puw_user = PortalUserWallet.objects.get(pu_id=user)
            
            filter_wallet_transaction = WalletTrn.objects.filter(pu=user)
            
            if consolidation_wallet is not None:
                filter_wallet_transaction = filter_wallet_transaction.filter(effectvie_wallet=consolidation_wallet)
            
            # descending 
            filter_wallet_transaction = filter_wallet_transaction.order_by('-pk')  # fatch data
            
            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size
            
            paginated_wallet_transaction = filter_wallet_transaction[start_index:end_index]
            
            total_items = filter_wallet_transaction.count()
            
            total_pages = (len(filter_wallet_transaction) + page_size - 1) // page_size
            
            serializer = WalletTrnSerializer(paginated_wallet_transaction, many=True)
            
            response_data = []
            
            for data in serializer.data:
                # data['current_balance'] = puw_user.main_wallet
                response_data.append(
                    {'effective_wallet': data.get("effectvie_wallet"), 'effective_ammount': data.get("effectvie_amt"),
                     'effective_type': data.get("effective_type")})
                # ADD DATE TIME
                if data.get('wl_trn_dt'):
                    data['wl_trn_dt'] = datetime.datetime.strptime(data['wl_trn_dt'],
                                                                   "%Y-%m-%dT%H:%M:%S.%f%z").strftime(
                        "%Y-%m-%d %I:%M %p")

            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serializer.data
            }

            return Response({'status': 'success', 'message': f'Get all user transaction.', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# extra add code
class FetchAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        user_id = request.user.id
        user_role = request.user.pu_role

        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        search_query = request.data.get('search', None)
        filter_value = request.data.get('filter_value', None)
        start_date = request.data.get('start_date', None)
        end_date = request.data.get('end_date', datetime.datetime.now().date())

        try:
            if user_role == "ADMIN":
                print('user_role-------', user_role)
                users_queryset = PortalUser.objects.filter(~Q(id=user_id), is_deleted=False)

            elif user_role == "DISTRIBUTOR":
                created_user = PortalUserDetails.objects.filter(created_by=user_id).values_list('pu', flat=True)

                users_queryset = PortalUser.objects.filter(id__in=created_user, is_deleted=False)

                print('users_queryset----GET dd---', users_queryset)

            else:
                return Response({'status': 'error', 'message': 'Invalid user role.'}, status=status.HTTP_404_NOT_FOUND)

            print('okkkkkk')
            print('filter_value-------------', filter_value)

            if filter_value:
                if filter_value == "DISTRIBUTOR":
                    print('DD ')
                    users_queryset = users_queryset.filter(pu_role="DISTRIBUTOR")

                elif filter_value == "RETAILER":
                    print('Retailer In ')
                    users_queryset = users_queryset.filter(pu_role="RETAILER")

            if search_query:
                print('searce ')
                users_queryset = users_queryset.filter(
                    Q(pu_name__icontains=search_query) |
                    Q(pu_email__icontains=search_query) |
                    Q(pu_contact_no__icontains=search_query) |
                    Q(pu_role__icontains=search_query)
                )
            if start_date:
                print('start_date---------', start_date)
                print('end_date------------', end_date)

                users_queryset = users_queryset.filter(created_at__date__range=[start_date, end_date])
                print('users_queryset-----', users_queryset)

            users_queryset = users_queryset.order_by('id')  # fatch data

            paginator = Paginator(users_queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            if not users_queryset.exists():
                return Response({
                    'status': 'success',
                    'message': 'No data found.',
                    'data': {
                        'total_pages': 0,
                        'current_page': 0,
                        'total_items': 0,
                        'results': []
                    }
                }, status=status.HTTP_200_OK)

            # Prepare response data
            print('------------------------ok')
            users_data = {}
            print('page_obj------')
            for usr in page_obj:
                portal_user_details = PortalUserDetails.objects.filter(pu=usr.id).first()
                print('portal_user_details------>>>>q', portal_user_details)

                if portal_user_details:
                    portal_user_serializer = PortalUserDetailsSerializers(
                        portal_user_details, context={'request': request}
                    )
                else:
                    portal_user_serializer = None

                users_data[usr.id] = {
                    'user': {
                        'id': usr.id if usr.id else '',
                        'name': usr.pu_name if usr.pu_name else '',
                        'email': usr.pu_email if usr.pu_email else '',
                        'contact_no': usr.pu_contact_no if usr.pu_contact_no else '',
                        'unique_id': portal_user_details.pud_unique_id if portal_user_details else '',
                    },
                    'user_details': portal_user_serializer.data if portal_user_serializer else []
                }

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': list(users_data.values())
            }

            return Response({
                'status': 'success',
                'message': 'Portal user Data',
                'data': paginated_response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RetailerDynamicServiceProviderAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        sp_id = request.data.get('sp_id')

        if not sp_id:
            return Response({'status': 'fail', 'message': 'sp_id is reqired.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user.id

        try:
            portal_user_charges = PortalUserCharges.objects.filter(pu_id=user)

            for charges in portal_user_charges:
                service_provider = AdServiceProvider.objects.get(sp_id=sp_id)
                exisring_pinned = PortalUserCharges.objects.filter(pu_id=user, is_pinned=True, is_deactive=False)
                if charges.sp == service_provider:

                    if charges.is_pinned == False:
                        if len(exisring_pinned) >= 7:
                            return Response(
                                {'status': 'fail', 'message': 'You can only pin a maximum of 7 service providers.'},
                                status=status.HTTP_400_BAD_REQUEST)

                        charges.is_pinned = True
                        charges.save()

                        return Response({'status': 'success', 'message': 'Service provider pinned successfully.'},
                                        status=status.HTTP_200_OK)

                    if charges.is_pinned == True:
                        charges.is_pinned = False
                        charges.save()

                        return Response({'status': 'success', 'message': 'Service provider unpinned successfully.'},
                                        status=status.HTTP_200_OK)

            return Response({'status': 'fail', 'message': 'No existing charges found for this user.'},
                            status=status.HTTP_404_NOT_FOUND)

        except AdServiceProvider.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Service provider dose not exists.'},
                            status=status.HTTP_404_NOT_FOUND)

        except PortalUserCharges.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Portal user charges dose not exists.'},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        user_id = request.user.id

        try:
            all_service_provider = AdServiceProvider.objects.filter(is_deleted=False, is_deactive=False,
                                                                    sa_provided=True)
            portal_user_charges = PortalUserCharges.objects.filter(pu_id=user_id, is_deactive=False)

            user_finance = UserServiceFinance.objects.filter(
                user_id=user_id
            ).first()

            can_show_instant = False
            if user_finance and user_finance.od_limit > 0 and user_finance.available_limit > 0:
                can_show_instant = True

            service_provider_list = []

            for service in all_service_provider:
                for charges in portal_user_charges:
                    if charges.sp == service:

                        if service.menu and service.menu.menu_name == "INSTANT PG" and not can_show_instant:
                            continue

                        exists_portal_user_charges = PortalUserCharges.objects.filter(sp=service, pu_id=user_id).first()
                        if exists_portal_user_charges:
                            pass

                        service_provider_data = {
                            'sp_id': service.sp_id,
                            'sp_name': service.sp_name,
                            'label': service.label,
                            'hsn_sac_id': service.hsn_sac.hsnsac_id if service.hsn_sac.hsnsac_id else None,
                            'hsn_sac_name': service.hsn_sac.hsnsac_code,
                            'service_id': service.service.service_id,
                            'service_name': service.service.service_name,
                            'tds_rate': service.tds_rate,
                            'is_pinned': charges.is_pinned,
                            'is_access': True if exists_portal_user_charges else False,
                            'menu_id': service.menu.menu_id if service.menu else None,
                            'menu_name': service.menu.menu_name if service.menu else None,
                        }
                        service_provider_list.append(service_provider_data)

            return Response({'status': 'success', 'message': 'Get all service provider.',
                             'data': {'results': service_provider_list}})

        except PortalUserCharges.DoesNotExist:
            return Response({'stauts': 'fail', 'message': 'Portal user service provider dose not exists.'},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AssignedPosDeviceAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsRetailer]

    def post(self, request):
        try:
            if 'retailer_id' in request.data and 'terminal_id' in request.data:
                return self.assign_pos_device(request)

            elif 'page_number' in request.data and 'page_size' in request.data:
                return self.fetch_retailer(request)

            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_retailer(self, request):
        try:
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            user_id = request.data.get('id')
            search = request.data.get('search')

            portal_users = PortalUser.objects.filter(pu_role="RETAILER", is_deleted=False)

            if user_id:
                portal_users = portal_users.filter(id=user_id)

            if search:
                portal_users = portal_users.filter(
                    Q(pu_name__icontains=search) |
                    Q(pu_email__icontains=search) |
                    Q(pu_contact_no__icontains=search)
                )

            if not portal_users.exists():
                return Response({
                    "status": "success",
                    "message": "Retailer data not found",
                    "data": {
                        "total_pages": 0,
                        "current_page": 0,
                        "total_items": 0,
                        "results": []
                    }
                }, status=status.HTTP_200_OK)

            paginator = Paginator(portal_users, page_size)
            page_obj = paginator.page(page_number)

            users_data = []
            for user in page_obj:
                pos_device = PosDevice.objects.filter(pu=user)
                terminals = [device.terminal for device in pos_device] if pos_device.exists() else None

                user_data = {
                    'id': user.id,
                    'name': user.pu_name,
                    'email': user.pu_email,
                    'contact_no': user.pu_contact_no,
                    'role': user.pu_role,
                    'is_pos_assigned': pos_device is not None,
                    'pos_terminal_id': terminals
                }

                users_data.append(user_data)

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': users_data
            }

            return Response(
                {'status': 'success', 'message': 'Retailer Data retrieved success ', 'data': paginated_response_data},
                status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def assign_pos_device(self, request):
        try:
            retailer_id = request.data.get('retailer_id')
            terminal_id = request.data.get('terminal_id')
            sp_id = request.data.get('sp_id')
            expiry_str = request.data.get('terminal_expiry')
            if not retailer_id:
                return Response({"status": "fail", "message": "Retailer ID is required."},
                                status=status.HTTP_400_BAD_REQUEST)

            if not terminal_id:
                return Response({"status": "fail", "message": "Terminal ID is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            

            expiry_datetime = expiry_str if expiry_str else None

            existing_terminal = PosDevice.objects.filter(terminal=terminal_id, is_deleted=False).first()
            if existing_terminal:
                return Response({
                    "status": "fail",
                    "message": "The terminal id is already assigned other retailer.",
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                retailer = PortalUser.objects.get(id=retailer_id, pu_role="RETAILER", is_deleted=False,
                                                  is_deactive=False)

            except PortalUser.DoesNotExist:
                return Response({"status": "fail", "message": "Retailer not found."}, status=status.HTTP_404_NOT_FOUND)

            # if PosDevice.objects.filter(pu=retailer, is_deleted=False).exists():
            #     return Response({
            #         "status": "fail",
            #         "message": "This retailer is already assigned POS device."
            #     }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                pos_device = PosDevice.objects.create(
                    pu=retailer,
                    terminal=terminal_id,
                    sp_id=sp_id,
                    created_by=request.user.id,
                    is_expires_at=expiry_datetime,
                )
                TerminalRetailerHistory.objects.create(
                    terminal=pos_device,
                    action='assigned',
                    performed_by=request.user,
                    remarks=f"POS device assigned to retailer ID {retailer_id}"
                )
                user_activity = {
                    "table_id": pos_device.pk,
                    "table_name": 'ad_pos_device',
                    "ua_action": 'Create',  # Action performed
                    "ua_description": 'POS device successfully assigned to the retailer.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(pos_device)
                }

                add_user_activity(user_activity)

            return Response({"status": "success", "message": "POS device successfully assigned to the retailer."},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"status": "error", "message": f"Internal server error: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        retailer_id = request.data.get('retailer_id')

        if not retailer_id:
            return Response({'status': 'fail', 'message': 'Retailer ID is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                retailer = PortalUser.objects.get(id=retailer_id, pu_role="RETAILER", is_deleted=False,
                                                  is_deactive=False)

                pos_device = PosDevice.objects.filter(pu=retailer).first()
                if not pos_device:
                    return Response(
                        {"status": "fail", "message": "POS device not found for the retailer."},
                        status=status.HTTP_404_NOT_FOUND)

                pos_device.is_deactive = not pos_device.is_deactive
                pos_device.updated_at = timezone.now()
                pos_device.save()

                message = 'POS Device Activated Successfully' if not pos_device.is_deactive else 'POS Device Deactivated Successfully'

            return Response({"status": "success", "message": message}, status=status.HTTP_200_OK)

        except PortalUser.DoesNotExist:
            return Response({"status": "fail", "message": "Retailer not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PosServiceTrnAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsRetailer]

    def post(self, request):
        trn_id = request.data.get('trn_id')
        tid_id = request.data.get('tid_id')
        search_txt = request.data.get('search')
        page_number = request.data.get('page_number')
        page_size = request.data.get('page_size')

        try:
            if not page_number:
                return Response({'status': 'fail', 'message': 'page_number is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not page_size:
                return Response({'status': 'fail', 'message': 'page_size is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if isnumber(page_size) == False:
                return Response({'status': 'fail', 'message': 'page_size must be a valid number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if isnumber(page_number) == False:
                    return Response({'status': 'fail', 'message': 'page_number must be a valid number.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if trn_id:
                if isnumber(trn_id) == False:
                    return Response({'status': 'fail', 'message': 'trn_id must contain only digits.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            queryset = PosServiceTrn.objects.all()

            if trn_id:
                queryset = queryset.filter(pos_trn_id=trn_id)

            if tid_id:
                queryset = queryset.filter(Q(trn_response__tid=tid_id))

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt)
                )

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True)
            paginated_response = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transaction data fetched successfully1.',
                'data': paginated_response
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# LIVE
class GlobalTrnAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsRetailer]

    def post(self, request):
        try:
            current_time = timezone.now()
            end_time = current_time.replace(hour=23, minute=30, second=0, microsecond=0) - timedelta(
                days=1)  # ==> is called 11:30 remove - timedelta(days=1) 
            start_time = end_time - timedelta(days=1)

            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'page_number must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if page_size <= 0:
                return Response({'status': 'fail', 'message': 'page_size must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            transactions = GlTrn.objects.filter(gl_trn_dt__range=[start_time, end_time])

            if not transactions.exists():
                return Response({
                    'status': 'success',
                    'message': 'No transactions found in the given time range.',
                    'data': []
                }, status=status.HTTP_200_OK)

            paginator = Paginator(transactions, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = GlTrnSerializer(page_obj.object_list, many=True)

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'transactions': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions fetched successfully.',
                'data': paginated_response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# class RetailerPosAPIView(APIView):  # FATCH RETAILER TRANSACTION
#     authentication_classes = [CustomJWTAuthentication]
#     permission_classes = [IsRetailer]

#     def post(self, request):
#         try:
#             user = request.user
#             page_number = int(request.data.get('page_number', 1))
#             page_size = int(request.data.get('page_size', 10))
#             terminal_id = request.data.get('terminal_id')
#             search_txt = request.data.get('search')
#             filter_by = request.data.get('filter_by')
#             start_date = request.data.get('start_date')
#             end_date = request.data.get('end_date', datetime.datetime.now().date())

#             if not str(page_number).isdigit() or int(page_number) <= 0:
#                 return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
#                                 status=status.HTTP_400_BAD_REQUEST)

#             if not str(page_size).isdigit() or int(page_size) <= 0:
#                 return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
#                                 status=status.HTTP_400_BAD_REQUEST)

#             pos_devices = PosDevice.objects.filter(pu=user)
#             if not pos_devices.exists():
#                 return Response({
#                     'status': 'fail',
#                     'message': 'No retailer found for the user.'
#                 }, status=status.HTTP_404_NOT_FOUND)

#             queryset = PosServiceTrn.objects.filter(created_by=request.user.id)
#             # gl_trn_queryset = GlTrn.objects.filter(pu_id=user).values_list('service_trn_id', flat=True)
#             # queryset = queryset.filter(pk__in=gl_trn_queryset)

#             if terminal_id:
#                 queryset = queryset.filter(terminal_id=terminal_id)

#             if search_txt:
#                 queryset = queryset.filter(
#                     Q(customer_name__icontains=search_txt) |
#                     Q(trn_unique_id__icontains=search_txt) |
#                     Q(terminal_id__icontains=search_txt)   |
#                     Q(trn_status__icontains=search_txt)
#                     )

#             if filter_by:
#                 allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
#                 if filter_by not in allowed_filters:
#                     return Response({
#                         'status': 'fail',
#                         'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
#                         status=status.HTTP_400_BAD_REQUEST)

#                 queryset = queryset.filter(trn_status=filter_by)

#             if start_date:
#                 try:
#                     start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
#                     queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
#                 except ValueError:
#                     return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
#                                     status=status.HTTP_400_BAD_REQUEST)

#             if end_date:
#                 try:
#                     end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
#                     queryset = queryset.filter(pos_trn_dt__date__lte=end_date)
#                 except ValueError:
#                     return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
#                                     status=status.HTTP_400_BAD_REQUEST)

#             if not queryset.exists():
#                 paginated_response_data = {
#                     'total_pages': 0,
#                     'current_page': 0,
#                     'total_items': 0,
#                     'results': []
#                 }
#                 return Response({
#                     'status': 'success',
#                     'message': 'Transaction Data not found.',
#                     'data': paginated_response_data,
#                 }, status=status.HTTP_200_OK)

#             paginator = Paginator(queryset, int(page_size))
#             try:
#                 page_obj = paginator.page(int(page_number))
#             except EmptyPage:
#                 return Response({
#                     'status': 'fail',
#                     'message': 'Page not found.',
#                     'data': {}
#                 }, status=status.HTTP_404_NOT_FOUND)

#             serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
#             with open("output_data_pos.txt", "a", encoding="utf-8") as f:
#                 f.write(json.dumps(serializer.data, indent=4, default=str))
#                 f.write("\n\n")

#             for data in serializer.data:
#                 data['settled_amount'] = 0.00
#                 if data['trn_status'] == "SETTLED":
#                     print(data['pos_trn_id'], "data['pos_trn_id']")
#                     gl_trn_data = GlTrn.objects.filter(
#                         service_trn_id=data['pos_trn_id'], 
#                         gl_tds_rate__isnull=False, 
#                         gl_tax_rate__isnull=False
#                     ).first()

#                     data['settled_amount'] = float(data['trn_amount']) - float(gl_trn_data.effectvie_amt)
#                     data['gl_tds_rate'] = float(gl_trn_data.gl_tds_rate)
#                     data['gl_tax_rate'] = float(gl_trn_data.gl_tax_rate)
#                     data['gl_tds_amt'] = float(gl_trn_data.gl_tds_amt)
#                     data['gl_tax_amt'] = float(gl_trn_data.gl_tax_amt)

#                 # Check if the value is a string before parsing
#                 if isinstance(data['pos_trn_dt'], str):
#                     data['pos_trn_dt'] = parser.parse(data['pos_trn_dt'])

#                 # Format to the required format
#                 data['pos_trn_dt'] = data['pos_trn_dt'].strftime("%d-%m-%Y %I:%M %p")

            

#             paginated_response_data = {
#                 'total_pages': paginator.num_pages,
#                 'current_page': page_obj.number,
#                 'total_items': paginator.count,
#                 'results': serializer.data
#             }

#             return Response({
#                 'status': 'success',
#                 'message': 'Transactions retrieved successfully.',
#                 'data': paginated_response_data,

#             }, status=status.HTTP_200_OK)

#         except Exception as e:
#             return Response({
#                 'status': 'error',
#                 'message': f'Internal server error: {str(e)}'
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
class RetailerPosAPIView(APIView):  # FATCH RETAILER TRANSACTION
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            pos_devices = PosDevice.objects.filter(pu=user)
            if not pos_devices.exists():
                return Response({
                    'status': 'fail',
                    'message': 'No retailer found for the user.'
                }, status=status.HTTP_404_NOT_FOUND)

            queryset = PosServiceTrn.objects.filter(created_by=request.user.id).order_by('-pos_trn_id')
            # gl_trn_queryset = GlTrn.objects.filter(pu_id=user).values_list('service_trn_id', flat=True)
            # queryset = queryset.filter(pk__in=gl_trn_queryset)

            if terminal_id:
                queryset = queryset.filter(terminal_id=terminal_id)

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(terminal_id__icontains=search_txt)   |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                data['settled_amount'] = 0.00
                if data['trn_status'] == "SETTLED":
                    
                    print(data['pos_trn_id'], "data['pos_trn_id']")
                    gl_trn_data = GlTrn.objects.filter(
                        service_trn_id=data['pos_trn_id'], 
                        gl_tds_rate__isnull=False, 
                        gl_tax_rate__isnull=False
                    ).first()


                    data['settled_amount'] = float(data['trn_amount']) - float(gl_trn_data.effectvie_amt)
                    data['gl_tds_rate'] = float(gl_trn_data.gl_tds_rate)
                    data['gl_tax_rate'] = float(gl_trn_data.gl_tax_rate)
                    data['gl_tds_amt'] = float(gl_trn_data.gl_tds_amt)
                    data['gl_tax_amt'] = float(gl_trn_data.gl_tax_amt)

                # Check if the value is a string before parsing
                if isinstance(data['pos_trn_dt'], str):
                    data['pos_trn_dt'] = parser.parse(data['pos_trn_dt'])

                # Format to the required format
                data['pos_trn_dt'] = data['pos_trn_dt'].strftime("%d-%m-%Y %I:%M %p")

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RetailerTerminalAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user_id = request.user.id

            page_number = request.data.get('page_number')
            page_size = request.data.get('page_size')

            if not page_number:
                return Response({'status': 'fail', 'message': 'page_number is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not page_size:
                return Response({'status': 'fail', 'message': 'page_size is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if page_size:
                if isnumber(page_size) == False:
                    return Response({'status': 'fail', 'message': 'page_size must contain only digits.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if isnumber(page_number) == False:
                    return Response({'status': 'fail', 'message': 'page_number must contain only digits.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            portal_users = PortalUser.objects.filter(pu_role="RETAILER", is_deleted=False)

            if user_id:
                portal_users = portal_users.filter(id=user_id)

            if not portal_users.exists():
                return Response({
                    "status": "success",
                    "message": "Retailer data not found.",
                    "data": []
                }, status=status.HTTP_200_OK)

            paginator = Paginator(portal_users, page_size)
            page_obj = paginator.page(page_number)

            users_data = []
            for user in page_obj:
                pos_device = PosDevice.objects.filter(pu=user)
                terminals = [device.terminal for device in pos_device] if pos_device.exists() else None

                user_data = {
                    'id': user.id,
                    'name': user.pu_name,
                    'email': user.pu_email,
                    'contact_no': user.pu_contact_no,
                    'role': user.pu_role,
                    'is_pos_assigned': pos_device.exists(),
                    'pos_terminal_id': terminals
                }

                users_data.append(user_data)

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': users_data
            }

            return Response({
                'status': 'success',
                'message': 'Retailer data retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TransactionSettlementAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin| IsDistributor]

    def post(self, request):
        try:
            if 'page_number' in request.data and 'page_size' in request.data:
                return self.fetch_transactions(request)
        
            elif 'trn_unique_id' in request.data:
                return self.create_settled_transaction(request)

            else:
                return Response({'status': 'error', 'message': 'Invalid data. Ensure that the necessary fields are provided.'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    def send_settlement_email(self, user_email, username, amount, transaction_id, user_name):
        try:
            email_data = {
                "subject": "Payment Settlement Successful",
                "recipient_list": [user_email],
                "username": user_name,
                "amount": float(amount),   
                "timestamp": now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": f"Your payment of ₹{amount} has been settled successfully. Transaction ID: {transaction_id}"
            }

            response = requests.post(
                "https://qaapi.fixpay.in/admin_hub/send-email/",
                json=email_data
            )

            print("EMAIL API RESPONSE:", response.status_code, response.text)
            return response.status_code == 200

        except Exception as e:
            print("EMAIL ERROR:", str(e))
            return False

    def create_settled_transaction(self, request):
        try:
            trn_unique_id = request.data.get('trn_unique_id')
            sp_id = request.data.get('sp_id')

            if not trn_unique_id:
                return Response({'status': 'fail', 'message': 'trn_unique_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            if not sp_id:
                return Response({'status': 'fail', 'message': 'sp_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            trn = PosServiceTrn.objects.filter(
                trn_unique_id=trn_unique_id,
                trn_status='COMPLETED'
            ).first()

            if not trn:
                return Response({'status': 'fail', 'message': 'No transaction found for the given trn_unique_id'}, status=status.HTTP_404_NOT_FOUND)
            
            terminal = PosDevice.objects.filter(terminal=trn.terminal_id).first()
            if not terminal:
                return Response({'status': 'fail', 'message': 'Terminal not found'}, status=status.HTTP_404_NOT_FOUND)

            expiry_str = terminal.is_expires_at 

            if not expiry_str:
                return Response({
                    'status': 'fail',
                    'message': 'Expiry time not provided.'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                expiry_date = datetime.datetime.strptime(expiry_str, "%d-%m-%Y").date()
            except Exception:
                return Response({
                    'status': 'fail',
                    'message': 'Invalid expiry date format.'
                }, status=status.HTTP_400_BAD_REQUEST)

            today_date = timezone.localdate()  

            if expiry_date < today_date:
                return Response({
                    'status': 'fail',
                    'message': 'Terminal is expired. Settlement not allowed.'
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                portal_user_details = PortalUserDetails.objects.get(pu_id=trn.created_by)
                get_pu = portal_user_details.pu
                rtl_wallet = PortalUserWallet.objects.get(pu_id=trn.created_by)
                # for retailer
                rt_gl = GlTrn.objects.create(
                    service_trn_id=trn.pk,
                    pu_id=trn.created_by,
                    gl_trn_amt=trn.trn_amount,
                    effectvie_wallet='pg_wallet',
                    effectvie_amt=trn.trn_amount,
                    service_trn_table='ad_pos_service_transaction',
                    effective_type='CR',
                    gl_trn_dt=now(),
                )

                WalletTrn.objects.create(
                    action_id=rt_gl.pk,
                    action_type='Service',
                    pu_id=trn.created_by,
                    wl_label=f"POS_by_{portal_user_details.pud_unique_id}_of_amount_{trn.trn_amount}_with_tx_id_{trn.trn_unique_id}",
                    effectvie_wallet='pg_wallet',
                    effectvie_amt=trn.trn_amount,
                    effective_type='CR',
                    current_balance=float(rtl_wallet.pg_wallet) + float(trn.trn_amount),
                    wl_trn_dt=now()
                )

                rtl_wallet.pg_wallet = float(rtl_wallet.pg_wallet) + float(trn.trn_amount)
                rtl_wallet.updated_at = now()
                rtl_wallet.save()

                # Prepare data for after_tx_cal
                data = {
                    'order_amount': trn.trn_amount,
                    'id': trn.created_by,
                    'sp_id': trn.sp_id,
                    'customer_contact_no': None,
                    'customer_name': trn.customer_name,
                    'trn_response': trn.trn_response,
                    'service_trn': trn.pk,
                    'label': AdServiceProvider.objects.get(sp_id=trn.sp_id).label,
                    'charge_level': trn.pos_charge_type
                }

                # Call after_tx_cal function
                after_tx_cal(request, data)

                trn.trn_status = "SETTLED"
                trn.is_settled = True
                trn.save()

                if get_pu.pu_email:
                    self.send_settlement_email(
                        user_email=get_pu.pu_email,
                        username=portal_user_details.pud_unique_id,
                        amount=trn.trn_amount,
                        transaction_id=trn.trn_unique_id,
                        user_name=get_pu.username
                    )

            return Response({
                'status': 'success',
                'message': 'Transaction settled successfully.'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_transactions(self, request):
        try:
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            user_id = request.data.get('user_id')
            custom_retailer = request.data.get('custom_retailer')  # New field added
            terminal_id = request.data.get('terminal_id')
            trn_unique_id = request.data.get('trn_unique_id') 
            bbps_request_id = request.data.get('bbps_request_id') 
            bbps_blr_id = request.data.get('bbps_blr_id') 
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            sp_id = request.data.get('sp_id')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())
            date_filter = request.data.get('date_filter')  # TODAY, WEEKLY, MONTHLY, YEARLY, CUSTOM

            if not sp_id:
                return Response({'status': 'fail', 'message': 'sp_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            service_provider = AdServiceProvider.objects.filter(sp_id=sp_id).first()

            if not service_provider:
                return Response({'status': 'fail', 'message': 'Service provider not found.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse user_id and custom_retailer as lists
            try:
                list_user = ast.literal_eval(user_id) if user_id else []
                if not isinstance(list_user, list):
                    raise ValueError("Invalid format for user_id")

                list_custom_retailer = ast.literal_eval(custom_retailer) if custom_retailer else []
                if not isinstance(list_custom_retailer, list):
                    raise ValueError("Invalid format for custom_retailer")

            except Exception:
                return Response({'status': 'fail', 'message': 'Invalid user_id or custom_retailer format. Must be lists of integers.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Combine both lists, remove duplicates
            combined_user_list = list(set(list_user + list_custom_retailer))

            if not str(page_size).isdigit() or not str(page_number).isdigit():
                return Response({'status': 'fail', 'message': 'page_number and page_size must be numeric.'}, status=status.HTTP_400_BAD_REQUEST)

            today = datetime.datetime.now().date()

            if date_filter:
                if date_filter == 'TODAY':
                    start_date, end_date = today, today

                elif date_filter == 'WEEKLY':
                    start_date, end_date = today - timedelta(days=6), today

                elif date_filter == 'MONTHLY':
                    start_date, end_date = today - timedelta(days=29), today 

                elif date_filter == 'YEARLY':
                    start_date, end_date = today.replace(month=1, day=1), today

                elif date_filter == 'CUSTOM' and (not start_date or not end_date):
                    return Response({'status': 'fail', 'message': 'For custom date filter, start_date and end_date are required.'}, status=status.HTTP_400_BAD_REQUEST)
                
            if start_date and isinstance(start_date, str):
                start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
                if start_date > today :
                    return Response({'status': 'fail', 'message': 'Start date cannot be later than today.'}, status=status.HTTP_400_BAD_REQUEST)
                
            if end_date and isinstance(end_date, str):
                end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
                if end_date > today:
                    return Response({'status': 'fail', 'message': 'End date cannot be later than today.'}, status=status.HTTP_400_BAD_REQUEST)
                
                end_date = datetime.datetime.combine(end_date, datetime.time.max)
            
            if not combined_user_list:
                if start_date is None:
                    start_date = datetime.datetime.now().date()
                print(start_date,end_date)
                
            # ADMIN 
            if request.user.pu_role == "ADMIN":
                if sp_id == '1':
                    queryset = PosServiceTrn.objects.all().order_by('-pk')
                    processed_data = pos_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)

                elif sp_id == '2':
                    queryset = BBPSBillPayment.objects.exclude(bbps_status='PENDING').order_by('-pk')
                    processed_data = bbps_fetch_transactions(request, queryset, filter_by, start_date, end_date, combined_user_list, bbps_request_id, bbps_blr_id, search_txt, page_size, page_number)

                elif sp_id == '3':
                    queryset = PgServiceTrn.objects.filter(pg_id=3,is_instant=False).exclude(trn_status='PENDING').order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                
                elif sp_id == '4':
                    queryset = PgServiceTrn.objects.filter(pg_id=4,is_instant=False).exclude(trn_status='PENDING').order_by('-pk')
                    
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '6':
                    queryset = PgServiceTrn.objects.filter(pg_id=5,is_instant=False).exclude(trn_status='PENDING').order_by('-pk')
                    processed_data = pg_fetch_transactions(
                        request, queryset, trn_unique_id, terminal_id, search_txt,
                        filter_by, start_date, end_date, combined_user_list, page_size, page_number
                    )
                elif sp_id == '7':
                    queryset = PgServiceTrn.objects.filter(pg_id=4,is_instant=True).exclude(trn_status='PENDING').order_by('-pk')
                    
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)

                elif sp_id == '8':
                    queryset = PgServiceTrn.objects.filter(pg_id=5,is_instant=True).exclude(trn_status='PENDING').order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)

                elif sp_id == '9':
                    queryset = PgServiceTrn.objects.filter(pg_id=3,is_instant=True).exclude(trn_status='PENDING').order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '10':
                    queryset = PgServiceTrn.objects.filter(pg_id=6,is_instant=False).exclude(trn_status='PENDING').order_by('-pk')                    
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '11':
                    queryset = PgServiceTrn.objects.filter(pg_id=6,is_instant=True).exclude(trn_status='PENDING').order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)

                else:
                    return Response({'status': 'fail', 'message': 'Invalid sp_id.'}, status=status.HTTP_400_BAD_REQUEST)
                
            # DISTRIBUTORS
            else:

                distributor_id = request.user.id

                retailers = PortalUserDetails.objects.filter(created_by=distributor_id)
                retailer_ids = retailers.values_list('pu', flat=True)

                if sp_id == '1':
                    queryset = PosServiceTrn.objects.filter(created_by__in=retailer_ids).order_by('-pk')
                    processed_data = pos_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                    
                elif sp_id == '2':
                    queryset = BBPSBillPayment.objects.filter(created_by__in=retailer_ids).order_by('-pk')
                    processed_data = bbps_fetch_transactions(request, queryset, filter_by, start_date, end_date, combined_user_list, bbps_request_id, bbps_blr_id, search_txt, page_size, page_number)


                elif sp_id == '3':
                    # queryset = PgServiceTrn.objects.filter(created_by__in=retailer_ids).order_by('-pk')
                    queryset = PgServiceTrn.objects.filter(created_by__in=retailer_ids,pg_id=3,is_instant=False).order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)

                elif sp_id == '4':
                    queryset = PgServiceTrn.objects.filter(
                        created_by__in=retailer_ids,
                        pg_id=4,
                        is_instant=False
                    ).order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '6':
                    # queryset = PgServiceTrn.objects.filter(created_by__in=retailer_ids).order_by('-pk')
                    queryset = PgServiceTrn.objects.filter(created_by__in=retailer_ids,pg_id=5,is_instant=False).order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '7':
                    queryset = PgServiceTrn.objects.filter(created_by__in=retailer_ids,pg_id=4,is_instant=True).order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '8':
                    queryset = PgServiceTrn.objects.filter(created_by__in=retailer_ids,pg_id=5,is_instant=True).order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '9':
                    queryset = PgServiceTrn.objects.filter(created_by__in=retailer_ids,pg_id=3,is_instant=True).order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '10':
                    queryset = PgServiceTrn.objects.filter(
                        created_by__in=retailer_ids,
                        pg_id=6,
                        is_instant=False
                    ).order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                elif sp_id == '11':
                    queryset = PgServiceTrn.objects.filter(
                        created_by__in=retailer_ids,
                        pg_id=6,
                        is_instant=True
                    ).order_by('-pk')
                    processed_data = pg_fetch_transactions(request, queryset, trn_unique_id, terminal_id, search_txt, filter_by, start_date, end_date, combined_user_list, page_size, page_number)
                else:
                    return Response({'status': 'fail', 'message': 'Invalid sp_id.'}, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                'status': 'success',
                'message': 'Transaction data fetched successfully.',
                'data': processed_data,
                'totals': processed_data.get('totals', {})  
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        

class RetailerTransactionAPIView(APIView):  # FATCH RETAILER TRANSACTION
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            pos_devices = PosDevice.objects.filter(pu=user)
            terminal_count = pos_devices.count()
            terminal_ids = list(pos_devices.values_list('terminal', flat=True)) if terminal_count > 0 else []

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            queryset = PosServiceTrn.objects.filter(created_by=request.user.id)

            # gl_trn_queryset = GlTrn.objects.filter(pu_id=user).values_list('service_trn_id', flat=True)
            # queryset = queryset.filter(pk__in=gl_trn_queryset)

            daily_transactions = queryset.filter(pos_trn_dt__range=[today_start, today_end])
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(terminal_id__icontains=search_txt)   |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)

            if terminal_id:
                queryset = queryset.filter(terminal_id=terminal_id)

            if start_date:
                queryset = queryset.filter(pos_trn_dt__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(pos_trn_dt__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'device_count': terminal_count,
                    'terminal_ids': terminal_ids,
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                }]
            }

            response_data = {
                'status': 'success',
                'message': 'Transaction data fetched successfully3.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#BBPS Cat service Charge Update API

class RetailerVegaahPGTransactionAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            
            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=4,is_instant=False)

            daily_transactions = queryset.filter(created_at__range=[today_start, today_end])
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)

            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                }]
            }
            

            response_data = {
                'status': 'success',
                'message': 'Vegaah transaction data fetched successfully.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RetailerVegaahPG2TransactionAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            
            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=5,is_instant=False)

            daily_transactions = queryset.filter(created_at__range=[today_start, today_end])
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)

            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                }]
            }
            print(paginated_response_data,'=====================================>>>>>>>>>>>>>>>>>>>>>>>>>')

            response_data = {
                'status': 'success',
                'message': 'Vegaah transaction data fetched successfully.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateServiceCategoryCharges(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        try:
            if 'service_id' in request.data and 'page_number' in request.data or 'page_size' in request.data:
                if request.data.get('service_id') == '2':
                    return self.fetch_bbps_data(request)
                elif request.data.get('service_id') == '3':
                    return self.fetch_recharge_data(request)
                else:
                    return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_bbps_data(self, request):
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        bbps_id = request.data.get('bbps_id', None)
        search = request.data.get('search', '')

        try:
            if not page_number:
                return Response({'status': 'fail', 'message': 'page_number is required.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not page_size:
                return Response({'status': 'fail', 'message': 'page_size is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not isnumber(page_number):
                return Response({'status': 'fail', 'message': 'page_number must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(page_size):
                return Response({'status': 'fail', 'message': 'page_size must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)

            page_number = int(page_number)
            page_size = int(page_size)

            if page_number < 1 or page_size < 1:
                return Response({'status': 'fail', 'message': 'page_number and page_size must be greater than 0.'},
                                status=status.HTTP_400_BAD_REQUEST)

            all_categories = BBPSBillerCategory.objects.filter(is_deleted=False, sa_provided=True).order_by('-pk')

            if bbps_id:
                all_categories = all_categories.filter(bbps_id=bbps_id).order_by('-pk')

            if search != '':
                all_categories = all_categories.filter(Q(category_name__icontains=search)).order_by('-pk')

            paginator = Paginator(all_categories, page_size)
            categories = paginator.page(page_number)
            serializer = BBPSBillerCategorySerializer(categories, many=True)
            data = {
                'total_pages': paginator.num_pages,
                'current_page': page_number,
                'total_items': paginator.count,
                'results': serializer.data
            }
            return Response({'status': 'success', 'message': 'BBPS Biller Categories', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        service_id = request.data.get('service_id')
        print('service_id--', service_id)
        try:
            if service_id == '2':
                return self.update_bbps_category(request)
            elif service_id == '3':
                return self.update_recharge_category(request)
            else:
                return Response({'status': 'fail', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update_bbps_category(self, request):
        bbps_id = request.data.get('bbps_id')
        service_id = request.data.get('service_id')
        sd_charges = request.data.get('sd_charges', None)
        md_charges = request.data.get('md_charges', None)
        dt_charges = request.data.get('dt_charges', None)
        rt_charges = request.data.get('rt_charges', None)
        charge_type = request.data.get('charge_type', None)
        rate_type = request.data.get('rate_type', None)
        commission_type = request.data.get('commission_type', None)
        message = 'BBPS Category updated successfully.'

        try:
            if not bbps_id:
                return Response({'status': 'fail', 'message': 'bbps_id is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not service_id:
                return Response({'status': 'fail', 'message': 'service_id is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not isnumber(bbps_id):
                return Response({'status': 'fail', 'message': 'bbps_id must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)

            service = AdService.objects.get(service_id=service_id)

            service_provider = AdServiceProvider.objects.filter(service_id=service).first()
            bbps_category = BBPSBillerCategory.objects.get(bbps_id=bbps_id)

            if not service.is_global:
                return Response({'status': 'fail', 'message': 'The service is not global.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not sd_charges and not md_charges and not dt_charges and not rt_charges:
                if not (bbps_category.sd_charges and bbps_category.md_charges and
                        bbps_category.dt_charges and bbps_category.rt_charges):
                    return Response({
                        'status': 'fail',
                        'message': 'The service and service provider are active. Please configure charges before proceeding.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if not bbps_category.is_deactive:
                    bbps_category.is_deactive = True
                    bbps_category.save()
                    message = 'BBPS category deactivated successfully.'
                else:
                    bbps_category.is_deactive = False
                    bbps_category.save()
                    message = 'BBPS category activated successfully.'
            else:
                def parse_charges(charges, charge_type, rate_type, commission_type):
                    if charges:
                        try:
                            charges = json.loads(charges)
                            if not isinstance(charges, dict):
                                raise ValidationError("Invalid format for charges. Must be a JSON object.")
                            charges.update({
                                'charge_type': charge_type,
                                'is_slab': False,
                                'maximum': 0.0,
                                'minimum': 0.0,
                                'rate_type': rate_type,
                                'commission_type': commission_type,
                                'effective_wallet': 'main_wallet'
                            })
                            return charges
                        except json.JSONDecodeError:
                            raise ValidationError("Invalid JSON format for charges.")
                    return None

                sd_charges = parse_charges(sd_charges, charge_type, rate_type, commission_type)
                md_charges = parse_charges(md_charges, charge_type, rate_type, commission_type)
                dt_charges = parse_charges(dt_charges, charge_type, rate_type, commission_type)
                rt_charges = parse_charges(rt_charges, charge_type, rate_type, commission_type)

                if not bbps_category.sd_charges and not bbps_category.md_charges and \
                        not bbps_category.dt_charges and not bbps_category.rt_charges:
                    message = 'BBPS Category added successfully.'

                bbps_category.sd_charges = [sd_charges] if sd_charges else bbps_category.sd_charges
                bbps_category.md_charges = [md_charges] if md_charges else bbps_category.md_charges
                bbps_category.dt_charges = [dt_charges] if dt_charges else bbps_category.dt_charges
                bbps_category.rt_charges = [rt_charges] if rt_charges else bbps_category.rt_charges
                bbps_category.save()

            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)

        except AdServiceProvider.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Service provider does not exist.'},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_recharge_data(self, request):
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        operator_id = request.data.get('operator_id', None)
        search = request.data.get('search', '')

        try:
            if not page_number:
                return Response({'status': 'fail', 'message': 'page_number is required.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not page_size:
                return Response({'status': 'fail', 'message': 'page_size is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not isnumber(page_number):
                return Response({'status': 'fail', 'message': 'page_number must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(page_size):
                return Response({'status': 'fail', 'message': 'page_size must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)

            page_number = int(page_number)
            page_size = int(page_size)

            if page_number < 1 or page_size < 1:
                return Response({'status': 'fail', 'message': 'page_number and page_size must be greater than 0.'},
                                status=status.HTTP_400_BAD_REQUEST)

            all_oprators = Oprators.objects.filter(is_deleted=False, sa_provided=True).order_by('-pk')

            if operator_id:
                all_oprators = all_oprators.filter(operator_id=operator_id).order_by('-pk')

            if search != '':
                all_oprators = all_oprators.filter(
                    Q(operator_name__icontains=search) | Q(operator_code__icontains=search) | Q(
                        operator_type__icontains=search)).order_by('-pk')

            paginator = Paginator(all_oprators, page_size)
            oprators = paginator.page(page_number)
            serializer = AdOperatorSerializer(oprators, many=True)
            data = {
                'total_pages': paginator.num_pages,
                'current_page': page_number,
                'total_items': paginator.count,
                'results': serializer.data
            }
            return Response({'status': 'success', 'message': 'Recharge Oprators fetch successfully', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update_recharge_category(self, request):
        operator_id = request.data.get('operator_id')
        service_id = request.data.get('service_id')
        sd_charges = request.data.get('sd_charges', None)
        md_charges = request.data.get('md_charges', None)
        dt_charges = request.data.get('dt_charges', None)
        rt_charges = request.data.get('rt_charges', None)
        charge_type = request.data.get('charge_type', None)
        rate_type = request.data.get('rate_type', None)
        commission_type = request.data.get('commission_type', None)
        message = 'Recharge Operator updated successfully.'

        try:
            if not operator_id:
                return Response({'status': 'fail', 'message': 'operator_id is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not service_id:
                return Response({'status': 'fail', 'message': 'service_id is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not isnumber(operator_id):
                return Response({'status': 'fail', 'message': 'operator_id must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)

            service = AdService.objects.get(service_id=service_id)
            service_provider = AdServiceProvider.objects.filter(service_id=service).first()
            operators = Oprators.objects.get(operator_id=operator_id)

            if not service.is_global:
                return Response({'status': 'fail', 'message': 'The service is not global.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not sd_charges and not md_charges and not dt_charges and not rt_charges:
                if not (operators.sd_charges and operators.md_charges and
                        operators.dt_charges and operators.rt_charges):
                    return Response({
                        'status': 'fail',
                        'message': 'The service and service provider are active. Please configure charges before proceeding.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if not operators.is_deactive:
                    operators.is_deactive = True
                    operators.save()
                    message = 'Recharge Operator deactivated successfully.'
                else:
                    operators.is_deactive = False
                    operators.save()
                    message = 'Recharge Operator activated successfully.'
            else:
                def parse_charges(charges, charge_type, rate_type, commission_type):
                    if charges:
                        try:
                            charges = json.loads(charges)
                            if not isinstance(charges, dict):
                                raise ValidationError("Invalid format for charges. Must be a JSON object.")
                            charges.update({
                                'charge_type': charge_type,
                                'is_slab': False,
                                'maximum': 0.0,
                                'minimum': 0.0,
                                'rate_type': rate_type,
                                'commission_type': commission_type,
                                'effective_wallet': 'commission_wallet'
                            })
                            return charges
                        except json.JSONDecodeError:
                            raise ValidationError("Invalid JSON format for charges.")
                    return None

                sd_charges = parse_charges(sd_charges, charge_type, rate_type, commission_type)
                md_charges = parse_charges(md_charges, charge_type, rate_type, commission_type)
                dt_charges = parse_charges(dt_charges, charge_type, rate_type, commission_type)
                rt_charges = parse_charges(rt_charges, charge_type, rate_type, commission_type)

                if not operators.sd_charges and not operators.md_charges and \
                        not operators.dt_charges and not operators.rt_charges:
                    message = 'Recharge Operator added successfully.'

                operators.sd_charges = [sd_charges] if sd_charges else operators.sd_charges
                operators.md_charges = [md_charges] if md_charges else operators.md_charges
                operators.dt_charges = [dt_charges] if dt_charges else operators.dt_charges
                operators.rt_charges = [rt_charges] if rt_charges else operators.rt_charges
                operators.save()

            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)

        except AdServiceProvider.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Service provider does not exist.'},
                            status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# transaction cretedby null to Assign Pos Device To Retailer
class AssignPosDeviceToRetailerAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        retailer_id = request.data.get('retailer_id')
        transaction_id = request.data.get('transaction_id')

        if not retailer_id:
            return Response({'status': "fail", 'message': 'retailer_id Required'}, status=status.HTTP_400_BAD_REQUEST)

        if not transaction_id:
            return Response({'status': "fail", 'message': 'transaction_id Required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                service_transaction = PosServiceTrn.objects.get(pos_trn_id=transaction_id, created_by__isnull=True)

                sp = AdServiceProvider.objects.filter(sp_id=service_transaction.sp_id).first()

                terminal_id = service_transaction.terminal_id

                if PosDevice.objects.filter(terminal=terminal_id).exists():
                    return Response({'status': "fail", 'message': 'Terminal ID already assigned'}, status=status.HTTP_400_BAD_REQUEST)
                
                user = PortalUser.objects.get(id=retailer_id,is_deleted=False, is_deactive=False)

                if not user.pu_role == 'RETAILER':
                    return Response({'status': "fail", 'message': 'Invalid retailer ID'}, status=status.HTTP_400_BAD_REQUEST)
                
                PosDevice.objects.create(
                    terminal=terminal_id,
                    pu=user,
                    sp = sp,
                    created_by=request.user.id
                    )
                pos_service_trns = PosServiceTrn.objects.filter(terminal_id=terminal_id)

                for pos_service in pos_service_trns:
                    pos_service.created_by=user.id
                    pos_service.save()

                return Response({'status': 'success', 'message': 'Terminal assigned successfully'}, status=status.HTTP_201_CREATED)

        except PosServiceTrn.DoesNotExist:
            return Response({'status': "fail", 'message': 'Invalid transaction ID, already assigned'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': "fail", 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Retailer Dashboard API
class RetailerDashboardAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsRetailer]

    def post(self, request):
        try:
            if 'card_no' in request.data and not ('bill_amount' in request.data):
                return self.charge_checker(request)
        
            elif 'card_no' in request.data and 'bill_amount' in request.data:
                return self.range_calculator(request)
            
            return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

    def charge_checker(self, request):
        try:
            card_no = request.data.get('card_no')

            if not card_no:
                return Response({'status': 'error', 'message': 'Card number is required'},status=status.HTTP_400_BAD_REQUEST)

            response = fetch_bin_details(card_no, request.user.id)

            data = {'charge_type': response.get('charge_type'), 'charge_value': response.get('rate_value'), 'rate_type': response.get('rate_type')}

            return Response(
                {'status': 'success', 'message': 'BIN details fetched successfully', 'data': data},status=status.HTTP_200_OK)


        except Exception as e:
            return Response({'status': 'error', 'message': 'An unexpected error occurred', 'error': str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def range_calculator(self,request):
        try:
            card_no = request.data.get('card_no')
            bill_amount = float(request.data.get('bill_amount', 0))

            if not card_no:
                return Response({'status': 'error', 'message': 'Card number is required'},status=status.HTTP_400_BAD_REQUEST)

            if not bill_amount:
                return Response({'status': 'error', 'message': 'Bill amount is required'},status=status.HTTP_400_BAD_REQUEST)
            
            response = fetch_bin_details(card_no, request.user.id)
            per = response.get('rate_value')

            print(per, 'per')

            pos_amount = (bill_amount * 100) / (100 + per)

            cash_amount = bill_amount - pos_amount
            # total_amount = pos_amount + cash_amount
 
            total_amount = bill_amount

            data = {
                'charge_type': response.get('charge_type'),
                'pos_amount': round(pos_amount, 2),
                'cash_amount': round(cash_amount, 2),
                'total_amount': round(total_amount, 2),
            }

            return Response({'status': 'success', 'message': 'Calculation successful', 'data': data},
                            status=status.HTTP_200_OK)
        

        except Exception as e:
            return Response({'status': 'error', 'message': 'An unexpected error occurred', 'error': str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)




import hashlib
import json
import requests
from django.conf import settings
from django.shortcuts import render, redirect

def generate_checksum(params, secret_key):
    """Generate checksum hash using SHA256"""
    sorted_params = sorted(params.items())
    checksum_str = "".join(f"{k}={v}" for k, v in sorted_params)
    return hashlib.sha256((checksum_str + secret_key).encode()).hexdigest()

def initiate_payment(request):
    if request.method == "POST":
        amount = request.POST.get("amount")
        order_id = "ORDER" + str(hashlib.md5(amount.encode()).hexdigest()[:10])  # Unique order ID
        
        SC = "PeNU93uJ2srVMDUp"
        airpay_config = settings.AIRPAY_CONFIG

        payment_data = {
            "mercid": "314614",
            "username": "U9tjY6MzSN",
            "password": "wKwHX3tT",
            "secret": "PeNU93uJ2srVMDUp",
            "amt": amount,
            "orderid": order_id,
            "txnmode": "1",  # 1 = Netbanking, 2 = Card, etc.
            "currency": "INR",
            "isocurrency": "356",
            "customerEmail": "user@example.com",
            "customerPhone": "9999999999",
            "successurl": "https://qaapi.fixpay.in/payinResponse/",
            "failureurl": "https://qaapi.fixpay.in/admin_hub/pos_test",
        }

        payment_data["checksum"] = generate_checksum(payment_data, SC)

        # Redirect to Airpay Payment Page
        payment_url = f"{airpay_config['BASE_URL']}/payment"
        return redirect(f"{payment_url}?{json.dumps(payment_data)}")
    
    return render(request, "payment_form.html")

from django.http import JsonResponse

def payment_success(request):
    return JsonResponse({"status": "success", "message": "Payment successful!"})

def payment_failed(request):
    return JsonResponse({"status": "failed", "message": "Payment failed!"})






from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import PortalUser, PortalUserWallet, WalletTrn
from .serializers import WalletTrnSerializer
import datetime

class AdminUserWalletTransactionsView(APIView):
    def post(self, request,user_id):
        data = {
            "total_pages": 0,
            "current_page": 0,
            "total_items": 0,
            "results": []
        }
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        consolidation_wallet = request.data.get('wallet', None)
        page_size = int(page_size)
        page_number = int(page_number)
        user = user_id

        print(user)
        try:
            user = PortalUser.objects.get(id=user, is_deleted=False)
            puw_user = PortalUserWallet.objects.get(pu_id=user)

            filter_wallet_transaction = WalletTrn.objects.filter(pu=user)

            if consolidation_wallet is not None:
                filter_wallet_transaction = filter_wallet_transaction.filter(effectvie_wallet=consolidation_wallet)

            # descending
            filter_wallet_transaction = filter_wallet_transaction.order_by('-pk')  # fatch data

            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size

            paginated_wallet_transaction = filter_wallet_transaction[start_index:end_index]

            total_items = filter_wallet_transaction.count()

            total_pages = (len(filter_wallet_transaction) + page_size - 1) // page_size

            serializer = WalletTrnSerializer(paginated_wallet_transaction, many=True)

            response_data = []

            for data in serializer.data:
                # data['current_balance'] = puw_user.main_wallet
                response_data.append(
                    {'effective_wallet': data.get("effectvie_wallet"), 'effective_ammount': data.get("effectvie_amt"),
                     'effective_type': data.get("effective_type")})
                # ADD DATE TIME
                if data.get('wl_trn_dt'):
                    data['wl_trn_dt'] = datetime.datetime.strptime(data['wl_trn_dt'],
                                                                   "%Y-%m-%dT%H:%M:%S.%f%z").strftime(
                        "%Y-%m-%d %I:%M %p")

            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serializer.data
            }

            return Response({'status': 'success', 'message': f'Get all user transaction.', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class AdminUserProfileAPIView(APIView):
    """
    API view to handle the user profile.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request,user_id):
        """
        API endpoint for retrieving the authenticated user's details.

        This endpoint requires authentication with a JWT token.
        """

        try:
            users = PortalUser.objects.get(id=user_id)
            print(users)

            if users.pu_role == "ADMIN":
                serializer = PortalUserSerializer(users, context={'request': request})
                user_data = serializer.data

                response_data = {
                    'status': 'success',
                    'message': 'Admin user data retrieved successfully',
                    'data': user_data
                }
                return Response(response_data, status=status.HTTP_200_OK)

            # Fetch user details and wallet for other roles
            user_details = PortalUserDetails.objects.filter(pu=users).first()
            wallet = PortalUserWallet.objects.filter(pu=users).first()

            wallet_serializer = PortalUserWalletSerializer(wallet, context={'request': request})
            serializer = PortalUserSerializer(users, context={'request': request})

            user_data = serializer.data
            wallet_data = wallet_serializer.data
            user_data['wallet'] = wallet_data

            if users.pu_role == "DISTRIBUTOR":
                try:
                    puc_obj = PortalUserCharges.objects.filter(pu_id=request.user.id).first()
                    distributor_hierarchy = DistributorHierarchy.objects.get(dh_id=user_details.dh_id)

                    if distributor_hierarchy.dh_name == 'SUPER DISTRIBUTOR':
                        partner_category = "SUPER DISTRIBUTOR"
                    elif distributor_hierarchy.dh_name == 'MASTER DISTRIBUTOR':
                        partner_category = "MASTER DISTRIBUTOR"
                    else:
                        partner_category = "DISTRIBUTOR"

                    user_data['partner_category'] = partner_category
                    user_data['distributor_wallet'] = {
                        'main_wallet': wallet.main_wallet,
                        'cashin_wallet': wallet.cashin_wallet,
                        'pg_wallet': wallet.pg_wallet
                    }
                    user_data['aadhaar_card'] = user_details.aadhaar_card
                    user_data['pan_card'] = user_details.pan_card
                    user_data['is_kyc_verified'] = users.is_kyc_verify

                except DistributorHierarchy.DoesNotExist:
                    return Response({
                        'status': 'fail',
                        'message': 'Partner Category Does Not Exist'
                    }, status=status.HTTP_404_NOT_FOUND)

            # Handle logic for RETAILER role
            if users.pu_role == 'RETAILER':
                user_data['partner_category'] = "RETAILER"
                user_data['retailer_wallet'] = {
                    'main_wallet': wallet.main_wallet,
                    'cashin_wallet': wallet.cashin_wallet,
                    'pg_wallet': wallet.pg_wallet
                }
                user_data['aadhaar_card'] = user_details.aadhaar_card
                user_data['pan_card'] = user_details.pan_card
                user_data['is_kyc_verified'] = users.is_kyc_verify

            response_data = {
                'status': 'success',
                'message': 'User data retrieved successfully',
                'data': user_data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            response_error = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_error, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        
class DistributorUserProfileAPIView(APIView):
    """
    API view to handle the user profile.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor]
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request,user_id):
        """
        API endpoint for retrieving the authenticated user's details.

        This endpoint requires authentication with a JWT token.
        """

        try:
            users = PortalUser.objects.get(id=user_id)
            print(users)


            # Fetch user details and wallet for other roles
            user_details = PortalUserDetails.objects.filter(pu=users).first()
            wallet = PortalUserWallet.objects.filter(pu=users).first()

            wallet_serializer = PortalUserWalletSerializer(wallet, context={'request': request})
            serializer = PortalUserSerializer(users, context={'request': request})

            user_data = serializer.data
            wallet_data = wallet_serializer.data
            user_data['wallet'] = wallet_data

            if users.pu_role == "DISTRIBUTOR":
                try:
                    puc_obj = PortalUserCharges.objects.filter(pu_id=request.user.id).first()
                    distributor_hierarchy = DistributorHierarchy.objects.get(dh_id=user_details.dh_id)

                    if distributor_hierarchy.dh_name == 'SUPER DISTRIBUTOR':
                        partner_category = "SUPER DISTRIBUTOR"
                    elif distributor_hierarchy.dh_name == 'MASTER DISTRIBUTOR':
                        partner_category = "MASTER DISTRIBUTOR"
                    else:
                        partner_category = "DISTRIBUTOR"

                    user_data['partner_category'] = partner_category
                    user_data['distributor_wallet'] = {
                        'main_wallet': wallet.main_wallet,
                        'cashin_wallet': wallet.cashin_wallet,
                        'pg_wallet': wallet.pg_wallet
                    }
                    user_data['aadhaar_card'] = user_details.aadhaar_card
                    user_data['pan_card'] = user_details.pan_card
                    user_data['is_kyc_verified'] = users.is_kyc_verify

                except DistributorHierarchy.DoesNotExist:
                    return Response({
                        'status': 'fail',
                        'message': 'Partner Category Does Not Exist'
                    }, status=status.HTTP_404_NOT_FOUND)

            # Handle logic for RETAILER role
            if users.pu_role == 'RETAILER':
                user_data['partner_category'] = "RETAILER"
                user_data['retailer_wallet'] = {
                    'main_wallet': wallet.main_wallet,
                    'cashin_wallet': wallet.cashin_wallet,
                    'pg_wallet': wallet.pg_wallet
                }
                user_data['aadhaar_card'] = user_details.aadhaar_card
                user_data['pan_card'] = user_details.pan_card
                user_data['is_kyc_verified'] = users.is_kyc_verify

            response_data = {
                'status': 'success',
                'message': 'User data retrieved successfully',
                'data': user_data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            response_error = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_error, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class ChangeMPINView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]

    def post(self, request):
        data = request.data
        old_mpin = data.get("old_mpin")
        new_mpin = data.get("new_mpin")
        confirm_mpin = data.get("confirm_mpin")  

        if not old_mpin or not new_mpin or not confirm_mpin:
            return Response({'status': 'fail', "error": "All MPIN fields are required"}, status=status.HTTP_400_BAD_REQUEST)

        if new_mpin != confirm_mpin:
            return Response({'status': 'fail', "error": "New MPIN and Confirm MPIN do not match"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            old_mpin = int(old_mpin)
            new_mpin = int(new_mpin)
        except ValueError:
            return Response({'status': 'fail', "error": "Invalid MPIN format"}, status=status.HTTP_400_BAD_REQUEST)

        user = PortalUser.objects.get(id=request.user.id)

        if user.mpin != old_mpin:
            return Response({'status': 'fail', "error": "Old MPIN is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        user.mpin = new_mpin
        user.save()

        return Response({'status': 'success', 'message': 'MPIN changed successfully'}, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]

    def post(self, request):
        data = request.data
        old_password = data.get("old_password")
        new_password = data.get("new_password")
        confirm_password = data.get("confirm_password")  

        if not old_password or not new_password or not confirm_password:
            return Response({'status': 'fail', 'error': 'All password fields are required'}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({'status': 'fail', 'error': 'New password and Confirm password do not match'}, status=status.HTTP_400_BAD_REQUEST)

        user = PortalUser.objects.get(id=request.user.id)

        if not check_password(old_password, user.password):
            return Response({'status': 'fail', 'error': 'Old password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

        user.password = make_password(new_password)
        user.save()

        return Response({'status': 'success', 'message': 'Password changed successful'}, status=status.HTTP_200_OK)




class NewBankDetailsAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        try:
            if 'bank_name' in request.data and 'ifsc_code' in request.data and 'account_number' in request.data:
                return self.add_or_update_bank_details(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid request'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def get(self, request):
        """ Handle GET request to fetch user bank details """
        return self.get_bank_details(request)
    
    def delete(self, request):
        """ Handle GET request to fetch user bank details """
        return self.delete_bank_details(request)

    def add_or_update_bank_details(self, request):
        try:
            user = request.user
            if not user:
                return Response({'status': 'fail', 'message': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

            bank_details_id = request.data.get('bank_details_id')  # ID for update
            bank_name = request.data.get('bank_name')
            ifsc_code = request.data.get('ifsc_code')
            account_number = request.data.get('account_number')
            account_holder = request.data.get('account_holder')
            branch = request.data.get('branch')

            required_fields = ['bank_name', 'ifsc_code', 'account_number' ,'account_holder']
            missing_fields = [field for field in required_fields if not request.data.get(field)]
            
            if missing_fields:
                return Response(
                    {'status': 'fail', 'message': f'Required fields are empty: {", ".join(missing_fields)}. Provide all required fields and try again'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validation checks
            if not isstring(bank_name):
                return Response({'status': 'fail', 'message': 'Invalid bank name. It should be a string.'}, status=status.HTTP_400_BAD_REQUEST)

            if not is_valid_ifsc(ifsc_code):
                return Response({'status': 'fail', 'message': 'Invalid IFSC code. Please check the format.'}, status=status.HTTP_400_BAD_REQUEST)

            if not isnumber(account_number):
                return Response({'status': 'fail', 'message': 'Invalid account number. It should contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            if not validate_account_number(account_number):
                return Response({'status': 'fail', 'message': 'Invalid account number. It should be between 11 and 16 digits.'}, status=status.HTTP_400_BAD_REQUEST)

            # If bank_details_id is provided, update the existing record
            if bank_details_id:
                existing_bank_details = BankDetailsUser.objects.filter(bd_id=bank_details_id, created_by=user, is_delete=False).first()
                if not existing_bank_details:
                    return Response({'status': 'fail', 'message': 'Bank details not found.'}, status=status.HTTP_404_NOT_FOUND)

                existing_bank_details.bank_name = bank_name
                existing_bank_details.ifsc_code = ifsc_code
                existing_bank_details.account_number = account_number
                existing_bank_details.account_holder_name = account_number
                existing_bank_details.bank_branch = branch


                existing_bank_details.save()

                return Response({'status': 'success', 'message': 'Bank details updated successfully.'}, status=status.HTTP_200_OK)

            # Check if bank details already exist for the same user
            get_exists_bank = BankDetailsUser.objects.filter(
                bank_name=bank_name, ifsc_code=ifsc_code, account_number=account_number, created_by=user, is_delete=False,account_holder_name = account_holder
            ).first()

            if get_exists_bank:
                return Response({'status': 'fail', 'message': 'Bank details already exist.'}, status=status.HTTP_400_BAD_REQUEST)

            # Create new bank details
            BankDetailsUser.objects.create(
                bank_name=bank_name,
                ifsc_code=ifsc_code,
                account_number=account_number,
                account_holder_name=account_holder,
                created_by=user,
                bank_branch=branch,

            )

            return Response({'status': 'success', 'message': 'Bank details added successfully.'}, status=status.HTTP_201_CREATED)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User does not exist.'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    



    
    def get_bank_details(self, request):
        try:
            # Fetch the authenticated user from the request
            user = request.user
            if not user:
                return Response({'status': 'fail', 'message': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

            # Fetch all bank details for the logged-in user where is_delete is False
            bank_details_list = BankDetailsUser.objects.filter(created_by=user, is_delete=False)

            if bank_details_list.exists():
                result = []
                for get_bank_detail in bank_details_list:
                    # Build the response data for each bank detail
                    bank_detail = {
                        'bank_details_id': get_bank_detail.bd_id,
                        'bank_name': get_bank_detail.bank_name,
                        'ifsc_code': get_bank_detail.ifsc_code,
                        'account_number': get_bank_detail.account_number,
                        'account_holder': get_bank_detail.account_holder_name
                    }
                    result.append(bank_detail)

                # Return the success response with the bank details
                return Response({'status': 'success', 'data': result}, status=status.HTTP_200_OK)
            else:
                return Response({'status': 'fail', 'message': 'No bank details found.'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            # Handle any other exceptions that may occur
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


 

    def delete_bank_details(self, request):
        try:
            # Fetch the authenticated user from the request
            user = request.user
            if not user:
                return Response({'status': 'fail', 'message': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

            # Get the bank details ID from the request
            print
            bank_details_id = request.data.get('bank_details_id')
            print(bank_details_id)

            if not bank_details_id:
                return Response({'status': 'fail', 'message': 'Bank details ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

            # Fetch the bank details for the logged-in user
            bank_detail = BankDetailsUser.objects.filter(
                created_by=user, 
                bd_id=bank_details_id, 
                is_delete=False
            ).first()

            if bank_detail:
                # Mark the bank details as deleted
                bank_detail.is_delete = True
                bank_detail.save()

                return Response({'status': 'success', 'message': 'Bank details deleted successfully.'}, status=status.HTTP_200_OK)
            else:
                return Response({'status': 'fail', 'message': 'No bank details found with the provided ID.'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







# class PayoutRequestAPIView(APIView):
#     authentication_classes = [CustomJWTAuthentication]
#     permission_classes = [IsAdmin | IsDistributor | IsRetailer]

#     def post(self, request):
#         try:
#             if 'bank_id' in request.data and 'amount' in request.data:
#                 return self.add_payout_request(request)
#             elif 'page_size' in request.data or 'page_size' in request.data:
#                 return self.get_payout_requests(request)
#             else:
#                 return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             print(str(e))
#             return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
#                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    



#     def add_payout_request(self, request):
#         try:
#             bd_id = request.data.get('bank_id')
#             deposit_amount = request.data.get('amount')
#             description = request.data.get('description')

#             if not bd_id:
#                 return Response({'status': 'fail', 'message': 'bank_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
#             if not deposit_amount:
#                 return Response({'status': 'fail', 'message': 'amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

#             try:
#                 deposit_amount = float(deposit_amount)
#                 if deposit_amount <= 0:
#                     return Response({'status': 'fail', 'message': 'Deposit amount must be a positive number.'}, status=status.HTTP_400_BAD_REQUEST)
#             except ValueError:
#                 return Response({'status': 'fail', 'message': 'Invalid deposit amount.'}, status=status.HTTP_400_BAD_REQUEST)

#             try:
#                 bank_detail = BankDetailsUser.objects.get(bd_id=bd_id)
#             except BankDetailsUser.DoesNotExist:
#                 return Response({'status': 'fail', 'message': 'Bank does not exist.'}, status=status.HTTP_400_BAD_REQUEST)

#             payout_request = PayoutRequest.objects.create(
#                 bank=bank_detail,
#                 amount=deposit_amount,
#                 description=description,
#                 created_at=timezone.now(),
#                 created_by=request.user
#             )

#             # Sending an email notification
#             subject = "New Payout Request Submitted"
#             message = f"""
#             Payout Request
            
#             Details:
#              - Retailer Name - {request.user.pu_name},
#             - Retailer Id - {request.user.username}
#             - Amount: {deposit_amount}
#             - Description: {description}
#             - Date: {timezone.now().strftime('%d-%m-%Y')}

            

#             Regards,
#             FixPay
#             """
#             recipient_email = 'mahesh.realwaysolutions@gmail.com'  
#             sender_email = 'sagar.realwaysolutions@gmail.com'

#             try:
#                 send_mail(subject, message, sender_email, [recipient_email])
#             except Exception as mail_error:
#                 print(str(mail_error))
#                 return Response({'status': 'error', 'message': f'Payout created but failed to send email: {str(mail_error)}'},
#                                 status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#             return Response({"status": "success", "message": "Payout request generated successfully."},
#                             status=status.HTTP_201_CREATED)

#         except Exception as e:
#             print(str(e))
#             return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
#                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)



#     def get_payout_requests(self, request):
#         try:
#             data = {
#                 'total_pages': 0,
#                 'current_page': 0,
#                 'total_items': 0,
#                 'results': []
#             }
#             deposite = {}
#             get_bank_details = []
#             page_size = int(request.data.get('page_size', 10))
#             page_number = int(request.data.get('page_number', 1))
#             # bank_details_id = request.data.get('bank_details_id', None)
#             # search = request.data.get('search', None)
#             if not page_size:
#                 return Response({'status': 'fail', 'message': 'Page size is required.'},
#                                 status=status.HTTP_400_BAD_REQUEST)

#             get_bank_details = PayoutRequest.objects.filter(is_delete=False)
            

        

#             paginator = Paginator(get_bank_details, page_size)

#             if page_number > paginator.num_pages:
#                 return Response({
#                     'status': 'success',
#                     'data': data
#                 }, status=status.HTTP_200_OK)

#             page_obj = paginator.get_page(page_number)

#             for bank_details in page_obj:
                

#                 results = {
#                     'pr_id':bank_details.pr_id,
#                     'retailer_id':bank_details.created_by.username,
#                     'name' : bank_details.created_by.pu_name,
#                     'amount': bank_details.amount,  
#                     'status': bank_details.request_status,  # Request Status
#                     'description': bank_details.description,  # Description
#                 }
#                 data['results'].append(results)


#             data['total_pages'] = paginator.num_pages
#             data['current_page'] = page_number
#             data['total_items'] = paginator.count

#             return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)

#         except Exception as e:
#             print(str(e))
#             return Response({
#                 'status': 'error',
#                 'message': f'Internal server error: {str(e)}'
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

class PayoutRequestAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        try:
            if 'bank_id' in request.data and 'amount' in request.data:
                return self.add_payout_request(request)
            elif 'page_size' in request.data or 'page_size' in request.data:
                return self.get_payout_requests(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(str(e))
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


    def add_payout_request(self, request):
        try:
            bd_id = request.data.get('bank_id')
            deposit_amount = request.data.get('amount')
            description = request.data.get('description')

            if not bd_id:
                return Response({'status': 'fail', 'message': 'bank_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not deposit_amount:
                return Response({'status': 'fail', 'message': 'amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                deposit_amount = float(deposit_amount)
                if deposit_amount <= 0:
                    return Response({'status': 'fail', 'message': 'Deposit amount must be a positive number.'}, status=status.HTTP_400_BAD_REQUEST)
            except ValueError:
                return Response({'status': 'fail', 'message': 'Invalid deposit amount.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                bank_detail = BankDetailsUser.objects.get(bd_id=bd_id)
            except BankDetailsUser.DoesNotExist:
                return Response({'status': 'fail', 'message': 'Bank does not exist.'}, status=status.HTTP_400_BAD_REQUEST)

            payout_request = PayoutRequest.objects.create(
                bank=bank_detail,
                amount=deposit_amount,
                description=description,
                created_at=timezone.now(),
                created_by=request.user
            )

            # Sending an email notification
            subject = "New Payout Request Submitted"
            message = f"""
            Payout Request
            
            Details:
             - Retailer Name - {request.user.pu_name},
            - Retailer Id - {request.user.username}
            - Amount: {deposit_amount}
            - Description: {description}
            - Date: {timezone.now().strftime('%d-%m-%Y')}

            

            Regards,
            FixPay
            """
            recipient_email = 'kunal@ssepl.live'  
            sender_email = 'noreply@fixpay.in'

            try:
                send_mail(subject, message, sender_email, [recipient_email])
            except Exception as mail_error:
                print(str(mail_error))
                return Response({'status': 'error', 'message': f'Payout created but failed to send email: {str(mail_error)}'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({"status": "success", "message": "Payout request generated successfully."},
                            status=status.HTTP_201_CREATED)

        except Exception as e:
            print(str(e))
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def get_payout_requests(self, request):
        try:
            data = {
                'total_pages': 0,
                'current_page': 0,
                'total_items': 0,
                'results': []
            }


            page_size = int(request.GET.get('page_size', 20))
            page_number = int(request.GET.get('page', 1))
            search = request.GET.get('search', '')

            if page_size <= 0:
                return Response({'status': 'fail', 'message': 'Page size must be greater than 0.'},
                                status=status.HTTP_400_BAD_REQUEST)


            get_bank_details = PayoutRequest.objects.filter(is_delete=False)

            if search:
                get_bank_details = get_bank_details.filter(
                    Q(created_by__username__icontains=search) |
                    Q(created_by__pu_name__icontains=search) |
                    Q(description__icontains=search)
                )


            get_bank_details = get_bank_details.order_by('-created_at')

            paginator = Paginator(get_bank_details, page_size)

            try:
                bank_details_data = paginator.page(page_number)
            except PageNotAnInteger:
                bank_details_data = paginator.page(1)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page number exceeds total pages.'
                }, status=status.HTTP_404_NOT_FOUND)


            for bank_details in bank_details_data:
                results = {
                    'pr_id': bank_details.pr_id,
                    'retailer_id': bank_details.created_by.username,
                    'name': bank_details.created_by.pu_name,
                    'amount': bank_details.amount,
                    'status': bank_details.request_status,
                    'description': bank_details.description,
                }
                data['results'].append(results)

            data['total_pages'] = paginator.num_pages
            data['current_page'] = page_number
            data['total_items'] = paginator.count

            return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e))
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



from django.utils.timezone import now
from django.http import JsonResponse

class PayoutActionView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        try:
            payout_ids = request.data.get('payout_ids', [])  
            status = request.data.get('request_status')

            print(payout_ids)
            if not isinstance(payout_ids, list) or not payout_ids or status not in ['APPROVED', 'REJECTED']:
                return JsonResponse({"error": "Invalid parameters"}, status=400)

            updated_payouts = []
            errors = []

            for payout_id in payout_ids:
                try:
                    payout = PayoutRequest.objects.get(pr_id=payout_id)

                    if payout.request_status in ['APPROVED', 'REJECTED']:
                        errors.append(f"Payout  is already {payout.request_status}")
                        continue

                    user_wallet = PortalUserWallet.objects.get(pu_id=payout.created_by)

                    if status == "APPROVED":
                        total_amount = payout.amount
                        actual_payout = total_amount - 10  
                        actual_charge = 10  

                        if user_wallet.main_wallet < total_amount:
                            errors.append(f"Payout ID {payout_id} failed: Insufficient wallet balance")
                            continue

                        user_wallet.main_wallet -= total_amount
                        user_wallet.save()

                        WalletTrn.objects.create(
                            action_id=payout.pr_id,
                            action_type="PAYOUT",
                            pu=payout.created_by,
                            wl_label="Payout Transfer",
                            effectvie_wallet="Main Wallet",
                            effectvie_amt=actual_payout,
                            effective_type="DEBIT",
                            wl_trn_des=f"Payout of ₹{actual_payout} processed",
                            wl_trn_dt=now(),
                            current_balance=user_wallet.main_wallet + actual_charge,
                        )

                        WalletTrn.objects.create(
                            action_id=payout.pr_id,
                            action_type="PAYOUT_CHARGE",
                            pu=payout.created_by,
                            wl_label="Payout Fee",
                            effectvie_wallet="Main Wallet",
                            effectvie_amt=actual_charge,
                            effective_type="DEBIT",
                            wl_trn_des=f"Payout charge of ₹{actual_charge} deducted",
                            wl_trn_dt=now(),
                            current_balance=user_wallet.main_wallet,
                        )

                    payout.request_status = status
                    payout.save()
                    updated_payouts.append(payout_id)

                except PayoutRequest.DoesNotExist:
                    errors.append(f"Payout ID {payout_id} not found")
                except PortalUserWallet.DoesNotExist:
                    errors.append(f"Wallet for Payout ID {payout_id} not found")
                except Exception as e:
                    errors.append(f"Payout ID {payout_id} failed: {str(e)}")

            response_data = {"success": True, "updated_payouts": updated_payouts}
            if errors:
                response_data["errors"] = errors

            return JsonResponse(response_data, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

from django.shortcuts import get_object_or_404
class ValidateMpinApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        try:
            data = json.loads(request.body)
            mpin = data.get("mpin")

            if mpin is None:
                return JsonResponse({"success": False, "error": "MPIN is required."}, status=400)

            if not isinstance(mpin, int):
                return JsonResponse({"success": False, "error": "MPIN should be a number."}, status=400)

            portal_user = get_object_or_404(PortalUser, id=request.user.id)

            if portal_user.mpin == mpin:
                return JsonResponse({"success": True, "message": "MPIN is valid."}, status=200)
            else:
                return JsonResponse({"success": False, "error": "Invalid MPIN."}, status=401)

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON format."}, status=400)
        except Exception as e:
            return JsonResponse({"success": False, "error": f"An error occurred: {str(e)}"}, status=500)


from django.http import HttpResponse
import csv
from rest_framework.decorators import api_view

@api_view(['POST'])
def export_payout_csv(request):
    payout_ids = request.data.get('payout_ids', []) 
    
    if not payout_ids:
        return Response({"error": "No payout IDs provided"}, status=400)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payout_requests.csv"'

    writer = csv.writer(response)

    # Fetch payout requests based on the payout IDs
    payout_requests = PayoutRequest.objects.filter(pr_id__in=payout_ids, is_delete=False)

    for payout in payout_requests:
        # Get bank details and payout information
        bank_details = payout.bank
        retailer_name = payout.created_by.pu_name  
        retailer_bank_account = bank_details.account_number
        retailer_ifsc_code = bank_details.ifsc_code
        payout_amount = payout.amount

        
        if payout_amount > 200000:
            transfer_method = 'RTGS'
        elif bank_details.ifsc_code.startswith('SBI'):
            transfer_method = 'DCR'
        else:
            transfer_method = 'NEFT'

        
        if payout.description:
            remark = payout.description
        else:
            status = payout.status
            timestamp = payout.created_at.strftime('%Y-%m-%d %H:%M:%S')  
            remark = f"Payment Initiated - {status} - {timestamp}"

        
        writer.writerow([
            '307398',  
            'FIX PAY SERVE PVT LTD',  
            '42871396236',  
            retailer_name,
            retailer_bank_account,
            retailer_ifsc_code,
            payout_amount,
            transfer_method,
            remark
        ])

    return response


from django.db.models.functions import TruncDate




class UpdatedWalletInRetailer(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def get(self, request):
        try:
            wallet = PortalUserWallet.objects.get(pu_id=request.user.id)
            total_balance = wallet.main_wallet
            print(wallet.main_wallet)

            pay_in = PosServiceTrn.objects.filter(
                trn_status="SUCCESS", is_settled=True
            ).aggregate(Sum("trn_amount"))["trn_amount__sum"] or 0

            print(pay_in)

            pay_out = PosServiceTrn.objects.filter(
                trn_status="FAILED", is_settled=False
            ).aggregate(Sum("trn_amount"))["trn_amount__sum"] or 0


            print(pay_out)
            today = datetime.datetime.today()

            pay_in_history = []
            pay_out_history = []
            static_amounts = [400000, 1000000, 1500000, 2000000, 2500000, 3000000, 4000000]  

            for i in range(7):
                date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                pay_in_history.append({"date": date, "amount": static_amounts[i % len(static_amounts)]})
                pay_out_history.append({"date": date, "amount": static_amounts[::-1][i % len(static_amounts)]})  

            
            # start_date = datetime.now() - timedelta(days=6)  

            # pay_in_history = (
            #     PosServiceTrn.objects.filter(
            #         trn_status="SUCCESS",
            #         is_settled=True,
            #         pos_trn_dt__date__gte=start_date,
            #     )
            #     .annotate(date=TruncDate("pos_trn_dt"))
            #     .values("date")
            #     .annotate(total=Sum("trn_amount"))
            #     .order_by("date")
            # )

            # pay_out_history = (
            #     PosServiceTrn.objects.filter(
            #         trn_status="FAILED",
            #         is_settled=False,
            #         pos_trn_dt__date__gte=start_date,
            #     )
            #     .annotate(date=TruncDate("pos_trn_dt"))
            #     .values("date")
            #     .annotate(total=Sum("trn_amount"))
            #     .order_by("date")
            # )

            

            return JsonResponse({
                "total_balance": float(total_balance),
                "pay_in": float(pay_in),
                "pay_out": float(pay_out),
                "pay_in_history": list(pay_in_history),
                "pay_out_history": list(pay_out_history),
            }, safe=False)

        except PortalUserWallet.DoesNotExist:
            return JsonResponse({"error": "User wallet not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        





from django.db.models import Sum
from django.utils.timezone import now, timedelta

from django.core.paginator import Paginator
from rest_framework.response import Response

class AdminHomePageRetailerDataApiView(APIView):

    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def get(self, request):
        today = now().date()
        start_of_week = today - timedelta(days=today.weekday())  
        start_of_month = today.replace(day=1)  

        # Aggregate wallet balances
        # Aggregate wallet balances only for approved retailers
        total_balances = PortalUserWallet.objects.filter(
            pu__pu_role="RETAILER",
            pu__pu_status="APPROVED"
        ).aggregate(
            total_main_wallet=Sum('main_wallet') or 0,
            total_cashin_wallet=Sum('cashin_wallet') or 0,
            total_pg_wallet=Sum('pg_wallet') or 0
        )

        print(total_balances)

        # Aggregate POS transactions and amounts
        pos_data = {
            "today_pos_amount": PosServiceTrn.objects.filter(pos_trn_dt__date=today,trn_status__in=["SETTLED", "COMPLETED"]).aggregate(total=Sum('trn_amount'))["total"] or 0,
            "this_week_pos_amount": PosServiceTrn.objects.filter(pos_trn_dt__date__gte=start_of_week,trn_status__in=["SETTLED", "COMPLETED"]).aggregate(total=Sum('trn_amount'))["total"] or 0,
            "this_month_pos_amount": PosServiceTrn.objects.filter(pos_trn_dt__date__gte=start_of_month,trn_status__in=["SETTLED", "COMPLETED"]).aggregate(total=Sum('trn_amount'))["total"] or 0,
            "today_pos_transaction": PosServiceTrn.objects.filter(pos_trn_dt__date=today,trn_status__in=["SETTLED", "COMPLETED"]).count(),
            "this_week_pos_transaction": PosServiceTrn.objects.filter(pos_trn_dt__date__gte=start_of_week,trn_status__in=["SETTLED", "COMPLETED"]).count(),
            "this_month_pos_transaction": PosServiceTrn.objects.filter(pos_trn_dt__date__gte=start_of_month,trn_status__in=["SETTLED", "COMPLETED"]).count(),
        }

        # Fetch retailers with PENDING status
        retailers = PortalUser.objects.filter(pu_role="RETAILER", pu_status="PENDING").values("id", "username", "pu_name", "pu_status")

        # Fetch retailer shop names
        retailer_details = PortalUserDetails.objects.filter(pu_id__in=[r["id"] for r in retailers]).values("pu_id", "shop_name")

        # Mapping retailer IDs to shop names
        retailer_shop_map = {detail["pu_id"]: detail["shop_name"] for detail in retailer_details}

        # Merging retailer data
        retailer_list = [
            {
                "retailer_id": retailer["username"],
                "retailer_name": retailer["pu_name"],
                "retailer_dba_name": retailer_shop_map.get(retailer["id"], "N/A"),
                "retailer_status": retailer["pu_status"]
            }
            for retailer in retailers
        ]

        # Pagination
        page = request.GET.get("page", 1)
        per_page = 10  # Show 10 records per page
        paginator = Paginator(retailer_list, per_page)
        paginated_retailers = paginator.get_page(page)

        data = {
            "total_main_wallet": total_balances["total_main_wallet"] or 0,
            "total_cashin_wallet": total_balances["total_cashin_wallet"] or 0,
            "total_pg_wallet": total_balances["total_pg_wallet"] or 0,
            "grand_total": (
                (total_balances["total_main_wallet"] or 0) +
                (total_balances["total_cashin_wallet"] or 0) +
                (total_balances["total_pg_wallet"] or 0)
            ),
            **pos_data,
            "retailers": list(paginated_retailers),
            "pagination": {
                "total_pages": paginator.num_pages,
                "current_page": paginated_retailers.number,
                "has_next": paginated_retailers.has_next(),
                "has_previous": paginated_retailers.has_previous(),
            }
        }

        return Response({
            "status": "success",
            "message": "Admin home page data retrieved successfully",
            "data": data
        })




from datetime import timedelta
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.core.paginator import Paginator
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.timezone import now

class AdminHomePageRetailerDataWithGraphApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]
    def get(self, request):
        today = now().date()
        start_of_month = today.replace(day=1)
        previous_month_start = (start_of_month - timedelta(days=1)).replace(day=1)
        previous_month_end = start_of_month - timedelta(days=1)

        previous_month_name = previous_month_start.strftime("%B")
        current_month_name = start_of_month.strftime("%B")

        def get_transaction_data(model, date_field):
            transactions = model.objects.filter(**{f"{date_field}__date__gte": previous_month_start},trn_status__in=["SETTLED", "COMPLETED"])

            daily_data = transactions.annotate(
                transaction_date=TruncDate(date_field)
            ).values('transaction_date').annotate(
                total_amount=Sum('trn_amount', default=0),
                total_transactions=Count('*')
            ).order_by('transaction_date')

            previous_month_daily = [entry for entry in daily_data if previous_month_start <= entry["transaction_date"] <= previous_month_end]
            current_month_daily = [entry for entry in daily_data if entry["transaction_date"] >= start_of_month]

            def get_weekly_data(month_start, month_end):
                week_data = {}
                total_transactions = 0
                total_amount = 0
                current_week_start = month_start
                week_counter = 1

                while current_week_start <= month_end:
                    week_end = current_week_start + timedelta(days=6)
                    week_transactions = transactions.filter(
                        **{f"{date_field}__date__gte": current_week_start, f"{date_field}__date__lte": week_end}
                    ).aggregate(
                        total_amount=Sum('trn_amount', default=0),
                        total_transactions=Count('*')
                    )

                    week_data[f"Week {week_counter}"] = {
                        "total_amount": week_transactions["total_amount"] or 0,
                        "total_transactions": week_transactions["total_transactions"] or 0
                    }

                    total_transactions += week_transactions["total_transactions"] or 0
                    total_amount += week_transactions["total_amount"] or 0

                    week_counter += 1
                    current_week_start = week_end + timedelta(days=1)

                return week_data, total_transactions, total_amount

            previous_month_weekly, prev_total_transactions, prev_total_amount = get_weekly_data(previous_month_start, previous_month_end)
            current_month_weekly, curr_total_transactions, curr_total_amount = get_weekly_data(start_of_month, today)

            latest_week_start = today - timedelta(days=today.weekday())
            latest_week_end = today

            daily_week_data = transactions.filter(
                **{f"{date_field}__date__gte": latest_week_start, f"{date_field}__date__lte": latest_week_end}
            ).annotate(
                transaction_date=TruncDate(date_field)
            ).values('transaction_date').annotate(
                total_amount=Sum('trn_amount', default=0),
                total_transactions=Count('*')
            ).order_by('transaction_date')

            latest_week_days = {day.strftime('%A'): {"total_amount": 0, "total_transactions": 0}
                                for day in [latest_week_start + timedelta(days=i) for i in range(7) if latest_week_start + timedelta(days=i) <= latest_week_end]}

            total_weekly_transactions = 0
            total_weekly_amount = 0

            for entry in daily_week_data:
                day_name = entry["transaction_date"].strftime('%A')
                latest_week_days[day_name] = {
                    "total_amount": entry["total_amount"] or 0,
                    "total_transactions": entry["total_transactions"] or 0
                }
                total_weekly_transactions += entry["total_transactions"] or 0
                total_weekly_amount += entry["total_amount"] or 0

            percentage_change = "No change"
            if prev_total_amount > 0:
                change = ((curr_total_amount - prev_total_amount) / prev_total_amount) * 100
                percentage_change = f"{abs(change):.2f}% {'increase' if change > 0 else 'decrease'} than {previous_month_name}"

            return {
                previous_month_name: {
                    "daily": previous_month_daily,
                    "weekly": previous_month_weekly,
                    "total_transactions": prev_total_transactions,
                    "total_amount": prev_total_amount
                },
                current_month_name: {
                    "daily": current_month_daily,
                    "weekly": current_month_weekly,
                    "total_transactions": curr_total_transactions,
                    "total_amount": curr_total_amount
                },
                "latest_week_days": latest_week_days,
                "total_weekly_transactions": total_weekly_transactions,
                "total_weekly_amount": total_weekly_amount,
                "percentage_change": percentage_change
            }

        pos_data = get_transaction_data(PosServiceTrn, "pos_trn_dt")
        pg_data = get_transaction_data(PgServiceTrn, "created_at")

        total_balances = PortalUserWallet.objects.filter(
            pu__pu_role="RETAILER",
            pu__pu_status="APPROVED"
        ).aggregate(
            total_main_wallet=Sum('main_wallet', default=0),
            total_cashin_wallet=Sum('cashin_wallet', default=0),
            total_pg_wallet=Sum('pg_wallet', default=0)
        )

        retailers = PortalUser.objects.filter(pu_role="RETAILER", pu_status="PENDING").values("id", "username", "pu_name", "pu_status")
        retailer_details = PortalUserDetails.objects.filter(pu_id__in=[r["id"] for r in retailers]).values("pu_id", "shop_name")
        retailer_shop_map = {detail["pu_id"]: detail["shop_name"] for detail in retailer_details}

        retailer_list = [
            {
                "id":retailer["id"],
                "retailer_id": retailer["username"],
                "retailer_name": retailer["pu_name"],
                "retailer_dba_name": retailer_shop_map.get(retailer["id"], "N/A"),
                "retailer_status": retailer["pu_status"]
            }
            for retailer in retailers
        ]

        page = request.GET.get("page", 1)
        per_page = 10
        paginator = Paginator(retailer_list, per_page)
        paginated_retailers = paginator.get_page(page)

        data = {
            "pos_data": pos_data,
            "pg_data": pg_data,
            "total_balances": {
                "total_main_wallet": total_balances["total_main_wallet"] or 0,
                "total_cashin_wallet": total_balances["total_cashin_wallet"] or 0,
                "total_pg_wallet": total_balances["total_pg_wallet"] or 0,
            },
            "pending_retailers": list(paginated_retailers)
        }

        return Response({
            "status": "success",
            "message": "Admin home page data retrieved successfully",
            "data": data
        })




from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework import status
from .models import PortalUser
import re

# Function to validate retailer ID or number
def validate_retailer_id_or_number(retailer_id):
    if retailer_id.startswith('R') and len(retailer_id) == 11:
        return 'Retailer ID valid'
    elif re.match(r'^\d{10}$', retailer_id):
        return 'Retailer Number valid'
    else:
        raise ValidationError("Invalid Retailer ID or Number")



class RetailerTransferView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]
    
    def post(self, request, *args, **kwargs):
        try:
            retailer_id = request.data.get('retailerId')
            selected_option = request.data.get('selectedOption')
            amount = request.data.get('amount')
            is_retailer_transfer_verified = request.data.get('confirm_step')

            if not retailer_id or not selected_option:
                raise ValidationError("Both retailerId and selectedOption are required.")

            # Find retailer based on ID or Contact Number
            retailer = None
            if retailer_id.startswith('R') and len(retailer_id) == 11:
                retailer = PortalUser.objects.filter(username=retailer_id).first()
            elif re.match(r'^\d{10}$', retailer_id):
                retailer = PortalUser.objects.filter(pu_contact_no=retailer_id).first()

            if not retailer:
                raise ValidationError("No retailer found with the given Retailer ID or Number.")

            # Get Admin (Requesting User)
            request_user = request.user  
            if not request_user:
                raise ValidationError("Unauthorized request. Please log in.")

            # Get Admin's Wallet
            admin_wallet = PortalUserWallet.objects.filter(pu=request_user).first()
            if not admin_wallet:
                raise ValidationError("Admin wallet not found.")

            if request_user == retailer:
                raise ValidationError("You cannot transfer funds to yourself.")
            # Wallet Mapping
            wallet_map = {
                'main_wallet': 'main_wallet',
                'pg_wallet': 'pg_wallet',
                'cashin_wallet': 'cashin_wallet'
            }
            if selected_option not in wallet_map:
                raise ValidationError("Invalid wallet option selected.")

            admin_balance = getattr(admin_wallet, wallet_map[selected_option])
            
            # Get Retailer's Wallet
            retailer_wallet = PortalUserWallet.objects.filter(pu=retailer).first()
            if not retailer_wallet:
                raise ValidationError("Retailer wallet not found.")
            
            retailer_balance = getattr(retailer_wallet, wallet_map[selected_option])

            if is_retailer_transfer_verified == "retailer_success_true":
                if not amount:
                    raise ValidationError("Amount is required.")

                try:
                    amount = Decimal(amount)  
                    if amount <= 0:
                        raise ValidationError("Amount must be a positive whole number.")
                except (ValueError, TypeError):
                    raise ValidationError("Invalid amount format. Amount must be a whole number.")

                if admin_balance < amount:
                    raise ValidationError("Insufficient balance in admin wallet.")

                # Perform transaction atomically
                with transaction.atomic():
                    # Deduct from admin
                    setattr(admin_wallet, wallet_map[selected_option], admin_balance - amount)
                    admin_wallet.save()

                    # Add to retailer
                    setattr(retailer_wallet, wallet_map[selected_option], retailer_balance + amount)
                    retailer_wallet.save()


                    if selected_option == 'pg_wallet':
                        selected_option_name = 'Balance Account'
                    elif selected_option == 'main_wallet':
                        selected_option_name = 'Service Account'
                    else:
                        selected_option_name = 'Cash Account'
                    # Prepare transaction labels
                    timestamp = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")
                    from_label = f'DR_{selected_option_name}_To_RetailerTransfer_{retailer.username}_{timestamp}'
                    to_label = f'CR_{selected_option_name}_From_RetailerTransfer_{retailer.username}_{timestamp}'

                    # Record transactions
                    transactions = [
                        {'pu': request_user, 'from_pu': request_user.id, 'to_pu': retailer.id, 'type': 'DR', 'label': from_label},
                        {'pu': retailer, 'from_pu': request_user.id, 'to_pu': retailer.id, 'type': 'CR', 'label': to_label}
                    ]
                    
                    for txn in transactions:
                        # Get the user's wallet
                        user_wallet = PortalUserWallet.objects.filter(pu=txn['pu']).first()
                        if not user_wallet:
                            raise ValidationError(f"Wallet not found for user {txn['pu'].username}")

                        global_transaction = GlTrn.objects.create(
                            pu=txn['pu'],
                            effectvie_wallet=selected_option,
                            effectvie_amt=amount,
                            effective_type=txn['type'],
                            service_trn_table='ad_wallet_transaction',
                            gl_trn_dt=timezone.now()
                        )
                        

                        WalletTrn.objects.create(
                            action_id=global_transaction.gl_trn_id,
                            action_type=f'Internal_{selected_option}_to_{selected_option}',
                            pu=txn['pu'],
                            wl_label=txn['label'],
                            effectvie_wallet=selected_option,
                            effectvie_amt=amount,
                            effective_type=txn['type'],
                            wl_trn_des="Retailer Wallet Transfer",
                            current_balance=getattr(user_wallet, wallet_map[selected_option]),  
                            wl_trn_dt=timezone.now(),
                            
                        )


                return Response(
                    {
                        "success": True,
                        "message": f"₹{amount} transferred successfully to {retailer.pu_name}.",
                        "retailer": {
                            "id": retailer.id,
                            "name": retailer.pu_name,
                            "contact_number": retailer.pu_contact_no,
                            "role": retailer.pu_role
                        }
                    },
                    status=status.HTTP_200_OK
                )

            return Response(
                {
                    "success": True,
                    "message": f"Transfer request for {retailer.pu_name} is ready for confirmation.",
                    "retailer": {
                        "id": retailer.id,
                        "name": retailer.pu_name,
                        "contact_number": retailer.pu_contact_no,
                        "role": retailer.pu_role
                    }
                },
                status=status.HTTP_200_OK
            )

        except ValidationError as e:
            return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return Response({"success": False, "message": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class RetailerResetMpinApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]

    def post(self, request):
        user = PortalUser.objects.get(id=request.user.id)
        print(user)
        user.mpin = 0
        user.save()
        return Response({'status': 'success', 'message': 'MPIN Reset successfully'}, status=status.HTTP_200_OK)






class RetailerHomePageDataWithGraphApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]
    
    def get(self, request):
        today = now().date()
        start_of_month = today.replace(day=1)
        previous_month_start = (start_of_month - timedelta(days=1)).replace(day=1)
        previous_month_end = start_of_month - timedelta(days=1)

        previous_month_name = previous_month_start.strftime("%B")
        current_month_name = start_of_month.strftime("%B")
        retailer_id = request.user.id
        def get_transaction_data(model, date_field):
            transactions = model.objects.filter(
                created_by=retailer_id,  
                **{f"{date_field}__date__gte": previous_month_start},
                trn_status__in=["SETTLED", "COMPLETED"]
            )

            daily_data = transactions.annotate(
                transaction_date=TruncDate(date_field)
            ).values('transaction_date').annotate(
                total_amount=Sum('trn_amount', default=0),
                total_transactions=Count('*')
            ).order_by('transaction_date')

            previous_month_daily = [entry for entry in daily_data if previous_month_start <= entry["transaction_date"] <= previous_month_end]
            current_month_daily = [entry for entry in daily_data if entry["transaction_date"] >= start_of_month]

            def get_weekly_data(month_start, month_end):
                week_data = {}
                total_transactions = 0
                total_amount = 0
                current_week_start = month_start
                week_counter = 1

                while current_week_start <= month_end:
                    week_end = current_week_start + timedelta(days=6)
                    week_transactions = transactions.filter(
                        **{f"{date_field}__date__gte": current_week_start, f"{date_field}__date__lte": week_end}
                    ).aggregate(
                        total_amount=Sum('trn_amount', default=0),
                        total_transactions=Count('*')
                    )

                    week_data[f"Week {week_counter}"] = {
                        "total_amount": week_transactions["total_amount"] or 0,
                        "total_transactions": week_transactions["total_transactions"] or 0
                    }

                    total_transactions += week_transactions["total_transactions"] or 0
                    total_amount += week_transactions["total_amount"] or 0

                    week_counter += 1
                    current_week_start = week_end + timedelta(days=1)

                return week_data, total_transactions, total_amount

            previous_month_weekly, prev_total_transactions, prev_total_amount = get_weekly_data(previous_month_start, previous_month_end)
            current_month_weekly, curr_total_transactions, curr_total_amount = get_weekly_data(start_of_month, today)

            latest_week_start = today - timedelta(days=today.weekday())
            latest_week_end = today

            daily_week_data = transactions.filter(
                **{f"{date_field}__date__gte": latest_week_start, f"{date_field}__date__lte": latest_week_end}
            ).annotate(
                transaction_date=TruncDate(date_field)
            ).values('transaction_date').annotate(
                total_amount=Sum('trn_amount', default=0),
                total_transactions=Count('*')
            ).order_by('transaction_date')

            latest_week_days = {day.strftime('%A'): {"total_amount": 0, "total_transactions": 0}
                                for day in [latest_week_start + timedelta(days=i) for i in range(7) if latest_week_start + timedelta(days=i) <= latest_week_end]}

            total_weekly_transactions = 0
            total_weekly_amount = 0

            for entry in daily_week_data:
                day_name = entry["transaction_date"].strftime('%A')
                latest_week_days[day_name] = {
                    "total_amount": entry["total_amount"] or 0,
                    "total_transactions": entry["total_transactions"] or 0
                }
                total_weekly_transactions += entry["total_transactions"] or 0
                total_weekly_amount += entry["total_amount"] or 0

            percentage_change = "No change"
            if prev_total_amount > 0:
                change = ((curr_total_amount - prev_total_amount) / prev_total_amount) * 100
                percentage_change = f"{abs(change):.2f}% {'increase' if change > 0 else 'decrease'} than {previous_month_name}"

            return {
                previous_month_name: {
                    "daily": previous_month_daily,
                    "weekly": previous_month_weekly,
                    "total_transactions": prev_total_transactions,
                    "total_amount": prev_total_amount
                },
                current_month_name: {
                    "daily": current_month_daily,
                    "weekly": current_month_weekly,
                    "total_transactions": curr_total_transactions,
                    "total_amount": curr_total_amount
                },
                "latest_week_days": latest_week_days,
                "total_weekly_transactions": total_weekly_transactions,
                "total_weekly_amount": total_weekly_amount,
                "percentage_change": percentage_change
            }

        pos_data = get_transaction_data(PosServiceTrn, "pos_trn_dt")
        pg_data = get_transaction_data(PgServiceTrn, "created_at")

        wallet_balance = PortalUserWallet.objects.filter(pu_id=retailer_id).aggregate(
            total_main_wallet=Sum('main_wallet', default=0),
            total_cashin_wallet=Sum('cashin_wallet', default=0),
            total_pg_wallet=Sum('pg_wallet', default=0)
        )

        recent_wallet_transactions = list(
            WalletTrn.objects.filter(pu_id=retailer_id)
            .order_by('-wl_trn_dt')[:8]
            .values('wl_trn_id', 'action_type', 'effectvie_amt', 'wl_trn_dt')
        )

        # Convert 'wl_trn_dt' to "YYYY-MM-DD hh:mm AM/PM"
        for data in recent_wallet_transactions:
            data['wl_trn_dt'] = datetime.datetime.strptime(
                str(data['wl_trn_dt']), "%Y-%m-%d %H:%M:%S.%f%z"
            ).strftime("%Y-%m-%d %I:%M %p")

        data = {
            "pos_data": pos_data,
            "pg_data": pg_data,
            "wallet_balance": {
                "total_main_wallet": wallet_balance["total_main_wallet"] or 0,
                "total_cashin_wallet": wallet_balance["total_cashin_wallet"] or 0,
                "total_pg_wallet": wallet_balance["total_pg_wallet"] or 0,
            },
            "recent_wallet_transactions": recent_wallet_transactions
        }

        return Response({
            "status": "success",
            "message": "Retailer home page data retrieved successfully",
            "data": data
        })




class RetailerPayoutAPiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]

    def get(self, request):
        try:
            data = {
                'total_pages': 0,
                'current_page': 0,
                'total_items': 0,
                'results': []
            }

            page_size = int(request.GET.get('page_size', 20))
            page_number = int(request.GET.get('page', 1))
            search = request.GET.get('search', '')

            if page_size <= 0:
                return Response({'status': 'fail', 'message': 'Page size must be greater than 0.'},
                                status=status.HTTP_400_BAD_REQUEST)

            get_bank_details = PayoutRequest.objects.filter(is_delete=False, created_by=request.user)

            if search:
                get_bank_details = get_bank_details.filter(
                    Q(created_by__username__icontains=search) |
                    Q(created_by__pu_name__icontains=search) |
                    Q(description__icontains=search)
                )

            get_bank_details = get_bank_details.order_by('-created_at')

            paginator = Paginator(get_bank_details, page_size)

            try:
                bank_details_data = paginator.page(page_number)
            except PageNotAnInteger:
                bank_details_data = paginator.page(1)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page number exceeds total pages.'
                }, status=status.HTTP_404_NOT_FOUND)

            for bank_details in bank_details_data:
                results = {
                    'pr_id': bank_details.pr_id,
                    'retailer_id': bank_details.created_by.username,
                    'name': bank_details.created_by.pu_name,
                    'amount': bank_details.amount,
                    'status': bank_details.request_status,
                    'description': bank_details.description,
                    'bank_name': bank_details.bank.bank_name if bank_details.bank else None,
                    'created_at': bank_details.created_at.strftime("%Y-%m-%d %H:%M:%S")
                }
                data['results'].append(results)

            data['total_pages'] = paginator.num_pages
            data['current_page'] = page_number
            data['total_items'] = paginator.count

            return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e))
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def put(self, request):
        try:
            pr_id = request.data.get('pr_id')
            if not pr_id:
                return Response({'status': 'fail', 'message': 'pr_id is required for update.'},
                                status=status.HTTP_400_BAD_REQUEST)

            payout = PayoutRequest.objects.filter(pr_id=pr_id, is_delete=False, created_by=request.user).first()
            if not payout:
                return Response({'status': 'fail', 'message': 'Payout request not found.'},
                                status=status.HTTP_404_NOT_FOUND)

            payout.amount = request.data.get('amount', payout.amount)
            payout.request_status = request.data.get('status', payout.request_status)
            payout.description = request.data.get('description', payout.description)

            bank_details_id = request.data.get('bank_details_id')
            print(bank_details_id)
            if bank_details_id is not None:
                try:
                    bank_instance = BankDetailsUser.objects.get(pk=bank_details_id, is_delete=False, created_by=request.user)
                    payout.bank = bank_instance
                except BankDetailsUser.DoesNotExist:
                    return Response({'status': 'fail', 'message': 'Selected bank not found or unauthorized.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            payout.save()

            return Response({'status': 'success', 'message': 'Payout request updated successfully.'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e))
            return Response({'status': 'error', 'message': f'Error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)



    def delete(self, request):
        try:
            pr_id = request.data.get('pr_id')
            if not pr_id:
                return Response({'status': 'fail', 'message': 'pr_id is required for deletion.'},
                                status=status.HTTP_400_BAD_REQUEST)

            payout = PayoutRequest.objects.filter(pr_id=pr_id, is_delete=False, created_by=request.user).first()
            if not payout:
                return Response({'status': 'fail', 'message': 'Payout request not found.'},
                                status=status.HTTP_404_NOT_FOUND)

            payout.is_delete = True
            payout.save()

            return Response({'status': 'success', 'message': 'Payout request deleted successfully.'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e))
            return Response({'status': 'error', 'message': f'Error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)






class StartingUserAPIView(APIView):
    def post(self, request):
        try:
            if 'aadhaar_card' in request.data and 'pan_card' in request.data and 'name' in request.data and 'email' in request.data and 'contact_no' in request.data:
                return self.add_users(request)

            elif 'aadhaar_card' in request.data:
                return self.verify_aadhaar(request)

            elif ('ref_id' in request.data and 'aadhaar_otp' in request.data) or (
                    'email' in request.data and 'email_otp' in request.data) or (
                    'contact_no' in request.data and 'contact_otp' in request.data):
                return self.verify_otp(request)

            elif 'pan_card' in request.data:
                return self.verify_pan(request)

            elif 'email' in request.data:
                return self.verify_email(request)

            elif 'contact_no' in request.data:
                return self.verify_contact(request)


            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




    def verify_aadhaar(self, request):
        aadhaar_card = request.data.get('aadhaar_card')
        if not aadhaar_card:
            return Response({"status": "fail", "message": "Aadhaar card is required."},
                            status=status.HTTP_400_BAD_REQUEST)

        if not isnumber(aadhaar_card):
            return Response({"status": "fail", "message": "Aadhaar card number must contain only digits."},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(aadhaar_card) != 12:
            return Response({"status": "fail", "message": "Aadhaar card number must be exactly 12 digits long."},
                            status=status.HTTP_400_BAD_REQUEST)

        # if PortalUserDetails.objects.filter(aadhaar_card=aadhaar_card).exists(): #===> ADHAR CHECk ALREDY RAGISTER 
        #     return Response({
        #         'status': 'fail',
        #         'message': 'This Aadhar number is already registered, use a different Aadhar number.'
        #     }, status=status.HTTP_400_BAD_REQUEST)

        aadhaar_response = aadhaar_verify(aadhaar_card)
        return Response(aadhaar_response['data'], status=aadhaar_response['status'])

    def verify_otp(self, request):
        if 'ref_id' in request.data and 'aadhaar_otp' in request.data:
            ref_id = request.data.get('ref_id')
            aadhaar_otp = request.data.get('aadhaar_otp')
            fwdp = request.data.get('fwdp')
            codeVerifier = request.data.get('codeVerifier')

            if not ref_id:
                return Response({"status": "fail", "message": "Referance id is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not aadhaar_otp:
                return Response({"status": "fail", "message": "Aadhaar OTP is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(aadhaar_otp):
                return Response({"status": "fail", "message": "Aadhaar OTP must contain only digits."},
                                status=status.HTTP_400_BAD_REQUEST)
            if len(aadhaar_otp) != 6:
                return Response({"status": "fail", "message": "OTP code must be exactly 6 digits long."},
                                status=status.HTTP_400_BAD_REQUEST)

            aadhaar_otp_response = aadhaar_otp_verify(aadhaar_otp, ref_id, fwdp, codeVerifier)
            return Response(aadhaar_otp_response['data'], status=aadhaar_otp_response['status'])

        elif 'email' in request.data and 'email_otp' in request.data:
            email = request.data.get('email')
            email_otp = request.data.get('email_otp')

            try:
                if not email:
                    return Response({"status": "fail", "message": "Email is required."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not email_otp:
                    return Response({"status": "fail", "message": "Email OTP is required."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not validation_email_address(email):
                    return Response({"status": "fail", "message": "Invalid email address format."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(email_otp):
                    return Response({"status": "fail", "message": "OTP code must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(email_otp) != 6:
                    return Response({"status": "fail", "message": "OTP code must be exactly 6 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)

                user = UserCodeVerification.objects.get(ucv_data=email)

                if user.verify_code == email_otp and user.verify_code_expire_at > timezone.now():
                    user.verify_code = None
                    user.verify_code_expire_at = None
                    user.is_verify = True
                    user.save()

                    response_data = {
                        'status': 'success',
                        'message': 'Email verification code verified successfully.',
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                else:
                    response_data = {
                        'status': 'fail',
                        'message': 'Invalid or expired verification code.'
                    }
                    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

            except UserCodeVerification.DoesNotExist:
                response_data = {
                    'status': 'error',
                    'message': 'User with this email does not exist.'
                }
                return Response(response_data, status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                response_data = {
                    'status': 'error',
                    'message': f'Internal server error: {str(e)}'
                }
                # Return a success response with status code 200
                return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        else:
            contact_no = request.data.get('contact_no')
            contact_otp = request.data.get('contact_otp')

            try:
                if not contact_no:
                    return Response({"status": "fail", "message": "Contact number is required."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not contact_otp:
                    return Response({"status": "fail", "message": "OTP code is required."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(contact_no):
                    return Response({"status": "fail", "message": "Contact number must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(contact_no) != 10:
                    return Response({"status": "fail", "message": "Contact number must be exactly 10 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(contact_otp):
                    return Response({"status": "fail", "message": "OTP code must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(contact_otp) != 6:
                    return Response({"status": "fail", "message": "OTP code must be exactly 6 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)

                user = UserCodeVerification.objects.get(ucv_data=contact_no)

                if user.verify_code == contact_otp and user.verify_code_expire_at > timezone.now():
                    user.verify_code = None
                    user.verify_code_expire_at = None
                    user.is_verify = True
                    user.save()

                    response_data = {
                        'status': 'success',
                        'message': 'Contact verification code verified successfully.',
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                else:
                    response_data = {
                        'status': 'fail',
                        'message': 'Invalid or expired verification code.'
                    }
                    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

            except UserCodeVerification.DoesNotExist:
                response_data = {
                    'status': 'error',
                    'message': 'User with this contact no does not exist.'
                }
                return Response(response_data, status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                response_data = {
                    'status': 'error',
                    'message': f'Internal server error: {str(e)}'
                }
                # Return a success response with status code 200
                return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def verify_pan(self, request):
        pan_card = request.data.get('pan_card')
        if not pan_card:
            return Response({"status": "fail", "message": "Pan card is required."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not checkpancardvalidation(pan_card):
            return Response({"status": "fail", "message": "Invalid PAN card format."},
                            status=status.HTTP_400_BAD_REQUEST)

        # if PortalUserDetails.objects.filter(pan_card=pan_card).exists(): #===> PAN ENTRY CHECK 
        #     return Response({
        #         'status': 'fail',
        #         'message': 'This Pan number is already registered, use a different Pan number.'
        #     }, status=status.HTTP_400_BAD_REQUEST)

        pan_card_response = verify_pan_card(pan_card)
        return Response(pan_card_response['data'], status=pan_card_response['status'])

    def verify_email(self, request):
        email = request.data.get('email')
        otp = get_random_string(length=6, allowed_chars='0123456789')
        try:
            if not email:
                return Response({"status": "fail", "message": "Email is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not validation_email_address(email):
                return Response({"status": "fail", "message": "Invalid email address format."},
                                status=status.HTTP_400_BAD_REQUEST)

            if PortalUser.objects.filter(pu_email=email, is_deleted=False).exists():
                return Response({
                    'status': 'fail',
                    'message': 'This Email is already registered, use a different Email.'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                pu_obj = UserCodeVerification.objects.get(ucv_data=email)
                pu_obj.verify_code = otp
                pu_obj.verify_code_expire_at = timezone.now() + timedelta(minutes=10)
                pu_obj.save()
            except UserCodeVerification.DoesNotExist:
                UserCodeVerification.objects.create(ucv_data=email, verify_code=otp,
                                                    verify_code_expire_at=timezone.now() + timedelta(minutes=10))

            # with transaction.atomic():
            #     send_email = send_email_otp(email, otp, 'Distributor')
            with transaction.atomic():
                print('----request......')
                # send_email = send_email_otp(email, otp, 'Retailer')
                # Send email using Project A's API
                send_email_subject = "OTP for Email Verification"
                
                email_data = {
                    "subject": send_email_subject,
                    "recipient_list": [email],
                    "otp": otp,
                    "role": "Retailer"  # Example role, can be dynamic
                }

                # Sending HTTP request to Project A's API to trigger the email sending
                send_email_url = "https://qaapi.fixpay.in/admin_hub/send-email/"
                response = requests.post(send_email_url, json=email_data)
            response_data = {
                'status': 'success',
                'message': 'Email sent successfully', }
            # Return a success response with status code 200
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            # Return a success response with status code 200
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def verify_contact(self, request):
        contact_no = request.data.get('contact_no')
        otp = get_random_string(length=6, allowed_chars='0123456789')
        try:
            if not contact_no:
                return Response({"status": "fail", "message": "Contact number is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(contact_no):
                return Response({"status": "fail", "message": "Contact number must contain only digits."},
                                status=status.HTTP_400_BAD_REQUEST)
            if len(contact_no) != 10:
                return Response({"status": "fail", "message": "Contact number must be exactly 10 digits long."},
                                status=status.HTTP_400_BAD_REQUEST)

            if PortalUser.objects.filter(pu_contact_no=contact_no, is_deleted=False).exists():
                return Response({
                    'status': 'fail',
                    'message': 'This contact number is already registered, use a different contact number.'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                pu_obj = UserCodeVerification.objects.get(ucv_data=contact_no)
                pu_obj.verify_code = otp
                pu_obj.verify_code_expire_at = timezone.now() + timedelta(minutes=10)
                pu_obj.save()
            except UserCodeVerification.DoesNotExist:
                UserCodeVerification.objects.create(ucv_data=contact_no, verify_code=otp,
                                                    verify_code_expire_at=timezone.now() + timedelta(minutes=10))

            # Prepare the SMS content
            response = mobicomm_submit_sms(contact_no, otp)

            # Check the SMS API response status
            if response.status_code == 200:
                response_data = {
                    'status': 'success',
                    'message': 'OTP has been sent via SMS.',
                    'data': {'contact_otp': otp}
                }
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                response_data = {
                    'status': 'error',
                    'message': 'Failed to send the OTP via SMS.',
                    'details': response.text  # Include the response for debugging
                }
                return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            print(e,'------------')
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            # Return a success response with status code 200
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def add_users(self, request):
        print('add_users', request.data)
        aadhaar_card = request.data.get('aadhaar_card')
        pan_card = request.data.get('pan_card')
        pan_response = request.data.get('pan_response')
        pu_name = request.data.get('name')
        pu_email = request.data.get('email')
        pu_contact_no = request.data.get('contact_no')
        alternate_contact_no = request.data.get('alternate_contact_no')
        address = request.data.get('address')
        state = request.data.get('state')
        city = request.data.get('city')
        zip_code = request.data.get('zip_code')
        profile_image = request.FILES.get('profile_image')
        aadhar_front_image = request.FILES.get('aadhar_image_front')
        aadhar_back_image = request.FILES.get('aadhar_image_back')
        pan_images = request.FILES.get('pan_image')
        parent_id = request.data.get('parent_id','')

        with open('uploaded_doc.txt', 'w') as f:
            f.write(f"profile_image: {profile_image.name if profile_image else 'None'}\n")
            f.write(f"aadhar_front_image: {aadhar_front_image.name if aadhar_front_image else 'None'}\n")
            f.write(f"aadhar_back_image: {aadhar_back_image.name if aadhar_back_image else 'None'}\n")
            f.write(f"pan_images: {pan_images.name if pan_images else 'None'}\n")



        
        try:
            with transaction.atomic():
                prefix_value = ""
                required_fields = ['aadhaar_card', 'pan_card', 'pan_response', 'name', 'email',
                                   'contact_no', 'alternate_contact_no', 'address', 'state', 'city', 'zip_code',
                                    "aadhar_image_front",
                                   "aadhar_image_back", "pan_image"]

                missing_fields = [field for field in required_fields if not request.data.get(field)]

                if missing_fields:
                    return Response(
                        {'status': 'fail',
                         'message': f'Required fields are empty: {", ".join(missing_fields)}. provide all required fields and try again'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if PortalUser.objects.filter(pu_contact_no=pu_contact_no, is_deleted=False).exists():
                    return Response({
                        'status': 'fail',
                        'message': 'This contact number is already registered, use a different contact number.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if not isnumber(aadhaar_card):
                    return Response({"status": "fail", "message": "Aadhaar card number must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(aadhaar_card) != 12:
                    return Response(
                        {"status": "fail", "message": "Aadhaar card number must be exactly 12 digits long."},
                        status=status.HTTP_400_BAD_REQUEST)
                if not checkpancardvalidation(pan_card):
                    return Response({"status": "fail", "message": "Invalid PAN card format."},
                                    status=status.HTTP_400_BAD_REQUEST)

                try:
                    parsed_data = json.loads(pan_response)
                except json.JSONDecodeError:
                    return Response({"status": "fail", "message": "PAN response must be valid JSON."},
                                    status=status.HTTP_400_BAD_REQUEST)

                if not validation_email_address(pu_email):
                    return Response({"status": "fail", "message": "Invalid email address format."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(pu_contact_no):
                    return Response({"status": "fail", "message": "Contact number must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(pu_contact_no) != 10:
                    return Response({"status": "fail", "message": "Contact number must be exactly 10 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isnumber(alternate_contact_no):
                    return Response({"status": "fail", "message": "Alternate contact number must be digit."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if len(alternate_contact_no) != 10:
                    return Response(
                        {"status": "fail", "message": "Alternate contact number must be exactly 10 digits long."},
                        status=status.HTTP_400_BAD_REQUEST)

                state_obj = State.objects.filter(state_name__icontains=state).first()

                if not state_obj:
                    return Response({'status': 'fail', 'message': 'State not found.'}, status=status.HTTP_404_NOT_FOUND)

                state_id = state_obj.state_id
                print('state_id==================>', state_id)
                short_name = state_obj.short_name
                print('short_name==================>', short_name)

                city_obj = City.objects.filter(city_name__icontains=city).first()
                if not city_obj:
                    return Response({'status': 'fail', 'message': 'City not found.'}, status=status.HTTP_404_NOT_FOUND)

                city_id = city_obj.city_id

                if not isnumber(zip_code):
                    return Response({"status": "fail", "message": "Zip code must contain only digits."},
                                    status=status.HTTP_400_BAD_REQUEST)

                if len(zip_code) != 6:
                    return Response({"status": "fail", "message": "Zip code must be exactly 6 digits long."},
                                    status=status.HTTP_400_BAD_REQUEST)

                # user = PortalUser.objects.get(id=request.user.id, is_deleted=False)

                prefix_value = "RT"

                unique_user_id = generate_userid(prefix_value, short_name)

                username = unique_user_id
                password = get_random_string(8)


                
                file_path1 = handle_uploaded_file(profile_image, 'Retailer/Docs',username) if profile_image else None
                pan_images = handle_uploaded_file(pan_images, 'Retailer/pan_card',username) if pan_images else None
                aadhar_front_image = handle_uploaded_file(aadhar_front_image,
                                                            'Retailer/aadhar_front',username) if aadhar_front_image else None
                aadhar_back_image = handle_uploaded_file(aadhar_back_image,
                                                            'Retailer/aadhar_back',username) if aadhar_back_image else None

                pu_obj = PortalUser.objects.create(
                    pu_name=pu_name,
                    pu_email=pu_email,
                    pu_contact_no=pu_contact_no,
                    username=username,
                    password=make_password(password),
                    pu_role="RETAILER",
                    is_kyc_verify=False,
                    pu_status="PENDING"
                )

                PortalUserWallet.objects.create(
                    main_wallet=0.00,
                    cashin_wallet=0.00,
                    pg_wallet=0.00,
                    pu=pu_obj
                )

                # Email sendd
                # send_user_credentials(pu_email, pu_name, username, password)
                send_email_subject = "Welcome to Fixpay!"
        
                email_data = {
                    "subject": send_email_subject,
                    "recipient_list": [pu_email],
                    "username": username,
                    "password": password,
                    "name": pu_name
                }

                # Sending HTTP request to Project A's API to trigger the welcome email
                send_email_url = "https://qaapi.fixpay.in/admin_hub/send-email/"
                response = requests.post(send_email_url, json=email_data)

                # Combine all paths into a single dictionary
                file_paths = {
                    'profile_image': file_path1,
                    'aadhar_front_image': aadhar_front_image,
                    'aadhar_back_image': aadhar_back_image,
                    'pan_images': pan_images
                }
                with open('uploaded_doc_p.txt', 'w') as test:
                    json.dump(file_paths, test)
                # Create PortalUserDetails
                try:
                    parent_get = PortalUser.objects.get(username=parent_id)
                except PortalUser.DoesNotExist:
                    parent_get = None
                PortalUserDetails.objects.create(
                    pu=pu_obj,
                    dh=None,
                    pud_unique_id=unique_user_id,
                    alternate_contact_no=alternate_contact_no,
                    address=address,
                    doc_images=file_paths,
                    state_id=state_id,
                    city_id=city_id,
                    zip_code=zip_code,
                    aadhaar_card=aadhaar_card,
                    pan_card=pan_card,
                    pan_response=pan_response,
                    created_by=parent_get.id if parent_get else None
                )



                user_activity = {
                    "table_id": pu_obj.pk,
                    "table_name": 'ad_portal_user',
                    "ua_action": 'Create',  # Action performed
                    "ua_description": 'User Created Successfully.',  # Action description
                    "created_by": request.user,  # Current user performing the action
                    "request_data": dict(request.data),  # Request data
                    "response_data": model_to_dict(pu_obj)
                }

                add_user_activity(user_activity)

                return Response({
                    'status': 'success',
                    'message': 'User Created Successfully'
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            

# def generate_pdf_from_template(template_name, context, output_filename):
#     html = render_to_string(template_name, context)
#     pdf_path = os.path.join(settings.MEDIA_ROOT, 'declarations', output_filename)
#     os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

#     with open(pdf_path, "wb") as result_file:
#         pisa_status = pisa.CreatePDF(html, dest=result_file)

#     if pisa_status.err:
#         return None
#     return os.path.join(settings.MEDIA_URL, 'declarations', output_filename)
from django.template.loader import render_to_string
from weasyprint import HTML
import os
from django.conf import settings

def generate_pdf_from_template(template_name, context, output_filename):
    html_string = render_to_string(template_name, context)
    pdf_path = os.path.join(settings.MEDIA_ROOT, 'declarations', output_filename)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    HTML(string=html_string, base_url=settings.BASE_DIR).write_pdf(pdf_path)

    return os.path.join(settings.MEDIA_URL, 'declarations', output_filename)

class RetailerDetailsVerifyApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]

    def post(self, request):
        required_fields = ['shop_name', 'shop_address', 'shop_images']
        missing_fields = [field for field in required_fields if not request.data.get(field)]

        if missing_fields:
            return Response(
                {'status': 'fail',
                 'message': f'Required fields are empty: {", ".join(missing_fields)}. Provide all required fields and try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return self.add_or_update_business_details(request)

    # def add_or_update_business_details(self, request):
    #     shop_name = request.data.get('shop_name')
    #     shop_address = request.data.get('shop_address')
    #     shop_images = request.FILES.get('shop_images')
    #     shop_gst_number = request.data.get('shop_gst_number') or None  # Handle empty GST as None

    #     try:
    #         with transaction.atomic():
    #             user = PortalUser.objects.get(id=request.user.id, is_deleted=False)

    #             # Validate GST duplication only if GST is provided
    #             existing_detail = PortalUserDetails.objects.filter(pu=user).first()
    #             if shop_gst_number:
    #                 gst_exists = PortalUserDetails.objects.filter(shop_gst_number=shop_gst_number)
    #                 if existing_detail:
    #                     if existing_detail.shop_gst_number != shop_gst_number and gst_exists.exists():
    #                         return Response({'status': 'fail', 'message': 'Shop GST number already exists.'},
    #                                         status=status.HTTP_400_BAD_REQUEST)
    #                 elif gst_exists.exists():
    #                     return Response({'status': 'fail', 'message': 'Shop GST number already exists.'},
    #                                     status=status.HTTP_400_BAD_REQUEST)

    #             # Create or update PortalUserDetails
    #             p, created = PortalUserDetails.objects.get_or_create(pu=user)

    #             # Ensure doc_images is a dictionary
    #             if not p.doc_images or not isinstance(p.doc_images, dict):
    #                 p.doc_images = {}

    #             # Handle file upload for shop image
    #             if shop_images:
    #                 file_path2 = handle_uploaded_file(shop_images, 'shopimages')
    #                 p.doc_images['shop_images'] = file_path2  # ✅ only updates shop_images key

    #             # Update other business details
    #             p.shop_name = shop_name
    #             p.shop_address = shop_address
    #             p.shop_gst_number = shop_gst_number
    #             p.save()

    #             # Update KYC verification status
    #             if not user.is_kyc_verify:
    #                 user.is_kyc_verify = True
    #                 user.under_review = True
    #             else:
    #                 user.under_review = False
    #             user.save()

    #             # Log user activity
    #             user_activity = {
    #                 "table_id": p.pk,
    #                 "table_name": 'ad_portal_user_details',
    #                 "ua_action": 'Create' if created else 'Update',
    #                 "ua_description": 'User Business Details Add Successfully.' if created else 'User Business Details Updated Successfully.',
    #                 "created_by": request.user,
    #                 "request_data": dict(request.data),
    #                 "response_data": model_to_dict(p)
    #             }
    #             add_user_activity(user_activity)

    #             return Response({
    #                 'status': 'success',
    #                 'message': 'User Business Details Add Successfully' if created else 'User Business Details Updated Successfully'
    #             }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    #     except Exception as e:
    #         print(e)
    #         return Response(
    #             {'status': 'error', 'message': f'Internal server error: {str(e)}'},
    #             status=status.HTTP_500_INTERNAL_SERVER_ERROR
    #         )


    def add_or_update_business_details(self, request):
        shop_name = request.data.get('shop_name')
        shop_address = request.data.get('shop_address')
        shop_gst_number = request.data.get('shop_gst_number')

        shop_images = request.FILES.getlist('shop_images')
        if not shop_gst_number or shop_gst_number.strip() == "":
            shop_gst_number = None

        try:
            with transaction.atomic():
                user = PortalUser.objects.get(id=request.user.id, is_deleted=False)

                existing_detail = PortalUserDetails.objects.filter(pu=user).first()
                if shop_gst_number is not None:
                    gst_exists = PortalUserDetails.objects.filter(shop_gst_number=shop_gst_number)
                    if existing_detail:
                        if existing_detail.shop_gst_number != shop_gst_number and gst_exists.exists():
                            return Response({'status': 'fail', 'message': 'Shop GST number already exists.'},
                                            status=status.HTTP_400_BAD_REQUEST)
                    elif gst_exists.exists():
                        return Response({'status': 'fail', 'message': 'Shop GST number already exists.'},
                                        status=status.HTTP_400_BAD_REQUEST)

                p, created = PortalUserDetails.objects.get_or_create(pu=user)

                if not p.doc_images or not isinstance(p.doc_images, dict):
                    p.doc_images = {}

                # Get existing shop images list safely
                existing_images = p.doc_images.get('shop_images', [])

                uploaded_paths = []
                if shop_images:
                    for img in shop_images:
                        file_path = handle_uploaded_file(img, 'shopimages',user.username)
                        uploaded_paths.append(file_path)

                # Merge existing and newly uploaded images, limit max 5 images
                combined_images = existing_images + uploaded_paths
                combined_images = combined_images[:5]  # ensure max 5

                p.doc_images['shop_images'] = combined_images

                p.shop_name = shop_name
                p.shop_address = shop_address
                p.shop_gst_number = shop_gst_number
                p.save()

                if not user.is_kyc_verify:
                    user.is_kyc_verify = True
                    user.under_review = True
                else:
                    user.under_review = False
                user.save()

                user_activity = {
                    "table_id": p.pk,
                    "table_name": 'ad_portal_user_details',
                    "ua_action": 'Create' if created else 'Update',
                    "ua_description": 'User Business Details Add Successfully.' if created else 'User Business Details Updated Successfully.',
                    "created_by": request.user,
                    "request_data": dict(request.data),
                    "response_data": model_to_dict(p)
                }
                add_user_activity(user_activity)

                return Response({
                    'status': 'success',
                    'message': 'User Business Details Add Successfully' if created else 'User Business Details Updated Successfully'
                }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        except Exception as e:
            print(e)
            return Response(
                {'status': 'error', 'message': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    
    def get(self, request):
        try:
            user = PortalUser.objects.get(id=request.user.id, is_deleted=False)
            details = PortalUserDetails.objects.filter(pu=user).first()

            if not details:
                return Response(
                    {'status': 'fail', 'message': 'No business details found for this user.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            shop_image_paths = details.doc_images.get('shop_images', []) if details.doc_images else []
            shop_images_urls = [get_full_image_url(request, path) for path in shop_image_paths]

            # Extract other images (all except shop_images)
            other_images = {}
            if details.doc_images:
                for key, value in details.doc_images.items():
                    if key != 'shop_images':
                        # Assuming non-shop_images are single strings, not lists
                        other_images[key] = get_full_image_url(request, value)

            print("Shop images URLs:", shop_images_urls)  # Debug print
            print("Other images URLs:", other_images)     # Debug print

            image_urls = {
                key: get_full_image_url(request, value)
                for key, value in details.doc_images.items()
            } if details.doc_images else None
            print(image_urls,)
            # Generate Declaration PDF
            # pan_response_data = {}
            # try:
            #     pan_response_data = json.loads(details.pan_response)
            # except (ValueError, TypeError):
            #     pan_response_data = {}
            # print(pan_response_data,'-----------------+++++')
            # # Extract full_address
            # residential_address = pan_response_data.get('address', {}).get('full_address', '')
            # # Generate Declaration PDF
            # print(residential_address,'===========_________+++++++')

            bank = BankDetailsUser.objects.filter(
                created_by=user,
                is_deactive=False,
                is_delete=False
            ).order_by('-created_at').first()

            if bank:
                bank_available = True
            else:
                bank_available = False
            context = {
                'user': {
                    'id': user.username,
                    'role': user.pu_role,
                    'name':user.pu_name,
                    'email':user.pu_email,
                    'contact':user.pu_contact_no,
                },
                'shop_name': details.shop_name,
                'shop_address': details.shop_address,
                'addhar_number': details.aadhaar_card,
                'pan_number':details.pan_card,
                'residential_address': details.address,
                'date': get_formatted_date(),
                'security_check_num': details.security_check_num,
                'bank_name': bank.bank_name if bank else None,
                'bank_branch': bank.bank_branch if bank else None,
                'account_number': bank.account_number if bank else None,
                'alternate_num':details.alternate_contact_no,
                'last_date':datetime.datetime.now().strftime("%d/%m/%Y"),
            }

            pdf_url = generate_pdf_from_template(
                'user_declaration.html',
                context,
                output_filename=f'declaration_user_{user.id}.pdf'
            )
            data = {
                'shop_name': details.shop_name,
                'shop_address': details.shop_address,
                'shop_gst_number': details.shop_gst_number,
                'shop_images': shop_images_urls,
                'shop_images_other': image_urls,
                'declaration_pdf_url': request.build_absolute_uri(pdf_url) if pdf_url else None,
                'upload_status': details.upload_status,
                'security_upload_status': details.security_upload_status,
                'pdf_upload_status': details.pdf_upload_status,
                'onboarding_cheque_comment': details.onboarding_cheque_comment,
                'security_cheque_comment': details.security_cheque_comment,
                'declaration_pdf_comment': details.declaration_pdf_comment,
                'onboarding_check_num': details.onboarding_check_num,
                'security_check_num': details.security_check_num,
                'bank_available':bank_available,

            }

            return Response({
                'status': 'success',
                'message': 'Business details fetched successfully.',
                'data': data
            }, status=status.HTTP_200_OK)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            return Response(
                {'status': 'error', 'message': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    
    def delete(self, request):
        try:
            image_path = request.data.get('image_path')
            
            if not image_path:
                return Response(
                    {'status': 'fail', 'message': 'Image path is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user = PortalUser.objects.get(id=request.user.id, is_deleted=False)
            details = PortalUserDetails.objects.filter(pu=user).first()
            
            if not details:
                return Response(
                    {'status': 'fail', 'message': 'No business details found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get current shop images
            shop_images = details.doc_images.get('shop_images', []) if details.doc_images else []
            
            # Remove the image from list
            if image_path in shop_images:
                shop_images.remove(image_path)
                details.doc_images['shop_images'] = shop_images
                details.save()
                
                # Optional: Delete physical file
                try:
                    import os
                    from django.conf import settings
                    file_full_path = os.path.join(settings.MEDIA_ROOT, image_path)
                    if os.path.exists(file_full_path):
                        os.remove(file_full_path)
                except Exception as e:
                    print(f"Error deleting physical file: {e}")
                
                # Log activity
                user_activity = {
                    "table_id": details.pk,
                    "table_name": 'ad_portal_user_details',
                    "ua_action": 'Delete',
                    "ua_description": f'Shop image deleted: {image_path}',
                    "created_by": request.user,
                    "request_data": {'image_path': image_path},
                    "response_data": {'remaining_images': shop_images}
                }
                add_user_activity(user_activity)
                
                return Response({
                    'status': 'success',
                    'message': 'Image deleted successfully',
                    'data': {'remaining_images': shop_images}
                }, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'status': 'fail', 'message': 'Image not found in shop images'},
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except PortalUser.DoesNotExist:
            return Response(
                {'status': 'fail', 'message': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"Error deleting image: {e}")
            return Response(
                {'status': 'error', 'message': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        


    # def get(self, request):
    #     try:
    #         user = PortalUser.objects.get(id=request.user.id, is_deleted=False)
    #         details = PortalUserDetails.objects.filter(pu=user).first()

    #         if not details:
    #             return Response(
    #                 {'status': 'fail', 'message': 'No business details found for this user.'},
    #                 status=status.HTTP_404_NOT_FOUND
    #             )

    #         image_urls = {
    #             key: get_full_image_url(request, value)
    #             for key, value in details.doc_images.items()
    #         } if details.doc_images else None
    #         print(image_urls,)
    #         # Generate Declaration PDF
    #         context = {
    #             'user': {
    #                 'id': user.username,
    #                 'role': user.pu_role,
    #                 'name':user.pu_name,
    #                 'email':user.pu_email,
    #                 'contact':user.pu_contact_no,
    #             },
    #             'shop_name': details.shop_name,
    #             'shop_address': details.shop_address,
    #         }
    #         pdf_url = generate_pdf_from_template(
    #             'user_declaration.html',
    #             context,
    #             output_filename=f'declaration_user_{user.id}.pdf'
    #         )
    #         declaration_pdf_url = request.build_absolute_uri(pdf_url).replace('http://', 'https://') if pdf_url else None
    #         data = {
    #             'shop_name': details.shop_name,
    #             'shop_address': details.shop_address,
    #             'shop_gst_number': details.shop_gst_number,
    #             'shop_images': image_urls,
    #             'declaration_pdf_url': declaration_pdf_url,
    #             'upload_status': details.upload_status,
    #             'security_upload_status': details.security_upload_status,
    #             'pdf_upload_status': details.pdf_upload_status,
    #             'onboarding_cheque_comment': details.onboarding_cheque_comment,
    #             'security_cheque_comment': details.security_cheque_comment,
    #             'declaration_pdf_comment': details.declaration_pdf_comment,
    #         }

    #         return Response({
    #             'status': 'success',
    #             'message': 'Business details fetched successfully.',
    #             'data': data
    #         }, status=status.HTTP_200_OK)

    #     except PortalUser.DoesNotExist:
    #         return Response({'status': 'fail', 'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
    #     except Exception as e:
    #         print(e)
    #         return Response(
    #             {'status': 'error', 'message': f'Internal server error: {str(e)}'},
    #             status=status.HTTP_500_INTERNAL_SERVER_ERROR
    #         )




from rest_framework.decorators import api_view
from rest_framework.response import Response
from admin_hub.models import CommissionLog, PortalUserWallet, PortalUser, UserCharge, PaymentGateway, CardType, PGBaseCharge, PgServiceTrn, PosServiceTrn
import decimal



def generate_transaction_id():
    return "FIXPAY" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def add_commission_to_wallet(user, commission_amount):
    wallet, created = PortalUserWallet.objects.get_or_create(pu=user)
    if wallet.pg_wallet is None:
        wallet.pg_wallet = decimal.Decimal('0')
    wallet.pg_wallet += commission_amount
    wallet.save()



from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
import decimal

@api_view(['POST'])
def manual_pg_transaction(request):
    # Fetch data from request
    user_id = request.data.get('user_id')
    amount = request.data.get('amount')
    pg_id = request.data.get('pg_id')
    card_type_id = request.data.get('card_type_id')

    if not user_id or not amount or not pg_id or not card_type_id:
        return Response({"status": False, "message": "All parameters are required"}, status=400)

    try:
        amount = decimal.Decimal(amount)
        if amount <= 0:
            return Response({"status": False, "message": "Amount must be greater than zero"}, status=400)
    except (ValueError, decimal.InvalidOperation):
        return Response({"status": False, "message": "Invalid amount format"}, status=400)

    # Get retailer and other related info
    retailer = get_object_or_404(PortalUser, id=user_id)
    get_retailer_details = get_object_or_404(PortalUserDetails, pu=retailer)
    payment_gateway = get_object_or_404(PaymentGateway, id=pg_id)
    card_type = get_object_or_404(CardType, id=card_type_id)

    # Try to get retailer specific charge first
    retailer_charge_percent = None
    try:
        retailer_charge = UserCharge.objects.get(user_id=retailer.id, pg=payment_gateway, card_type=card_type)
        retailer_charge_percent = retailer_charge.charge_percent
    except UserCharge.DoesNotExist:
        # Fallback to base PG charge if no retailer-specific charge found
        pg_base_charge = PGBaseCharge.objects.filter(
            role=retailer.pu_role.title(),
            pg=payment_gateway,
            card_type=card_type
        ).first()

        if pg_base_charge:
            retailer_charge_percent = pg_base_charge.charge_percent
        else:
            return Response({"status": False, "message": "No applicable charge percent found."}, status=400)

    # If retailer_charge_percent is None, use base charge percent
    if retailer_charge_percent is None:
        retailer_charge_percent = pg_base_charge.charge_percent

    # Calculate charges
    total_charge_amount = (amount * retailer_charge_percent) / decimal.Decimal(100)
    net_credit_to_user = amount - total_charge_amount

    # Generate a unique transaction ID
    trn_unique_id = generate_transaction_id()

    # Create the transaction record
    pg_service_trn = PgServiceTrn.objects.create(
        trn_unique_id=trn_unique_id,
        trn_amount=amount,
        trn_response={
            "pg_id": payment_gateway.id,
            "card_type_id": card_type.id,
        },
        pg=payment_gateway,
        card_type=card_type,
        is_settled=False,
        trn_status="COMPLETED",
        created_by=retailer.id,
        buyer_email=retailer.pu_email,
        buyer_phone=retailer.pu_contact_no,
        buyer_firstname=retailer.pu_name,
        buyer_lastname=request.data.get('buyer_lastname', ''),
        buyer_address=get_retailer_details.shop_address,
        buyer_city=get_retailer_details.shop_city,
        buyer_state=get_retailer_details.shop_state,
        buyer_country=request.data.get('buyer_country', ''),
        buyer_pincode=get_retailer_details.shop_zip_code,
        retailer_charge_percent=retailer_charge_percent,
        total_charge_amount=total_charge_amount,
        net_credit_to_user=net_credit_to_user
    )

    return Response({
        "status": True,
        "message": "Transaction entry created successfully in PgServiceTrn.",
        "transaction_id": pg_service_trn.trn_unique_id
    })

from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from admin_hub.models import (
    PgServiceTrn, PortalUser, PortalUserDetails, PaymentGateway, CardType,
    UserCharge, CommissionLog, PortalUserWallet, GlTrn, WalletTrn, PGBaseCharge
)
import decimal

def get_charge_percent(user, pg, card_type):
    """Get charge percent for a user, falling back to base charge if not defined."""
    user_charge = UserCharge.objects.filter(user_id=user, pg=pg, card_type=card_type).first()
    if user_charge:
        return user_charge.charge_percent
    base_charge = PGBaseCharge.objects.filter(role=user.pu_role.title(), pg=pg, card_type=card_type).first()
    if base_charge:
        return base_charge.charge_percent
    raise Exception(f"No charge defined for user: {user.username} (role: {user.pu_role})")




# @transaction.atomic
# def settle_pg_base_transaction(pg_service_trn_id):
#     pg_service_trn = get_object_or_404(PgServiceTrn, pg_trn_id=pg_service_trn_id)

#     if pg_service_trn.is_settled:
#         return {"status": False, "message": "Transaction already settled"}

#     retailer = get_object_or_404(PortalUser, id=pg_service_trn.created_by)
#     retailer_details = get_object_or_404(PortalUserDetails, pu=retailer)
#     pg = get_object_or_404(PaymentGateway, id=pg_service_trn.pg_id)
#     card_type = get_object_or_404(CardType, id=pg_service_trn.card_type_id)


#     service_provider = AdServiceProvider.objects.filter(
#         service__service_name='PG',
#         pg=pg  
#     ).first()
    

#     # Step 0: Get retailer commission percentage
#     try:
#         retailer_percent = get_charge_percent(retailer, pg, card_type)
#     except Exception as e:
#         return {"status": False, "message": str(e)}

#     trn_amount = decimal.Decimal(pg_service_trn.trn_amount)

#     # ---------- Step 1: Credit full transaction amount to retailer (INSTANT) -------------
#     wallet, _ = PortalUserWallet.objects.get_or_create(pu=retailer)
#     current_balance = float(wallet.pg_wallet or 0)
#     new_balance = current_balance + float(trn_amount)
#     wallet.pg_wallet = decimal.Decimal(new_balance)
#     wallet.save()

#     WalletTrn.objects.create(
#         action_id=pg_service_trn.pk,
#         action_type='Service',
#         pu_id=retailer.id,
#         wl_label=f"PG_by_{retailer_details.pud_unique_id}_of_amount_{trn_amount}_with_tx_id_{pg_service_trn.trn_unique_id}",
#         effectvie_wallet='pg_wallet',
#         effectvie_amt=trn_amount,
#         effective_type='CR',
#         current_balance=new_balance,
#         wl_trn_dt=now()
#     )

#     # ---------- Step 2: Debit retailer commission (INSTANT) -------------
#     retailer_comm = (retailer_percent * trn_amount) / decimal.Decimal('100')
#     new_balance -= float(retailer_comm)
#     wallet.pg_wallet = decimal.Decimal(new_balance)
#     wallet.save()


#     CommissionLog.objects.create(
#         pg_service_trn=pg_service_trn,
#         user=retailer,
#         commission_amount=retailer_comm,
#         level=retailer.pu_role or "RETAILER"
#     )

#     WalletTrn.objects.create(
#         action_id=pg_service_trn.pk,
#         action_type='Commission',
#         pu_id=retailer.id,
#         wl_label=f"Using PG {retailer_details.pud_unique_id} gets {retailer_comm} Rs CHARGE WITH GST in pg_wallet as debited",
#         effectvie_wallet='pg_wallet',
#         effectvie_amt=retailer_comm,
#         effective_type='DR',
#         current_balance=new_balance,
#         wl_trn_dt=now()
#     )

#     if service_provider:
#         if card_type.name.lower() == 'rupay':
#             mdr_percent = service_provider.rupay_mdr
#         elif card_type.name.lower() == 'mastercard':
#             mdr_percent = service_provider.mastercard_mdr
#         elif card_type.name.lower() == 'visa':
#             mdr_percent = service_provider.visa_mdr
#         else:
#             mdr_percent = decimal.Decimal('0.00')

#         mdr_amount = (trn_amount * mdr_percent) / decimal.Decimal('100')
#         gst_amount = (mdr_amount * service_provider.gst_percentage) / decimal.Decimal('100')
#         receivable_amount = trn_amount - mdr_amount - gst_amount

#         # Quantize
#         mdr_amount = mdr_amount.quantize(decimal.Decimal('0.00'))
#         gst_amount = gst_amount.quantize(decimal.Decimal('0.00'))
#         receivable_amount = receivable_amount.quantize(decimal.Decimal('0.00'))

#         # Save in transaction
#         pg_service_trn.sp_mdr_amount = mdr_amount
#         pg_service_trn.sp_gst_amount = gst_amount
#         pg_service_trn.sp_receivable_amount = receivable_amount
#         pg_service_trn.save()
#     else:
#         mdr_amount = gst_amount = receivable_amount = decimal.Decimal('0.00')

#     # ---------- Step 4: Create UNSETTLED commission records ONLY for parents -------------
#     current_user = retailer
#     prev_percent = retailer_percent

#     while True:
#         parent_details = PortalUserDetails.objects.filter(
#             pud_unique_id=current_user.username
#         ).first()
        
#         if not parent_details or not parent_details.created_by:
#             break

#         parent_user = PortalUser.objects.filter(
#             id=parent_details.created_by
#         ).first()
        
#         if not parent_user:
#             break

#         try:
#             parent_percent = get_charge_percent(parent_user, pg, card_type)
#         except Exception as e:
#             return {"status": False, "message": f"Parent charge missing: {str(e)}"}

#         diff_percent = prev_percent - parent_percent

#         if diff_percent > 0:
#             parent_comm = (diff_percent * trn_amount) / decimal.Decimal('100')

#             # Create UNSETTLED commission record ONLY for parent (distributor)
#             CommissionTransaction.objects.create(
#                 transaction_id=pg_service_trn.trn_unique_id,
#                 distributor_id=parent_user.id,  # Parent (distributor/super distributor)
#                 retailer_id=retailer.id,        # Original retailer who did transaction
#                 service_provider=service_provider,
#                 amount=parent_comm,
#                 settlement_status='UNSETTLED',
#             )

#         current_user = parent_user
#         prev_percent = parent_percent

#     # ---------- Step 5: Mark transaction as processed ----------
#     pg_service_trn.is_settled = True
#     pg_service_trn.trn_status = "SETTLED"
#     pg_service_trn.save()

#     try:
#         if retailer.pu_email:
#             email_data = {
#                 "subject": "Payment Settlement Successful",
#                 "recipient_list": [retailer.pu_email],
#                 "username": retailer_details.pud_unique_id,
#                 "amount": str(trn_amount),
#                 "timestamp": now().strftime("%Y-%m-%d %H:%M:%S"),
#                 "message": (
#                     f"Your payment gateway transaction of ₹{trn_amount} has been "
#                     f"settled successfully. Transaction ID: {pg_service_trn.trn_unique_id}."
#                 )
#             }

#             requests.post(
#                 "https://qaapi.fixpay.in/admin_hub/send-email/",
#                 json=email_data,
#                 timeout=10
#             )
#     except Exception as e:
#         print(f"Error sending settlement email: {str(e)}")

#     return {
#         "status": True,
#         "message": "Transaction Settled Successfully",
#         "transaction_id": pg_service_trn.trn_unique_id,
#     }

@transaction.atomic
def settle_pg_base_transaction(pg_service_trn_id):
    """
    Settle payment gateway transaction with instant charge support.
    Instant charge applies only to retailer, not to parent hierarchy.
    """
    pg_service_trn = get_object_or_404(PgServiceTrn, pg_trn_id=pg_service_trn_id)

    if pg_service_trn.is_settled:
        return {"status": False, "message": "Transaction already settled"}

    # Fetch required objects
    retailer = get_object_or_404(PortalUser, id=pg_service_trn.created_by)
    retailer_details = get_object_or_404(PortalUserDetails, pu=retailer)
    pg = get_object_or_404(PaymentGateway, id=pg_service_trn.pg_id)
    card_type = get_object_or_404(CardType, id=pg_service_trn.card_type_id)

    service_provider = AdServiceProvider.objects.filter(
        service__service_name='PG',
        pg=pg  
    ).first()

    is_instant = pg_service_trn.is_instant
    trn_amount = Decimal(str(pg_service_trn.trn_amount))

    # Step 0: Get retailer commission percentage
    try:
        retailer_percent = get_charge_percent(retailer, pg, card_type)
    except Exception as e:
        return {"status": False, "message": str(e)}

    retailer_percent = Decimal(str(retailer_percent))
    base_retailer_percent = retailer_percent  # Save original (without instant charge)

    # Get instant charge if applicable
    instant_charge = Decimal('0.00')
    if is_instant:
        instant_data = UserServiceFinance.objects.filter(user=retailer).first()
        if instant_data and instant_data.instant_charge:
            instant_charge = Decimal(str(instant_data.instant_charge))

    # ---------- Step 1: Credit full transaction amount to retailer -------------
    wallet, _ = PortalUserWallet.objects.get_or_create(pu=retailer)
    current_balance = wallet.pg_wallet or Decimal('0.00')
    new_balance = (current_balance + trn_amount).quantize(Decimal('0.00'))
    wallet.pg_wallet = new_balance
    wallet.save()

    WalletTrn.objects.create(
        action_id=pg_service_trn.pk,
        action_type='Service',
        pu_id=retailer.id,
        wl_label=f"PG_by_{retailer_details.pud_unique_id}_of_amount_{trn_amount}_with_tx_id_{pg_service_trn.trn_unique_id}",
        effectvie_wallet='pg_wallet',
        effectvie_amt=trn_amount,
        effective_type='CR',
        current_balance=new_balance,
        wl_trn_dt=now()
    )

    # ---------- Step 2: Debit retailer commission (with instant charge if applicable) -------------
    # Add instant charge to retailer's commission
    if is_instant and instant_charge > 0:
        retailer_percent = retailer_percent + instant_charge

    retailer_comm = (retailer_percent * trn_amount / Decimal('100')).quantize(Decimal('0.00'))
    new_balance = (new_balance - retailer_comm).quantize(Decimal('0.00'))
    wallet.pg_wallet = new_balance
    wallet.save()

    CommissionLog.objects.create(
        pg_service_trn=pg_service_trn,
        user=retailer,
        commission_amount=retailer_comm,
        level=retailer.pu_role or "RETAILER"
    )

    WalletTrn.objects.create(
        action_id=pg_service_trn.pk,
        action_type='Commission',
        pu_id=retailer.id,
        wl_label=f"Using PG {retailer_details.pud_unique_id} gets {retailer_comm} Rs CHARGE WITH GST in pg_wallet as debited",
        effectvie_wallet='pg_wallet',
        effectvie_amt=retailer_comm,
        effective_type='DR',
        current_balance=new_balance,
        wl_trn_dt=now()
    )

    # ---------- Step 3: Calculate and save service provider charges -------------
    if service_provider:
        # Determine MDR based on card type
        if card_type.name.lower() == 'rupay':
            mdr_percent = service_provider.rupay_mdr
        elif card_type.name.lower() == 'mastercard':
            mdr_percent = service_provider.mastercard_mdr
        elif card_type.name.lower() == 'visa':
            mdr_percent = service_provider.visa_mdr
        else:
            mdr_percent = Decimal('0.00')

        mdr_amount = (trn_amount * mdr_percent / Decimal('100')).quantize(Decimal('0.00'))
        gst_amount = (mdr_amount * service_provider.gst_percentage / Decimal('100')).quantize(Decimal('0.00'))
        receivable_amount = (trn_amount - mdr_amount - gst_amount).quantize(Decimal('0.00'))

        # Save in transaction
        pg_service_trn.sp_mdr_amount = mdr_amount
        pg_service_trn.sp_gst_amount = gst_amount
        pg_service_trn.sp_receivable_amount = receivable_amount
        pg_service_trn.created_at = get_ist_time()  
        pg_service_trn.save()

    # ---------- Step 4: Create UNSETTLED commission records for parent hierarchy -------------
    current_user = retailer
    prev_percent = base_retailer_percent  # Use base percent (without instant charge)

    while True:
        parent_details = PortalUserDetails.objects.filter(
            pud_unique_id=current_user.username
        ).first()
        
        if not parent_details or not parent_details.created_by:
            break

        parent_user = PortalUser.objects.filter(
            id=parent_details.created_by
        ).first()
        
        if not parent_user:
            break

        try:
            parent_percent = Decimal(str(get_charge_percent(parent_user, pg, card_type)))
        except Exception as e:
            return {"status": False, "message": f"Parent charge missing: {str(e)}"}

        diff_percent = prev_percent - parent_percent

        if diff_percent > 0:
            parent_comm = (diff_percent * trn_amount / Decimal('100')).quantize(Decimal('0.00'))

            # Create UNSETTLED commission record for parent (distributor/super distributor)
            CommissionTransaction.objects.create(
                transaction_id=pg_service_trn.trn_unique_id,
                distributor_id=parent_user.id,  # Parent (distributor/super distributor)
                retailer_id=retailer.id,        # Original retailer who did transaction
                service_provider=service_provider,
                amount=parent_comm,
                settlement_status='UNSETTLED',
            )

        current_user = parent_user
        prev_percent = parent_percent

    # ---------- Step 5: Mark transaction as settled ----------
    pg_service_trn.is_settled = True
    pg_service_trn.trn_status = "SETTLED"
    pg_service_trn.save()

    # ---------- Step 6: Send settlement email notification ----------
    try:
        if retailer.pu_email:
            email_data = {
                "subject": "Payment Settlement Successful",
                "recipient_list": [retailer.pu_email],
                "username": retailer_details.pud_unique_id,
                "amount": str(trn_amount),
                "timestamp": now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": (
                    f"Your payment gateway transaction of ₹{trn_amount} has been "
                    f"settled successfully. Transaction ID: {pg_service_trn.trn_unique_id}."
                )
            }

            requests.post(
                "https://qaapi.fixpay.in/admin_hub/send-email/",
                json=email_data,
                timeout=10
            )
    except Exception as e:
        print(f"Error sending settlement email: {str(e)}")

    return {
        "status": True,
        "message": "Transaction Settled Successfully",
        "transaction_id": pg_service_trn.trn_unique_id,
    }
@api_view(['POST'])
def settle_pg_transaction(request):
    trn_id = request.data.get('transaction_id')

    if not trn_id:
        return Response({"status": False, "message": "Transaction ID is required"}, status=400)

    try:

        result = settle_pg_base_transaction(trn_id)
    except Exception as e:
        return Response({"status": False, "message": str(e)}, status=500)

    if result["status"]:
        return Response(result, status=200)
    else:
        return Response(result, status=400)







# @csrf_exempt
# def payinResponse(request):
#     if request.method == "POST":
#         data = request.POST.dict()

        
#         with open("payin_data.txt", "a") as f:
#             for key, value in data.items():
#                 f.write(f"{key}: {value}\n")
#             f.write("\n")

#         Api_Req_Response.objects.create(
#             api_type="airpay_pg",
#             api_request={},
#             api_response=data,
#         )
#         if data.get("TRANSACTIONPAYMENTSTATUS") == "SUCCESS":
#             Api_Req_Response.objects.create(
#                 api_type="airpay_pg",
#                 api_request={},
#                 api_response=data,
#             )
#             return redirect('https://qaapi.fixpay.in/paymentsuccess')
#         else:
#             return redirect('https://qaapi.fixpay.in/paymentfaild')

#     return redirect('https://qaapi.fixpay.in/paymentfaild')


from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt



@csrf_exempt
def payinResponse(request):
    if request.method == "POST":
        data = request.POST.dict()  # Collect all the data from the POST request
        # Check if the payment status is SUCCESS
        if data.get("TRANSACTIONPAYMENTSTATUS") == "SUCCESS":
            trn_unique_id = data.get("TRANSACTIONID") 

            try:
                pg_service_trn = PgServiceTrn.objects.get(trn_unique_id=trn_unique_id)

                card_issuer_name = data.get("CARDISSUER", "").strip().lower()
                if card_issuer_name:
                    try:
                        card_type = CardType.objects.get(name__iexact=card_issuer_name)
                        pg_service_trn.card_type = card_type
                    except CardType.DoesNotExist:
                        pass
                pg_service_trn.trn_status = "COMPLETED"  
                pg_service_trn.trn_response=data
                pg_service_trn.save()  
                retailer = pg_service_trn.created_by
                user_finance = UserServiceFinance.objects.filter(
                    user_id=retailer
                ).first()
                if pg_service_trn.is_instant:
                    if user_finance:
                        amount = pg_service_trn.trn_amount
                        txn_amount = Decimal(str(amount))
                        user_finance.usage_limit += txn_amount
                        user_finance.available_limit -= txn_amount
                        user_finance.save()
                        
                        print(f"Instant Transaction Update → usage_limit: {user_finance.usage_limit}, available_limit: {user_finance.available_limit}")
                    else:
                        print("No UserServiceFinance record found for instant transaction!")
                else:
                    print("Not an instant transaction — finance not updated.")

            except PgServiceTrn.DoesNotExist:
                pass

            
            query_params = '&'.join([f"{key}={value}" for key, value in data.items()])

            # Redirect with all data as query parameters
            return HttpResponseRedirect(f'https://partner.fixpay.in/payinResponse?{query_params}')
        
        else:
            # If payment failed, redirect to the failure page
            return HttpResponseRedirect(f'https://partner.fixpay.in/payinResponse?TRANSACTIONPAYMENTSTATUS=FAILED')

    # Default failure redirect if not POST method
    return HttpResponseRedirect(f'https://partner.fixpay.in/payinResponse?TRANSACTIONPAYMENTSTATUS=FAILED')




def airpay_faild(request):
    return render(request, 'paymentfaild.html')

def airpay_success_updated(request):
    return render(request, 'payinResponse.html')





import datetime
from decimal import Decimal, ROUND_DOWN
from django.shortcuts import get_object_or_404, render
from rest_framework.views import APIView
from rest_framework.response import Response
from decimal import InvalidOperation
import jwt
from rest_framework_simplejwt.tokens import AccessToken
class AirpayPG(APIView):
    def post(self, request):    
        if 'amount' in request.data:
            return self.add_airpay_payment_initiate(request)
        return Response({'error': 'Amount is required'}, status=400)
    

    def add_airpay_payment_initiate(self, request):
        try:
            print("Starting add_airpay_payment_initiate")

            token = request.data.get('token')
            print(f"Token: {token}")

            clean_card = request.data.get('cardNumber', '')

            # Non-digit characters hatao (spaces, hyphens, etc.)
            credit_card_num = re.sub(r'\D', '', clean_card)

            customer_name = request.data.get('customerName')
            print(f"Customer Name: {customer_name}")

            mobile = request.data.get('mobile')
            print(f"Mobile: {mobile}")

            is_instant = request.data.get('is_instant', False)

            name_parts = customer_name.split() if customer_name else []
            print(f"Name Parts: {name_parts}")

            if len(name_parts) > 1:
                buyer_firstname = name_parts[0]
                buyer_lastname = " ".join(name_parts[1:])
            elif len(name_parts) == 1:
                buyer_firstname = name_parts[0]
                buyer_lastname = name_parts[0]
            else:
                buyer_firstname = ""
                buyer_lastname = ""
            print(f"Buyer Firstname: {buyer_firstname}, Buyer Lastname: {buyer_lastname}")

            bin_details = fetch_bin_details_pg(credit_card_num)
            print(f"BIN Details: {bin_details}")

            if bin_details['status'] != 'success':
                print("BIN status not successful")
                return {"status": "error", "message": bin_details['message']}

            card_type = bin_details['card_type']
            brand = bin_details['brand']
            print(f"Card Type: {card_type}, Brand: {brand}")

            card_type_instance = CardType.objects.filter(name__icontains=brand).first()
            print(f"Card Type Instance: {card_type_instance}")

            if not card_type_instance:
                print(f"Card type '{brand}' not supported")
                return Response({
                    "status": "error",
                    "message": f"Card type '{brand}' not supported"
                }, status=400)

            amount_str = request.data.get('amount')
            print(f"Amount String: {amount_str}")

            try:
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                print(f"User ID from token: {user_id}")
            except TokenError:
                print("Invalid or expired token")
                return Response({'error': 'Invalid or expired token'}, status=401)

            user = PortalUser.objects.get(id=user_id)
            print(f"PortalUser: {user}")

            try:
                amount = Decimal(amount_str).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
                print(f"Amount (Decimal): {amount}")
            except (ValueError, TypeError, InvalidOperation) as ex:
                print(f"Invalid amount error: {ex}")
                return Response({'error': 'Invalid amount'}, status=400)

            pg_id = 3
            card_type_id = card_type_instance.id
            print(f"PG ID: {pg_id}, Card Type ID: {card_type_id}")

            payment_gateway = get_object_or_404(PaymentGateway, id=pg_id)
            print(f"PaymentGateway: {payment_gateway}")

            card_type = get_object_or_404(CardType, id=card_type_id)
            print(f"CardType: {card_type}")

            retailer = user
            retailer_details = get_object_or_404(PortalUserDetails, pu=retailer)
            print(f"Retailer Details: {retailer_details}")


            user_service_finance = None
            instant_charge_percent = Decimal('0.00')
            
            if is_instant:
                
                try:
                    user_service_finance = UserServiceFinance.objects.filter(
                        user=retailer
                    ).first()
                    
                    if not user_service_finance:
                        print("No instant finance configuration found for user")
                        return Response({
                            'status': 'error',
                            'error': 'Instant payment not configured for your account. Please contact administrator.'
                        }, status=400)
                    
                    instant_limit = Decimal(str(user_service_finance.od_limit))
                    instant_charge_percent = Decimal(str(user_service_finance.instant_charge))
                    available_limit = Decimal(str(user_service_finance.available_limit))
                    
                    print(f"User OD Limit: ₹{instant_limit}")
                    print(f"Instant Charge: {instant_charge_percent}%")
                    print(f"Current Amount: ₹{amount}")
                    if amount > available_limit:
                        print(f"Insufficient Limit! Required: ₹{amount}, Available: ₹{available_limit}")
                        
                        return Response({
                            'status': 'error',
                            'error': f'Insufficient instant payment limit. Transaction amount: ₹{amount}. Available limit: ₹{available_limit}.'
                        }, status=400)
                    
                    print(f"Sufficient Limit. Remaining after transaction: ₹{available_limit - amount}")
                    
                except Exception as e:
                    print(f"Error checking instant limit: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return Response({
                        'status': 'error',
                        'error': 'Failed to verify instant payment limit. Please try again.'
                    }, status=500)

            try:
                retailer_charge = UserCharge.objects.get(user_id=retailer.id, pg=payment_gateway, card_type=card_type)
                charge_percent = retailer_charge.charge_percent
                print(f"Retailer-specific charge: {charge_percent}%")
            except UserCharge.DoesNotExist:
                try:
                    pg_base_charge = PGBaseCharge.objects.get(
                        role=retailer.pu_role.title(),
                        pg=payment_gateway,
                        card_type=card_type
                    )
                    charge_percent = pg_base_charge.charge_percent
                    print(f"Role-based base charge: {charge_percent}%")
                except PGBaseCharge.DoesNotExist:
                    print("No applicable charge percent found.")
                    return Response({
                        "status": False,
                        "message": "No applicable charge percent found."
                    }, status=400)

            total_charge_percent = charge_percent + instant_charge_percent
            total_charge_amount = (amount * total_charge_percent) / Decimal('100')
            net_credit_to_user = amount - total_charge_amount
            print(f"Total Charge Amount: {total_charge_amount}")
            print(f"Net Credit to User: {net_credit_to_user}")


            service_provider = AdServiceProvider.objects.filter(
                service__service_name='PG',
                pg=payment_gateway  
            ).first()
           
                
            if card_type.name.lower() == 'rupay':
                mdr_percent = service_provider.rupay_mdr
            elif card_type.name.lower() == 'mastercard':
                mdr_percent = service_provider.mastercard_mdr
            elif card_type.name.lower() == 'visa':
                mdr_percent = service_provider.visa_mdr
            else:
                mdr_percent = Decimal('0.00')

            mdr_amount = (amount * mdr_percent / Decimal('100')).quantize(Decimal('0.00'))
            gst_amount = (mdr_amount * service_provider.gst_percentage / Decimal('100')).quantize(Decimal('0.00'))
            receivable_amount = (amount - mdr_amount - gst_amount).quantize(Decimal('0.00'))

            

            state_name = ""
            city_name = ""
            if retailer_details.state_id:
                state = State.objects.filter(state_id=retailer_details.state_id).first()
                state_name = state.state_name if state else ""
            print(f"State Name: {state_name}")

            if retailer_details.city_id:
                city = City.objects.filter(city_id=retailer_details.city_id).first()
                city_name = city.city_name if city else ""
            print(f"City Name: {city_name}")

            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            order_id = f"AIR{timestamp}"
            print(f"Generated Order ID: {order_id}")

            pg_service_trn = PgServiceTrn.objects.create(
                trn_unique_id=order_id,
                trn_amount=amount,
                trn_response={},
                pg=payment_gateway,
                card_type=card_type,
                is_settled=False,
                trn_status="PENDING",
                created_by=retailer.id,
                buyer_email=retailer.pu_email,
                buyer_phone=mobile,
                buyer_firstname=buyer_firstname,
                buyer_lastname=buyer_lastname,
                buyer_address=state_name or "",
                buyer_city=city_name or "",
                buyer_state=state_name or "",
                buyer_country="India",
                buyer_pincode=retailer_details.zip_code or "",
                retailer_charge_percent=total_charge_percent,
                total_charge_amount=total_charge_amount,
                net_credit_to_user=net_credit_to_user,
                credit_card_num=credit_card_num,
                is_instant=is_instant,
                sp_mdr_amount=mdr_amount,
                sp_gst_amount=gst_amount,
                sp_receivable_amount=receivable_amount
            )
            print(f"Created PgServiceTrn: {pg_service_trn}")

            pg_auth_details = PaymentGetwayAuthenticationDetails.objects.filter(is_deactive=False).first()

            retailer_data = {
                "email": user.pu_email,
                "phone": mobile,
                "firstname": buyer_firstname,
                "lastname": buyer_lastname,
                "address": state_name or "",
                "city": city_name or "",
                "state": state_name or "",
                "country": "India",
                "pincode": retailer_details.zip_code or "",
                "amount_paise": amount,
                "order_id": order_id,
                "currency": 356,
                "iso_currency": "INR",
                "secret": pg_auth_details.client_secret_key,
                "mercid": pg_auth_details.mid,
                "username": pg_auth_details.username,
                "password": pg_auth_details.password,
            }
            print(f"Retailer Payload Data: {retailer_data}")

            payload = {
                'buyerEmail': retailer_data['email'],
                'buyerPhone': retailer_data['phone'],
                'buyerFirstName': retailer_data['firstname'],
                'buyerLastName': retailer_data['lastname'],
                'buyerAddress': retailer_data['address'],
                'amount': retailer_data['amount_paise'],
                'buyerCity': retailer_data['city'],
                'buyerState': retailer_data['state'],
                'buyerPinCode': retailer_data['pincode'],
                'buyerCountry': retailer_data['country'],
                'orderid': retailer_data['order_id'],
                'currency': retailer_data['currency'],
                'isocurrency': retailer_data['iso_currency'],
                'customvar': "",
                'txnsubtype': "",
                "username":retailer_data["username"],
                "secret":retailer_data["secret"],
                "mercid":retailer_data["mercid"],
                "password":retailer_data["password"],


            }
            print(f"Final Payload for Render: {payload}")

            return render(request, 'transaction.html', {"payload": payload})

        except PortalUser.DoesNotExist:
            print("PortalUser not found")
            return Response({'error': 'User not found'}, status=404)
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return Response({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

class RetailerAirpayPgAPIView(APIView): 
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())


            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # pos_devices = PosDevice.objects.filter(pu=user)
            # if not pos_devices.exists():
            #     return Response({
            #         'status': 'fail',
            #         'message': 'No retailer found for the user.'
            #     }, status=status.HTTP_404_NOT_FOUND)

            # queryset = PgServiceTrn.objects.filter(created_by=request.user.id)
            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=3,is_instant=False).order_by('-created_at')
            
            # gl_trn_queryset = GlTrn.objects.filter(pu_id=user).values_list('service_trn_id', flat=True)
            # queryset = queryset.filter(pk__in=gl_trn_queryset)


            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)
                print(queryset,'--------------')

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PgServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                
                # Check if the value is a string before parsing
                if isinstance(data['created_at'], str):
                    data['created_at'] = parser.parse(data['created_at'])

                # Format to the required format
                data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RetailerInstantAirpayPgAPIView(APIView): 
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())


            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            

            queryset = PgServiceTrn.objects.filter(created_by=request.user.id,pg_id=3,is_instant=True)
            
            


            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)
                print(queryset,'--------------')

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PgServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                
                # Check if the value is a string before parsing
                if isinstance(data['created_at'], str):
                    data['created_at'] = parser.parse(data['created_at'])

                # Format to the required format
                data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

            


            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RetailerVegaahPGAPIView(APIView): 
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())


            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # pos_devices = PosDevice.objects.filter(pu=user)
            # if not pos_devices.exists():
            #     return Response({
            #         'status': 'fail',
            #         'message': 'No retailer found for the user.'
            #     }, status=status.HTTP_404_NOT_FOUND)

            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=4,is_instant=False).order_by('-created_at')

            
            # gl_trn_queryset = GlTrn.objects.filter(pu_id=user).values_list('service_trn_id', flat=True)
            # queryset = queryset.filter(pk__in=gl_trn_queryset)


            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)
                print(queryset,'--------------')

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PgServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                
                # Check if the value is a string before parsing
                if isinstance(data['created_at'], str):
                    data['created_at'] = parser.parse(data['created_at'])

                # Format to the required format
                data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

            with open("output_data_pos.txt", "a", encoding="utf-8") as f:
                f.write(json.dumps(serializer.data, indent=4, default=str))
                f.write("\n\n")


            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class RetailerVegaahPG2APIView(APIView): 
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())


            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # pos_devices = PosDevice.objects.filter(pu=user)
            # if not pos_devices.exists():
            #     return Response({
            #         'status': 'fail',
            #         'message': 'No retailer found for the user.'
            #     }, status=status.HTTP_404_NOT_FOUND)

            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=5,is_instant=False).order_by('-created_at')

            
            # gl_trn_queryset = GlTrn.objects.filter(pu_id=user).values_list('service_trn_id', flat=True)
            # queryset = queryset.filter(pk__in=gl_trn_queryset)


            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)
                print(queryset,'--------------')

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PgServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                
                # Check if the value is a string before parsing
                if isinstance(data['created_at'], str):
                    data['created_at'] = parser.parse(data['created_at'])

                # Format to the required format
                data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

            with open("output_data_pos.txt", "a", encoding="utf-8") as f:
                f.write(json.dumps(serializer.data, indent=4, default=str))
                f.write("\n\n")


            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





class RetailerPGTransactionAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            queryset = PgServiceTrn.objects.filter(created_by=request.user.id,pg_id=3,is_instant=False)

            # gl_trn_queryset = GlTrn.objects.filter(pu_id=user).values_list('service_trn_id', flat=True)
            # queryset = queryset.filter(pk__in=gl_trn_queryset)

            daily_transactions = queryset.filter(created_at__range=[today_start, today_end])
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)


            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                }]
            }

            response_data = {
                'status': 'success',
                'message': 'Transaction data fetched successfully.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class RetailerInstantAirpayTransactionAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            queryset = PgServiceTrn.objects.filter(created_by=request.user.id,pg_id=3,is_instant=True)

            # gl_trn_queryset = GlTrn.objects.filter(pu_id=user).values_list('service_trn_id', flat=True)
            # queryset = queryset.filter(pk__in=gl_trn_queryset)

            daily_transactions = queryset.filter(created_at__range=[today_start, today_end])
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()

            user_service_finance = UserServiceFinance.objects.filter(
                user=request.user
            ).first()
            total_od_limit = getattr(user_service_finance, 'od_limit', 0) or 0

            # Remaining
            remaining_od_limit = getattr(user_service_finance, 'available_limit', 0) or 0

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)


            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                    'total_od_limit': total_od_limit,
                    'remaining_od_limit': remaining_od_limit
                }]
            }

            response_data = {
                'status': 'success',
                'message': 'Transaction data fetched successfully.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@api_view(['POST'])
def assign_charges(request):
    pg_id = request.data.get("pg_id", 3)

    role_charge_map = {
        'ADMIN': Decimal('1.25'),
        'SUPER DISTRIBUTOR':Decimal('1.28'),
        'MASTER DISTRIBUTOR':Decimal('1.30'),
        'DISTRIBUTOR': Decimal('1.35'),
        'RETAILER': Decimal('1.40'),
    }

    try:
        pg_instance = PaymentGateway.objects.get(id=pg_id)
    except PaymentGateway.DoesNotExist:
        return Response({"error": f"Payment Gateway with id={pg_id} not found."},
                        status=status.HTTP_404_NOT_FOUND)

    all_users = PortalUser.objects.filter(is_deleted=False, is_deactive=False)
    card_types = CardType.objects.all()

    count_created = 0
    for user in all_users:
        charge_percent = role_charge_map.get(user.pu_role)
        if charge_percent is None:
            continue

        for card in card_types:
            exists = UserCharge.objects.filter(
                pg=pg_instance,
                card_type=card,
                user_id=user
            ).exists()

            if not exists:
                UserCharge.objects.create(
                    pg=pg_instance,
                    card_type=card,
                    charge_percent=charge_percent,
                    user_id=user.id
                )
                count_created += 1

    return Response({
        "message": f"assigned successfully."
    }, status=status.HTTP_200_OK)









# get data of pg and card-----------------------

@api_view(["GET"])
def get_payment_gateways(request):
    pgs = PaymentGateway.objects.filter(is_active=True).values("id", "name")
    return Response({"status": "success", "data": list(pgs)})

@api_view(["GET"])
def get_card_types(request):
    cards = CardType.objects.all().values("id", "name", "created_at")
    return Response({"status": "success", "data": list(cards)})


from collections import defaultdict
#for user level charge-----------------------------
class UserLevelChargeApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        try:
            if 'page_number' in request.data or 'page_size' in request.data or 'ul_id' in request.data:
                return self.fetch_user_level_charge(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(str(e))
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    def fetch_user_level_charge(self, request):
        ul_id = request.data.get("ul_id")
        page_number = request.data.get("page_number", 1)
        page_size = request.data.get("page_size")

        try:
            if not page_size:
                return Response({'status': 'fail', 'message': 'page_size is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(page_size):
                return Response({'status': 'fail', 'message': 'page_size must be numeric.'}, status=status.HTTP_400_BAD_REQUEST)
            if page_number and not isnumber(page_number):
                return Response({'status': 'fail', 'message': 'page_number must be numeric.'}, status=status.HTTP_400_BAD_REQUEST)
            if ul_id and not isnumber(ul_id):
                return Response({'status': 'fail', 'message': 'ul_id must be numeric.'}, status=status.HTTP_400_BAD_REQUEST)

            # Base query
            queryset = UserCharge.objects.select_related('user', 'pg', 'card_type')
            if ul_id:
                queryset = queryset.filter(charge_id=ul_id)

            queryset = queryset.order_by('-charge_id')

            # Group by (user_id, pg_id)
            grouped = defaultdict(lambda: {
                "charge_id": None,
                "username": "",
                "pg_name": "",
                "Mastercard": "-",
                "Rupay": "-",
                "Visa": "-"
            })

            for item in queryset:
                if not item.user or not item.pg or not item.card_type:
                    continue  # Skip incomplete data

                key = (item.user.id, item.pg.id)
                entry = grouped[key]

                # Assign basic info
                entry["charge_id"] = item.charge_id
                entry["username"] = item.user.username
                entry["pg_name"] = item.pg.name

                card_type = item.card_type.name.strip().lower()
                charge_value = str(item.charge_percent or "0.000")

                if card_type == "mastercard":
                    entry["mastercard_charge"] = charge_value
                elif card_type == "rupay":
                    entry["rupay_charge"] = charge_value
                elif card_type == "visa":
                    entry["visa_charge"] = charge_value

            grouped_list = list(grouped.values())

            # Paginate the grouped result
            paginator = Paginator(grouped_list, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found', 'data': {}}, status=status.HTTP_404_NOT_FOUND)

            paginated_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': page_obj.object_list
            }

            return Response({
                'status': 'success',
                'message': 'User level charge data',
                'data': paginated_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'fail',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from admin_hub.models import PortalUserCharges, PortalUser

@require_GET
def check_service_provider_active(request):
    username = request.GET.get('username')

    if not username:
        return JsonResponse({'error': 'Username is required.'}, status=400)

    try:
        user = PortalUser.objects.get(username=username)
    except PortalUser.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)

    if user.pu_role == 'Retailer':
        is_active = PortalUserCharges.objects.filter(
            pu_id=user.id,
            sp_id=3,
            is_deactive=False
        ).exists()
    else:
        is_active = True

    return JsonResponse({'username': username, 'service_provider_active': is_active})


class AddUserLevelChargeApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        # Use print to output raw request data
        print(f"Raw request data: {request.data}")  # Print full request data for debugging

        charges = request.data.get('charges', [])
        print(f"Charges received: {charges}")

        if not charges:
            return Response({'status': 'fail', 'message': 'Charges are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Iterate over the charges list and validate each entry
        for charge in charges:
            username = charge.get('username')
            pg_id = charge.get('pg_id')
            card_type_id = charge.get('card_type_id')
            charge_per = charge.get('charge_per')

            # Validate the fields
            if not username:
                return Response({'status': 'fail', 'message': 'Username is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not pg_id:
                return Response({'status': 'fail', 'message': 'Payment gateway is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not card_type_id:
                return Response({'status': 'fail', 'message': 'Card type is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not charge_per:
                return Response({'status': 'fail', 'message': 'Charge percentage is required.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                # Check if charge already exists for the given user, payment gateway, and card type
                if UserCharge.objects.filter(pg_id=pg_id, card_type_id=card_type_id, user_id__username=username).exists():
                    return Response({
                        'status': 'fail',
                        'message': f"Charge for {username}, payment gateway, and card type already exists."
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Get the related objects
                payment_gateway = PaymentGateway.objects.get(id=pg_id)
                card_type = CardType.objects.get(id=card_type_id)
                user = PortalUser.objects.get(username=username)

                # Create a new UserCharge entry
                UserCharge.objects.create(
                    pg=payment_gateway,
                    card_type=card_type,
                    charge_percent=charge_per,
                    user=user
                )
                print(f"Charge added for user: {username}, payment gateway: {payment_gateway.name}, card type: {card_type.name}")

            except PaymentGateway.DoesNotExist:
                print(f"Payment Gateway with id {pg_id} not found.")
                return Response({'status': 'fail', 'message': f'Payment Gateway with id {pg_id} not found.'}, status=status.HTTP_404_NOT_FOUND)
            except CardType.DoesNotExist:
                print(f"Card Type with id {card_type_id} not found.")
                return Response({'status': 'fail', 'message': f'Card Type with id {card_type_id} not found.'}, status=status.HTTP_404_NOT_FOUND)
            except PortalUser.DoesNotExist:
                print(f"User with username {username} not found.")
                return Response({'status': 'fail', 'message': f'User with username {username} not found.'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                print(f"Error adding user-level charge: {str(e)}")  # Print the complete exception
                return Response({'status': 'error', 'message': f'Error adding user-level charge: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'success', 'message': 'User-level charges added successfully.'}, status=status.HTTP_201_CREATED)



class EditUserLevelChargeApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def put(self, request):
        charges = request.data.get('charges', [])

        print(charges)

        if not charges:
            return Response({'status': 'fail', 'message': 'Charges are required.'}, status=status.HTTP_400_BAD_REQUEST)

        for charge in charges:
            username = charge.get('username')
            pg_id = charge.get('pg_id')
            card_type_id = charge.get('card_type_id')
            charge_per = charge.get('charge_per')

            if not all([username, pg_id, card_type_id, charge_per]):
                return Response({
                    'status': 'fail',
                    'message': 'All fields (username, pg_id, card_type_id, charge_per) are required.'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                user = PortalUser.objects.get(username=username)
                user_charge = UserCharge.objects.get(pg_id=pg_id, card_type_id=card_type_id, user_id=user)

                # Update the charge percentage
                user_charge.charge_percent = charge_per
                user_charge.save()

                print(f"Updated charge for user: {username}, pg_id: {pg_id}, card_type_id: {card_type_id}")

            except PortalUser.DoesNotExist:
                return Response({'status': 'fail', 'message': f'User with username {username} not found.'}, status=status.HTTP_404_NOT_FOUND)
            except UserCharge.DoesNotExist:
                return Response({
                    'status': 'fail',
                    'message': f"No existing charge found for user {username}, pg_id {pg_id}, card_type_id {card_type_id}."
                }, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({'status': 'error', 'message': f'Error updating charge: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'success', 'message': 'Charges updated successfully.'}, status=status.HTTP_200_OK)
from django.db import IntegrityError

class DeleteUserLevelChargeApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def delete(self, request):
        username = request.data.get("username")
        pg_name = request.data.get("pg_id")
        if not username or not pg_name:
            return JsonResponse({"error": "Both username and pg_name are required"}, status=400)

        try:
            payment_gateway = get_object_or_404(PaymentGateway, name=pg_name)
            
            user_charges = UserCharge.objects.filter(user__username=username, pg=payment_gateway)
            if not user_charges.exists():
                return JsonResponse({"error": "No charges found for this user and payment gateway."}, status=404)
            deleted_count, _ = user_charges.delete()
            if deleted_count > 0:
                return JsonResponse({"message": f"Successfully deleted {deleted_count} charges for user {username} with payment gateway {pg_name}."}, status=200)
            else:
                return JsonResponse({"error": "No charges were deleted."}, status=400)
        except IntegrityError as e:
            return JsonResponse({"error": f"Integrity error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Something went wrong: {str(e)}"}, status=500)

#for base charge --------------------------------

from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status



class PGChargeConfigView(APIView):
    def get(self, request):
        # Fetching payment gateways and card types
        payment_gateways = PaymentGateway.objects.filter(is_active=True).values("id", "name")
        card_types = CardType.objects.all().values("id", "name")

        # Fetch PGBaseCharge for the selected gateway and card type
        pg_base_charges = PGBaseCharge.objects.select_related('pg', 'card_type').all()

        # Prepare the data to be returned
        pg_base_charge_data = {}
        for charge in pg_base_charges:
            gateway_id = charge.pg.id
            role = charge.role
            card_type = charge.card_type.name

            if gateway_id not in pg_base_charge_data:
                pg_base_charge_data[gateway_id] = {}

            if role not in pg_base_charge_data[gateway_id]:
                pg_base_charge_data[gateway_id][role] = {}

            # Store the charge percentage in the correct role and card type
            pg_base_charge_data[gateway_id][role][card_type] = str(charge.charge_percent)

        return Response({
            "status": "success",
            "payment_gateways": list(payment_gateways),
            "card_types": list(card_types),
            "pg_base_charge_data": pg_base_charge_data,  # Include PGBaseCharge data
        })

    def post(self, request):
        gateway_id = request.data.get('gateway')
        charge_data = request.data.get('data')

        if not gateway_id or not charge_data:
            return Response({
                "status": "error",
                "message": "Gateway ID or charge data missing"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Define role hierarchy
        role_hierarchy = ['Admin', 'Super Distributor', 'Master Distributor', 'Distributor', 'Retailer']

        try:
            for role, card_data in charge_data.items():
                if role not in role_hierarchy:
                    return Response({
                        "status": "error",
                        "message": f"Invalid role provided: {role}"
                    }, status=status.HTTP_400_BAD_REQUEST)

                role_index = role_hierarchy.index(role)

                for card_type_name, charge_percent in card_data.items():
                    # Convert to Decimal safely
                    try:
                        charge_percent = float(charge_percent)
                    except (TypeError, ValueError):
                        charge_percent = None

                    card_type = CardType.objects.get(name=card_type_name)

                    # Check against parent's charge
                    if role_index > 0:  # Not Admin
                        parent_role = role_hierarchy[role_index - 1]
                        parent_charge = PGBaseCharge.objects.filter(
                            pg_id=gateway_id,
                            role=parent_role,
                            card_type=card_type
                        ).first()

                        if parent_charge and charge_percent is not None and parent_charge.charge_percent is not None:
                            if charge_percent < float(parent_charge.charge_percent):
                                return Response({
                                    "status": "error",
                                    "message": (
                                        f"{role} charge for {card_type.name} cannot be less than its parent "
                                        f"({parent_role}: {parent_charge.charge_percent}%)"
                                    )
                                }, status=status.HTTP_400_BAD_REQUEST)

                    # Save or update
                    PGBaseCharge.objects.update_or_create(
                        pg_id=gateway_id,
                        role=role,
                        card_type=card_type,
                        defaults={'charge_percent': charge_percent}
                    )

        except CardType.DoesNotExist:
            return Response({
                "status": "error",
                "message": f"Card type {card_type_name} not found."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "status": "success",
            "message": "Charge data updated successfully!"
        })



class BaseChargeApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]

    def post(self, request):
        try:
            if 'pg_id' in request.data and 'card_type_id' in request.data and 'charge_per' in request.data:
                return self.add_base_charge(request)
            elif 'page_number' in request.data or 'page_size' in request.data or 'bc_id' in request.data:
                return self.fetch_fund_request(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def add_base_charge(self, request):
        
        pg_id = request.data.get('pg_id')
        card_type_id = request.data.get('card_type_id')
        charge_per = request.data.get('charge_per')

        print(pg_id, card_type_id, charge_per)  # Useful for debugging

        # Validate required fields
        if not pg_id:
            return Response({'status': 'fail', 'message': 'Payment gateway is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not card_type_id:
            return Response({'status': 'fail', 'message': 'Card type is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not charge_per:
            return Response({'status': 'fail', 'message': 'Charge percentage is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Check if the combination of pg_id and card_type_id already exists
            if PGBaseCharge.objects.filter(pg_id=pg_id, card_type_id=card_type_id).exists():
                return Response({
                    'status': 'fail',
                    'message': 'Base charge for this payment gateway and card type already exists.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Retrieve the related payment gateway and card type
            payment_gateway = PaymentGateway.objects.get(id=pg_id)
            card_type = CardType.objects.get(id=card_type_id)

            # Create the new base charge
            PGBaseCharge.objects.create(
                pg=payment_gateway,
                card_type=card_type,
                charge_percent=charge_per
            )

            return Response({'status': 'success', 'message': 'Base charge added successfully.'}, status=status.HTTP_201_CREATED)

        except PaymentGateway.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Payment Gateway not found.'}, status=status.HTTP_404_NOT_FOUND)
        except CardType.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Card Type not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Error adding base charge: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



    def fetch_fund_request(self, request):
        bc_id = request.data.get("bc_id")
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size')

        try:
            if not page_size: return Response({'status': 'fail','message': 'page_size is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(page_size): return Response({'status': 'fail','message': 'page_size must contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number:
                if not isnumber(page_number): return Response({'status': 'fail','message': 'page_number must contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            if bc_id:
                if not isnumber(bc_id): return Response({'status': 'fail','message': 'fr_id must contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            if request.user.pu_role == "ADMIN":
                queryset = PGBaseCharge.objects.filter()
            else:
                queryset = PGBaseCharge.objects.filter()

            if bc_id:
                queryset = queryset.filter(pk=bc_id)

            queryset = queryset.order_by('-pk')

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            if page_obj is not None:
                if not queryset.exists():
                    paginated_response_data = {
                        'total_pages': 0,
                        'current_page': 0,
                        'total_items': 0,
                        'results': []
                    }
                    response_data = {
                        'status': 'fail',
                        'message': 'Fund request Data not found.',
                        'data': paginated_response_data
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                serializer = PGBaseChargeSerializer(page_obj.object_list, many=True, context={'request': request})
                paginated_response_data = {
                    'total_pages': paginator.num_pages,
                    'current_page': page_obj.number,
                    'total_items': paginator.count,
                    'results': serializer.data
                }
                return Response({
                    'status': 'success',
                    'message': 'Fund request data',
                    'data': paginated_response_data
                }, status=status.HTTP_200_OK)

            serializer = PGBaseChargeSerializer(queryset, many=True, context={'request': request})
            response_data = {
                'status': 'success',
                'message': 'Fund request data',
                'data': serializer.data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'fail', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    
    def put(self, request):
        try:
            if 'bc_id' in request.data:
                return self.base_charge_update(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(e)
            return Response({'status': 'error', 'message': 'Internal server error.', 'data': str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def base_charge_update(self, request):
        try:
            bc_id = request.data.get("bc_id")
            pg_id = request.data.get("pg_id")
            card_type_id = request.data.get("card_type_id")
            charge_per = request.data.get("charge_per")

            if not bc_id:
                return Response({'status': 'fail', 'message': 'bc_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                base_charge = PGBaseCharge.objects.get(pk=bc_id)
            except PGBaseCharge.DoesNotExist:
                return Response({'status': 'fail', 'message': 'Base charge record does not exist.'}, status=status.HTTP_404_NOT_FOUND)

            if pg_id:
                try:
                    payment_gateway = PaymentGateway.objects.get(id=pg_id)
                    base_charge.pg = payment_gateway
                except PaymentGateway.DoesNotExist:
                    return Response({'status': 'fail', 'message': 'Payment gateway not found.'}, status=status.HTTP_404_NOT_FOUND)

            if card_type_id:
                try:
                    card_type = CardType.objects.get(id=card_type_id)
                    base_charge.card = card_type
                except CardType.DoesNotExist:
                    return Response({'status': 'fail', 'message': 'Card type not found.'}, status=status.HTTP_404_NOT_FOUND)

            if charge_per is not None:
                base_charge.charge_percent = charge_per

            base_charge.save()

            return Response({'status': 'success', 'message': 'Base charge updated successfully.'}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




    def delete(self, request):
        try:
            bc_id = request.data.get('bc_id')

            print(bc_id,'-----------------11507')

            if not bc_id:
                return Response({'status': 'fail', 'message': 'bc_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(bc_id):
                return Response({'status': 'fail', 'message': 'bc_id must contain only digits.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                queryset = PGBaseCharge.objects.get(id=bc_id)
            except PGBaseCharge.DoesNotExist:
                return Response({'status': 'fail', 'message': 'Base Charge does not exist.'}, status=status.HTTP_404_NOT_FOUND)

            queryset.delete()
            return Response({'status': 'success', 'message': 'Base Charge deleted successfully.'}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': 'Internal server error.', 'data': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#new 9/5/25 all charge user



class BuildUserHierarchyView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]
    def get(self, request, *args, **kwargs):
        payment_gateway_filter = request.GET.get("payment_gateway")
        if not payment_gateway_filter:
            return JsonResponse({"error": "Please provide a payment_gateway parameter."}, status=400)

        payment_gateway = PaymentGateway.objects.filter(name__iexact=payment_gateway_filter.strip()).first()
        if not payment_gateway:
            return JsonResponse({"error": "Payment gateway not found."}, status=404)

        users = PortalUser.objects.all()
        user_details = PortalUserDetails.objects.all()
        charges = UserCharge.objects.filter(pg=payment_gateway).select_related("card_type", "pg")

        card_map = {card.id: card.name.strip().lower() for card in CardType.objects.all()}

        user_map = {user.id: user for user in users}
        children_map = defaultdict(list)
        user_charge_map = defaultdict(lambda: {"mastercard": 0, "visa": 0, "rupay": 0})

        for charge in charges:
            user_id = charge.user_id
            card_type = card_map.get(charge.card_type_id, "").strip().lower()
            if card_type in ["mastercard", "visa", "rupay"]:
                user_charge_map[user_id][card_type] += float(charge.charge_percent or 0)


        for detail in user_details:
            if detail.pu_id and detail.created_by:
                children_map[detail.created_by].append(detail.pu_id)

        def build_tree(user_id):
            user = user_map.get(user_id)
            if not user:
                return {}

            charges = user_charge_map.get(user_id, {})

            username = user.username

            # Map role based on the start of the username
            role_prefix = username[:2].upper()  # First 2 characters (case-insensitive)
            prefix_role_map = {
                "SD": "Super Distributor",
                "MD": "Master Distributor",
                "DT": "Distributor",
                "RT": "Retailer",
            }
            display_role = prefix_role_map.get(role_prefix, user.pu_role)

            # Sort children by username
            children_ids = children_map.get(user_id, [])
            sorted_children_ids = sorted(
                children_ids,
                key=lambda uid: user_map[uid].username.lower() if uid in user_map else ""
            )

            return {
                "id": user_id,
                "username": username,
                "role": display_role,
                "charges": charges,
                "children": [build_tree(child_id) for child_id in sorted_children_ids]
            }

        admin_user = PortalUser.objects.filter(pu_role="ADMIN").first()
        if not admin_user:
            return JsonResponse({"error": "Admin user not found."}, status=404)

        admin_children_ids = children_map.get(admin_user.id, [])
        hierarchy = [build_tree(child_id) for child_id in admin_children_ids]

        return JsonResponse(hierarchy, safe=False, json_dumps_params={"indent": 2})



class PGServiceCategoryCharges(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        print(request.data)

        try:
            service_id = str(request.data.get('service_id'))

            if (
                'service_id' in request.data and
                ('page_number' in request.data or 'page_size' in request.data)
            ):
                if service_id in ['3', '7']:
                    return self.fetch_pg_data(request)

            if service_id in ['3', '7'] and all(
                key in request.data for key in ['client_key', 'secret_key']
            ):
                return self.handle_credentials(request)

            return Response(
                {'status': 'error', 'message': 'Invalid request payload'},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def handle_credentials(self, request):
        try:
            service_id = str(request.data.get('service_id'))

            if service_id == '7':
                missing_fields = [
                    field for field in ['client_key', 'secret_key']
                    if not request.data.get(field)
                ]
                if missing_fields:
                    return Response(
                        {
                            'status': 'fail',
                            'message': f"Missing required fields: {', '.join(missing_fields)}"
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                new_pg_auth = PaymentGetwayAuthenticationDetails.objects.create(
                    client_key=request.data.get('client_key'),
                    client_secret_key=request.data.get('secret_key'),
                    min_amount=request.data.get('min_amount'),
                    max_amount=request.data.get('max_amount'),
                    sp_id=service_id
                )

            elif service_id == '3':
                missing_fields = [
                    field for field in ['username', 'password', 'secret_key', 'mid']
                    if not request.data.get(field)
                ]
                if missing_fields:
                    return Response(
                        {
                            'status': 'fail',
                            'message': f"Missing required fields: {', '.join(missing_fields)}"
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                new_pg_auth = PaymentGetwayAuthenticationDetails.objects.create(
                    username=request.data.get('username'),
                    password=request.data.get('password'),
                    client_secret_key=request.data.get('secret_key'),
                    client_key=request.data.get('client_key'),
                    mid=request.data.get('mid'),
                    sp_id=service_id
                )

            else:
                return Response(
                    {'status': 'fail', 'message': 'Invalid service_id'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response(
                {
                    'status': 'success',
                    'message': 'Credentials added successfully',
                    'pg_auth_id': new_pg_auth.pg_auth_id
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def fetch_pg_data(self, request):
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        search = request.data.get('search', '')
        sp_id = request.data.get('service_id')


        try:
            if not page_number:
                return Response({'status': 'fail', 'message': 'page_number is required.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not page_size:
                return Response({'status': 'fail', 'message': 'page_size is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not isnumber(page_number):
                return Response({'status': 'fail', 'message': 'page_number must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isnumber(page_size):
                return Response({'status': 'fail', 'message': 'page_size must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)

            page_number = int(page_number)
            page_size = int(page_size)

            if page_number < 1 or page_size < 1:
                return Response({'status': 'fail', 'message': 'page_number and page_size must be greater than 0.'},
                                status=status.HTTP_400_BAD_REQUEST)

            all_data = PaymentGetwayAuthenticationDetails.objects.filter(sp_id=sp_id).order_by('-pk')
            print(all_data,'------------------------------------------------------------------------')


            if search != '':
                all_data = all_data.filter(Q(mid__icontains=search) | Q(username__icontains=search))

            paginator = Paginator(all_data, page_size)
            try:
                data_page = paginator.page(page_number)
            except Exception as e:
                return Response({'status': 'fail', 'message': 'Invalid page number or page size.'},
                                status=status.HTTP_400_BAD_REQUEST)
            serializer = PaymentGetwayAuthenticationDetailsSerializer(data_page, many=True)

            data = {
                'total_pages': paginator.num_pages,
                'current_page': page_number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            

            return Response({'status': 'success', 'message': 'Credentials fetched successfully',
                             'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e))
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def put(self, request):
        service_id = str(request.data.get('service_id'))
        print('service_id--', service_id)

        try:
            if service_id in ['3', '7']:
                return self.update_pg_auth_status(request)

            return Response(
                {'status': 'fail', 'message': 'Invalid service_id'},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            return Response(
                {'status': 'error', 'message': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update_pg_auth_status(self, request):
        pg_auth_id = request.data.get('pg_auth_id')
        is_deactive = request.data.get('is_deactive', None)

        mid = request.data.get('mid')
        username = request.data.get('username')
        password = request.data.get('password')
        secret_key = request.data.get('secret_key')
        client_key = request.data.get('client_key')
        min_amount = request.data.get('min_amount')
        max_amount = request.data.get('max_amount')

        if not pg_auth_id:
            return Response(
                {'status': 'fail', 'message': 'pg_auth_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            auth_obj = PaymentGetwayAuthenticationDetails.objects.get(pg_auth_id=pg_auth_id)
            updated = False

            if mid is not None:
                auth_obj.mid = mid.strip()
                updated = True

            if username is not None:
                auth_obj.username = username.strip()
                updated = True

            if password is not None:
                auth_obj.password = password.strip()
                updated = True

            if secret_key is not None:
                auth_obj.client_secret_key = secret_key.strip()
                updated = True

            if client_key is not None:
                auth_obj.client_key = client_key.strip()
                updated = True

            if min_amount is not None:
                auth_obj.min_amount = min_amount
                updated = True

            if max_amount is not None:
                auth_obj.max_amount = max_amount
                updated = True

            if not updated:
                deactivating = is_deactive in [True, 'true', 'True', '1', 1]

                if not deactivating:
                    existing_active = PaymentGetwayAuthenticationDetails.objects.filter(
                        sp_id=auth_obj.sp_id,
                        is_deactive=False
                    ).exclude(pg_auth_id=pg_auth_id).first()

                    if existing_active:
                        return Response(
                            {
                                'status': 'fail',
                                'message': f'Credential {existing_active.pg_auth_id} is already active.'
                            },
                            status=status.HTTP_400_BAD_REQUEST
                        )

                auth_obj.is_deactive = deactivating
                auth_obj.save()

                return Response(
                    {'status': 'success', 'message': 'Status updated successfully.'},
                    status=status.HTTP_200_OK
                )

            auth_obj.save()
            return Response(
                {'status': 'success', 'message': 'Credentials updated successfully.'},
                status=status.HTTP_200_OK
            )

        except PaymentGetwayAuthenticationDetails.DoesNotExist:
            return Response(
                {'status': 'fail', 'message': 'Credentials not found.'},
                status=status.HTTP_404_NOT_FOUND
            )





class PGServiceCategoryChargesTid(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        try:
            # Fetch paginated TID data
            if 'service_id' in request.data and ('page_number' in request.data or 'page_size' in request.data):
                if str(request.data.get('service_id')) in ['4', '6']:
                    return self.fetch_tid_data(request)

                return Response({'status': 'error', 'message': 'Invalid data'}, status=400)


            # Add new TID credentials
            if all(param in request.data for param in ['username', 'password', 'mid', 'unique_name']):
                return self.handle_tid_credentials(request)

            return Response({'status': 'error', 'message': 'Invalid data'}, status=400)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=500)

    def handle_tid_credentials(self, request):
        try:
            username = request.data.get('username')
            password = request.data.get('password')
            mid = request.data.get('mid')  # TID stored in mid field
            unique_name = request.data.get('unique_name')
            sp_id = request.data.get('service_id')
            min_amount = request.data.get('min_amount', 50.00)
            max_amount = request.data.get('max_amount', 39990.00)
            print(sp_id,'======================================================================>>>>>>>>>>>>>14289')

            missing_fields = [f for f in ['username', 'password', 'mid', 'unique_name'] if not request.data.get(f)]
            if missing_fields:
                return Response(
                    {'status': 'fail', 'message': f'Missing required fields: {", ".join(missing_fields)}'},
                    status=400
                )

            # Check if unique_name already exists
            if PaymentGetwayAuthenticationDetails.objects.filter(unique_name=unique_name).exists():
                return Response(
                    {'status': 'fail', 'message': 'This unique name already exists'},
                    status=400
                )

            new_tid_auth = PaymentGetwayAuthenticationDetails.objects.create(
                username=username,
                password=password,
                mid=mid,
                unique_name=unique_name,
                is_deactive=False,
                sp_id=sp_id,
                min_amount=min_amount, 
                max_amount=max_amount, 

            )

            return Response({
                'status': 'success',
                'message': 'TID credentials added successfully',
                'pg_auth_id': new_tid_auth.pg_auth_id
            }, status=201)

        except Exception as e:
            return Response({'status': 'error', 'message': f"Error while saving TID credentials: {str(e)}"}, status=500)

    def fetch_tid_data(self, request):
        print('===============================>>>>>>>>>>>>>>>>>>>>>>')
        try:

            print('====================================__________________________________________')
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search = request.data.get('search', '')
            sp_id = request.data.get('service_id') 

            all_data = PaymentGetwayAuthenticationDetails.objects.filter(
                sp_id=sp_id,
                mid__isnull=False,
                unique_name__isnull=False  
            ).order_by('-pk')
            print(all_data,'=====================>>>>>>>>>>>>>>>>')
            if search:
                all_data = all_data.filter(Q(mid__icontains=search) | Q(username__icontains=search) | Q(unique_name__icontains=search))

            paginator = Paginator(all_data, page_size)
            try:
                data_page = paginator.page(page_number)
            except Exception:
                return Response({'status': 'fail', 'message': 'Invalid page number.'}, status=400)

            serializer = PaymentGetwayAuthenticationDetailsSerializer(data_page, many=True)

            data = {
                'total_pages': paginator.num_pages,
                'current_page': page_number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({'status': 'success', 'message': 'TID credentials fetched successfully', 'data': data}, status=200)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=500)

    def put(self, request):
        service_id = request.data.get('service_id')
        if service_id not in ['4', '6']:
            return Response({'status': 'fail', 'message': 'Invalid data'}, status=400)
        return self.update_tid_auth_status(request)

    def update_tid_auth_status(self, request):
        pg_auth_id = request.data.get('pg_auth_id')
        username = request.data.get('username')
        password = request.data.get('password')
        mid = request.data.get('mid')  # TID in mid field
        unique_name = request.data.get('unique_name')
        is_deactive = request.data.get('is_deactive', None)
        sp_id = request.data.get('sp_id')
        min_amount = request.data.get('min_amount')
        max_amount = request.data.get('max_amount')

        if not pg_auth_id:
            return Response({'status': 'fail', 'message': 'pg_auth_id is required.'}, status=400)

        try:
            auth_obj = PaymentGetwayAuthenticationDetails.objects.get(pg_auth_id=pg_auth_id)
            updated = False

            # Update credentials if provided
            if mid is not None:
                auth_obj.mid = mid.strip()
                updated = True
            if username is not None:
                auth_obj.username = username.strip()
                updated = True
            if password is not None:
                auth_obj.password = password.strip()
                updated = True
            if unique_name is not None:
                # Check if new unique_name already exists (excluding current record)
                if PaymentGetwayAuthenticationDetails.objects.filter(unique_name=unique_name).exclude(pg_auth_id=pg_auth_id).exists():
                    return Response(
                        {'status': 'fail', 'message': 'This unique name already exists'},
                        status=400
                    )
                auth_obj.unique_name = unique_name.strip()
                updated = True
            if sp_id is not None:
                auth_obj.sp_id = sp_id
                updated = True

            if min_amount is not None:
                auth_obj.min_amount = Decimal(str(min_amount))
                updated = True
            if max_amount is not None:
                auth_obj.max_amount = Decimal(str(max_amount))
                updated = True

            if not updated:
                if is_deactive is not None:
                    auth_obj.is_deactive = is_deactive in [True, 'true', 'True', '1', 1]
                else:
                    auth_obj.is_deactive = not auth_obj.is_deactive

                auth_obj.save()
                action = "deactivated" if auth_obj.is_deactive else "activated"
                return Response({
                    'status': 'success',
                    'message': f'TID credentials {action} successfully.'
                }, status=200)

            # Save updated fields
            auth_obj.save()
            return Response({'status': 'success', 'message': 'TID credentials updated successfully.'}, status=200)

        except PaymentGetwayAuthenticationDetails.DoesNotExist:
            return Response({'status': 'fail', 'message': 'TID credentials not found.'}, status=404)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=500)





from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .bbps_service import *

class DmtSenderVerification(APIView):
    def post(self, request):
        mobile = request.data.get('mobile_number')
        print(mobile)
        if not mobile:
            return Response(
                {'status': 'fail', 'message': 'Mobile number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        sender = SenderDmt.objects.filter(mobile_number=mobile).first()
        if sender:
            beneficiaries = BeneficiaryDmt.objects.filter(sender=sender)
            beneficiary_data = [
                {
                    'id': b.id,
                    'mobile_number': b.mobile_number,
                    'account_number': b.account_number
                } for b in beneficiaries
            ]
            return Response({'status': 'exists', 'beneficiaries': beneficiary_data})
        print('----------this is not in sender------------------------------------------------------------')
        result = register_sender_to_bbps_dmt(mobile)

        Api_Req_Response.objects.create(
            api_type="SenderRegister",
            api_request={'mobile_number': mobile},
            api_response=result
        )
        if result['success']:
            new_sender = SenderDmt.objects.create(
                mobile_number=mobile,
                name=result.get('name', 'Unknown')
            )
            return Response({'status': 'registered', 'sender_id': new_sender.id})
        else:
            return Response(
                {'status': 'error', 'message': result['error']},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )





class GetAllRecipientsView(APIView):
    def post(self, request):
        sender_mobile = request.data.get('senderMobileNumber')
        txn_type = request.data.get('txnType', 'IMPS')
        bank_id = request.data.get('bankId', 'ARTL')

        if not sender_mobile:
            return Response({'success': False, 'error': 'senderMobileNumber is required'}, status=status.HTTP_400_BAD_REQUEST)

        result = get_all_recipients(sender_mobile, txn_type, bank_id)
        
        return Response(result, status=status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST)

from .zoho_mail import *



from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from django.http import JsonResponse


from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from django.http import JsonResponse
import json




def html_send_email(subject, recipient_list, role=None, otp=None, username=None, password=None, name=None,
               amount=None, timestamp=None, total_balance=None, bbps_balance=None,
               wallet_current=None, service_name=None,dba_name=None,message=None):

    
    if "OTP" in subject:  # Sending OTP email
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
                    <h4>Hello Partner,</h4>
                    <p>We hope this message finds you well!</p>
                    <p>Your OTP for email verification is: <strong>{otp}</strong></p>
                    <p>Please make sure to keep it confidential and do not share it with anyone.</p>
                    <p>If you did not request this, please disregard this email.</p>
                    <p>If you have any questions or need further assistance, feel free to contact our support team.</p>
                    <p>Best regards,<br>SSEPL</p>
                </div>
                <div class="footer">
                    <p>This email is generated automatically, please do not reply.</p>
                </div>
            </body>
            </html>
        """
    elif "Welcome" in subject:  # Sending user credentials email
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
    elif "Wallet Transfer Alert - FIXPAY" in subject:
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
                        border-radius: 8px;
                        padding: 20px;
                        box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                    }}
                    h2 {{
                        color: #004aad;
                    }}
                    p {{
                        color: #333333;
                        margin: 10px 0;
                    }}
                    .highlight {{
                        font-weight: bold;
                        color: #000;
                    }}
                    .footer {{
                        margin-top: 30px;
                        font-size: 0.85em;
                        color: #888;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Wallet Transfer Notification</h2>
                    <p>Dear Admin,</p>
                    <p>A wallet transfer has been successfully processed on the FIXPAY system.</p>
                    <p><b>User:</b> {username}</p>
                    <p><b>Amount:</b> ₹{amount}</p>
                    <p><b>From Wallet:</b> Balance Account</p>
                    <p><b>To Wallet:</b> Service Account</p>
                    <p><b>Timestamp:</b> {timestamp}</p>
                    <hr>
                    <h3>📊 Wallet Balances</h3>
                    <p><b>Service Account Balance:</b> ₹{total_balance}</p>
                    <h3>🏦 BBPS Deposit Balance</h3>
                    <p><b>BBPS Amount:</b> ₹{bbps_balance}</p>
                    <div class="footer">
                        <p>This is an automated alert from FIXPAY Wallet System. For any queries, please contact our support team.</p>
                    </div>
                </div>
            </body>
            </html>
        """
    elif "Retailer Wallet Balance Update" in subject:
        html_content = f"""  
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
                <p>The retailer <strong>{username}</strong> ({username}, {dba_name}) has successfully used the <strong>{service_name}</strong> service.</p>
                <p>The current wallet balance is: <span class="balance">{wallet_current}</span></p>
                <p>The current BBPS balance is: <span class="balance">{bbps_balance}</span></p>
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
    elif "Payment Settlement Successful" in subject:
        html_content = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background-color: #f0f4f8;
                        padding: 20px;
                        margin: 0;
                    }}
                    .container {{
                        background-color: #ffffff;
                        border-radius: 12px;
                        padding: 30px;
                        max-width: 600px;
                        margin: 0 auto;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    }}
                    .header {{
                        text-align: center;
                        padding-bottom: 20px;
                        border-bottom: 3px solid #28a745;
                    }}
                    .header h2 {{
                        color: #28a745;
                        margin: 0;
                        font-size: 24px;
                    }}
                    .success-icon {{
                        font-size: 50px;
                        color: #28a745;
                        margin: 20px 0;
                    }}
                    .info-box {{
                        background-color: #f8f9fa;
                        border-left: 4px solid #28a745;
                        padding: 15px;
                        margin: 20px 0;
                        border-radius: 5px;
                    }}
                    .info-row {{
                        display: flex;
                        justify-content: space-between;
                        padding: 8px 0;
                        border-bottom: 1px solid #e9ecef;
                    }}
                    .info-row:last-child {{
                        border-bottom: none;
                    }}
                    .info-label {{
                        color: #6c757d;
                        font-weight: 500;
                    }}
                    .info-value {{
                        color: #212529;
                        font-weight: 600;
                    }}
                    .amount {{
                        font-size: 28px;
                        color: #28a745;
                        font-weight: bold;
                        text-align: center;
                        margin: 20px 0;
                    }}
                    .message {{
                        background-color: #e7f5e9;
                        padding: 15px;
                        border-radius: 8px;
                        color: #155724;
                        margin: 20px 0;
                        text-align: center;
                    }}
                    .footer {{
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 2px solid #e9ecef;
                        font-size: 0.85em;
                        color: #6c757d;
                        text-align: center;
                    }}
                    .contact {{
                        margin-top: 15px;
                        padding: 10px;
                        background-color: #fff3cd;
                        border-radius: 5px;
                        color: #856404;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="success-icon">✓</div>
                        <h2>Payment Settlement Successful</h2>
                    </div>
                    
                    <p style="margin-top: 20px; font-size: 16px;">Dear <strong>{username}</strong>,</p>
                    
                    <div class="message">
                        <p style="margin: 0; font-size: 16px;">Your payment has been settled successfully!</p>
                    </div>
                    
                    <div class="amount">₹ {amount}</div>
                    
                    <div class="info-box">
                        <div class="info-row">
                            <span class="info-label">User ID:</span>
                            <span class="info-value">{username}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Settlement Amount:</span>
                            <span class="info-value">₹ {amount}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Settlement Date:</span>
                            <span class="info-value">{timestamp}</span>
                        </div>
                    </div>
                    
                    <p style="color: #495057; line-height: 1.6;">
                        {message}
                    </p>
                    
                    
                    
                    <div class="footer">
                        <p><strong>FIXPAY SERVE PRIVATE LIMITED</strong></p>
                        <p style="margin: 5px 0;">This is an automated email. Please do not reply to this message.</p>
                        <p style="margin: 5px 0; color: #28a745;">Thank you for choosing FIXPAY!</p>
                    </div>
                </div>
            </body>
            </html>
        """
    elif "Bill Payment Successful" in subject:
        html_content = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background-color: #f0f4f8;
                        padding: 20px;
                        margin: 0;
                    }}
                    .container {{
                        background-color: #ffffff;
                        border-radius: 12px;
                        padding: 30px;
                        max-width: 600px;
                        margin: 0 auto;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    }}
                    .header {{
                        text-align: center;
                        padding-bottom: 20px;
                        border-bottom: 3px solid #28a745;
                    }}
                    .header h2 {{
                        color: #28a745;
                        margin: 0;
                        font-size: 24px;
                    }}
                    .success-icon {{
                        font-size: 50px;
                        color: #28a745;
                        margin: 20px 0;
                    }}
                    .info-box {{
                        background-color: #f8f9fa;
                        border-left: 4px solid #28a745;
                        padding: 15px;
                        margin: 20px 0;
                        border-radius: 5px;
                    }}
                    .info-row {{
                        display: flex;
                        justify-content: space-between;
                        padding: 8px 0;
                        border-bottom: 1px solid #e9ecef;
                    }}
                    .info-row:last-child {{
                        border-bottom: none;
                    }}
                    .info-label {{
                        color: #6c757d;
                        font-weight: 500;
                    }}
                    .info-value {{
                        color: #212529;
                        font-weight: 600;
                    }}
                    .amount {{
                        font-size: 28px;
                        color: #28a745;
                        font-weight: bold;
                        text-align: center;
                        margin: 20px 0;
                    }}
                    .message {{
                        background-color: #e7f5e9;
                        padding: 15px;
                        border-radius: 8px;
                        color: #155724;
                        margin: 20px 0;
                        text-align: center;
                    }}
                    .footer {{
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 2px solid #e9ecef;
                        font-size: 0.85em;
                        color: #6c757d;
                        text-align: center;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="success-icon">✓</div>
                        <h2>Bill Payment Successful</h2>
                    </div>
                    
                    <p style="margin-top: 20px; font-size: 16px;">Dear <strong>{name or username}</strong>,</p>
                    
                    <div class="message">
                        <p style="margin: 0; font-size: 16px;">Your bill payment has been processed successfully!</p>
                    </div>
                    
                    <div class="amount">₹ {amount}</div>
                    
                    <div class="info-box">
                        <div class="info-row">
                            <span class="info-label">Service:</span>
                            <span class="info-value">{service_name}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Transaction ID:</span>
                            <span class="info-value">{username}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Amount Paid:</span>
                            <span class="info-value">₹ {amount}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Payment Date:</span>
                            <span class="info-value">{timestamp}</span>
                        </div>
                    </div>
                    
                    <p style="color: #495057; line-height: 1.6;">
                        Thank you for using FIXPAY services. Your payment has been successfully processed and credited to the biller.
                    </p>
                    
                    <div class="footer">
                        <p><strong>FIXPAY SERVE PRIVATE LIMITED</strong></p>
                        <p style="margin: 5px 0;">This is an automated email. Please do not reply to this message.</p>
                        <p style="margin: 5px 0;">For support, contact us at <strong>(+91) 99999 99999</strong></p>
                    </div>
                </div>
            </body>
            </html>
        """
    elif "Daily Login Reminder" in subject:
        html_content = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        background-color: #f4f7f9;
                        padding: 20px;
                        margin: 0;
                    }}
                    .container {{
                        background-color: #ffffff;
                        border-radius: 10px;
                        padding: 30px;
                        max-width: 800px;
                        margin: 0 auto;
                        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                    }}
                    .header {{
                        text-align: center;
                        padding-bottom: 20px;
                        border-bottom: 3px solid #007bff;
                        margin-bottom: 30px;
                    }}
                    .header h2 {{
                        color: #007bff;
                        margin: 0;
                        font-size: 26px;
                    }}
                    .info-box {{
                        background-color: #f8f9fa;
                        border-left: 4px solid #007bff;
                        padding: 15px;
                        margin: 20px 0;
                        border-radius: 5px;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin: 20px 0;
                    }}
                    th {{
                        background-color: #007bff;
                        color: white;
                        padding: 12px;
                        text-align: left;
                        border: 1px solid #ddd;
                    }}
                    td {{
                        border: 1px solid #ddd;
                        padding: 10px;
                    }}
                    .footer {{
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 2px solid #e9ecef;
                        font-size: 0.85em;
                        color: #6c757d;
                        text-align: center;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>🔔 Daily Login Reminder</h2>
                        <p style="color: #666; margin: 5px 0;">Security Alert for Your Retailers</p>
                    </div>
                    
                    <p style="font-size: 16px;">Dear,</p>
                    <p style="color: #555;">Date: <strong>{timestamp}</strong></p>
                    
                    <div class="info-box">
                        <p style="margin: 5px 0;">This is your daily security reminder for retailers under your hierarchy.</p>
                    </div>
                    
                    {message}
                    
                    <div class="footer">
                        <p><strong>FIXPAY SERVE PRIVATE LIMITED</strong></p>
                        <p style="margin: 5px 0;">This is an automated email. Please do not reply to this message.</p>
                        <p style="margin: 5px 0;">For support, contact us at <strong>(+91) 99999 99999</strong></p>
                    </div>
                </div>
            </body>
            </html>
        """
    else:
        html_content = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        background-color: #f9f9f9;
                        padding: 20px;
                    }}
                    .container {{
                        background-color: #ffffff;
                        border-radius: 8px;
                        padding: 20px;
                        box-shadow: 0 0 10px rgba(0, 0, 0, 0.05);
                    }}
                    h2 {{
                        color: #333333;
                        font-size: 18px;
                    }}
                    p {{
                        color: #555555;
                        font-size: 14px;
                    }}
                    .footer {{
                        margin-top: 30px;
                        font-size: 0.8em;
                        color: #888888;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <p>{subject}</p>
                    <p>{message}</p>
                    <p>If you have any queries or concerns, please reach out to our support team.</p>
                    <p>Regards,<br><strong>FIXPAY SERVE PRIVATE LIMITED</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated email. Please do not reply.</p>
                </div>
            </body>
            </html>
        """
    return html_content
    

@csrf_exempt
@api_view(['POST'])
def SendEmailView(request):
    subject = request.data.get("subject",'OTP')
    recipient_list = request.data.get("recipient_list")
    if isinstance(recipient_list, str):
        try:
            recipient_list = json.loads(recipient_list)  # convert JSON string to list
        except json.JSONDecodeError:
            recipient_list = [recipient_list]  # single string to list

    to_emails = ", ".join(recipient_list)  # comma-separated string for Zoho

    otp = request.data.get("otp")
    role = request.data.get("role")
    username = request.data.get("username")
    password = request.data.get("password")
    name = request.data.get("name")

    amount = request.data.get("amount")
    timestamp = request.data.get("timestamp")
    total_balance = request.data.get("total_balance")
    bbps_balance = request.data.get("bbps_balance")
    wallet_current = request.data.get("wallet_current")
    service_name = request.data.get("service_name")
    dba_name = request.data.get("dba_name")
    message = request.data.get("message")


    send_email_status = html_send_email(
        subject,
        recipient_list,
        role=role,
        otp=otp,
        username=username,
        password=password,
        name=name,
        amount=amount,
        timestamp=timestamp,
        total_balance=total_balance,
        bbps_balance=bbps_balance,
        wallet_current=wallet_current,
        service_name=service_name,
        dba_name=dba_name,
        message=message

    )
    content = send_email_status

    try:
        success = zoho_send_email(to_emails, subject, content)

        if success:
            return JsonResponse({"status": "success", "message": "Email sent successfully"})
        else:
            return JsonResponse({"status": "error", "message": "Failed to send email"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})



@api_view(['GET'])
def check_in_register_parent(request):
    parent_id = request.GET.get('parent_id')
    if not parent_id:
        return Response({
            'status': 'error',
            'message': 'Distributor Id parameter is required.',
            'data': None
        }, status=400)
    try:
        check_parent = PortalUser.objects.get(username=parent_id)
    except PortalUser.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Distributor not found.',
            'data': None
        }, status=404)
    return Response({
        'status': 'success',
        'message': 'Distributor is correct.',
        'data': check_parent.pu_name
    })


from django.utils.dateformat import format
from django.utils.timezone import is_aware, make_naive

from django.template.loader import render_to_string
from xhtml2pdf import pisa
from django.core.files.base import ContentFile
from django.conf import settings
import os



def serialize_datetime(dt):
    if not dt:
        return None
    # convert aware datetime to naive UTC
    if is_aware(dt):
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat() + "Z"  # ISO8601 UTC format

class AdminDocumentApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request):
        user_id = request.query_params.get('user_id')  # GET param
        
        if not user_id:
            return Response(
                {'status': 'fail', 'message': 'User ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = PortalUser.objects.get(id=user_id, is_deleted=False)
            details = PortalUserDetails.objects.filter(pu=user).first()

            if not details:
                return Response(
                    {'status': 'fail', 'message': 'No business details found for this user.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            image_urls = {
                key: get_full_image_url(request, value)
                for key, value in details.doc_images.items()
            } if details.doc_images else None
            
            # Generate Declaration PDF
            context = {
                'user': {
                    'id': user.username,
                    'name': user.pu_role,
                }
            }
            pdf_url = generate_pdf_from_template(
                'user_declaration.html',
                context,
                output_filename=f'declaration_user_{user.id}.pdf'
            )
            
            # Document approval statuses (with fallback to Pending)
            document_statuses = {
                "onboarding": getattr(details, "upload_status", "Pending"),
                "security_cheque": getattr(details, "security_upload_status", "Pending"),
                "declaration": getattr(details, "pdf_upload_status", "Pending"),
            }
            document_comments = {
            "onboarding": details.onboarding_cheque_comment or "",
            "security_cheque": details.security_cheque_comment or "",
            "declaration": details.declaration_pdf_comment or "",
        }
            
            # Uploaded timestamps you want to add
            uploaded_times = {
                "onboarding_cheque_uploaded_at": details.onboarding_cheque_uploaded_at.isoformat() if details.onboarding_cheque_uploaded_at else None,
                "security_cheque_uploaded_at": details.security_cheque_uploaded_at.isoformat() if details.security_cheque_uploaded_at else None,
                "declaration_pdf_uploaded_at": details.declaration_pdf_uploaded_at.isoformat() if details.declaration_pdf_uploaded_at else None,
            }


            data = {
                'shop_name': details.shop_name,
                'shop_address': details.shop_address,
                'shop_gst_number': details.shop_gst_number,
                'shop_images': image_urls,
                'declaration_pdf_url': request.build_absolute_uri(pdf_url) if pdf_url else None,
                'document_statuses': document_statuses,
                'uploaded_times': uploaded_times,
                'document_comments': document_comments,  # <-- comments added here
                'onboarding_check_num':details.onboarding_check_num,
                'security_check_num':details.security_check_num,

            }

            print(data)

            return Response({
                'status': 'success',
                'message': 'Business details fetched successfully.',
                'data': data
            }, status=status.HTTP_200_OK)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            return Response(
                {'status': 'error', 'message': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        user_id = request.data.get('user_id')
        document_key = request.data.get('document_key')
        new_status = request.data.get('new_status')
        comment = request.data.get('comment', '').strip()  # get comment, default empty

        if not user_id or not document_key or not new_status:
            return Response(
                {'status': 'fail', 'message': 'user_id, document_key and new_status are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if document_key not in ["onboarding", "security_cheque", "declaration"]:
            return Response(
                {'status': 'fail', 'message': 'Invalid document_key.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status not in ["waiting", "in_review", "approved", "rejected"]:
            return Response(
                {'status': 'fail', 'message': 'Invalid new_status.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = PortalUser.objects.get(id=user_id, is_deleted=False)
            details = PortalUserDetails.objects.filter(pu=user).first()

            if not details:
                return Response(
                    {'status': 'fail', 'message': 'No business details found for this user.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Map document keys to status and comment fields on PortalUserDetails model
            status_field_map = {
                "onboarding": "upload_status",
                "security_cheque": "security_upload_status",
                "declaration": "pdf_upload_status",
            }

            comment_field_map = {
                "onboarding": "onboarding_cheque_comment",
                "security_cheque": "security_cheque_comment",
                "declaration": "declaration_pdf_comment",
            }

            # Update status
            setattr(details, status_field_map[document_key], new_status)

            # Save comment only if provided
            if comment:
                setattr(details, comment_field_map[document_key], comment)

            details.save()

            return Response({
                'status': 'success',
                'message': f'{document_key} status updated to {new_status} and comment saved.'
            }, status=status.HTTP_200_OK)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            return Response(
                {'status': 'error', 'message': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

from django.utils import timezone

class RetailerDocumentsUploadAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]

    def post(self, request):
        onboarding_cheque_image = request.FILES.get('onboarding_fee_cheque')
        security_cheque = request.FILES.get('security_cheque')
        declaration_pdf = request.FILES.get('signed_declaration_pdf')

        if not any([onboarding_cheque_image, security_cheque, declaration_pdf]):
            return Response(
                {'status': 'fail', 'message': 'At least one document must be uploaded.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = PortalUser.objects.get(id=request.user.id, is_deleted=False)
            p = PortalUserDetails.objects.get(pu=user)

            doc_images = p.doc_images or {}
            uploaded_files = []
            skipped_files = []

            now = timezone.now()

            # Check and upload onboarding cheque
            if onboarding_cheque_image:
                if p.upload_status in ['approved', 'in_review']:
                    skipped_files.append('onboarding_cheque_image (already submitted)')
                else:
                    doc_images['onboarding_cheque_image'] = handle_uploaded_file(onboarding_cheque_image, 'onboarding_cheque_image',user.username)
                    uploaded_files.append('onboarding_cheque_image')
                    p.onboarding_cheque_uploaded_at = now  # update timestamp

            # Check and upload security cheque
            if security_cheque:
                if p.security_upload_status in ['approved', 'in_review']:
                    skipped_files.append('security_cheque (already submitted)')
                else:
                    doc_images['security_cheque'] = handle_uploaded_file(security_cheque, 'security_cheque',user.username)
                    uploaded_files.append('security_cheque')
                    p.security_cheque_uploaded_at = now  # update timestamp

            # Check and upload declaration PDF
            if declaration_pdf:
                if p.pdf_upload_status in ['approved', 'in_review']:
                    skipped_files.append('declaration_pdf (already submitted)')
                else:
                    doc_images['declaration_pdf'] = handle_uploaded_file(declaration_pdf, 'declaration_pdf',user.username)
                    uploaded_files.append('declaration_pdf')
                    p.declaration_pdf_uploaded_at = now  # update timestamp
                    # As per your comment, do not update p.pdf_upload_status here

            # Save if anything was uploaded
            if uploaded_files:
                p.doc_images = doc_images
                p.save()

            message = ''
            if uploaded_files:
                message += f"Uploaded successfully: {', '.join(uploaded_files)}. "
            if skipped_files:
                message += f"Skipped: {', '.join(skipped_files)}."

            return Response({
                'status': 'success' if uploaded_files else 'fail',
                'message': message.strip(),
                'uploaded_files': uploaded_files,
                'skipped_files': skipped_files,
            }, status=status.HTTP_200_OK if uploaded_files else status.HTTP_400_BAD_REQUEST)

        except PortalUserDetails.DoesNotExist:
            return Response(
                {'status': 'fail', 'message': 'Business details not found. Please add business info first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'status': 'error', 'message': f'Error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UpdateUploadStatusAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]

    def post(self, request):
        status_param = request.data.get("status")

        try:
            user = PortalUser.objects.get(id=request.user.id, is_deleted=False)
            p = PortalUserDetails.objects.get(pu=user)

            if status_param in ['in_review', 'approved', 'rejected','pending']:
                p.upload_status = status_param
                p.security_upload_status = status_param
                p.pdf_upload_status = status_param
                p.save()
                return Response({"status": "success", "message": f"Status updated to {status_param}"})
            else:
                return Response({"status": "fail", "message": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)

        except PortalUserDetails.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Business details not found.'},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Re-Active the Retailer Account From Admin -------------------
class MaintainRetailerStatusApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        try:
            if 'user_id' in request.data:
                return self.activate_retailer(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def activate_retailer(self, request):
        user_id = request.data.get('user_id')
        user = get_object_or_404(PortalUser, id=user_id, pu_role='RETAILER')

        if user.is_deactive:
            user.is_deactive = False
            user.pu_status = 'APPROVED'
            user.save(update_fields=['is_deactive','pu_status'])

            
            last_log = PortalUserLoginLogs.objects.filter(pu_user=user).order_by('-created_at').first()
            if last_log:
                last_log.created_at = timezone.now()
                last_log.save(update_fields=['created_at'])

            return Response({
                'status': 'success',
                'message': 'Retailer account reactivated successfully.'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': 'info',
                'message': 'Retailer account is already active.'
            }, status=status.HTTP_200_OK)



class TerminalsApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsAdmin | IsRetailer]
    parser_classes = (MultiPartParser, FormParser)
    def post(self, request):
        print(request.data,'==========================================>request.data')
        try:
            if 'terminal_id' in request.data and 'action' in request.data:
                return self.toggle_terminal_status(request)
            elif 'terminal_id' in request.data and 'terminal_expiry' in request.data:
                return self.update_terminal_expiry(request)
            elif 'terminal_id' in request.data:
                return self.terminal_history(request)
            elif ('page_number' in request.data and 'page_size' in request.data) or 'request_user_id' in request.data:
                return self.fetch_pos_devices(request)
            else:
                return Response({'status': 'error', 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            response_data = {
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def fetch_pos_devices(self, request):
        user_id = request.user.id
        try:
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search = request.data.get('search', None)
            retailer_id = request.data.get('retailer_id', None)
            start_date = request.data.get('start_date', None)
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            pos_devices = PosDevice.objects.filter(is_deleted=False).order_by('-pk')

            if request.user.pu_role != "ADMIN":
                # Non-admin users see only their own created devices
                pos_devices = pos_devices.filter(created_by=user_id)

            if retailer_id:
                pos_devices = pos_devices.filter(pu__id=retailer_id)

            if search:
                search = search.strip()
                pos_devices = pos_devices.filter(
                    Q(terminal__icontains=search) |
                    Q(pu__username__icontains=search) |
                    Q(pu__pu_name__icontains=search)
                )

            if start_date:
                pos_devices = pos_devices.filter(created_at__date__range=[start_date, end_date])

            paginator = Paginator(pos_devices, page_size)
            page_obj = paginator.page(page_number)

            devices_data = []
            for device in page_obj:
                user = device.pu
                business_name = (
                    PortalUserDetails.objects.filter(pu=user).values_list('shop_name', flat=True).first()
                    if user else None
                )
                device_status = 'Deactive' if device.is_deactive else 'Active'

                print(business_name, '=>                             -------business name ')

                devices_data.append({
                    "id": device.pos_d_id,
                    "terminal": device.terminal,
                    "status": device_status,
                    "is_deactive": device.is_deactive,
                    "created_at": device.created_at,
                    "expire_t": device.is_expires_at or None,

                    "retailer": {
                        'user_id':user.id if user else None,
                        "id": user.username if user else None,
                        "name": user.pu_name if user else None,
                        "business_name": business_name,
                    },
                    "service_provider": {
                        "id": device.sp.id if device.sp else None,
                        "name": getattr(device.sp, 'name', None),
                    }
                })



            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': devices_data
            }

            return Response({'status': 'success', 'message': 'POS Device Data', 'data': paginated_response_data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e), '---- fetch_pos_devices error')
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def toggle_terminal_status(self, request):
        try:
            terminal_id = request.data.get('terminal_id')
            action = request.data.get('action')
            print(terminal_id, action, '=========> terminal_id and action')

            device = PosDevice.objects.filter(terminal=terminal_id, is_deleted=False).first()
            print(device, '=========> device')

            if not device:
                return Response({'status': 'error', 'message': 'Terminal not found'}, status=status.HTTP_404_NOT_FOUND)

            if action not in ['activate', 'deactivate']:
                return Response({'status': 'error', 'message': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                if action == 'activate':
                    device.is_deactive = False
                    history_action = 'activated'
                else:
                    device.is_deactive = True
                    history_action = 'deactivated'

                device.save()

                
                TerminalRetailerHistory.objects.create(
                    terminal=device,
                    action=history_action,
                    performed_by=request.user,
                    remarks=f"Terminal {history_action} by user ID {request.user.id}"
                )

            return Response({'status': 'success', 'message': f'Terminal {action}d successfully.'}, status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e), '=========> str(e)')
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def terminal_history(self, request):
        try:
            terminal_id = request.data.get('terminal_id')
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search = request.data.get('search', None)

            device = PosDevice.objects.filter(terminal=terminal_id, is_deleted=False).first()
            if not device:
                return Response({'status': 'error', 'message': 'Terminal not found'}, status=status.HTTP_404_NOT_FOUND)

            history_qs = TerminalRetailerHistory.objects.filter(terminal=device).order_by('-timestamp')
            if search:
                search = search.strip()
                if search.isdigit():
                    history_qs = history_qs.filter(
                        Q(action__icontains=search) |
                        Q(remarks__icontains=search) |
                        Q(performed_by__username__icontains=search) |
                        Q(terminal_h_id=int(search))  # Exact match if numeric
                    )
                else:
                    history_qs = history_qs.filter(
                        Q(action__icontains=search) |
                        Q(remarks__icontains=search) |
                        Q(performed_by__username__icontains=search)
                    )

            paginator = Paginator(history_qs, page_size)
            page_obj = paginator.get_page(page_number)

            history_data = []
            for terminal_h in page_obj:
                history_data.append({
                    'terminal_hid': terminal_h.terminal_h_id,
                    'action': terminal_h.action,
                    'created_by': terminal_h.performed_by.username if terminal_h.performed_by else None,
                    'remarks': terminal_h.remarks,
                    'timestamp': terminal_h.timestamp.strftime('%Y-%m-%d %I:%M:%S %p'),
                })

            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': history_data
            }

            return Response({
                'status': 'success',
                'message': 'Terminal History Data',
                'data': paginated_response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e),'+++++>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>error')
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def update_terminal_expiry(self, request):

        try:
            terminal_id = request.data.get("terminal_id")
            terminal_expiry = request.data.get("terminal_expiry")

            if not terminal_id or not terminal_expiry:
                return Response({"status": "error", "message": "Missing terminal_id or terminal_expiry"},
                                status=status.HTTP_400_BAD_REQUEST)

            device = PosDevice.objects.filter(terminal=terminal_id, is_deleted=False).first()
            if not device:
                return Response({"status": "error", "message": "Terminal not found"}, status=status.HTTP_404_NOT_FOUND)

            # Convert string to datetime

            with transaction.atomic():
                device.is_expires_at = terminal_expiry
                device.save()

                TerminalRetailerHistory.objects.create(
                    terminal=device,
                    action='expiry_updated',
                    performed_by=request.user,
                    remarks=f"Terminal expiry updated to {terminal_expiry} by user ID {request.user.id}"
                )

            return Response({"status": "success", "message": "Terminal expiry updated successfully."},
                            status=status.HTTP_200_OK)

        except Exception as e:
            print(str(e), '=========> expiry update error')
            return Response({"status": "error", "message": f"Internal server error: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import traceback
    
import json
from django.views import View
from django.http import JsonResponse
from django.db.models import Q
from .models import PortalUser, BulkMessageLog
from django.utils.decorators import method_decorator
@method_decorator(csrf_exempt, name='dispatch')
class BulkMessageView(View):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]
    parser_classes = (MultiPartParser, FormParser)

    
    prefix_role_map = {
        "SD": "Super Distributor",
        "MD": "Master Distributor",
        "DT": "Distributor",
        "RT": "Retailer",
    }
    reverse_prefix_map = {v: k for k, v in prefix_role_map.items()}


    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            roles = data.get('roles', {})
            to_list = data.get('to', '')
            exclude_list = data.get('exclude', '')
            subject = data.get('subject', '')
            message = data.get('message', '')
            send_type = data.get('sendType', '').lower()


            if (not roles and not to_list.strip()) or not subject.strip() or not message.strip():
                return JsonResponse({
                    "status": "error",
                    "message": "Please provide recipients (roles or to list), subject, and message."
                }, status=400)

            q_filter = Q()

            if roles:
                for role_full_name, state in roles.items():
                    prefix = self.reverse_prefix_map.get(role_full_name)
                    if not prefix:
                        continue
                    
                    if state == "all":
                        q_filter |= Q(username__startswith=prefix)
                    elif state == "active":
                        q_filter |= Q(username__startswith=prefix, is_deactive=False)
                    elif state == "deactive":
                        q_filter |= Q(username__startswith=prefix, is_deactive=True)
                
                q_filter &= Q(is_deleted=False)
                users_by_roles = PortalUser.objects.filter(q_filter)
            else:
                users_by_roles = PortalUser.objects.none()

            to_usernames = set()
            if to_list.strip():
                to_usernames = set(u.strip() for u in to_list.split(",") if u.strip())

            role_usernames = set(users_by_roles.values_list('username', flat=True))
            combined_usernames = role_usernames.union(to_usernames)

            exclude_usernames = set()
            if exclude_list.strip():
                exclude_usernames = set(u.strip() for u in exclude_list.split(",") if u.strip())

            final_usernames = combined_usernames - exclude_usernames

            final_users = PortalUser.objects.filter(
                username__in=final_usernames,
            )

            # Send mail or SMS
            if send_type == "mail":
                result = self.send_bulk_mail(final_users, subject, message)
            elif send_type == "sms":
                result = self.send_bulk_sms(final_users, message)
            else:
                return JsonResponse({"status": "error", "message": "Invalid sendType"}, status=400)

            return JsonResponse({"status": "success", "message": result})

        except Exception as e:
            # Write full traceback and error message to file for debugging
            with open('bulk_error.txt', 'a') as f:
                f.write(f"\n[ERROR] {str(e)}\n")
                f.write(traceback.format_exc())
                f.write("\n\n")

            # Also optionally log to console
            print(f"Exception in BulkMessageView.post: {e}")
            traceback.print_exc()

            return JsonResponse({"status": "error", "message": "Internal Server Error"}, status=500)


    # def post(self, request, *args, **kwargs):
    #     data = json.loads(request.body)
    #     roles = data.get('roles', {})
    #     to_list = data.get('to', '')
    #     exclude_list = data.get('exclude', '')
    #     subject = data.get('subject', '')
    #     message = data.get('message', '')
    #     send_type = data.get('sendType', '').lower()
    #     with open('bulk_error.txt','a') as f:
    #         f.write(data)


    #     if (not roles and not to_list.strip()) or not subject.strip() or not message.strip():
    #         return JsonResponse({
    #             "status": "error",
    #             "message": "Please provide recipients (roles or to list), subject, and message."
    #         }, status=400)



    #     print(data,'==============================>>>>>>>>>>>>>>>>>>>> request.data')

    #     q_filter = Q()

    #     if roles:
    #         for role_full_name, state in roles.items():
    #             prefix = self.reverse_prefix_map.get(role_full_name)
    #             if not prefix:
    #                 continue
                
    #             if state == "all":
    #                 q_filter |= Q(username__startswith=prefix)
    #             elif state == "active":
    #                 q_filter |= Q(username__startswith=prefix, is_deactive=False)
    #             elif state == "deactive":
    #                 q_filter |= Q(username__startswith=prefix, is_deactive=True)
            
    #         q_filter &= Q(is_deleted=False)
    #         users_by_roles = PortalUser.objects.filter(q_filter)
    #     else:
    #         users_by_roles = PortalUser.objects.none()

    #     to_usernames = set()
    #     if to_list.strip():
    #         to_usernames = set(u.strip() for u in to_list.split(",") if u.strip())

    #     role_usernames = set(users_by_roles.values_list('username', flat=True))
    #     combined_usernames = role_usernames.union(to_usernames)

    #     exclude_usernames = set()
    #     if exclude_list.strip():
    #         exclude_usernames = set(u.strip() for u in exclude_list.split(",") if u.strip())

    #     final_usernames = combined_usernames - exclude_usernames

    #     final_users = PortalUser.objects.filter(
    #         username__in=final_usernames,
    #     )



    #     # Send mail or SMS
    #     if send_type == "mail":
    #         result = self.send_bulk_mail(final_users, subject, message)
    #     elif send_type == "sms":
    #         result = self.send_bulk_sms(final_users, message)
    #     else:
    #         return JsonResponse({"status": "error", "message": "Invalid sendType"}, status=400)

    #     return JsonResponse({"status": "success", "message": result})


    def send_bulk_mail(self, users, subject, message):
        sent_to = []
        failed_to = []
        
        for user in users:
            print(f"Processing user: {user.username}, Email: {user.pu_email}")
            try:
                recipient_list = [user.pu_email]

                # Your custom email rendering function
                html_content = html_send_email(
                    subject=subject,
                    recipient_list=recipient_list,
                    message=message,
                )

                to_emails = ", ".join(recipient_list)
                success = zoho_send_email(to_emails, subject, html_content)

                if success:
                    sent_to.append(user.username)
                    print(f"Email sent to {user.username} ({user.pu_email})")

                    BulkMessageLog.objects.create(
                        user=user,
                        message_type='mail',
                        subject=subject,
                        message=message,
                    )
                else:
                    failed_to.append(user.username)
                    print(f"Failed to send mail to {user.username} ({user.pu_email})")

            except Exception as e:
                failed_to.append(user.username)
                print(f"Exception while sending to {user.username} ({user.pu_email}): {e}")


        return f"Mail sent to {len(sent_to)} users. Failed for {len(failed_to)} users."



    # def send_bulk_sms(self, users, message):
    #     sent_to = []
    #     for user in users:
    #         try:
    #             send_sms(user.pu_contact_no, message)
    #             sent_to.append(user.username)

    #             BulkMessageLog.objects.create(
    #                 user=user,
    #                 message_type='sms',
    #                 message=message
    #             )
    #         except Exception as e:
    #             print(f"Failed to send SMS to {user.pu_contact_no}: {e}")

    #     return f"SMS sent to {len(sent_to)} users."




def fetch_card_details(request):
    mobile = request.GET.get("mobile")
    if not mobile:
        return JsonResponse([], safe=False)

    records = PgServiceTrn.objects.filter(buyer_phone=mobile).values(
        'buyer_firstname', 'buyer_lastname', 'credit_card_num', 'trn_response'
    )

    result = []
    seen = set()

    for record in records:
        card_number = record.get('credit_card_num') or record['trn_response'].get('cardnumber', '')
        card_number = str(card_number).strip()

        full_name = f"{record['buyer_firstname']} {record['buyer_lastname']}".strip()
        unique_key = (card_number, full_name)

        if card_number and unique_key not in seen:
            seen.add(unique_key)
            result.append({
                "cardNumber": card_number,
                "customerName": full_name
            })

    return JsonResponse(result, safe=False)




def check_ifsc(request):
    if request.method == "GET":
        ifsc = request.GET.get("ifsc")
        if not ifsc:
            return JsonResponse({"error": "IFSC code is required"}, status=400)

        full_response = verify_ifsc(ifsc)

        try:
            data = full_response.content.decode("utf-8")
            import json
            parsed = json.loads(data)
            if "bank" in parsed:
                return JsonResponse({
                    "bank": parsed.get("bank"),
                    "address": parsed.get("address"),
                    "city": parsed.get("city"),
                    "state": parsed.get("state"),
                    "branch": parsed.get("branch"),
                }, status=200)
            else:
                return JsonResponse({"error": "Bank not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

# def check_ifsc(request):
#     if request.method == "GET":
#         ifsc = request.GET.get("ifsc")
#         if not ifsc:
#             return JsonResponse({"error": "IFSC code is required"}, status=400)

#         # Call the verification API
#         full_response = verify_ifsc(ifsc)

#         # Extract JSON data
#         try:
#             data = full_response.content.decode("utf-8")
#             import json
#             parsed = json.loads(data)
#             if "bank" in parsed:
#                 return JsonResponse({"bank": parsed["bank"]}, status=200)
#             else:
#                 return JsonResponse({"error": "Bank not found"}, status=404)
#         except Exception as e:
#             return JsonResponse({"error": str(e)}, status=500)

#     return JsonResponse({"error": "Invalid request method"}, status=405)


class ChequeNumberApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer | IsDistributor]

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            index = data.get('index')
            cheque_number = data.get('cheque_number')

            if index not in [0, 1] or not cheque_number:
                return JsonResponse({'status': 'error', 'message': 'Invalid data'}, status=400)

            try:
                retailer = PortalUserDetails.objects.get(pu=request.user)
            except PortalUserDetails.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Retailer not found'}, status=404)


            has_bank = BankDetailsUser.objects.filter(created_by=request.user.id).exists()
            if not has_bank:
                return JsonResponse({'status': 'error', 'message': 'bank account not available .please add.'}, status=400)

            # Determine which field to check and update
            if index == 0:
                was_empty = not retailer.onboarding_check_num
                retailer.onboarding_check_num = cheque_number
            elif index == 1:
                was_empty = not retailer.security_check_num
                retailer.security_check_num = cheque_number

            retailer.save()
            action = 'added' if was_empty else 'updated'
            return JsonResponse({'status': 'success', 'message': f'Cheque number {action} successfully'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



class DistributorLedgerApiView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor]

    def post(self, request):
        print(request.data,'+++++++++++++++++++++++++++++++++++++++++++++++++++>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
        try:
            if 'from_id' in request.data and  'from_wallet' in request.data and 'amount' in request.data:
                print('if')
                return self.wallet_to_wallet(request)
            elif 'contact_no' in request.data and 'amount' in request.data and 'from_wallet' in request.data:
                print('if1')
                return self.wallet_to_other_wallet(request)
            else:
                return Response({'status': 'fail', 'message': 'Invalid request data.'},
                                status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def wallet_to_wallet(self, request):
        try:
            from_id = request.data.get('from_id')
            updated_to_wallet = request.data.get('updated_to_wallet')
            from_wallet = request.data.get('from_wallet')
            description = request.data.get('description', None)
            amount = request.data.get('amount')
            
            to_wallet = 'main_wallet'  

            if updated_to_wallet == 'cashin_wallet':
                to_wallet = 'cashin_wallet'
            
            main_wallet = 'main_wallet'

            # Validate required parameters
            if not from_wallet:
                return Response({'status': 'fail', 'message': 'from_wallet is required.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not amount:
                return Response({'status': 'fail', 'message': 'amount is required.'},
                                status=status.HTTP_400_BAD_REQUEST)


            from_wallet_validation = isstring(from_wallet)
            if from_wallet_validation == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid from wallet. It should contain only alphabetic characters.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if from_wallet not in ['cashin_wallet', 'pg_wallet']:
                return Response({'status': 'fail',
                                 'message': 'Invalid wallet name. Please choose from cashin_wallet or pg_wallet.'},
                                status=status.HTTP_400_BAD_REQUEST)

            amount = decimal.Decimal(amount)

            get_user = PortalUser.objects.get(id=from_id)

            if main_wallet == to_wallet or main_wallet == from_wallet or to_wallet == 'cashin_wallet':
                
                if main_wallet == to_wallet and main_wallet == from_wallet:
                    return Response(
                        {'status': 'fail', 'message': f'Either from_wallet and to_wallet must be {main_wallet}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                # If transferring from 'pg_wallet' to 'cashin_wallet'
                if from_wallet == 'pg_wallet' and to_wallet == 'cashin_wallet':
                    print('----------------------5300')
                    user = get_user.id
                    retailer = PortalUser.objects.get(id=user, is_deleted=False)
                    retailer_details = PortalUserDetails.objects.get(pu=retailer)
                    user_wallet = PortalUserWallet.objects.get(pu=retailer)

                    if getattr(user_wallet, from_wallet) < amount:
                        return Response(
                            {'status': 'fail', 'message': f'Insufficient funds in {from_wallet}.', 'is_success': True},
                            status=status.HTTP_400_BAD_REQUEST)

                    # Debit from pg_wallet and Credit to cashin_wallet
                    setattr(user_wallet, from_wallet, getattr(user_wallet, from_wallet) - amount)
                    setattr(user_wallet, to_wallet, getattr(user_wallet, to_wallet) + amount)

                    user_wallet.save()

                    # Prepare transaction labels
                    from_wallet_name = 'Balance Account'
                    to_wallet_name = 'Cash Account'
                    main_wallet_name = 'Service Account'
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    from_label = f'{retailer_details.pud_unique_id}_DR_Internal{from_wallet_name}To{to_wallet_name}_{timestamp}'
                    to_label = f'{retailer_details.pud_unique_id}_CR_Internal{from_wallet_name}To{to_wallet_name}_{timestamp}'

                    # Record the transactions
                    wallet_transaction = {'CR': [to_wallet, to_label], 'DR': [from_wallet, from_label]}
                    for key, value in wallet_transaction.items():
                        global_transaction = GlTrn.objects.create(
                            pu=retailer,
                            effectvie_wallet=value[0],
                            effectvie_amt=amount,
                            effective_type=key,
                            service_trn_table='ad_wallet_trnasaction',
                            gl_trn_dt=timezone.now()
                        )

                        WalletTrn.objects.create(
                            action_id=global_transaction.gl_trn_id,
                            action_type=f'Internal_{from_wallet}_to_{to_wallet}',
                            pu=retailer,
                            wl_label=value[1],
                            effectvie_wallet=value[0],
                            effectvie_amt=amount,
                            effective_type=key,
                            wl_trn_des=description if description else None,
                            current_balance=getattr(user_wallet, value[0]),
                            wl_trn_dt=timezone.now()
                        )

                    return Response(
                        {'status': 'success', 'message': f'{amount} transferred from {from_wallet} to {to_wallet}.',
                        'is_success': True}, status=status.HTTP_200_OK)

                # Existing functionality for transferring to main_wallet (if applicable)
                user = get_user.id
                retailer = PortalUser.objects.get(id=user, is_deleted=False)
                retailer_details = PortalUserDetails.objects.get(pu=retailer)
                user_wallet = PortalUserWallet.objects.get(pu=retailer)

                if getattr(user_wallet, from_wallet) < amount:
                    return Response(
                        {'status': 'fail', 'message': f'Insufficient funds in {from_wallet}.', 'is_success': True},
                        status=status.HTTP_400_BAD_REQUEST)

                

                setattr(user_wallet, from_wallet, getattr(user_wallet, from_wallet) - amount)
                setattr(user_wallet, to_wallet, getattr(user_wallet, to_wallet) + amount)

                user_wallet.save()
                from_wallet_name = ''
                if from_wallet == 'cashin_wallet':
                    from_wallet_name = 'Cash Account'
                elif from_wallet == 'pg_wallet':
                    from_wallet_name = 'Balance Account'
                main_wallet_name = 'Service Account'
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                from_label = f'{retailer_details.pud_unique_id}_DR_Internal{from_wallet_name}To{main_wallet_name}_{timestamp}'
                to_label = f'{retailer_details.pud_unique_id}_CR_Internal{from_wallet_name}To{main_wallet_name}_{timestamp}'
                wallet_transaction = {'CR': [main_wallet, to_label], 'DR': [from_wallet, from_label]}
                for key, value in wallet_transaction.items():
                    global_transaction = GlTrn.objects.create(
                        pu=retailer,
                        effectvie_wallet=value[0],
                        effectvie_amt=amount,
                        effective_type=key,
                        service_trn_table='ad_wallet_trnasaction',
                        gl_trn_dt=timezone.now()
                    )

                    WalletTrn.objects.create(
                        action_id=global_transaction.gl_trn_id,
                        action_type=f'Internal_{from_wallet}_to_{main_wallet}',
                        pu=retailer,
                        wl_label=value[1],
                        effectvie_wallet=value[0],
                        effectvie_amt=amount,
                        effective_type=key,
                        wl_trn_des=description if description else None,
                        current_balance=getattr(user_wallet, value[0]),
                        wl_trn_dt=timezone.now()
                    )

                total_balances = PortalUserWallet.objects.filter(
                    pu__pu_role="RETAILER",
                    pu__pu_status="APPROVED"
                ).aggregate(
                    total_main_wallet=Sum('main_wallet', default=0),
                )

                    # Fetch BBPS Deposit Balance
                bbps_balance = get_bbps_deposit_balance()


                send_email_subject = "Wallet Transfer Alert - FIXPAY"

                # Convert Decimal values to float or string before sending them
                email_data = {
                    "subject": send_email_subject,
                    "recipient_list": ["kunal@ssepl.live"],
                    "username": request.user.username,
                    "amount": float(amount),  # Convert Decimal to float
                    "timestamp": timestamp,
                    "total_balance": float(total_balances['total_main_wallet']),  # Convert Decimal to float
                    "bbps_balance": float(bbps_balance),  # Convert Decimal to float
                }



                # Sending HTTP request to Project A's API to trigger the email sending
                send_email_url = "https://qaapi.fixpay.in/admin_hub/send-email/"
                response = requests.post(send_email_url, json=email_data)

                return Response(
                    {'status': 'success', 'message': f'{amount} transferred from {from_wallet} to {to_wallet}.',
                     'is_success': True}, status=status.HTTP_200_OK)

            else:
                return Response(
                    {'status': 'fail', 'message': f'Either from_wallet or to_wallet must be {main_wallet}.'},
                    status=status.HTTP_400_BAD_REQUEST)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)
        except PortalUserWallet.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Wallet not found for the user.'},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    
    def wallet_to_other_wallet(self, request):
        try:
            contact_no = request.data.get('contact_no')
            amount = request.data.get('amount')
            from_wallet = request.data.get('from_wallet')

            if not contact_no: return Response({'status': 'fail', 'message': 'contact no is required.'},
                                               status=status.HTTP_400_BAD_REQUEST)
            if not amount: return Response({'status': 'fail', 'message': 'amount is required.'},
                                           status=status.HTTP_400_BAD_REQUEST)
            if not from_wallet: return Response({'status': 'fail', 'message': 'from wallet is required.'},
                                                status=status.HTTP_400_BAD_REQUEST)

            validation_contact_number = validate_mobile_number(contact_no)
            if validation_contact_number == False:
                return Response({'status': 'fail', 'message': 'Invalid Mobile Number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            validation_amount = isnumber(amount)
            if validation_amount == False:
                return Response({'status': 'fail', 'message': 'Invalid amount. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            from_Wallet_validation = isstring(from_wallet)
            if from_Wallet_validation == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid from wallet. It should contain only alphabetic characters.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if from_wallet not in 'main_wallet':
                return Response({'status': 'fail', 'message': 'Invalid wallet name. Please choose from main_wallet.'},
                                status=status.HTTP_400_BAD_REQUEST)

            amount = Decimal(amount)
            main_wallet = 'main_wallet'

            user = PortalUser.objects.get(id=request.user.id, is_deleted=False)
            get_user = PortalUser.objects.get(pu_contact_no=contact_no, is_deleted=False)
            to_user_details = PortalUserDetails.objects.get(pu=user)
            from_user_details = PortalUserDetails.objects.get(pu=get_user)
            if get_user.pu_role not in ['RETAILER', 'DISTRIBUTOR']:
                return Response({'status': 'fail',
                                 'message': 'Only Retailers and Distributors are authorized to perform this action.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if request.user.id == get_user.id:
                return Response({'status': 'fail',
                                 'message': 'Self-transfer is not allowed. You cannot transfer funds to your own wallet.',
                                 'is_success': True}, status=status.HTTP_400_BAD_REQUEST)

            from_user_wallet = PortalUserWallet.objects.get(pu=get_user)
            to_user_wallet = PortalUserWallet.objects.get(pu=request.user.id)
            from_wallet_balance = Decimal(getattr(to_user_wallet, from_wallet))

            if from_wallet_balance < amount:
                return Response(
                    {'status': 'fail', 'message': f'Insufficient funds in {from_wallet}.', 'is_success': True},
                    status=status.HTTP_400_BAD_REQUEST)

            setattr(from_user_wallet, main_wallet, Decimal(getattr(from_user_wallet, main_wallet)) + amount)
            setattr(to_user_wallet, from_wallet, from_wallet_balance - amount)

            from_user_wallet.save()
            to_user_wallet.save()
            from_wallet_name = ''
            if from_wallet == 'cashin_wallet':
                from_wallet_name = 'CashIn'
            elif from_wallet == 'pg_wallet':
                from_wallet_name = 'Pg'
            main_wallet_name = 'Main'

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            from_label = f'{from_user_details.pud_unique_id}_CR_{from_wallet}_Internal{from_wallet_name}To{main_wallet_name}_{timestamp}'
            to_label = f'{to_user_details.pud_unique_id}_DR_{main_wallet}_Internal{from_wallet_name}To{main_wallet_name}_{timestamp}'
            wallet_transaction = {'CR': [from_wallet, from_label], 'DR': [main_wallet, to_label]}
            for key, value in wallet_transaction.items():
                global_transaction = GlTrn.objects.create(
                    pu=user,
                    effectvie_wallet=value[0],
                    effectvie_amt=amount,
                    effective_type=key,
                    service_trn_table='ad_wallet_trnsaction',
                    gl_trn_dt=timezone.now()
                )

                WalletTrn.objects.create(
                    action_id=global_transaction.gl_trn_id,
                    action_type=f'Internal{from_wallet}_to_{main_wallet}',
                    pu=get_user,
                    wl_label=value[1],
                    effectvie_wallet=value[0],
                    effectvie_amt=amount,
                    effective_type=key,
                    wl_trn_des=f"{user.pu_name} transferred {amount} from their wallet to {get_user.pu_name} ",
                    current_balance=from_wallet_balance.main_wallet,
                    wl_trn_dt=timezone.now()
                )

                


            return Response({
                'status': 'success',
                'message': f'{amount} transferred from {from_wallet} of to_user_wallet to {main_wallet} of from_user_wallet.',
                'is_success': True
            }, status=status.HTTP_200_OK)

        except PortalUserWallet.DoesNotExist:
            return Response({'status': 'fail', 'message': 'user wallet dose not exists'},
                            status=status.HTTP_404_NOT_FOUND)

        except PortalUser.DoesNotExist:
            return Response({'status': 'fail', 'message': 'user dose not exists.'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)





class DistributorRetailerTransferView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]
    
    def post(self, request, *args, **kwargs):
        print("-------->>>>>>>>>>>>>>>>>>>>>>>>>>>>>>", request.data)
        try:
            user_id = request.data.get('userId')
            retailer_id = request.data.get('retailerId')
            selected_option = request.data.get('selectedOption')
            amount = request.data.get('amount')
            is_retailer_transfer_verified = request.data.get('confirm_step')

            if not retailer_id or not selected_option:
                return JsonResponse({'status': 'error', 'message': "Both Id and selectedOption are required."}, status=400)

            # Find retailer
            retailer = None
            if retailer_id[:2] in ['RT', 'SD', 'MT', 'DT'] and len(retailer_id) == 11:
                retailer = PortalUser.objects.filter(username=retailer_id).first()
            elif re.match(r'^\d{10}$', retailer_id):
                retailer = PortalUser.objects.filter(pu_contact_no=retailer_id).first()

            if not retailer:
                return Response({'status': 'error', 'message': "No user found with the given ID or Number."}, status=400)

            user = PortalUser.objects.get(id=user_id)
            request_user = user

            admin_wallet = PortalUserWallet.objects.filter(pu=request_user).first()
            if not admin_wallet:
                return Response({'status': 'error', 'message': "Admin wallet not found."}, status=400)

            if request_user == retailer:
                return Response({'status': 'error', 'message': "You cannot transfer funds to yourself."}, status=400)

            # Wallet Mapping
            wallet_map = {
                'main_wallet': 'main_wallet',
                'pg_wallet': 'pg_wallet',
                'cashin_wallet': 'cashin_wallet'
            }
            if selected_option not in wallet_map:
                return Response({'status': 'error', 'message': "Invalid wallet option selected."}, status=400)

            admin_balance = getattr(admin_wallet, wallet_map[selected_option]) or Decimal('0.00')

            print(admin_balance,'----------------------->>>')
            retailer_wallet = PortalUserWallet.objects.filter(pu=retailer).first()
            if not retailer_wallet:
                raise ValidationError("Retailer wallet not found.")
            retailer_balance = getattr(retailer_wallet, wallet_map[selected_option]) or Decimal('0.00')

            if is_retailer_transfer_verified == "retailer_success_true":
                if not amount:
                    return Response({'status': 'error', 'message': "Amount is required."}, status=400)


                if admin_balance < Decimal(amount):
                    return JsonResponse({'status': 'error', 'message': "Insufficient balance in admin wallet."}, status=400)

                # Transaction
                with transaction.atomic():
                    setattr(admin_wallet, wallet_map[selected_option], admin_balance - Decimal(amount))
                    admin_wallet.save()

                    setattr(retailer_wallet, wallet_map[selected_option], retailer_balance + Decimal(amount))
                    retailer_wallet.save()

                    if selected_option == 'pg_wallet':
                        selected_option_name = 'Balance Account'
                    elif selected_option == 'main_wallet':
                        selected_option_name = 'Service Account'
                    else:
                        selected_option_name = 'Cash Account'

                    timestamp = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")
                    from_label = f'DR_{selected_option_name}_To_Other_Fund_Transfer_{retailer_id}_{timestamp}'
                    to_label = f'CR_{selected_option_name}_From_Other_Fund_Transfer_{request_user.username}_{timestamp}'

                    transactions = [
                        {'pu': request_user, 'from_pu': request_user.id, 'to_pu': retailer.id, 'type': 'DR', 'label': from_label},
                        {'pu': retailer, 'from_pu': request_user.id, 'to_pu': retailer.id, 'type': 'CR', 'label': to_label}
                    ]

                    for txn in transactions:
                        user_wallet = PortalUserWallet.objects.filter(pu=txn['pu']).first()
                        if not user_wallet:
                            raise ValidationError(f"Wallet not found for user {txn['pu'].username}")

                        global_transaction = GlTrn.objects.create(
                            pu=txn['pu'],
                            effectvie_wallet=selected_option,
                            effectvie_amt=amount,
                            effective_type=txn['type'],
                            service_trn_table='ad_wallet_transaction',
                            gl_trn_dt=timezone.now()
                        )

                        WalletTrn.objects.create(
                            action_id=global_transaction.gl_trn_id,
                            action_type=f'Internal_{selected_option}_to_{selected_option}',
                            pu=txn['pu'],
                            wl_label=txn['label'],
                            effectvie_wallet=selected_option,
                            effectvie_amt=amount,
                            effective_type=txn['type'],
                            wl_trn_des=" Wallet Transfer",
                            current_balance=getattr(user_wallet, wallet_map[selected_option]),
                            wl_trn_dt=timezone.now(),
                        )

                return Response(
                    {
                        "success": True,
                        "message": f"₹{amount} transferred successfully to {retailer.pu_name}.",
                        "retailer": {
                            "id": retailer.id,
                            "name": retailer.pu_name,
                            "contact_number": retailer.pu_contact_no,
                            "role": retailer.pu_role
                        }
                    },
                    status=status.HTTP_200_OK
                )

            return Response(
                {
                    "success": True,
                    "message": f"Transfer request for {retailer.pu_name} is ready for confirmation.",
                    "retailer": {
                        "id": retailer.id,
                        "name": retailer.pu_name,
                        "contact_number": retailer.pu_contact_no,
                        "role": retailer.pu_role
                    }
                },
                status=status.HTTP_200_OK
            )

        except ValidationError as e:
            traceback
            return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            traceback.print_exc()  # This prints the full traceback to the server logs

            print(f"Unexpected error: {str(e)}")
            return Response({"success": False, "message": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)








class DistributorTransferView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor | IsRetailer]
    
    def post(self, request, *args, **kwargs):
        try:
            retailer_id = request.data.get('retailerId')
            selected_option = request.data.get('selectedOption')
           
            amount = request.data.get('amount')
            is_retailer_transfer_verified = request.data.get('confirm_step')

            if not retailer_id or not selected_option:
                raise ValidationError("Both retailerId and selectedOption are required.")

            # Find retailer based on ID or Contact Number
            retailer = None

            # Match IDs starting with R, S, M, D and 11 chars long (e.g. RTGJ0125002, SDGJ0125001, etc.)
            if retailer_id[:1] in ['R', 'S', 'M', 'D'] and len(retailer_id) == 11:
                retailer = PortalUser.objects.filter(username=retailer_id).first()

            # Match 10-digit mobile numbers
            elif re.match(r'^\d{10}$', retailer_id):
                retailer = PortalUser.objects.filter(pu_contact_no=retailer_id).first()

            if not retailer:
                raise ValidationError("No retailer found with the given Retailer ID or Number.")


            # Get Admin (Requesting User)
            request_user = request.user  
            if not request_user:
                raise ValidationError("Unauthorized request. Please log in.")

            # Get Admin's Wallet
            admin_wallet = PortalUserWallet.objects.filter(pu=request_user).first()
            if not admin_wallet:
                raise ValidationError("Admin wallet not found.")

            if request_user == retailer:
                raise ValidationError("You cannot transfer funds to yourself.")
            # Wallet Mapping
            wallet_map = {
                'main_wallet': 'main_wallet',
                'pg_wallet': 'pg_wallet',
                'cashin_wallet': 'cashin_wallet'
            }
            if selected_option not in wallet_map:
                raise ValidationError("Invalid wallet option selected.")

            admin_balance = getattr(admin_wallet, wallet_map[selected_option])
            
            # Get Retailer's Wallet
            retailer_wallet = PortalUserWallet.objects.filter(pu=retailer).first()
            if not retailer_wallet:
                raise ValidationError("wallet not found.")
            
            retailer_balance = getattr(retailer_wallet, wallet_map[selected_option])

            if is_retailer_transfer_verified == "retailer_success_true":
                if not amount:
                    raise ValidationError("Amount is required.")

                try:
                    amount = Decimal(amount)  
                except (ValueError, TypeError):
                    raise ValidationError("Invalid amount format. Amount must be a whole number.")

                if admin_balance < amount:
                    raise ValidationError("Insufficient balance in admin wallet.")

                # Perform transaction atomically
                with transaction.atomic():
                    # Deduct from admin
                    setattr(admin_wallet, wallet_map[selected_option], admin_balance - amount)
                    admin_wallet.save()

                    # Add to retailer
                    setattr(retailer_wallet, wallet_map[selected_option], retailer_balance + amount)
                    retailer_wallet.save()

                    if selected_option == 'pg_wallet':
                        selected_option_name = 'Balance Account'
                    elif selected_option == 'main_wallet':
                        selected_option_name = 'Service Account'
                    else:
                        selected_option_name = 'Cash Account'
                    # Prepare transaction labels
                    timestamp = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")
                    from_label = f'DR_{selected_option_name}_To_DistributorTransfer_{retailer.username}_{timestamp}'
                    to_label = f'CR_{selected_option_name}_From_DistributorTransfer_{retailer.username}_{timestamp}'

                    # Record transactions
                    transactions = [
                        {'pu': request_user, 'from_pu': request_user.id, 'to_pu': retailer.id, 'type': 'DR', 'label': from_label},
                        {'pu': retailer, 'from_pu': request_user.id, 'to_pu': retailer.id, 'type': 'CR', 'label': to_label}
                    ]
                    
                    for txn in transactions:
                        # Get the user's wallet
                        user_wallet = PortalUserWallet.objects.filter(pu=txn['pu']).first()
                        if not user_wallet:
                            raise ValidationError(f"Wallet not found for user {txn['pu'].username}")

                        global_transaction = GlTrn.objects.create(
                            pu=txn['pu'],
                            effectvie_wallet=selected_option,
                            effectvie_amt=amount,
                            effective_type=txn['type'],
                            service_trn_table='ad_wallet_transaction',
                            gl_trn_dt=timezone.now()
                        )
                        

                        WalletTrn.objects.create(
                            action_id=global_transaction.gl_trn_id,
                            action_type=f'Internal_{selected_option}_to_{selected_option}',
                            pu=txn['pu'],
                            wl_label=txn['label'],
                            effectvie_wallet=selected_option,
                            effectvie_amt=amount,
                            effective_type=txn['type'],
                            wl_trn_des="Distributor Wallet Transfer",
                            current_balance=getattr(user_wallet, wallet_map[selected_option]),  
                            wl_trn_dt=timezone.now(),
                            
                        )


                return Response(
                    {
                        "success": True,
                        "message": f"₹{amount} transferred successfully to {retailer.pu_name}.",
                        "retailer": {
                            "id": retailer.id,
                            "name": retailer.pu_name,
                            "contact_number": retailer.pu_contact_no,
                            "role": retailer.pu_role
                        }
                    },
                    status=status.HTTP_200_OK
                )

            return Response(
                {
                    "success": True,
                    "message": f"Transfer request for {retailer.pu_name} is ready for confirmation.",
                    "retailer": {
                        "id": retailer.id,
                        "name": retailer.pu_name,
                        "contact_number": retailer.pu_contact_no,
                        "role": retailer.pu_role
                    }
                },
                status=status.HTTP_200_OK
            )

        except ValidationError as e:
            return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return Response({"success": False, "message": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





from .cron_job import process_inprogress_bbps

class ProcessInprogressBBPSView(APIView):
    """
    API endpoint to manually trigger processing of INPROGRESS BBPS payments.
    """

    def post(self, request, *args, **kwargs):
        try:
            process_inprogress_bbps()
            return Response(
                {"status": "success", "message": "BBPS INPROGRESS payments processed successfully."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )




from rest_framework.renderers import JSONRenderer  
from urllib.parse import urlencode


VEGAAH_CURRENCY = "INR"
# VEGAAH_API_URL1 = "https://checkout.vegaah.com/vegaahpayments/v2/payments/pay-request"
# VEGAAH_API_URL2 = "https://checkout.vegaah.com/vegaahpayments/v2/payments/pay-request"
VEGAAH_API_URL1 = "https://test-vegaah.concertosoft.com/vegaahpayments/v2/payments/pay-request"
VEGAAH_API_URL2 = "https://test-vegaah.concertosoft.com/vegaahpayments/v2/payments/pay-request"


# VEGAAH_API_URL = "https://checkout.vegaah.com/vegaahpayments/v2/payments/pay-request"


FRONTEND_URL = 'http://localhost:3000'
BACKEND_BASE_URL = 'https://qaapi.fixpay.in'


class GetAuthProfiles(APIView):
    def get(self, request):
        try:
            profiles = PaymentGetwayAuthenticationDetails.objects.filter(
                sp_id=4,
                is_deactive=False,
                unique_name__isnull=False  
            ).values('pg_auth_id', 'unique_name','min_amount',
                'max_amount')
            
            profiles_list = list(profiles)

            for profile in profiles_list:
                profile['min_amount'] = float(profile['min_amount'])
                profile['max_amount'] = float(profile['max_amount'])
            
            print(f"Fetched {len(profiles_list)} active auth profiles")
            
            return Response(profiles_list, status=200)
            
        except Exception as e:
            print(f"Error fetching auth profiles: {str(e)}")
            return Response({
                'error': 'Failed to fetch payment gateway profiles',
                'detail': str(e)
            }, status=500)

class GetAuthProfilesVeg2(APIView):
    def get(self, request):
        try:
            profiles = PaymentGetwayAuthenticationDetails.objects.filter(
                sp_id=6,
                is_deactive=False,
                unique_name__isnull=False  
            ).values('pg_auth_id', 'unique_name','min_amount',
                'max_amount')
            
            profiles_list = list(profiles)
            for profile in profiles_list:
                profile['min_amount'] = float(profile['min_amount'])
                profile['max_amount'] = float(profile['max_amount'])
            
            print(f"Fetched {len(profiles_list)} active auth profiles")
            
            return Response(profiles_list, status=200)
            
        except Exception as e:
            print(f"Error fetching auth profiles: {str(e)}")
            return Response({
                'error': 'Failed to fetch payment gateway profiles',
                'detail': str(e)
            }, status=500)




class VegaahPG(APIView):
    renderer_classes = [JSONRenderer]  
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]
    
    def post(self, request):
        if 'amount' in request.data:
            return self.add_vegaah_payment_initiate(request)
        return Response({'error': 'Amount is required'}, status=400)

    def write_to_log(self, message):
        """Write message to log file"""
        try:
            with open('vegaah_payment_log.txt', 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except Exception as e:
            print(f"Failed to write to log: {e}")

    def add_vegaah_payment_initiate(self, request):
        try:
            token = request.data.get('token')
            credit_card_num = request.data.get('cardNumber')
            customer_name = request.data.get('customerName')
            mobile = request.data.get('mobile')
            amount_str = request.data.get('amount')
            auth_profile_name = request.data.get('authProfile')
            is_instant = request.data.get('is_instant', False)

            self.write_to_log("\n" + "="*60)
            self.write_to_log("=== [VegaahPG] Payment Initiation Request ===")
            self.write_to_log("="*60)
            self.write_to_log(f"Mobile: {mobile}")
            self.write_to_log(f"Card Number: {credit_card_num[:4]}...{credit_card_num[-4:] if credit_card_num else 'N/A'}")
            self.write_to_log(f"Customer: {customer_name}")
            self.write_to_log(f"Amount: ₹{amount_str}")
            self.write_to_log(f"Auth Profile: {auth_profile_name}")
            self.write_to_log("="*60)

            if not auth_profile_name:
                self.write_to_log("Auth profile not provided")
                return Response({
                    'status': 'error',
                    'error': 'Payment gateway profile is required'
                }, status=400)

            try:
                auth_details = PaymentGetwayAuthenticationDetails.objects.get(
                    unique_name=auth_profile_name,
                    is_deactive=False
                )
                
                VEGAAH_MERCHANT_ID = auth_details.mid
                VEGAAH_TERMINAL_ID = auth_details.username
                VEGAAH_PASSWORD = auth_details.password
                
                self.write_to_log("\n---Auth Details Loaded Successfully ---")
                self.write_to_log(f"Profile Name: {auth_profile_name}")
                self.write_to_log(f"Merchant ID: {VEGAAH_MERCHANT_ID[:10]}...{VEGAAH_MERCHANT_ID[-10:] if VEGAAH_MERCHANT_ID else 'None'}")
                self.write_to_log(f"Terminal ID: {VEGAAH_TERMINAL_ID}")
                self.write_to_log(f"Password: ***{VEGAAH_PASSWORD[-4:] if VEGAAH_PASSWORD else 'None'}")
                self.write_to_log("-"*60)
                
            except PaymentGetwayAuthenticationDetails.DoesNotExist:
                self.write_to_log(f"Auth profile '{auth_profile_name}' not found or inactive")
                return Response({
                    'status': 'error',
                    'error': f"Payment gateway profile '{auth_profile_name}' not found or inactive"
                }, status=404)

            if not all([VEGAAH_MERCHANT_ID, VEGAAH_TERMINAL_ID, VEGAAH_PASSWORD]):
                self.write_to_log("Incomplete authentication details")
                self.write_to_log(f"  - Merchant ID: {'✓' if VEGAAH_MERCHANT_ID else '✗'}")
                self.write_to_log(f"  - Terminal ID: {'✓' if VEGAAH_TERMINAL_ID else '✗'}")
                self.write_to_log(f"  - Password: {'✓' if VEGAAH_PASSWORD else '✗'}")
                return Response({
                    'status': 'error',
                    'error': 'Incomplete authentication details for selected profile. Please contact administrator.'
                }, status=400)

            self.write_to_log("\n--- Card BIN Lookup ---")
            bin_details = fetch_bin_details_pg(credit_card_num)
            
            if bin_details['status'] != 'success':
                self.write_to_log(f"BIN lookup failed: {bin_details['message']}")
                return Response({
                    "status": "error", 
                    "message": bin_details['message']
                }, status=400)
            
            card_type = bin_details['card_type']
            brand = bin_details['brand']
            self.write_to_log(f"✓ Card Type: {card_type}")
            self.write_to_log(f"✓ Brand: {brand}")
            
            card_type_instance = CardType.objects.filter(name__icontains=brand).first()
            if not card_type_instance:
                self.write_to_log(f"Card type '{brand}' not supported")
                return Response({
                    "status": "error",
                    "message": f"Card type '{brand}' is not supported"
                }, status=400)
            
            self.write_to_log(f"Card Type Instance: {card_type_instance.name} (ID: {card_type_instance.id})")

            try:
                decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = decoded.get('user_id')
                if not user_id:
                    return Response({'error': 'Invalid token'}, status=401)

                user = PortalUser.objects.get(id=user_id)
                self.write_to_log(f"User Authenticated: {user.pu_email} (ID: {user.id})")

            except jwt.ExpiredSignatureError:
                return Response({'error': 'Token has expired'}, status=401)
            except jwt.InvalidTokenError:
                return Response({'error': 'Invalid token'}, status=401)

            try:
                amount = Decimal(amount_str).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
                # amount = 1

                if amount <= 0:
                    return Response({'error': 'Amount must be greater than 0'}, status=400)
                self.write_to_log(f"✓ Validated Amount: ₹{amount}")
            except (ValueError, TypeError, InvalidOperation):
                return Response({'error': 'Invalid amount format'}, status=400)

            pg_id = 4  
            payment_gateway = get_object_or_404(PaymentGateway, id=pg_id)
            self.write_to_log(f"✓ Payment Gateway: {payment_gateway.name}")

            card_type = get_object_or_404(CardType, id=card_type_instance.id)

            retailer = user
            retailer_details = get_object_or_404(PortalUserDetails, pu=retailer)
            self.write_to_log(f"Retailer Details: {retailer_details.pud_id}")


            user_service_finance = None
            instant_charge_percent = Decimal('0.00')
            
            if is_instant:
                print("\n--- Instant Payment: Checking Limit & Charge ---")
                
                try:
                    user_service_finance = UserServiceFinance.objects.filter(
                        user=retailer
                    ).first()
                    
                    if not user_service_finance:
                        print("No instant finance configuration found for user")
                        return Response({
                            'status': 'error',
                            'error': 'Instant payment not configured for your account. Please contact administrator.'
                        }, status=400)
                    
                    instant_limit = Decimal(str(user_service_finance.od_limit))
                    instant_charge_percent = Decimal(str(user_service_finance.instant_charge))
                    available_limit = Decimal(str(user_service_finance.available_limit))
                    
                    print(f"User OD Limit: ₹{instant_limit}")
                    print(f"Instant Charge: {instant_charge_percent}%")
                    print(f"Current Amount: ₹{amount}")
                    if amount > available_limit:
                        print(f"Insufficient Limit! Required: ₹{amount}, Available: ₹{available_limit}")
                        
                        return Response({
                            'status': 'error',
                            'error': f'Insufficient instant payment limit. Transaction amount: ₹{amount}. Available limit: ₹{available_limit}.'
                        }, status=400)
                    
                    print(f"Sufficient Limit. Remaining after transaction: ₹{available_limit - amount}")
                    
                except Exception as e:
                    print(f"Error checking instant limit: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return Response({
                        'status': 'error',
                        'error': 'Failed to verify instant payment limit. Please try again.'
                    }, status=500)

            self.write_to_log("\n--- Charge Lookup ---")
            try:
                retailer_charge = UserCharge.objects.get(
                    user_id=retailer.id, 
                    pg=payment_gateway, 
                    card_type=card_type
                )
                charge_percent = retailer_charge.charge_percent
                self.write_to_log(f"✓ Retailer-specific charge: {charge_percent}%")
            except UserCharge.DoesNotExist:
                self.write_to_log("⚠ Retailer charge not found, checking PG base charge...")
                try:
                    # Map username prefix to role
                    prefix_role_map = {
                        "SD": "Super Distributor",
                        "MD": "Master Distributor",
                        "DT": "Distributor",
                        "RT": "Retailer",
                        "AD": "Admin",
                    }
                    
                    # Get username and extract prefix
                    username = retailer.pu_username if hasattr(retailer, 'pu_username') else str(retailer.username)
                    user_prefix = username[:2].upper() if username else ""
                    user_role = prefix_role_map.get(user_prefix, "Retailer")
                    
                    self.write_to_log(f"Username: {username}")
                    self.write_to_log(f"Prefix: {user_prefix}")
                    self.write_to_log(f"Determined Role: {user_role}")
                    
                    pg_base_charge = PGBaseCharge.objects.get(
                        pg=payment_gateway, 
                        card_type=card_type,
                        role=user_role  # THIS IS THE CRITICAL FILTER
                    )
                    charge_percent = pg_base_charge.charge_percent
                    self.write_to_log(f"✓ PG base charge for {user_role}: {charge_percent}%")
                    
                except PGBaseCharge.DoesNotExist:
                    self.write_to_log(f"❌ No PG base charge found for role: {user_role}")
                    return Response({
                        "status": False, 
                        "message": f"No applicable charge percent found for {user_role}."
                    }, status=400)
                    
                except PGBaseCharge.MultipleObjectsReturned:
                    self.write_to_log(f"⚠ Multiple charges found for {user_role}, using first one")
                    pg_base_charge = PGBaseCharge.objects.filter(
                        pg=payment_gateway, 
                        card_type=card_type,
                        role=user_role
                    ).first()
                    
                    if pg_base_charge:
                        charge_percent = pg_base_charge.charge_percent
                        self.write_to_log(f"✓ Using charge: {charge_percent}%")
                    else:
                        return Response({
                            "status": False, 
                            "message": f"No applicable charge percent found."
                        }, status=400)
            total_charge_percent = charge_percent + instant_charge_percent

            total_charge_amount = (amount * total_charge_percent) / Decimal('100')
            net_credit_to_user = amount - total_charge_amount

            self.write_to_log(f"Charge Amount: ₹{total_charge_amount}")
            self.write_to_log(f"Net Credit: ₹{net_credit_to_user}")



            service_provider = AdServiceProvider.objects.filter(
                service__service_name='PG',
                pg=payment_gateway  
            ).first()
           
                
            if card_type.name.lower() == 'rupay':
                mdr_percent = service_provider.rupay_mdr
            elif card_type.name.lower() == 'mastercard':
                mdr_percent = service_provider.mastercard_mdr
            elif card_type.name.lower() == 'visa':
                mdr_percent = service_provider.visa_mdr
            else:
                mdr_percent = Decimal('0.00')

            mdr_amount = (amount * mdr_percent / Decimal('100')).quantize(Decimal('0.00'))
            gst_amount = (mdr_amount * service_provider.gst_percentage / Decimal('100')).quantize(Decimal('0.00'))
            receivable_amount = (amount - mdr_amount - gst_amount).quantize(Decimal('0.00'))

            state_name = ""
            city_name = ""
            if retailer_details.state_id:
                state = State.objects.filter(state_id=retailer_details.state_id).first()
                if state:
                    state_name = state.state_name

            if retailer_details.city_id:
                city = City.objects.filter(city_id=retailer_details.city_id).first()
                if city:
                    city_name = city.city_name

            s = ''.join(ch for ch in str(credit_card_num) if ch.isdigit())
            last4 = ""
            masked_pan = ""
            bin_number = ""
            
            if len(s) >= 4:
                last4 = s[-4:]
                masked_pan = f"XXXX-XXXX-XXXX-{last4}"
                bin_number = s[:6] if len(s) >= 6 else s[:4]

            self.write_to_log(f"\n--- Card Details ---")
            self.write_to_log(f"BIN: {bin_number}")
            self.write_to_log(f"Masked: {masked_pan}")
            self.write_to_log(f"Last 4: {last4}")

            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            order_id = f"VGH{timestamp}"
            self.write_to_log(f"\n✓ Order ID Generated: {order_id}")

            amount_for_signature = f"{amount:.2f}"
            
            signature_string = f"{order_id}|{VEGAAH_TERMINAL_ID}|{VEGAAH_PASSWORD}|{VEGAAH_MERCHANT_ID}|{amount_for_signature}|{VEGAAH_CURRENCY}"
            signature = hashlib.sha256(signature_string.encode()).hexdigest()

            self.write_to_log("\n--- Signature Generation ---")
            self.write_to_log(f"Format: orderId|terminalId|password|merchantId|amount|currency")
            self.write_to_log(f"String: {signature_string}")
            self.write_to_log(f"SHA256: {signature[:20]}...{signature[-20:]}")

            payload = {
                "terminalId": VEGAAH_TERMINAL_ID,
                "password": VEGAAH_PASSWORD,
                "signature": signature,
                "paymentType": "1",
                "amount": amount_for_signature,
                "currency": VEGAAH_CURRENCY,
                "order": {
                    "orderId": order_id,
                    "description": f"Payment for order {order_id}"
                },
                "customer": {
                    "customerEmail": user.pu_email,
                    "billingAddressStreet": retailer_details.address or "",
                    "billingAddressCity": city_name or "",
                    "billingAddressState": state_name or "",
                    "billingAddressPostalCode": str(retailer_details.zip_code or ""),
                    "billingAddressCountry": "IN"
                },
                "returnUrl": {
                    "successUrl": f"{BACKEND_BASE_URL}/admin_hub/vegaah-callback/",
                    "failureUrl": f"{BACKEND_BASE_URL}/admin_hub/vegaah-callback/",
                    "webhookUrl": f"{BACKEND_BASE_URL}/admin_hub/vegaah-webhook/"
                }
            }

            self.write_to_log("\n---Vegaah API Request ---")
            self.write_to_log(f"URL: {VEGAAH_API_URL1}")
            self.write_to_log(json.dumps(payload, indent=2))

            try:
                self.write_to_log("\nSending request to Vegaah API...")
                
                resp = requests.post(
                    VEGAAH_API_URL1, 
                    json=payload, 
                    headers={'Content-Type': 'application/json'}, 
                    timeout=60 
                )
                
                self.write_to_log(f"✓ Response Status: {resp.status_code}")
                api_response = resp.json()
                
            except requests.exceptions.Timeout:
                self.write_to_log("Request timeout")
                return Response({
                    'status': 'error',
                    'error': 'Payment gateway is taking too long to respond. Please try again.'
                }, status=504)
            except requests.exceptions.ConnectionError as e:
                self.write_to_log(f"Connection error: {str(e)}")
                return Response({
                    'status': 'error',
                    'error': 'Unable to connect to payment gateway. Please check your internet connection.'
                }, status=503)
            except requests.exceptions.RequestException as e:
                self.write_to_log(f"Request error: {str(e)}")
                return Response({
                    'status': 'error',
                    'error': f'Failed to connect with payment gateway: {str(e)}'
                }, status=500)
            except ValueError as e:
                self.write_to_log(f"Invalid JSON response: {str(e)}")
                return Response({
                    'status': 'error',
                    'error': 'Invalid response from payment gateway'
                }, status=500)

            self.write_to_log("\n---API Response ---")
            self.write_to_log(json.dumps(api_response, indent=2))

            response_code = api_response.get('responseCode')
            
            if not response_code:
                error_msg = api_response.get('message', 'Payment link generation failed')
                self.write_to_log(f"No response code: {error_msg}")
                return Response({
                    'status': 'error',
                    'error': error_msg
                }, status=400)

            if response_code != '001':
                error_desc = api_response.get('responseDescription', 'Payment request failed')
                self.write_to_log(f"Payment failed: {error_desc}")
                return Response({
                    'status': 'error',
                    'error': error_desc
                }, status=400)

            transaction_id = api_response.get('transactionId')
            order_details = api_response.get('orderDetails', {})
            payment_link_data = api_response.get('paymentLink', {})
            
            self.write_to_log(f"\nTransaction ID: {transaction_id}")

            self.write_to_log("\n--- Saving Transaction ---")
            
            pg_service_trn = PgServiceTrn.objects.create(
                trn_unique_id=order_id,
                trn_amount=amount,
                trn_response=api_response,
                pg=payment_gateway,
                card_type=card_type,
                is_settled=False,
                trn_status="PENDING",
                created_by=retailer.id,
                buyer_email=user.pu_email,
                buyer_phone=mobile,
                buyer_firstname=customer_name.split()[0] if customer_name else "",
                buyer_lastname=customer_name.split()[1] if customer_name and len(customer_name.split()) > 1 else "",
                buyer_address=state_name or "",
                buyer_city=city_name or "",
                buyer_state=state_name or "",
                buyer_country="India",
                buyer_pincode=retailer_details.zip_code or 0,
                retailer_charge_percent=total_charge_percent, 
                total_charge_amount=total_charge_amount,
                net_credit_to_user=net_credit_to_user,
                is_instant=is_instant,
                sp_mdr_amount=mdr_amount,
                sp_gst_amount=gst_amount,
                sp_receivable_amount=receivable_amount
            )

            self.write_to_log(f"Transaction saved (DB ID: {pg_service_trn.pg_trn_id})")

            payment_link_base = payment_link_data.get('linkUrl', '')
            payment_link = f"{payment_link_base}{transaction_id}" if payment_link_base and transaction_id else ""

            self.write_to_log(f"\n Payment Link: {payment_link}")
            self.write_to_log("="*60)

            return Response({
                'status': 'success',
                'message': 'Payment link generated successfully',
                'data': {
                    'paymentLink': payment_link,
                    'transactionId': transaction_id,
                    'orderId': order_id,
                    'amount': str(amount),
                    'responseCode': response_code,
                    'responseDescription': api_response.get('responseDescription', ''),
                    'transactionDateTime': api_response.get('transactionDateTime', ''),
                    'authProfile': auth_profile_name,
                    'isInstant': is_instant,  
                    'totalCharge': str(total_charge_percent)
                }
            }, status=200)

        except PortalUser.DoesNotExist:
            self.write_to_log("User not found")
            return Response({'status': 'error', 'error': 'User not found'}, status=404)
        except PortalUserDetails.DoesNotExist:
            self.write_to_log("User details not found")
            return Response({'status': 'error', 'error': 'User details not found'}, status=404)
        except Exception as e:
            self.write_to_log("Unexpected error occurred")
            import traceback
            self.write_to_log(traceback.format_exc())
            return Response({'status': 'error', 'error': f'An unexpected error occurred: {str(e)}'}, status=500)
        
@csrf_exempt
def vegaah_callback(request):
    

    return HttpResponse("Sucess")


from django.views.decorators.http import require_POST



@csrf_exempt
@require_POST
def vegaah_webhook(request):
    try:
        data = json.loads(request.body)

        VegaahPgLogs.objects.create(
            order_id=data.get('orderId', ''),
            request=data,           
            response={}             
        )

        response_code = data.get('responseCode', '')
        result = data.get('result', '')
        response_desc = data.get('responseDescription', '')
        transaction_id = data.get('transactionId', '')
        order_id = data.get('orderId', '')
        amount = data.get('amount', '')
        terminal_id = data.get('terminalId', '')

        pg_service_trn = PgServiceTrn.objects.filter(
            trn_unique_id=order_id
        ).first()

        if pg_service_trn:
            if result.upper() == 'SUCCESS' and response_code == '000':
                pg_service_trn.trn_status = 'COMPLETED'
                retailer = pg_service_trn.created_by
                user_finance = UserServiceFinance.objects.filter(
                    user_id=retailer,
                ).first()

                if pg_service_trn.is_instant:
                    if user_finance:
                        txn_amount = Decimal(str(amount))
                        user_finance.usage_limit += txn_amount
                        user_finance.available_limit -= txn_amount
                        user_finance.save()
                        print(f"Instant Transaction Update → usage_limit: {user_finance.usage_limit}, available_limit: {user_finance.available_limit}")
                    else:
                        print("No UserServiceFinance record found for instant transaction!")
                else:
                    print("Not an instant transaction — finance not updated.")
            elif result.upper() == 'FAILURE':
                pg_service_trn.trn_status = 'FAILED'
            else:
                pg_service_trn.trn_status = 'PENDING'

            pg_service_trn.trn_response = data
            pg_service_trn.save()

            latest_log = VegaahPgLogs.objects.filter(order_id=order_id).order_by('-created_at').first()
            if latest_log:
                latest_log.response = data
                latest_log.save()
        else:
            print("Transaction not found for order_id:", order_id, data)

    except Exception as e:
        print("Webhook Exception:", str(e))

    return JsonResponse({'success': 'true'}, status=200)  

@csrf_exempt
@require_POST
def vegaah_prod_webhook(request):
    try:
        data = json.loads(request.body)

        VegaahPgLogs.objects.create(
            order_id=data.get('orderId', ''),
            request=data,           
            response={}             
        )

        response_code = data.get('responseCode', '')
        result = data.get('result', '')
        response_desc = data.get('responseDescription', '')
        transaction_id = data.get('transactionId', '')
        order_id = data.get('orderId', '')
        amount = data.get('amount', '')
        terminal_id = data.get('terminalId', '')

        pg_service_trn = PgServiceTrn.objects.filter(
            trn_unique_id=order_id
        ).first()

        if pg_service_trn:
            if result.upper() == 'SUCCESS' and response_code == '000':
                pg_service_trn.trn_status = 'COMPLETED'
                retailer = pg_service_trn.created_by
                user_finance = UserServiceFinance.objects.filter(
                    user_id=retailer
                ).first()

                if pg_service_trn.is_instant:
                    if user_finance:
                        txn_amount = Decimal(str(amount))
                        user_finance.usage_limit += txn_amount
                        user_finance.available_limit -= txn_amount
                        user_finance.save()
                        print(f"Instant Transaction Update → usage_limit: {user_finance.usage_limit}, available_limit: {user_finance.available_limit}")
                    else:
                        print("No UserServiceFinance record found for instant transaction!")
                else:
                    print("Not an instant transaction — finance not updated.")
            elif result.upper() == 'FAILURE':
                pg_service_trn.trn_status = 'FAILED'
            else:
                pg_service_trn.trn_status = 'PENDING'

            pg_service_trn.trn_response = data
            pg_service_trn.save()
            latest_log = VegaahPgLogs.objects.filter(order_id=order_id).order_by('-created_at').first()
            if latest_log:
                latest_log.response = data
                latest_log.save()
        else:
            print("Transaction not found for order_id:", order_id, data)

    except Exception as e:
        print("Webhook Exception:", str(e))

    return JsonResponse({'success': 'true'}, status=200)  






# class BBPSRefundAPIView(APIView):
#     authentication_classes = [CustomJWTAuthentication]
#     permission_classes = [IsAdmin | IsDistributor]

#     def post(self, request):
#         try:
#             bbps_id = request.data.get('bbps_id')
#             bbps_request_id = request.data.get('bbps_request_id')
#             refund_reason = request.data.get('refund_reason', 'Admin initiated refund')


#             if not bbps_id and not bbps_request_id:
#                 return Response({
#                     'st': False,
#                     'msg': 'bbps_id or bbps_request_id is required'
#                 }, status=status.HTTP_400_BAD_REQUEST)

#             if bbps_id:
#                 bbps_transaction = BBPSBillPayment.objects.filter(bbps_id=bbps_id).first()
#             else:
#                 bbps_transaction = BBPSBillPayment.objects.filter(bbps_request_id=bbps_request_id).first()

#             if not bbps_transaction:
#                 return Response({
#                     'st': False,
#                     'msg': 'BBPS transaction not found'
#                 }, status=status.HTTP_404_NOT_FOUND)

#             if bbps_transaction.bbps_status != 'INPROGRESS':
#                 return Response({
#                     'st': False,
#                     'msg': f'Refund not allowed. Current status: {bbps_transaction.bbps_status}'
#                 }, status=status.HTTP_400_BAD_REQUEST)


#             if not bbps_transaction.bbps_amount or bbps_transaction.bbps_amount <= 0:
#                 return Response({
#                     'st': False,
#                     'msg': 'Invalid transaction amount'
#                 }, status=status.HTTP_400_BAD_REQUEST)

#             if not bbps_transaction.created_by:
#                 return Response({
#                     'st': False,
#                     'msg': 'User information not found in transaction'
#                 }, status=status.HTTP_400_BAD_REQUEST)


#             with transaction.atomic():

#                 try:
#                     portal_user = PortalUser.objects.get(id=bbps_transaction.created_by)
#                     portal_user_details = PortalUserDetails.objects.get(pu_id=bbps_transaction.created_by)
#                     user_wallet = PortalUserWallet.objects.get(pu_id=bbps_transaction.created_by)
#                 except (PortalUser.DoesNotExist, PortalUserDetails.DoesNotExist, PortalUserWallet.DoesNotExist):
#                     return Response({
#                         'st': False,
#                         'msg': 'User or wallet not found'
#                     }, status=status.HTTP_404_NOT_FOUND)

#                 refund_amount = Decimal(str(bbps_transaction.bbps_amount))


#                 gl_trn = GlTrn.objects.create(
#                     service_trn_id=bbps_transaction.bbps_id,
#                     pu_id=bbps_transaction.created_by,
#                     gl_trn_amt=refund_amount,
#                     effectvie_wallet='main_wallet',
#                     effectvie_amt=refund_amount,
#                     service_trn_table='ad_bbps_bill_payment',
#                     effective_type='CR',
#                     gl_trn_dt=now(),
#                 )


#                 new_balance = Decimal(str(user_wallet.main_wallet)) + refund_amount
                
#                 WalletTrn.objects.create(
#                     action_id=gl_trn.pk,
#                     action_type='Refund',
#                     pu_id=bbps_transaction.created_by,
#                     wl_label=f"BBPS_Refund_by_{portal_user_details.pud_unique_id}_of_amount_{refund_amount}_with_request_id_{bbps_transaction.bbps_request_id}",
#                     effectvie_wallet='main_wallet',
#                     effectvie_amt=refund_amount,
#                     effective_type='CR',
#                     wl_trn_des=refund_reason,
#                     current_balance=new_balance,
#                     wl_trn_dt=now(),
#                     wl_reason=refund_reason
#                 )


#                 user_wallet.main_wallet = new_balance
#                 user_wallet.updated_at = now()
#                 user_wallet.save()


#                 bbps_transaction.bbps_status = 'FAILED'
#                 bbps_transaction.updated_at = now()
#                 bbps_transaction.save()

#             return Response({
#                 'st': True,
#                 'msg': f'Refund successful. Amount ₹{refund_amount} credited to user wallet.',
#                 'data': {
#                     'bbps_id': bbps_transaction.bbps_id,
#                     'bbps_request_id': bbps_transaction.bbps_request_id,
#                     'refund_amount': float(refund_amount),
#                     'user_id': bbps_transaction.created_by,
#                     'new_wallet_balance': float(new_balance),
#                     'status': 'FAILED'
#                 }
#             }, status=status.HTTP_200_OK)

#         except Exception as e:
#             traceback.print_exc()
#             return Response({
#                 'st': False,
#                 'msg': f'Internal server error: {str(e)}'
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BBPSRefundAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor]

    def post(self, request):
        try:
            bbps_id = request.data.get('bbps_id')
            bbps_request_id = request.data.get('bbps_request_id')
            refund_reason = request.data.get('refund_reason', 'Admin initiated refund')

            if not bbps_id and not bbps_request_id:
                return Response({
                    'st': False,
                    'msg': 'bbps_id or bbps_request_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():

                try:
                    if bbps_id:
                        bbps_transaction = BBPSBillPayment.objects.select_for_update().get(bbps_id=bbps_id)
                    else:
                        bbps_transaction = BBPSBillPayment.objects.select_for_update().get(bbps_request_id=bbps_request_id)
                except BBPSBillPayment.DoesNotExist:
                    return Response({
                        'st': False,
                        'msg': 'BBPS transaction not found'
                    }, status=status.HTTP_404_NOT_FOUND)

                if bbps_transaction.bbps_status != 'INPROGRESS':
                    return Response({
                        'st': False,
                        'msg': f'Refund not allowed. Current status: {bbps_transaction.bbps_status}'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if not bbps_transaction.bbps_amount or Decimal(str(bbps_transaction.bbps_amount)) <= 0:
                    return Response({
                        'st': False,
                        'msg': 'Invalid transaction amount'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if not bbps_transaction.created_by:
                    return Response({
                        'st': False,
                        'msg': 'User information not found in transaction'
                    }, status=status.HTTP_400_BAD_REQUEST)

                try:
                    portal_user = PortalUser.objects.get(id=bbps_transaction.created_by)
                    portal_user_details = PortalUserDetails.objects.get(pu_id=bbps_transaction.created_by)
                    user_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=bbps_transaction.created_by)
                except (PortalUser.DoesNotExist, PortalUserDetails.DoesNotExist, PortalUserWallet.DoesNotExist):
                    return Response({
                        'st': False,
                        'msg': 'User or wallet not found'
                    }, status=status.HTTP_404_NOT_FOUND)

                refund_amount = Decimal(str(bbps_transaction.bbps_amount))

                gl_trn = GlTrn.objects.create(
                    service_trn_id=bbps_transaction.bbps_id,
                    pu_id=bbps_transaction.created_by,
                    gl_trn_amt=refund_amount,
                    effectvie_wallet='main_wallet',
                    effectvie_amt=refund_amount,
                    service_trn_table='ad_bbps_bill_payment',
                    effective_type='CR',
                    gl_trn_dt=now(),
                )

                new_balance = Decimal(str(user_wallet.main_wallet)) + refund_amount

                WalletTrn.objects.create(
                    action_id=gl_trn.pk,
                    action_type='Refund',
                    pu_id=bbps_transaction.created_by,
                    wl_label=f"BBPS_Refund_by_{portal_user_details.pud_unique_id}_of_amount_{refund_amount}_with_request_id_{bbps_transaction.bbps_request_id}",
                    effectvie_wallet='main_wallet',
                    effectvie_amt=refund_amount,
                    effective_type='CR',
                    wl_trn_des=refund_reason,
                    current_balance=new_balance,
                    wl_trn_dt=now(),
                    wl_reason=refund_reason
                )

                user_wallet.main_wallet = new_balance
                user_wallet.updated_at = now()
                user_wallet.save(update_fields=["main_wallet", "updated_at"])

                bbps_transaction.bbps_status = 'FAILED'
                bbps_transaction.updated_at = now()
                bbps_transaction.save(update_fields=["bbps_status", "updated_at"])

            return Response({
                'st': True,
                'msg': f'Refund successful. Amount ₹{refund_amount} credited to user wallet.',
                'data': {
                    'bbps_id': bbps_transaction.bbps_id,
                    'bbps_request_id': bbps_transaction.bbps_request_id,
                    'refund_amount': float(refund_amount),
                    'user_id': bbps_transaction.created_by,
                    'new_wallet_balance': float(new_balance),
                    'status': 'FAILED'
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'st': False,
                'msg': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# class CheckTransactionStatus(APIView):
#     """Check the current status of a transaction"""
#     authentication_classes = [CustomJWTAuthentication]
#     permission_classes = [IsDistributor | IsRetailer]
    
#     def get(self, request):
#         order_id = request.GET.get('orderId')
        
#         if not order_id:
#             return Response({'error': 'orderId is required'}, status=400)
        
#         try:
#             pg_service_trn = PgServiceTrn.objects.filter(
#                 trn_unique_id=order_id
#             ).first()
            
#             if not pg_service_trn:
#                 return Response({'error': 'Transaction not found'}, status=404)
            
#             # Get the current status
#             current_status = pg_service_trn.trn_status
            
#             print(f"[Status Check] Order: {order_id}, Status: {current_status}")
            
#             # If status is still PENDING, return PENDING
#             # (Don't change anything in database, just return current status)
#             return Response({
#                 'status': current_status,  # This will be 'PENDING', 'COMPLETED', or 'FAILED'
#                 'orderId': order_id,
#                 'amount': str(pg_service_trn.trn_amount),
#                 'transactionId': pg_service_trn.trn_response.get('transactionId', '') if pg_service_trn.trn_response else '',
#                 'responseCode': pg_service_trn.trn_response.get('responseCode', '') if pg_service_trn.trn_response else '',
#                 'responseDescription': pg_service_trn.trn_response.get('responseDescription', '') if pg_service_trn.trn_response else ''
#             }, status=200)
            
#         except Exception as e:
#             print(f"Error checking transaction status: {str(e)}")
#             return Response({'error': str(e)}, status=500)

class CheckTransactionStatus(APIView):
    """
    Common transaction status API
    Works for Vegaah PG and Razorpay
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]

    def get(self, request):
        order_id = request.GET.get('orderId')

        if not order_id:
            return Response(
                {'error': 'orderId is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pg_service_trn = PgServiceTrn.objects.filter(
            trn_unique_id=order_id
        ).first()

        if not pg_service_trn:
            return Response(
                {'error': 'Transaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        current_status = pg_service_trn.trn_status

        # Debug log
        print(f"[CHECK STATUS] orderId={order_id} status={current_status}")

        # Normalize status (safety)
        if current_status not in ['PENDING', 'COMPLETED', 'FAILED']:
            current_status = 'PENDING'

        return Response(
            {
                'orderId': order_id,
                'status': current_status,
                'amount': str(pg_service_trn.trn_amount),
            },
            status=status.HTTP_200_OK
        )


class VegaahPG2(APIView):
    renderer_classes = [JSONRenderer]  
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]
    
    def post(self, request):
        if 'amount' in request.data:
            return self.add_vegaah_payment_initiate(request)
        return Response({'error': 'Amount is required'}, status=400)

    def write_to_log(self, message):
        """Write message to log file"""
        try:
            with open('vegaah_payment_log_2.txt', 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except Exception as e:
            print(f"Failed to write to log: {e}")

    def add_vegaah_payment_initiate(self, request):
        try:
            token = request.data.get('token')
            credit_card_num = request.data.get('cardNumber')
            customer_name = request.data.get('customerName')
            mobile = request.data.get('mobile')
            amount_str = request.data.get('amount')
            auth_profile_name = request.data.get('authProfile')
            is_instant = request.data.get('is_instant', False)


            self.write_to_log("\n" + "="*60)
            self.write_to_log("=== [VegaahPG] Payment Initiation Request ===")
            self.write_to_log("="*60)
            self.write_to_log(f"Mobile: {mobile}")
            self.write_to_log(f"Card Number: {credit_card_num[:4]}...{credit_card_num[-4:] if credit_card_num else 'N/A'}")
            self.write_to_log(f"Customer: {customer_name}")
            self.write_to_log(f"Amount: ₹{amount_str}")
            self.write_to_log(f"Auth Profile: {auth_profile_name}")
            self.write_to_log("="*60)

            if not auth_profile_name:
                self.write_to_log("Auth profile not provided")
                return Response({
                    'status': 'error',
                    'error': 'Payment gateway profile is required'
                }, status=400)

            try:
                auth_details = PaymentGetwayAuthenticationDetails.objects.get(
                    sp_id=6,
                    unique_name=auth_profile_name,
                    is_deactive=False
                )
                
                VEGAAH_MERCHANT_ID = auth_details.mid
                VEGAAH_TERMINAL_ID = auth_details.username
                VEGAAH_PASSWORD = auth_details.password
                
                self.write_to_log("\n---Auth Details Loaded Successfully ---")
                self.write_to_log(f"Profile Name: {auth_profile_name}")
                self.write_to_log(f"Merchant ID: {VEGAAH_MERCHANT_ID[:10]}...{VEGAAH_MERCHANT_ID[-10:] if VEGAAH_MERCHANT_ID else 'None'}")
                self.write_to_log(f"Terminal ID: {VEGAAH_TERMINAL_ID}")
                self.write_to_log(f"Password: ***{VEGAAH_PASSWORD[-4:] if VEGAAH_PASSWORD else 'None'}")
                self.write_to_log("-"*60)
                
            except PaymentGetwayAuthenticationDetails.DoesNotExist:
                self.write_to_log(f"Auth profile '{auth_profile_name}' not found or inactive")
                return Response({
                    'status': 'error',
                    'error': f"Payment gateway profile '{auth_profile_name}' not found or inactive"
                }, status=404)

            if not all([VEGAAH_MERCHANT_ID, VEGAAH_TERMINAL_ID, VEGAAH_PASSWORD]):
                self.write_to_log("Incomplete authentication details")
                self.write_to_log(f"  - Merchant ID: {'✓' if VEGAAH_MERCHANT_ID else '✗'}")
                self.write_to_log(f"  - Terminal ID: {'✓' if VEGAAH_TERMINAL_ID else '✗'}")
                self.write_to_log(f"  - Password: {'✓' if VEGAAH_PASSWORD else '✗'}")
                return Response({
                    'status': 'error',
                    'error': 'Incomplete authentication details for selected profile. Please contact administrator.'
                }, status=400)

            self.write_to_log("\n--- Card BIN Lookup ---")
            bin_details = fetch_bin_details_pg(credit_card_num)
            
            if bin_details['status'] != 'success':
                self.write_to_log(f"BIN lookup failed: {bin_details['message']}")
                return Response({
                    "status": "error", 
                    "message": bin_details['message']
                }, status=400)
            
            card_type = bin_details['card_type']
            brand = bin_details['brand']
            self.write_to_log(f"✓ Card Type: {card_type}")
            self.write_to_log(f"✓ Brand: {brand}")
            
            card_type_instance = CardType.objects.filter(name__icontains=brand).first()
            if not card_type_instance:
                self.write_to_log(f"Card type '{brand}' not supported")
                return Response({
                    "status": "error",
                    "message": f"Card type '{brand}' is not supported"
                }, status=400)
            
            self.write_to_log(f"Card Type Instance: {card_type_instance.name} (ID: {card_type_instance.id})")

            try:
                decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = decoded.get('user_id')
                if not user_id:
                    return Response({'error': 'Invalid token'}, status=401)

                user = PortalUser.objects.get(id=user_id)
                self.write_to_log(f"User Authenticated: {user.pu_email} (ID: {user.id})")

            except jwt.ExpiredSignatureError:
                return Response({'error': 'Token has expired'}, status=401)
            except jwt.InvalidTokenError:
                return Response({'error': 'Invalid token'}, status=401)

            try:
                amount = Decimal(amount_str).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
                # amount = 1

                if amount <= 0:
                    return Response({'error': 'Amount must be greater than 0'}, status=400)
                self.write_to_log(f"✓ Validated Amount: ₹{amount}")
            except (ValueError, TypeError, InvalidOperation):
                return Response({'error': 'Invalid amount format'}, status=400)

            pg_id = 5  
            payment_gateway = get_object_or_404(PaymentGateway, id=pg_id)
            self.write_to_log(f"✓ Payment Gateway: {payment_gateway.name}")

            card_type = get_object_or_404(CardType, id=card_type_instance.id)

            retailer = user
            retailer_details = get_object_or_404(PortalUserDetails, pu=retailer)
            self.write_to_log(f"Retailer Details: {retailer_details.pud_id}")



            user_service_finance = None
            instant_charge_percent = Decimal('0.00')
            if is_instant:
                print("\n--- Instant Payment: Checking Limit & Charge ---")
                try:
                    user_service_finance = UserServiceFinance.objects.filter(
                        user=retailer
                    ).first()
                    if not user_service_finance:
                        print("No instant finance configuration found for user")
                        return Response({
                            'status': 'error',
                            'error': 'Instant payment not configured for your account. Please contact administrator.'
                        }, status=400)
                    instant_limit = Decimal(str(user_service_finance.od_limit))
                    instant_charge_percent = Decimal(str(user_service_finance.instant_charge))
                    available_limit = Decimal(str(user_service_finance.available_limit))
                    print(f"User OD Limit: ₹{instant_limit}")
                    print(f"Instant Charge: {instant_charge_percent}%")
                    print(f"Current Amount: ₹{amount}")
                    if amount > available_limit:
                        print(f"Insufficient Limit! Required: ₹{amount}, Available: ₹{available_limit}")
                        return Response({
                            'status': 'error',
                            'error': f'Insufficient instant payment limit. Transaction amount: ₹{amount}. Available limit: ₹{available_limit}.'
                        }, status=400)
                    print(f"Sufficient Limit. Remaining after transaction: ₹{available_limit - amount}")
                except Exception as e:
                    print(f"Error checking instant limit: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return Response({
                        'status': 'error',
                        'error': 'Failed to verify instant payment limit. Please try again.'
                    }, status=500)

            self.write_to_log("\n--- Charge Lookup ---")
            try:
                retailer_charge = UserCharge.objects.get(
                    user_id=retailer.id, 
                    pg=payment_gateway, 
                    card_type=card_type
                )
                charge_percent = retailer_charge.charge_percent
                self.write_to_log(f"✓ Retailer-specific charge: {charge_percent}%")
            except UserCharge.DoesNotExist:
                self.write_to_log("⚠ Retailer charge not found, checking PG base charge...")
                try:
                    # Map username prefix to role
                    prefix_role_map = {
                        "SD": "Super Distributor",
                        "MD": "Master Distributor",
                        "DT": "Distributor",
                        "RT": "Retailer",
                        "AD": "Admin",
                    }
                    
                    # Get username and extract prefix
                    username = retailer.pu_username if hasattr(retailer, 'pu_username') else str(retailer.username)
                    user_prefix = username[:2].upper() if username else ""
                    user_role = prefix_role_map.get(user_prefix, "Retailer")
                    
                    self.write_to_log(f"Username: {username}")
                    self.write_to_log(f"Prefix: {user_prefix}")
                    self.write_to_log(f"Determined Role: {user_role}")
                    
                    pg_base_charge = PGBaseCharge.objects.get(
                        pg=payment_gateway, 
                        card_type=card_type,
                        role=user_role  # THIS IS THE CRITICAL FILTER
                    )
                    charge_percent = pg_base_charge.charge_percent
                    self.write_to_log(f"✓ PG base charge for {user_role}: {charge_percent}%")
                    
                except PGBaseCharge.DoesNotExist:
                    self.write_to_log(f"❌ No PG base charge found for role: {user_role}")
                    return Response({
                        "status": False, 
                        "message": f"No applicable charge percent found for {user_role}."
                    }, status=400)
                    
                except PGBaseCharge.MultipleObjectsReturned:
                    self.write_to_log(f"⚠ Multiple charges found for {user_role}, using first one")
                    pg_base_charge = PGBaseCharge.objects.filter(
                        pg=payment_gateway, 
                        card_type=card_type,
                        role=user_role
                    ).first()
                    
                    if pg_base_charge:
                        charge_percent = pg_base_charge.charge_percent
                        self.write_to_log(f"✓ Using charge: {charge_percent}%")
                    else:
                        return Response({
                            "status": False, 
                            "message": f"No applicable charge percent found."
                        }, status=400)
            
            
            total_charge_percent = charge_percent + instant_charge_percent
            total_charge_amount = (amount * total_charge_percent) / Decimal('100')
            net_credit_to_user = amount - total_charge_amount

            self.write_to_log(f"Charge Amount: ₹{total_charge_amount}")
            self.write_to_log(f"Net Credit: ₹{net_credit_to_user}")



            service_provider = AdServiceProvider.objects.filter(
                service__service_name='PG',
                pg=payment_gateway  
            ).first()
           
                
            if card_type.name.lower() == 'rupay':
                mdr_percent = service_provider.rupay_mdr
            elif card_type.name.lower() == 'mastercard':
                mdr_percent = service_provider.mastercard_mdr
            elif card_type.name.lower() == 'visa':
                mdr_percent = service_provider.visa_mdr
            else:
                mdr_percent = Decimal('0.00')

            mdr_amount = (amount * mdr_percent / Decimal('100')).quantize(Decimal('0.00'))
            gst_amount = (mdr_amount * service_provider.gst_percentage / Decimal('100')).quantize(Decimal('0.00'))
            receivable_amount = (amount - mdr_amount - gst_amount).quantize(Decimal('0.00'))

            state_name = ""
            city_name = ""
            if retailer_details.state_id:
                state = State.objects.filter(state_id=retailer_details.state_id).first()
                if state:
                    state_name = state.state_name

            if retailer_details.city_id:
                city = City.objects.filter(city_id=retailer_details.city_id).first()
                if city:
                    city_name = city.city_name

            s = ''.join(ch for ch in str(credit_card_num) if ch.isdigit())
            last4 = ""
            masked_pan = ""
            bin_number = ""
            
            if len(s) >= 4:
                last4 = s[-4:]
                masked_pan = f"XXXX-XXXX-XXXX-{last4}"
                bin_number = s[:6] if len(s) >= 6 else s[:4]

            self.write_to_log(f"\n--- Card Details ---")
            self.write_to_log(f"BIN: {bin_number}")
            self.write_to_log(f"Masked: {masked_pan}")
            self.write_to_log(f"Last 4: {last4}")

            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            order_id = f"VGH{timestamp}"
            self.write_to_log(f"\n✓ Order ID Generated: {order_id}")

            amount_for_signature = f"{amount:.2f}"
            
            signature_string = f"{order_id}|{VEGAAH_TERMINAL_ID}|{VEGAAH_PASSWORD}|{VEGAAH_MERCHANT_ID}|{amount_for_signature}|{VEGAAH_CURRENCY}"
            signature = hashlib.sha256(signature_string.encode()).hexdigest()

            self.write_to_log("\n--- Signature Generation ---")
            self.write_to_log(f"Format: orderId|terminalId|password|merchantId|amount|currency")
            self.write_to_log(f"String: {signature_string}")
            self.write_to_log(f"SHA256: {signature[:20]}...{signature[-20:]}")

            payload = {
                "terminalId": VEGAAH_TERMINAL_ID,
                "password": VEGAAH_PASSWORD,
                "signature": signature,
                "paymentType": "1",
                "amount": amount_for_signature,
                "currency": VEGAAH_CURRENCY,
                "order": {
                    "orderId": order_id,
                    "description": f"Payment for order {order_id}"
                },
                "customer": {
                    "customerEmail": user.pu_email,
                    "billingAddressStreet": retailer_details.address or "",
                    "billingAddressCity": city_name or "",
                    "billingAddressState": state_name or "",
                    "billingAddressPostalCode": str(retailer_details.zip_code or ""),
                    "billingAddressCountry": "IN"
                },
                "returnUrl": {
                    "webhookUrl": f"{BACKEND_BASE_URL}/admin_hub/vegaah-webhook-test-2"
                }
            }

            self.write_to_log("\n---Vegaah API Request ---")
            self.write_to_log(f"URL: {VEGAAH_API_URL2}")
            self.write_to_log(json.dumps(payload, indent=2))

            try:
                self.write_to_log("\nSending request to Vegaah API...")
                
                resp = requests.post(
                    VEGAAH_API_URL2, 
                    json=payload, 
                    headers={'Content-Type': 'application/json'}, 
                    timeout=60 
                )
                
                self.write_to_log(f"✓ Response Status: {resp.status_code}")
                api_response = resp.json()
                
            except requests.exceptions.Timeout:
                self.write_to_log("Request timeout")
                return Response({
                    'status': 'error',
                    'error': 'Payment gateway is taking too long to respond. Please try again.'
                }, status=504)
            except requests.exceptions.ConnectionError as e:
                self.write_to_log(f"Connection error: {str(e)}")
                return Response({
                    'status': 'error',
                    'error': 'Unable to connect to payment gateway. Please check your internet connection.'
                }, status=503)
            except requests.exceptions.RequestException as e:
                self.write_to_log(f"Request error: {str(e)}")
                return Response({
                    'status': 'error',
                    'error': f'Failed to connect with payment gateway: {str(e)}'
                }, status=500)
            except ValueError as e:
                self.write_to_log(f"Invalid JSON response: {str(e)}")
                return Response({
                    'status': 'error',
                    'error': 'Invalid response from payment gateway'
                }, status=500)

            self.write_to_log("\n---API Response ---")
            self.write_to_log(json.dumps(api_response, indent=2))

            response_code = api_response.get('responseCode')
            
            if not response_code:
                error_msg = api_response.get('message', 'Payment link generation failed')
                self.write_to_log(f"No response code: {error_msg}")
                return Response({
                    'status': 'error',
                    'error': error_msg
                }, status=400)

            if response_code != '001':
                error_desc = api_response.get('responseDescription', 'Payment request failed')
                self.write_to_log(f"Payment failed: {error_desc}")
                return Response({
                    'status': 'error',
                    'error': error_desc
                }, status=400)

            transaction_id = api_response.get('transactionId')
            order_details = api_response.get('orderDetails', {})
            payment_link_data = api_response.get('paymentLink', {})
            
            self.write_to_log(f"\nTransaction ID: {transaction_id}")

            self.write_to_log("\n--- Saving Transaction ---")
            
            pg_service_trn = PgServiceTrn.objects.create(
                trn_unique_id=order_id,
                trn_amount=amount,
                trn_response=api_response,
                pg=payment_gateway,
                card_type=card_type,
                is_settled=False,
                trn_status="PENDING",
                created_by=retailer.id,
                buyer_email=user.pu_email,
                buyer_phone=mobile,
                buyer_firstname=customer_name.split()[0] if customer_name else "",
                buyer_lastname=customer_name.split()[1] if customer_name and len(customer_name.split()) > 1 else "",
                buyer_address=state_name or "",
                buyer_city=city_name or "",
                buyer_state=state_name or "",
                buyer_country="India",
                buyer_pincode=retailer_details.zip_code or 0,
                retailer_charge_percent=total_charge_percent,
                total_charge_amount=total_charge_amount,
                net_credit_to_user=net_credit_to_user,
                is_instant=is_instant,
                sp_mdr_amount=mdr_amount,
                sp_gst_amount=gst_amount,
                sp_receivable_amount=receivable_amount
            )

            self.write_to_log(f"Transaction saved (DB ID: {pg_service_trn.pg_trn_id})")

            payment_link_base = payment_link_data.get('linkUrl', '')
            payment_link = f"{payment_link_base}{transaction_id}" if payment_link_base and transaction_id else ""

            self.write_to_log(f"\n Payment Link: {payment_link}")
            self.write_to_log("="*60)

            return Response({
                'status': 'success',
                'message': 'Payment link generated successfully',
                'data': {
                    'paymentLink': payment_link,
                    'transactionId': transaction_id,
                    'orderId': order_id,
                    'amount': str(amount),
                    'responseCode': response_code,
                    'responseDescription': api_response.get('responseDescription', ''),
                    'transactionDateTime': api_response.get('transactionDateTime', ''),
                    'authProfile': auth_profile_name
                }
            }, status=200)

        except PortalUser.DoesNotExist:
            self.write_to_log("User not found")
            return Response({'status': 'error', 'error': 'User not found'}, status=404)
        except PortalUserDetails.DoesNotExist:
            self.write_to_log("User details not found")
            return Response({'status': 'error', 'error': 'User details not found'}, status=404)
        except Exception as e:
            self.write_to_log("Unexpected error occurred")
            import traceback
            self.write_to_log(traceback.format_exc())
            return Response({'status': 'error', 'error': f'An unexpected error occurred: {str(e)}'}, status=500)
        

@csrf_exempt
@require_POST
def vegaah_webhook_2(request):
    try:
        data = json.loads(request.body)
        VegaahPgLogs.objects.create(
            order_id=data.get('orderId', ''),
            request=data,           
            response={}             
        )

        response_code = data.get('responseCode', '')
        result = data.get('result', '')
        response_desc = data.get('responseDescription', '')
        transaction_id = data.get('transactionId', '')
        order_id = data.get('orderId', '')
        amount = data.get('amount', '')
        terminal_id = data.get('terminalId', '')

        pg_service_trn = PgServiceTrn.objects.filter(
            trn_unique_id=order_id
        ).first()

        if pg_service_trn:
            if result.upper() == 'SUCCESS' and response_code == '000':
                pg_service_trn.trn_status = 'COMPLETED'
                retailer = pg_service_trn.created_by
                user_finance = UserServiceFinance.objects.filter(
                    user_id=retailer
                ).first()

                if pg_service_trn.is_instant:
                    if user_finance:
                        txn_amount = Decimal(str(amount))
                        user_finance.usage_limit += txn_amount
                        user_finance.available_limit -= txn_amount
                        user_finance.save()
                        print(f"Instant Transaction Update → usage_limit: {user_finance.usage_limit}, available_limit: {user_finance.available_limit}")
                    else:
                        print("No UserServiceFinance record found for instant transaction!")
                else:
                    print("Not an instant transaction — finance not updated.")
            elif result.upper() == 'FAILED':
                pg_service_trn.trn_status = 'FAILED'
            else:
                pg_service_trn.trn_status = 'PENDING'

            pg_service_trn.trn_response = data
            pg_service_trn.save()

            latest_log = VegaahPgLogs.objects.filter(order_id=order_id).order_by('-created_at').first()
            if latest_log:
                latest_log.response = data
                latest_log.save()
        else:
            print("Transaction not found for order_id:", order_id, data)

    except Exception as e:
        print("Webhook Exception:", str(e))

    return JsonResponse({'success': 'true'}, status=200)  





class CommissionListView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]
    
    def post(self, request):
        try:
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            distributor_id = request.data.get('distributor_id')
            retailer_id = request.data.get('retailer_id')
            service_provider_id = request.data.get('service_provider_id')
            settlement_status = request.data.get('status')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date')
            transaction_id = request.data.get('transaction_id')
            
            if not distributor_id:
                return Response({
                    'st': False,
                    'msg': 'Distributor ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            print("Filtering CommissionTransaction for distributor_id:", distributor_id)
            print("Status filter:", settlement_status)  

            queryset = CommissionTransaction.objects.select_related(
                'distributor', 'retailer', 'service_provider'
            ).filter(
                distributor_id=distributor_id
            ).order_by('-created_at')

            print("Generated SQL Query:", str(queryset.query))

           
            if retailer_id:
                queryset = queryset.filter(retailer_id=retailer_id)
            
            if service_provider_id:
                queryset = queryset.filter(service_provider_id=service_provider_id)
            
            if settlement_status and settlement_status.strip():
                queryset = queryset.filter(settlement_status=settlement_status)
                print(f"Applied status filter: {settlement_status}") 
            else:
                print("No status filter applied (showing all)") 
            
            if start_date:
                try:
                    start_datetime = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                    queryset = queryset.filter(created_at__gte=start_datetime)
                except ValueError:
                    pass
            
            if transaction_id and transaction_id.strip():
                queryset = queryset.filter(transaction_id__icontains=transaction_id)
                print(f"Applied transaction_id filter: {transaction_id}")
            if end_date:
                try:
                    end_datetime = datetime.datetime.strptime(end_date, "%Y-%m-%d")
                    end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                    queryset = queryset.filter(created_at__lte=end_datetime)
                except ValueError:
                    pass

            summary_queryset = CommissionTransaction.objects.filter(
                distributor_id=distributor_id
            )

            today = timezone.localtime().date()
            yesterday = today - timedelta(days=1)
            current_month = today.month
            current_year = today.year

            today_start = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
            today_end = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))
            yesterday_start = timezone.make_aware(datetime.datetime.combine(yesterday, datetime.time.min))
            yesterday_end = timezone.make_aware(datetime.datetime.combine(yesterday, datetime.time.max))

            summary = summary_queryset.aggregate(
                total_unsettled=Sum('amount', filter=Q(settlement_status='UNSETTLED')),
                today_commission=Sum('amount', filter=Q(created_at__gte=today_start, created_at__lte=today_end)),
                yesterday_commission=Sum('amount', filter=Q(created_at__gte=yesterday_start, created_at__lte=yesterday_end)),
                month_commission=Sum('amount', filter=Q(created_at__year=current_year, created_at__month=current_month))
            )

            print("\n===== Commission Summary Debug =====")
            print(f"Today Range: {today_start} -> {today_end}")
            print(f"Yesterday Range: {yesterday_start} -> {yesterday_end}")
            print("Summary Data:", summary)
            print("====================================\n")

            total_items = queryset.count()
            total_pages = (total_items + page_size - 1) // page_size
            start = (page_number - 1) * page_size
            end = start + page_size

            paginated_data = queryset[start:end]
            
            print(f"Total items after filtering: {total_items}")  
            print(f"Paginated data count: {len(paginated_data)}")  

            commission_list = []
            for item in paginated_data:
                commission_list.append({
                    'commission_id': item.id,
                    'transaction_id': item.transaction_id,
                    'distributor': {
                        'id': item.distributor.id,
                        'name': item.distributor.pu_name,
                        'username': item.distributor.username
                    },
                    'retailer': {
                        'id': item.retailer.id,
                        'name': item.retailer.pu_name,
                        'username': item.retailer.username
                    },
                    'service_provider': {
                        'id': item.service_provider.sp_id,
                        'name': item.service_provider.sp_name,
                        'label': item.service_provider.label,
                        'service_name': item.service_provider.service.service_name
                    },
                    'amount': float(item.amount or 0),
                    'settlement_status': item.settlement_status,
                    'settlement_mode': item.settlement_mode,
                    'settlement_date': item.settlement_date,
                    'created_at': item.created_at
                })

            print(f"Commission List count: {len(commission_list)}")
            print("=========================================\n")

            return Response({
                'st': True,
                'msg': 'Commission data fetched successfully',
                'resData': {
                    'commissions': commission_list,
                    'summary': {
                        'total_unsettled': float(summary.get('total_unsettled') or 0),
                        'today_commission': float(summary.get('today_commission') or 0),
                        'yesterday_commission': float(summary.get('yesterday_commission') or 0),
                        'month_commission': float(summary.get('month_commission') or 0)
                    },
                    'pagination': {
                        'page_number': page_number,
                        'page_size': page_size,
                        'total_items': total_items,
                        'total_pages': total_pages
                    }
                }
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"Error in CommissionListView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'st': False,
                'msg': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DistributorListView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]
    
    def get(self, request):
        try:
            search_username = request.query_params.get('username', None)
            
            distributors = PortalUser.objects.filter(
                pu_role='DISTRIBUTOR',
                is_deleted=False,
                is_deactive=False,
                pu_status='APPROVED'
            )
            
            if search_username:
                distributors = distributors.filter(username__iexact=search_username)
            
            distributors = distributors.values(
                'id', 'pu_name', 'username', 'pu_email', 'pu_contact_no'
            ).order_by('pu_name')
            
            distributor_list = []
            for dist in distributors:
                distributor_list.append({
                    'value': str(dist['id']),
                    'label': f"{dist['pu_name']} ({dist['username']})",
                    'name': dist['pu_name'],
                    'username': dist['username'],
                    'email': dist['pu_email'],
                    'contact': dist['pu_contact_no']
                })
            
            return Response({
                'status': 'success',
                'message': 'Distributors fetched successfully',
                'data': distributor_list
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RetailerCommissionListView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]
    
    def post(self, request):
        try:
            user = request.user
            
            if user.pu_role != 'RETAILER':
                return Response({
                    'st': False,
                    'msg': 'Only retailers can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            settlement_status = request.data.get('status')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date')
            service_provider_id = request.data.get('service_provider_id')  
            transaction_id = request.data.get('transaction_id')  
            
            queryset = CommissionTransaction.objects.select_related(
                'distributor', 'retailer', 'service_provider'
            ).filter(
                retailer=user
            ).order_by('-created_at')
            
            if settlement_status:
                queryset = queryset.filter(settlement_status=settlement_status)
            
            if service_provider_id:
                try:
                    sp_id = int(service_provider_id)
                    queryset = queryset.filter(service_provider_id=sp_id)
                except (ValueError, TypeError):
                    pass
            
            if start_date:
                try:
                    start_datetime = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                    queryset = queryset.filter(created_at__gte=start_datetime)
                except ValueError:
                    pass

            if transaction_id:
                queryset = queryset.filter(transaction_id__icontains=transaction_id.strip())
            
            
            if end_date:
                try:
                    end_datetime = datetime.datetime.strptime(end_date, "%Y-%m-%d")
                    end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                    queryset = queryset.filter(created_at__lte=end_datetime)
                except ValueError:
                    pass

            summary_queryset = CommissionTransaction.objects.filter(retailer=user)
            
            if service_provider_id:
                try:
                    sp_id = int(service_provider_id)
                    summary_queryset = summary_queryset.filter(service_provider_id=sp_id)
                except (ValueError, TypeError):
                    pass

            today = timezone.localtime().date()
            yesterday = today - timedelta(days=1)
            current_month = today.month
            current_year = today.year

            today_start = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
            today_end = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))
            yesterday_start = timezone.make_aware(datetime.datetime.combine(yesterday, datetime.time.min))
            yesterday_end = timezone.make_aware(datetime.datetime.combine(yesterday, datetime.time.max))

            summary = summary_queryset.aggregate(
                total_unsettled=Sum('amount', filter=Q(settlement_status='UNSETTLED')),
                today_commission=Sum('amount', filter=Q(created_at__gte=today_start, created_at__lte=today_end)),
                yesterday_commission=Sum('amount', filter=Q(created_at__gte=yesterday_start, created_at__lte=yesterday_end)),
                month_commission=Sum('amount', filter=Q(created_at__year=current_year, created_at__month=current_month))
            )

            total_items = queryset.count()
            total_pages = (total_items + page_size - 1) // page_size
            start = (page_number - 1) * page_size
            end = start + page_size

            paginated_data = queryset[start:end]

            commission_list = []
            for item in paginated_data:
                commission_list.append({
                    'commission_id': item.id,
                    'transaction_id': item.transaction_id,
                    'distributor': {
                        'id': item.distributor.id,
                        'name': item.distributor.pu_name,
                        'username': item.distributor.username
                    },
                    'service_provider': {
                        'id': item.service_provider.sp_id,
                        'name': item.service_provider.sp_name,
                        'label': item.service_provider.label,
                        'service_name': item.service_provider.service.service_name
                    },
                    'amount': float(item.amount or 0),
                    'settlement_status': item.settlement_status,
                    'settlement_mode': item.settlement_mode,
                    'settlement_date': item.settlement_date,
                    'created_at': item.created_at
                })

            return Response({
                'st': True,
                'msg': 'Commission data fetched successfully',
                'resData': {
                    'commissions': commission_list,
                    'summary': {
                        'total_unsettled': float(summary.get('total_unsettled') or 0),
                        'today_commission': float(summary.get('today_commission') or 0),
                        'yesterday_commission': float(summary.get('yesterday_commission') or 0),
                        'month_commission': float(summary.get('month_commission') or 0)
                    },
                    'pagination': {
                        'page_number': page_number,
                        'page_size': page_size,
                        'total_items': total_items,
                        'total_pages': total_pages
                    }
                }
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"Error in RetailerCommissionListView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'st': False,
                'msg': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.utils.timezone import now
import logging

logger = logging.getLogger('commission_audit')




from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Q

class CommissionAutoSettlementConfigView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def get_distributor_obj(self, distributor_id: int):
        if not distributor_id:
            return None
        return PortalUser.objects.filter(id=distributor_id).first()

    def get(self, request):
        distributor_id = request.query_params.get("distributor_id")
        list_all = request.query_params.get("list")
        search = request.query_params.get("search")
        role = request.query_params.get("role")

        try:
            if search or role:
                distributors = PortalUser.objects.all()
                if search:
                    distributors = distributors.filter(
                        Q(pu_name__icontains=search) | Q(username__icontains=search)
                    )
                if role:
                    distributors = distributors.filter(pu_role=role)
                
                data = []
                for dist in distributors:
                    config = CommissionAutoSettlementConfig.objects.filter(distributor=dist).first()
                    data.append({
                        "distributor_id": dist.id,
                        "distributor_name": dist.pu_name,
                        "distributor_role": dist.pu_role,
                        "auto_settlement_delay_days": config.auto_settlement_delay_days if config else 1,
                        "is_active": config.is_active if config else True,
                        "config_id": config.id if config else None
                    })
                return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)

            if list_all:
                configs = CommissionAutoSettlementConfig.objects.all().select_related('distributor')
                data = []
                for config in configs:
                    data.append({
                        "config_id": config.id,
                        "distributor_id": config.distributor.id if config.distributor else None,
                        "distributor_name": config.distributor.pu_name if config.distributor else "Global Default",
                        "distributor_role": config.distributor.pu_role if config.distributor else None,
                        "auto_settlement_delay_days": config.auto_settlement_delay_days,
                        "is_active": config.is_active,
                    })
                return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)

            distributor = self.get_distributor_obj(distributor_id) if distributor_id else None
            config = CommissionAutoSettlementConfig.objects.filter(distributor=distributor).first()

            if not config:
                data = {
                    "config_id": None,
                    "distributor_id": distributor.id if distributor else None,
                    "distributor_name": distributor.pu_name if distributor else "Global Default",
                    "distributor_role": distributor.pu_role if distributor else None,
                    "auto_settlement_delay_days": 1,
                    "is_active": True,
                }
            else:
                data = {
                    "config_id": config.id,
                    "distributor_id": distributor.id if distributor else None,
                    "distributor_name": distributor.pu_name if distributor else "Global Default",
                    "distributor_role": distributor.pu_role if distributor else None,
                    "auto_settlement_delay_days": config.auto_settlement_delay_days,
                    "is_active": config.is_active,
                }

            return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"status": "fail", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    def post(self, request):
        distributor_id = request.data.get("distributor_id")
        delay_days = request.data.get("auto_settlement_delay_days")
        is_active = request.data.get("is_active", True)


        print(distributor_id,delay_days,is_active)

        try:
            delay_days = int(delay_days)
        except (TypeError, ValueError):
            return Response(
                {"status": "fail", "message": "Invalid delay days"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if delay_days < 0:
            return Response(
                {"status": "fail", "message": "Delay days cannot be negative"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        distributor = None
        if distributor_id:
            distributor = PortalUser.objects.filter(id=distributor_id).first()
            if not distributor:
                return Response(
                    {"status": "fail", "message": "Distributor not found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )

        config, created = CommissionAutoSettlementConfig.objects.update_or_create(
            distributor=distributor,
            defaults={
                "auto_settlement_delay_days": delay_days, 
                "is_active": is_active, 
                "created_by": request.user
            },
        )

        return Response(
            {
                "status": "success",
                "message": "Configuration created" if created else "Configuration updated",
                "data": {
                    "config_id": config.id,
                    "distributor_id": distributor.id if distributor else None,
                    "distributor_name": distributor.pu_name if distributor else "Global Default",
                    "distributor_role": distributor.pu_role if distributor else None,
                    "auto_settlement_delay_days": config.auto_settlement_delay_days,
                    "is_active": config.is_active,
                },
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


    @transaction.atomic
    def delete(self, request):
        config_id = request.data.get("config_id")
        
        if not config_id:
            return Response(
                {"status": "fail", "message": "Config ID required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        config = CommissionAutoSettlementConfig.objects.filter(id=config_id).first()
        if not config:
            return Response(
                {"status": "fail", "message": "Configuration not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        if config.distributor is None:
            return Response(
                {"status": "fail", "message": "Cannot delete global configuration"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        config.delete()
        return Response(
            {"status": "success", "message": "Configuration deleted"}, 
            status=status.HTTP_200_OK
        )

class ManualCommissionSettlementView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    @transaction.atomic
    def post(self, request):
        from admin_hub.settlement_utils import settle_commissions

        try:
            commission_ids = (
                request.data.get('commission_ids') or
                request.data.getlist('commission_ids[]') or
                []
            )
            print("=== DEBUG COMMISSION SETTLEMENT ===")
            print("Raw request data:", request.data)
            print("Resolved commission_ids:", commission_ids)
            print("Performed by:", request.user.username)

            if not commission_ids:
                return Response({
                    'status': 'fail',
                    'message': 'commission_ids are required'
                }, status=status.HTTP_400_BAD_REQUEST)

            results = settle_commissions(
                commission_ids=commission_ids,
                performed_by=request.user,
                mode='MANUAL'
            )

            print("Settlement results:", results)

            return Response({
                'status': 'success',
                'message': f"Successfully settled {sum([r.get('commission_count', 0) for r in results])} commissions",
                'data': results
            }, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            print("Exception during commission settlement:")
            traceback.print_exc()  

            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class AutoCommissionSettlementCronView(APIView):
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        from admin_hub.settlement_utils import (
            get_eligible_commissions_for_auto_settlement,
            settle_commissions
        )
        
        try:
            eligible_commission_ids = get_eligible_commissions_for_auto_settlement()
            
            if not eligible_commission_ids:
                return Response({
                    'status': 'success',
                    'message': 'No eligible commissions found'
                }, status=status.HTTP_200_OK)
            
            results = settle_commissions(
                commission_ids=eligible_commission_ids,
                performed_by=None,
                mode='AUTO'
            )
            
            total_settled = sum([r['commission_count'] for r in results])
            total_amount = sum([float(r['total_amount']) for r in results])
            
            return Response({
                'status': 'success',
                'message': f'Successfully settled {total_settled} commissions',
                'data': {
                    'total_settled': total_settled,
                    'total_amount': str(total_amount),
                    'distributors_count': len(results)
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Auto-settlement failed: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





class ServiceProviderListView(APIView):
    def get(self, request):
        try:
            providers = AdServiceProvider.objects.all()
            serializer = ServiceProviderSerializer(providers, many=True)
            return Response({
                "status": "success",
                "message": "Service providers fetched successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            print("Error fetching service providers:", e)
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import connection
from admin_hub.models import WalletTrn, CommissionTransaction, PortalUser

class PgTransactionDetailsView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin | IsDistributor]

    def get(self, request, wl_trn_id):
        try:
            wallet_trn = get_object_or_404(WalletTrn, wl_trn_id=wl_trn_id)
            
            if wallet_trn.action_type != 'Commission Settlement':
                return Response({
                    'status': 'fail',
                    'message': 'This is not a commission settlement transaction'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        id, 
                        total_amount, 
                        mode, 
                        reference_commissions, 
                        distributor_id, 
                        performed_by_id, 
                        created_at
                    FROM ad_commission_settlement_log
                    WHERE id = %s
                """, [wallet_trn.action_id])
                
                row = cursor.fetchone()
                
                if not row:
                    return Response({
                        'status': 'fail',
                        'message': 'Settlement log not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                settlement_log_raw = {
                    'id': row[0],
                    'total_amount': row[1],
                    'mode': row[2],
                    'reference_commissions': row[3],
                    'distributor_id': row[4],
                    'performed_by_id': row[5],
                    'created_at': row[6]
                }
            
            commission_ids = settlement_log_raw['reference_commissions']
            
            if isinstance(commission_ids, str):
                try:
                    commission_ids = json.loads(commission_ids)
                except:
                    try:
                        commission_ids = eval(commission_ids)
                    except:
                        commission_ids = []
            
            if not isinstance(commission_ids, list):
                commission_ids = list(commission_ids) if commission_ids else []
            
            print(f"Commission IDs: {commission_ids}, Type: {type(commission_ids)}")
            
            # Get distributor and performed_by details
            distributor = get_object_or_404(PortalUser, id=settlement_log_raw['distributor_id'])
            performed_by = None
            if settlement_log_raw['performed_by_id']:
                performed_by = PortalUser.objects.filter(id=settlement_log_raw['performed_by_id']).first()
            
            # Get all commission transactions related to this settlement
            commissions = CommissionTransaction.objects.filter(
                id__in=commission_ids
            ).select_related('distributor', 'retailer', 'service_provider')
            
            commission_details = []
            for comm in commissions:
                commission_details.append({
                    'id': comm.id,
                    'transaction_id': comm.transaction_id,
                    'retailer_name': comm.retailer.username,
                    'retailer_id': comm.retailer.id,
                    'service_provider': comm.service_provider.sp_name,
                    'amount': str(comm.amount),
                    'settlement_status': comm.settlement_status,
                    'settlement_mode': comm.settlement_mode,
                    'settlement_date': comm.settlement_date.strftime('%Y-%m-%d %H:%M:%S') if comm.settlement_date else None,
                    'created_at': comm.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                })
            
            response_data = {
                'wallet_transaction': {
                    'id': wallet_trn.wl_trn_id,
                    'label': wallet_trn.wl_label,
                    'amount': str(wallet_trn.effectvie_amt),
                    'type': wallet_trn.effective_type,
                    'current_balance': str(wallet_trn.current_balance),
                    'date': wallet_trn.wl_trn_dt.strftime('%Y-%m-%d %H:%M:%S'),
                },
                'settlement_details': {
                    'id': settlement_log_raw['id'],
                    'distributor_name': distributor.username,
                    'distributor_id': distributor.id,
                    'total_amount': str(settlement_log_raw['total_amount']),
                    'mode': settlement_log_raw['mode'],
                    'performed_by': performed_by.username if performed_by else 'SYSTEM',
                    'created_at': settlement_log_raw['created_at'].strftime('%Y-%m-%d %H:%M:%S'),
                    'commission_count': len(commission_ids),
                },
                'commissions': commission_details
            }
            
            return Response({
                'status': 'success',
                'data': response_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            print("Exception in PgTransactionDetailsView:")
            traceback.print_exc()
            
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CronListView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request):
        try:
            cron = CronJobConfiguration.objects.filter(is_active=True).first()

            if not cron:
                return Response({
                    "status": False,
                    "data": None
                }, status=status.HTTP_200_OK)
            print(cron,'=========================>>>>>>>>>>>>>>>>>>>>>>')
            data = {
                "id": cron.id,
                "name": cron.name,
                "cron_url" : cron.cron_url.strip(),
                "description": cron.description,
                "is_active": cron.is_active,
                "created_at": cron.created_at,
                "updated_at": cron.updated_at,
            }

            return Response({
                "status": True,
                "data": data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print("Error fetching cron:", e)
            return Response({
                "status": False,
                "data": None
            }, status=status.HTTP_200_OK)


from rest_framework.pagination import PageNumberPagination

import math


class DistributorCommissionStatsView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor] 

    def get(self, request):
        try:
            distributor = request.user
            
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            
            yesterday_start = (today_start - timedelta(days=1))
            yesterday_end = today_start - timedelta(microseconds=1)
            
            month_start = today_start.replace(day=1)
            
            total_settled = CommissionTransaction.objects.filter(
                distributor=distributor,
                settlement_status__in=[
                    CommissionSettlementStatus.MANUAL_SETTLED,
                    CommissionSettlementStatus.AUTO_SETTLED
                ]
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            today_commission = CommissionTransaction.objects.filter(
                distributor=distributor,
                created_at__range=[today_start, today_end]
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            yesterday_commission = CommissionTransaction.objects.filter(
                distributor=distributor,
                created_at__range=[yesterday_start, yesterday_end]
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            this_month_commission = CommissionTransaction.objects.filter(
                distributor=distributor,
                created_at__gte=month_start
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            data = {
                "total_settled": float(total_settled),
                "today_commission": float(today_commission),
                "yesterday_commission": float(yesterday_commission),
                "this_month_commission": float(this_month_commission)
            }
            
            return Response({
                "status": True,
                "data": data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            print("Error fetching distributor commission stats:", e)
            return Response({
                "status": False,
                "message": "Error fetching commission statistics",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

class DistributorCommissionListView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor]
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        return self._handle_request(request)
    
    def post(self, request):
        return self._handle_request(request)

    def _handle_request(self, request):
        try:
            distributor = request.user
            
            if request.method == 'POST':
                params = request.data
            else:
                params = request.query_params
            
            filter_by = params.get('filter_by', 'UNSETTLED')
            page_number = int(params.get('page_number', params.get('page', 1)))
            page_size = int(params.get('page_size', 50))
            search = params.get('search', '').strip()
            
            stats_data = self._get_commission_stats(distributor, filter_by)
            paginated_response = self._get_commission_list(
                distributor, filter_by, page_number, page_size, search, request
            )
            
            total_pages = math.ceil(
                paginated_response['count'] / page_size
            ) if paginated_response['count'] > 0 else 1
            

            results_with_metadata = paginated_response['results'].copy() if paginated_response['results'] else []
            
            return Response({
                "status": True,
                "message": "Commission data fetched successfully",
                "data": {
                    "results": results_with_metadata,
                    
                    "total_pages": total_pages,
                    "total_items": paginated_response['count'],
                    "current_page": page_number,
                    "stats": stats_data, 
                    
                    "count": paginated_response['count'],
                    "next": paginated_response['next'],
                    "previous": paginated_response['previous'],
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print("Error:", e)
            import traceback
            traceback.print_exc()
            return Response({
                "status": False,
                "message": "Error fetching commission data",
                "data": {"results": []}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_date_ranges(self):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(microseconds=1)
        
        month_start = today_start.replace(day=1)
        
        return {
            'today_start': today_start,
            'today_end': today_end,
            'yesterday_start': yesterday_start,
            'yesterday_end': yesterday_end,
            'month_start': month_start
        }

    def _get_base_filter(self, distributor, filter_by):
        if filter_by == 'SETTLED':
            base_filter = {
                "distributor": distributor,
                "settlement_status__in": [
                    CommissionSettlementStatus.MANUAL_SETTLED,
                    CommissionSettlementStatus.AUTO_SETTLED
                ]
            }
            date_field = "settlement_date"
        else:
            base_filter = {
                "distributor": distributor,
                "settlement_status": CommissionSettlementStatus.UNSETTLED
            }
            date_field = "created_at"
        
        return base_filter, date_field

    def _get_commission_stats(self, distributor, filter_by):
        date_ranges = self._get_date_ranges()
        base_filter, date_field = self._get_base_filter(distributor, filter_by)
        
        model = CommissionTransaction
        
        total_amount = model.objects.filter(**base_filter).aggregate(
            total=Sum('amount')
        )["total"] or Decimal("0.00")
        
        total_count = model.objects.filter(**base_filter).count()
        
        today_amount = model.objects.filter(
            **base_filter,
            **{f"{date_field}__range": [date_ranges['today_start'], date_ranges['today_end']]}
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        
        yesterday_amount = model.objects.filter(
            **base_filter,
            **{f"{date_field}__range": [date_ranges['yesterday_start'], date_ranges['yesterday_end']]}
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        
        this_month_amount = model.objects.filter(
            **base_filter,
            **{f"{date_field}__gte": date_ranges['month_start']}
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        
        return {
            "total_amount": float(total_amount),
            "total_count": total_count,
            "today_amount": float(today_amount),
            "yesterday_amount": float(yesterday_amount),
            "this_month_amount": float(this_month_amount),
            "filter_by": filter_by
        }

    def _get_commission_list(self, distributor, filter_by, page_number, page_size, search, request):
        base_filter, date_field = self._get_base_filter(distributor, filter_by)
        model = CommissionTransaction
        
        queryset = model.objects.filter(**base_filter).select_related(
            "retailer", "service_provider"
        )
        
        if search:
            queryset = queryset.filter(
                Q(transaction_id__icontains=search) |
                Q(retailer__username__icontains=search) |
                Q(retailer__unique_id__icontains=search) |
                Q(service_provider__name__icontains=search)
            )
        
        commissions = queryset.order_by(f"-{date_field}")
        
        start = (page_number - 1) * page_size
        end = start + page_size
        total_count = commissions.count()
        paginated_items = commissions[start:end]
        
        results = []
        for c in paginated_items:
            results.append({
                "id": c.id,
                "transaction_id": c.transaction_id,
                "retailer_name": c.retailer.username if c.retailer else "-",
                "retailer_id": c.retailer.username,
                "service_provider": c.service_provider.sp_name if c.service_provider else "-",
                "service_name": (
                    c.service_provider.service.service_name
                    if c.service_provider and c.service_provider.service
                    else "-"
                ),
                "amount": float(c.amount),
                "settlement_status": c.settlement_status,
                "settlement_mode": c.settlement_mode if hasattr(c, 'settlement_mode') else None,
                "settlement_date": (
                    c.settlement_date.strftime("%Y-%m-%d %H:%M:%S")
                    if c.settlement_date else None
                ),
                "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            })
        
        next_url = None
        previous_url = None
        if end < total_count:
            next_url = f"?page_number={page_number + 1}&page_size={page_size}"
        if page_number > 1:
            previous_url = f"?page_number={page_number - 1}&page_size={page_size}"
        
        return {
            'results': results,
            'count': total_count,
            'next': next_url,
            'previous': previous_url
        }


class DistributorCommissionPageStatsView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor]

    def get(self, request):
        return self._handle_request(request)
    
    def post(self, request):
        return self._handle_request(request)

    def _handle_request(self, request):
        try:
            distributor = request.user
            params = request.query_params if request.method == 'GET' else request.data
            filter_by = params.get('filter_by', 'UNSETTLED')
            
            view = DistributorCommissionListView()
            stats_data = view._get_commission_stats(distributor, filter_by)
            
            return Response({
                "status": True,
                "message": "Stats fetched successfully",
                "data": stats_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print("Error:", e)
            return Response({
                "status": False,
                "message": "Error fetching commission stats",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DistributorCommissionTransactionsView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor]
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        return self._handle_request(request)
    
    def post(self, request):
        return self._handle_request(request)

    def _handle_request(self, request):
        try:
            distributor = request.user
            params = request.query_params if request.method == 'GET' else request.data
            filter_by = params.get('filter_by', 'UNSETTLED')
            
            view = DistributorCommissionListView()
            view.pagination_class = self.pagination_class
            paginated_data = view._get_commission_list(distributor, filter_by, request)
            
            return Response({
                "status": True,
                **paginated_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print("Error:", e)
            return Response({
                "status": False,
                "message": "Error fetching commission transactions",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ServiceAccountRequestAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer | IsDistributor]

    def post(self, request):

        try:
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            
            user = request.user
            
            filter_requests = ServiceAccountRequest.objects.filter(
                pu=user
            ).order_by('-created_at')  # Latest first
            
            # Pagination
            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size
            
            paginated_requests = filter_requests[start_index:end_index]
            
            total_items = filter_requests.count()
            total_pages = (total_items + page_size - 1) // page_size
            
            serializer = ServiceAccountRequestSerializer(paginated_requests, many=True)
            
            formatted_data = []
            for item in serializer.data:
                if item.get('created_at'):
                    item['created_at'] = datetime.datetime.strptime(
                        item['created_at'], 
                        "%Y-%m-%dT%H:%M:%S.%f%z"
                    ).strftime("%Y-%m-%d %I:%M %p")
                formatted_data.append(item)
            
            response_data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': formatted_data
            }
            
            return Response({
                'status': 'success',
                'message': 'Service account requests retrieved successfully',
                'data': response_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    


class AdminServiceAccountRequestAPIView(APIView):

    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        try:
            if 'page_number' in request.data or 'page_size' in request.data:
                return self.fetch_service_account_requests(request)
            elif 'sar_id' in request.data and 'request_status' in request.data:
                return self.approve_reject_settlement(request)
            else:
                return Response({
                    'status': 'error',
                    'message': 'Invalid data'
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_service_account_requests(self, request):
        try:
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            status_filter = request.data.get('status', None)
            search = request.data.get('search', None)
            
            filter_requests = ServiceAccountRequest.objects.select_related('pu').all()

            if status_filter and status_filter.strip():
                filter_requests = filter_requests.filter(request_status=status_filter.upper())

            if search and search.strip():
                from django.db.models import Q
                filter_requests = filter_requests.filter(
                    Q(pu__pu_name__icontains=search) |
                    Q(pu__pu_contact_no__icontains=search)
                )

            filter_requests = filter_requests.order_by('-created_at')

            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size

            paginated_requests = filter_requests[start_index:end_index]

            total_items = filter_requests.count()
            total_pages = (total_items + page_size - 1) // page_size

            serializer = ServiceAccountRequestSerializer(paginated_requests, many=True)

            formatted_data = []
            for item in serializer.data:
                if item.get('created_at'):
                    try:
                        dt = datetime.datetime.fromisoformat(item['created_at'].replace("Z", "+00:00"))
                        item['created_at'] = dt.strftime("%d-%m-%Y %I:%M %p")
                    except:
                        pass

                formatted_data.append(item)

            response_data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': formatted_data
            }

            return Response({
                'status': 'success',
                'message': 'Service account requests retrieved successfully',
                'data': response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error in fetch_service_account_requests: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def approve_reject_settlement(self, request):
        try:
            sar_id = request.data.get('sar_id')
            action = request.data.get('request_status')  
            reason = request.data.get('reason', None)
            
            if not sar_id:
                return Response({
                    'status': 'fail',
                    'message': 'Request ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not action:
                return Response({
                    'status': 'fail',
                    'message': 'Action is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            service_request = ServiceAccountRequest.objects.select_related(
                'pu'
            ).get(sar_id=sar_id)
            
            if service_request.request_status == 'SETTLED':
                return Response({
                    'status': 'fail',
                    'message': f'Request already settled'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            retailer = service_request.pu
            
            if action == 'SETTLED':

                user_wallet = PortalUserWallet.objects.get(pu=retailer)
                amount = Decimal(service_request.amount)
                
                if user_wallet.pg_wallet < amount:
                    return Response({
                        'status': 'fail',
                        'message': 'Insufficient balance in Balance Account'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                user_wallet.pg_wallet -= amount
                user_wallet.main_wallet += amount
                user_wallet.save()
                
                retailer_code = retailer.username
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                from_label = f"{retailer_code}_DR_Internal_BalanceAccount_To_ServiceAccount_{timestamp}"
                to_label = f"{retailer_code}_CR_Internal_BalanceAccount_To_ServiceAccount_{timestamp}"
                
                wallet_transaction = {
                    'CR': ['main_wallet', to_label], 
                    'DR': ['pg_wallet', from_label]
                }
                
                for key, value in wallet_transaction.items():
                    global_transaction = GlTrn.objects.create(
                        pu=retailer,
                        effectvie_wallet=value[0],
                        effectvie_amt=amount,
                        effective_type=key,
                        service_trn_table='ad_service_account_request',
                        service_trn_id=service_request.sar_id,
                        gl_trn_dt=timezone.now()
                    )
                    
                    WalletTrn.objects.create(
                        action_id=global_transaction.gl_trn_id,
                        action_type='Internal_pg_wallet_to_main_wallet',
                        pu=retailer,
                        wl_label=value[1],
                        effectvie_wallet=value[0],
                        effectvie_amt=amount,
                        effective_type=key,
                        wl_trn_des=service_request.description,
                        current_balance=getattr(user_wallet, value[0]),
                        wl_trn_dt=timezone.now()
                    )
            
            service_request.request_status = action
            service_request.reasons = reason
            service_request.updated_at = timezone.now()
            service_request.updated_by = request.user.id
            service_request.save()
            
            return Response({
                'status': 'success',
                'message': f'Service Account request settled successfully and funds transferred',
                'is_success': True
            }, status=status.HTTP_200_OK)
            
        except ServiceAccountRequest.DoesNotExist:
            return Response({
                'status': 'fail',
                'message': 'Service account request not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except PortalUserWallet.DoesNotExist:
            return Response({
                'status': 'fail',
                'message': 'User wallet not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Error in approve_reject_settlement: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






class RetailerInstantVegaahPGFirstAPIView(APIView): 
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())


            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)


            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=4,is_instant=True).order_by('-created_at')

            


            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)
                print(queryset,'--------------')

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PgServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                
                if isinstance(data['created_at'], str):
                    data['created_at'] = parser.parse(data['created_at'])

                data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

            with open("output_data_pos.txt", "a", encoding="utf-8") as f:
                f.write(json.dumps(serializer.data, indent=4, default=str))
                f.write("\n\n")


            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class RetailerInstantVegaahPGSecondAPIView(APIView): 
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())


            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)


            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=5,is_instant=True).order_by('-created_at')

            


            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)
                print(queryset,'--------------')

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PgServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                
                if isinstance(data['created_at'], str):
                    data['created_at'] = parser.parse(data['created_at'])

                data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

            with open("output_data_pos.txt", "a", encoding="utf-8") as f:
                f.write(json.dumps(serializer.data, indent=4, default=str))
                f.write("\n\n")


            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class RetailerVegaahPGFirstTransactionAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            
            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=4,is_instant=True)

            daily_transactions = queryset.filter(
                created_at__range=[today_start, today_end],
                trn_status__in=['COMPLETED', 'SETTLED'] 
            )
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()


            

            user_service_finance = UserServiceFinance.objects.filter(
                user=request.user
            ).first()
            total_od_limit = getattr(user_service_finance, 'od_limit', 0) or 0

            # Remaining
            remaining_od_limit = getattr(user_service_finance, 'available_limit', 0) or 0

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)

            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                    'total_od_limit': total_od_limit,
                    'remaining_od_limit': remaining_od_limit
                }]
            }

            response_data = {
                'status': 'success',
                'message': 'Vegaah transaction data fetched successfully.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class RetailerVegaahPGSecondTransactionAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            
            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=5,is_instant=True)

            daily_transactions = queryset.filter(created_at__range=[today_start, today_end])
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()


            

            # Get user's assigned od_limit
            user_service_finance = UserServiceFinance.objects.filter(
                user=request.user
            ).first()
            total_od_limit = getattr(user_service_finance, 'od_limit', 0) or 0
            remaining_od_limit = getattr(user_service_finance, 'available_limit', 0) or 0


            # Remaining
            

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)

            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                    'total_od_limit': total_od_limit,
                    'remaining_od_limit': remaining_od_limit
                }]
            }

            response_data = {
                'status': 'success',
                'message': 'Vegaah transaction data fetched successfully.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class AdminMarkRecievedAPIView(APIView):

    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        try:
            pg_trn_id = request.data.get('pg_trn_id')
            service_provider_id = request.data.get('service_provider_id')
            
            if not pg_trn_id:
                return Response({
                    'status': False,
                    'message': 'Transaction ID is required'
                }, status=400)
            
            if not service_provider_id:
                return Response({
                    'status': False,
                    'message': 'Service Provider ID is required'
                }, status=400)
            
            pg_service_trn = get_object_or_404(PgServiceTrn, pg_trn_id=pg_trn_id)
            
            if pg_service_trn.trn_status != 'SETTLED':
                return Response({
                    'status': False,
                    'message': 'Transaction must be settled before marking as received'
                }, status=400)
            
            if pg_service_trn.is_received:
                return Response({
                    'status': False,
                    'message': 'Settlement already marked as received'
                }, status=400)
            
            service_provider = AdServiceProvider.objects.filter(
                sp_id=service_provider_id,
                pg=pg_service_trn.pg
            ).first()
            
            if not service_provider:
                return Response({
                    'status': False,
                    'message': 'Service provider not found'
                }, status=404)
            
            if service_provider.sp_id not in [7, 8,9,11]:
                return Response({
                    'status': False,
                    'message': 'Receive action only available for specific payment gateways'
                }, status=400)
            
            retailer = get_object_or_404(PortalUser, id=pg_service_trn.created_by)
            
            user_service_finance, created = UserServiceFinance.objects.get_or_create(
                user=retailer,
                defaults={
                    'instant_charge': Decimal('0.00'),
                    'od_limit': Decimal('0.00'),
                    'available_limit': Decimal('0.00'),
                    'usage_limit': Decimal('0.00')
                }
            )
            
            trn_amount = Decimal(str(pg_service_trn.trn_amount))
            
            if trn_amount <= 0:
                return Response({
                    'status': False,
                    'message': 'No receivable amount found for this transaction'
                }, status=400)
            
            old_available_limit = user_service_finance.available_limit
            new_available_limit = old_available_limit + trn_amount
            
            user_service_finance.available_limit = new_available_limit
            user_service_finance.save()
            
            pg_service_trn.is_received = True
            pg_service_trn.save()
            
            return Response({
                'status': 'success',
                'message': f'Settlement marked as received. ₹{trn_amount} added to available limit.',
                'data': {
                    'transaction_id': pg_service_trn.trn_unique_id,
                    'pg_trn_id': pg_service_trn.pg_trn_id,
                    'receivable_amount': str(trn_amount),
                    'retailer_id': retailer.id,
                    'retailer_name': retailer.pu_name if hasattr(retailer, 'pu_name') else retailer.username,
                    'old_available_limit': str(old_available_limit),
                    'new_available_limit': str(new_available_limit),
                    'current_usage': str(user_service_finance.usage_limit),
                    'od_limit': str(user_service_finance.od_limit),
                    'service_provider_id': service_provider.sp_id,
                    'is_received': True
                }
            }, status=200)
            
        except PgServiceTrn.DoesNotExist:
            return Response({
                'status': False,
                'message': 'Transaction not found'
            }, status=404)
        
        except PortalUser.DoesNotExist:
            return Response({
                'status': False,
                'message': 'Retailer not found'
            }, status=404)
        
        except Exception as e:
            print(f"Error in mark_pg_settlement_received: {str(e)}")
            import traceback
            print(traceback.format_exc())
            
            return Response({
                'status': False,
                'message': f'An error occurred: {str(e)}'
            }, status=500)







class UserServiceFinanceView(APIView):    
    def get(self, request):
        user_id = request.query_params.get('user_id') or request.data.get('user_id')
        try:
            if not user_id:
                return Response({
                    'status': 'fail',
                    'message': 'user_id is required.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                user_id = int(user_id)
            except (ValueError, TypeError):
                print(f"Invalid user_id format: {user_id}")
                return Response({
                    'status': 'fail',
                    'message': 'Invalid user_id format. Must be a number.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                user = PortalUser.objects.get(id=user_id)
            except PortalUser.DoesNotExist:
                return Response({
                    'status': 'fail',
                    'message': 'User not found.'
                }, status=status.HTTP_404_NOT_FOUND)
            
            user_finance, created = UserServiceFinance.objects.get_or_create(
                user_id=user_id,
                defaults={
                    'instant_charge': Decimal('0'),
                    'od_limit': Decimal('0'),
                    'available_limit': Decimal('0'),
                    'usage_limit': Decimal('0')
                }
            )
            
            serializer = UserServiceFinanceSerializer(user_finance)
            
            return Response({
                'status': 'success',
                'message': 'User Service Finance fetched successfully.',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error in GET UserServiceFinanceView: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    
    def post(self, request):
        user_id = request.data.get('user_id')
        instant_charge = request.data.get('instant_charge')
        od_limit = request.data.get('od_limit')
        
        try:
            if not user_id:
                return Response({
                    'status': 'fail',
                    'message': 'user_id is required.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                user_id = int(user_id)
            except (ValueError, TypeError):
                print(f"Invalid user_id format: {user_id}")
                return Response({
                    'status': 'fail',
                    'message': 'Invalid user_id format. Must be a number.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if instant_charge is None or instant_charge == '' or instant_charge == 0:
                return Response({
                    'status': 'fail',
                    'message': 'Instant charge is required and must be greater than 0.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                instant_charge_value = Decimal(str(instant_charge))
                if instant_charge_value <= 0:
                    return Response({
                        'status': 'fail',
                        'message': 'Instant charge must be greater than 0.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except (ValueError, TypeError, InvalidOperation):
                return Response({
                    'status': 'fail',
                    'message': 'Invalid instant charge value. Please enter a valid number.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if od_limit is None or od_limit == '' or od_limit == 0:
                return Response({
                    'status': 'fail',
                    'message': 'OD limit is required and must be greater than 0.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                od_limit_value = Decimal(str(od_limit))
                if od_limit_value <= 0:
                    return Response({
                        'status': 'fail',
                        'message': 'OD limit must be greater than 0.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except (ValueError, TypeError, InvalidOperation):
                return Response({
                    'status': 'fail',
                    'message': 'Invalid OD limit value. Please enter a valid number.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                user = PortalUser.objects.get(id=user_id)
            except PortalUser.DoesNotExist:
                return Response({
                    'status': 'fail',
                    'message': 'User not found.'
                }, status=status.HTTP_404_NOT_FOUND)
            
            with transaction.atomic():
                user_finance, created = UserServiceFinance.objects.get_or_create(
                    user_id=user_id,
                    defaults={
                        'instant_charge': instant_charge_value,
                        'od_limit': od_limit_value,
                        'available_limit': od_limit_value,
                        'usage_limit': Decimal('0')
                    }
                )
                
                if not created:
                    print(f"Updating existing finance record for user {user_id}")
                    
                    user_finance.instant_charge = instant_charge_value
                    
                    old_od_limit = user_finance.od_limit
                    difference = od_limit_value - old_od_limit
                    
                    user_finance.od_limit = od_limit_value
                    user_finance.available_limit = user_finance.available_limit + difference
                    
                    user_finance.save()
                else:
                    print(f"Created new finance record for user {user_id}")
                    print(f"instant_charge={instant_charge_value}, od_limit={od_limit_value}")
                
                add_user_activity({
                    "table_id": user_finance.id,
                    "table_name": "user_service_finance",
                    "ua_action": "Create" if created else "Update",
                    "ua_description": f'User Service Finance {"created" if created else "updated"} successfully for user {user.username}.',
                    "created_by": request.user,
                    "request_data": json.dumps({
                        "user_id": user_id,
                        "instant_charge": str(instant_charge),
                        "od_limit": str(od_limit)
                    }, default=str),
                    "response_data": json.dumps({
                        "id": user_finance.id,
                        "user_id": user_finance.user_id,
                        "instant_charge": float(user_finance.instant_charge),
                        "od_limit": float(user_finance.od_limit),
                        "available_limit": float(user_finance.available_limit),
                        "usage_limit": float(user_finance.usage_limit)
                    }, default=str),
                })
                                
                serializer = UserServiceFinanceSerializer(user_finance)
                
                return Response({
                    'status': 'success',
                    'message': f'User Service Finance {"created" if created else "updated"} successfully.',
                    'data': serializer.data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            print(f"❌ Error in POST UserServiceFinanceView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RetailerRazorpayPGAPIView(APIView): 
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())


            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            

            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=6,is_instant=False).order_by('-created_at')

            
            


            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)
                print(queryset,'--------------')

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PgServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                
                # Check if the value is a string before parsing
                if isinstance(data['created_at'], str):
                    data['created_at'] = parser.parse(data['created_at'])

                # Format to the required format
                data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

            with open("output_data_pos.txt", "a", encoding="utf-8") as f:
                f.write(json.dumps(serializer.data, indent=4, default=str))
                f.write("\n\n")


            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





class RetailerRazorpayPGTransactionAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            
            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=6,is_instant=False)

            daily_transactions = queryset.filter(created_at__range=[today_start, today_end])
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)

            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                }]
            }
            print(paginated_response_data,'=====================================>>>>>>>>>>>>>>>>>>>>>>>>>')

            response_data = {
                'status': 'success',
                'message': 'Vegaah transaction data fetched successfully.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class RetailerRazorpayPGInstantTransactionAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            # Input parameters
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            search_txt = request.data.get('search')
            filter_by = request.data.get('status')
            start_date = request.data.get('start_date')
            terminal_id = request.data.get('terminal_id')
            end_date = request.data.get('end_date', datetime.datetime.now().date())

            if not page_size or page_size <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size.'}, status=status.HTTP_400_BAD_REQUEST)

            if page_number <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            
            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=6,is_instant=True)

            daily_transactions = queryset.filter(created_at__range=[today_start, today_end])
            daily_total_amount = daily_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            daily_total_count = daily_transactions.count()

            settled_transactions = queryset.filter(trn_status='COMPLETED')
            settled_total_amount = settled_transactions.aggregate(Sum('trn_amount'))['trn_amount__sum'] or 0
            settled_total_count = settled_transactions.count()


            

            # Get user's assigned od_limit
            user_service_finance = UserServiceFinance.objects.filter(
                user=request.user
            ).first()
            total_od_limit = getattr(user_service_finance, 'od_limit', 0) or 0
            remaining_od_limit = getattr(user_service_finance, 'available_limit', 0) or 0


            # Remaining
            

            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: COMPLETED, SETTLED, FAILED.'},
                        status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(trn_status=filter_by)

            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)

            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

            paginator = Paginator(queryset, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({'status': 'fail', 'message': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = PosServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})
            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': [{
                    'daily_total_amount': daily_total_amount,
                    'daily_total_count': daily_total_count,
                    'up_comming_settled_total_amount': settled_total_amount,
                    'up_comming_settled_total_count': settled_total_count,
                    'total_od_limit': total_od_limit,
                    'remaining_od_limit': remaining_od_limit
                }]
            }

            response_data = {
                'status': 'success',
                'message': 'Vegaah transaction data fetched successfully.',
                'data': paginated_response_data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class RetailerInstantRazorpayPGFirstAPIView(APIView): 
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        try:
            user = request.user
            page_number = int(request.data.get('page_number', 1))
            page_size = int(request.data.get('page_size', 10))
            terminal_id = request.data.get('terminal_id')
            search_txt = request.data.get('search')
            filter_by = request.data.get('filter_by')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date', datetime.datetime.now().date())


            if not str(page_number).isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_number. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not str(page_size).isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page_size. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)


            queryset = PgServiceTrn.objects.filter(created_by=request.user.id, pg_id=6,is_instant=True).order_by('-created_at')

            


            if search_txt:
                queryset = queryset.filter(
                    Q(customer_name__icontains=search_txt) |
                    Q(trn_unique_id__icontains=search_txt) |
                    Q(trn_status__icontains=search_txt)
                    )

            if filter_by:
                allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
                if filter_by not in allowed_filters:
                    return Response({
                        'status': 'fail',
                        'message': f'Invalid status filter. Allowed values are: {", ".join(allowed_filters)}.'},
                        status=status.HTTP_400_BAD_REQUEST)

                queryset = queryset.filter(trn_status=filter_by)
                print(queryset,'--------------')

            if start_date:
                try:
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    queryset = queryset.filter(pos_trn_dt__date__gte=start_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid start_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if end_date:
                try:
                    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=end_date)
                except ValueError:
                    return Response({'status': 'fail', 'message': 'Invalid end_date format. Use YYYY-MM-DD.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not queryset.exists():
                paginated_response_data = {
                    'total_pages': 0,
                    'current_page': 0,
                    'total_items': 0,
                    'results': []
                }
                return Response({
                    'status': 'success',
                    'message': 'Transaction Data not found.',
                    'data': paginated_response_data,
                }, status=status.HTTP_200_OK)

            paginator = Paginator(queryset, int(page_size))
            try:
                page_obj = paginator.page(int(page_number))
            except EmptyPage:
                return Response({
                    'status': 'fail',
                    'message': 'Page not found.',
                    'data': {}
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = PgServiceTrnSerializer(page_obj.object_list, many=True, context={'request': request})

            for data in serializer.data:
                
                
                if isinstance(data['created_at'], str):
                    data['created_at'] = parser.parse(data['created_at'])

                data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

            with open("output_data_pos.txt", "a", encoding="utf-8") as f:
                f.write(json.dumps(serializer.data, indent=4, default=str))
                f.write("\n\n")


            paginated_response_data = {
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total_items': paginator.count,
                'results': serializer.data
            }

            return Response({
                'status': 'success',
                'message': 'Transactions retrieved successfully.',
                'data': paginated_response_data,

            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




import requests
import json
import datetime
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse

# RAZORPAY_KEY_ID = "rzp_test_RtSCLYeHg0bNUf"  
# RAZORPAY_KEY_SECRET = "3xbjRXEG2NAwAOV0kam5PtJm"  
# RAZORPAY_API_URL = "https://api.razorpay.com/v1/payment_links"

import json
import datetime
import requests
import jwt
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer




class RazorpayPG(APIView):
    renderer_classes = [JSONRenderer]  
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsRetailer]
    
    def post(self, request):
        if 'amount' in request.data:
            return self.add_vegaah_payment_initiate(request)
        return Response({'error': 'Amount is required'}, status=400)

    def add_vegaah_payment_initiate(self, request):
        try:
            token = request.data.get('token')
            credit_card_num = request.data.get('cardNumber')
            customer_name = request.data.get('customerName')
            mobile = request.data.get('mobile')
            amount_str = request.data.get('amount')
            is_instant = request.data.get('is_instant', False)
            try:
                auth_details = PaymentGetwayAuthenticationDetails.objects.filter(
                    sp_id=7,
                    is_deactive=False
                ).first()  
                
                if not auth_details:
                    return Response({
                        'status': 'error',
                        'error': 'No active payment terminal configured. Please contact administrator.'
                    }, status=404)
                
                RAZORPAY_CLIENT_KEY = auth_details.client_key
                RAZORPAY_SECRET_KEY = auth_details.client_secret_key
                MIN_AMOUNT = Decimal(str(auth_details.min_amount)) if auth_details.min_amount else Decimal('50')
                MAX_AMOUNT = Decimal(str(auth_details.max_amount)) if auth_details.max_amount else Decimal('39990')
            except Exception as e:
                return Response({
                    'status': 'error',
                    'error': 'Failed to load payment configuration'
                }, status=500)
            if not all([RAZORPAY_CLIENT_KEY, RAZORPAY_SECRET_KEY]):
                return Response({
                    'status': 'error',
                    'error': 'Incomplete authentication details for selected profile. Please contact administrator.'
                }, status=400)
            bin_details = fetch_bin_details_pg(credit_card_num)
            
            if bin_details['status'] != 'success':
                print(f"BIN lookup failed: {bin_details['message']}")
                return Response({
                    "status": "error", 
                    "message": bin_details['message']
                }, status=400)
            
            card_type = bin_details['card_type']
            brand = bin_details['brand']
            
            card_type_instance = CardType.objects.filter(name__icontains=brand).first()
            if not card_type_instance:
                print(f"Card type '{brand}' not supported")
                return Response({
                    "status": "error",
                    "message": f"Card type '{brand}' is not supported"
                }, status=400)
            try:
                decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = decoded.get('user_id')
                if not user_id:
                    return Response({'error': 'Invalid token'}, status=401)

                user = PortalUser.objects.get(id=user_id)
                print(f"User Authenticated: {user.pu_email} (ID: {user.id})")

            except jwt.ExpiredSignatureError:
                return Response({'error': 'Token has expired'}, status=401)
            except jwt.InvalidTokenError:
                return Response({'error': 'Invalid token'}, status=401)

            try:
                amount = Decimal(amount_str).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
                if amount <= 0:
                    return Response({'error': 'Amount must be greater than 0'}, status=400)
                
                if amount < MIN_AMOUNT:
                    return Response({
                        'status': 'error',
                        'error': f'Amount must be at least ₹{MIN_AMOUNT}'
                    }, status=400)
                
                if amount > MAX_AMOUNT:
                    return Response({
                        'status': 'error',
                        'error': f'Amount cannot exceed ₹{MAX_AMOUNT}'
                    }, status=400)
                
            except (ValueError, TypeError, InvalidOperation):
                return Response({'error': 'Invalid amount format'}, status=400)

            pg_id = 6  
            payment_gateway = get_object_or_404(PaymentGateway, id=pg_id)
            card_type = get_object_or_404(CardType, id=card_type_instance.id)
            retailer = user
            retailer_details = get_object_or_404(PortalUserDetails, pu=retailer)

            user_service_finance = None
            instant_charge_percent = Decimal('0.00')
            if is_instant:
                try:
                    user_service_finance = UserServiceFinance.objects.filter(
                        user=retailer
                    ).first()  
                    if not user_service_finance:
                        return Response({
                            'status': 'error',
                            'error': 'Instant payment not configured for your account. Please contact administrator.'
                        }, status=400)
                    
                    instant_limit = Decimal(str(user_service_finance.od_limit))
                    instant_charge_percent = Decimal(str(user_service_finance.instant_charge))
                    available_limit = Decimal(str(user_service_finance.available_limit))
                    if amount > available_limit:
                        return Response({
                            'status': 'error',
                            'error': f'Insufficient instant payment limit. Transaction amount: ₹{amount}. Available limit: ₹{available_limit}.'
                        }, status=400)      
                    
                except Exception as e:
                    return Response({
                        'status': 'error',
                        'error': 'Failed to verify instant payment limit. Please try again.'
                    }, status=500)

            try:
                retailer_charge = UserCharge.objects.get(
                    user_id=retailer.id, 
                    pg=payment_gateway, 
                    card_type=card_type
                )
                charge_percent = retailer_charge.charge_percent
            except UserCharge.DoesNotExist:
                try:
                    pg_base_charge = (
                        PGBaseCharge.objects
                        .filter(pg=payment_gateway, card_type=card_type)
                        .order_by('charge_percent')
                        .first()
                    )
                    if pg_base_charge:
                        charge_percent = pg_base_charge.charge_percent
                    else:
                        return Response({
                            "status": False, 
                            "message": "No applicable charge percent found."
                        }, status=400)

                except PGBaseCharge.DoesNotExist:
                    return Response({
                        "status": False, 
                        "message": "No applicable charge percent found."
                    }, status=400)

            total_charge_percent = charge_percent + instant_charge_percent
            total_charge_amount = (amount * total_charge_percent) / Decimal('100')
            net_credit_to_user = amount - total_charge_amount

            service_provider = AdServiceProvider.objects.filter(
                service__service_name='PG',
                pg=payment_gateway  
            ).first()

            print(service_provider,'========================mkss')
        

            print("\n================ CARD DETAILS =====================")
            print(f"Card Type          : {card_type.name}")
            print(f"Transaction Amount : ₹{amount}")

            card_name = card_type.name.lower()

            if 'rupay' in card_name:
                mdr_percent = service_provider.rupay_mdr
            elif 'mastercard' in card_name:
                mdr_percent = service_provider.mastercard_mdr
            elif 'visa' in card_name:
                mdr_percent = service_provider.visa_mdr
            else:
                mdr_percent = Decimal('0.00')

            print(mdr_percent,'=============================mkssssssssss')


            print("\n================ MDR DETAILS ======================")
            print(f"MDR Percentage     : {mdr_percent}%")

            mdr_amount = (amount * mdr_percent / Decimal('100')).quantize(Decimal('0.00'))
            print(f"MDR Amount         : ₹{mdr_amount}")

            gst_amount = (mdr_amount * service_provider.gst_percentage / Decimal('100')).quantize(Decimal('0.00'))
            print(f"GST Amount         : ₹{gst_amount}")

            receivable_amount = (amount - mdr_amount - gst_amount).quantize(Decimal('0.00'))
           
            


            state_name = ""
            city_name = ""
            if retailer_details.state_id:
                state = State.objects.filter(state_id=retailer_details.state_id).first()
                if state:
                    state_name = state.state_name

            if retailer_details.city_id:
                city = City.objects.filter(city_id=retailer_details.city_id).first()
                if city:
                    city_name = city.city_name

            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            order_id = f"RZP{timestamp}"

            amount_paise = int(amount * 100)

            callback_url = "https://qa.fixpay.in/retailer-rpay"
            if is_instant:
                callback_url = "https://qa.fixpay.in/instant-rpay"

            payload = {
                "amount": amount_paise,
                "currency": "INR",
                "accept_partial": False,
                "reference_id": order_id,
                "description": f"Payment for order {order_id}",
                "customer": {
                    "name": customer_name,
                    "email": user.pu_email,
                    "contact": mobile
                },
                "notify": {
                    "sms": True,
                    "email": True
                },
                "callback_url": callback_url,
                "callback_method": "get"
            }

            print("\n--- Razorpay API Request ---")
            print(f"URL: https://api.razorpay.com/v1/payment_links")
            print(json.dumps(payload, indent=2))

            razorpay_log, log_created = RazorpayPgLogs.objects.update_or_create(
                order_id=order_id,
                defaults={
                    'request': payload,
                    'status': 'INITIATING'
                }
            )
            
            if log_created:
                print(f"✓ New payment log created (ID: {razorpay_log.logs_id})")
            else:
                print(f"✓ Existing payment log updated (ID: {razorpay_log.logs_id})")

            try:                
                resp = requests.post(
                    "https://api.razorpay.com/v1/payment_links",
                    json=payload,
                    auth=(RAZORPAY_CLIENT_KEY, RAZORPAY_SECRET_KEY),
                    headers={'Content-Type': 'application/json'},
                    timeout=60
                )
                
                api_response = resp.json()
                
            except requests.exceptions.Timeout:
                razorpay_log.status = 'TIMEOUT'
                razorpay_log.save()
                return Response({
                    'status': 'error',
                    'error': 'Payment gateway is taking too long to respond. Please try again.'
                }, status=504)
            except requests.exceptions.ConnectionError as e:
                razorpay_log.status = 'CONNECTION_ERROR'
                razorpay_log.response = {'error': str(e)}
                razorpay_log.save()
                return Response({
                    'status': 'error',
                    'error': 'Unable to connect to payment gateway. Please check your internet connection.'
                }, status=503)
            except requests.exceptions.RequestException as e:
                razorpay_log.status = 'ERROR'
                razorpay_log.response = {'error': str(e)}
                razorpay_log.save()
                return Response({
                    'status': 'error',
                    'error': f'Failed to connect with payment gateway: {str(e)}'
                }, status=500)
            except ValueError as e:
                razorpay_log.status = 'INVALID_RESPONSE'
                razorpay_log.save()
                return Response({
                    'status': 'error',
                    'error': 'Invalid response from payment gateway'
                }, status=500)

            print(json.dumps(api_response, indent=2))

            if 'error' in api_response:
                error_msg = api_response['error'].get('description', 'Payment link generation failed')
                razorpay_log.status = 'FAILED'
                razorpay_log.response = api_response
                razorpay_log.save()
                return Response({
                    'status': 'error',
                    'error': error_msg
                }, status=400)

            if resp.status_code != 200:
                razorpay_log.status = 'FAILED'
                razorpay_log.response = api_response
                razorpay_log.save()
                return Response({
                    'status': 'error',
                    'error': f'Razorpay returned status {resp.status_code}'
                }, status=resp.status_code)

            payment_link = api_response.get('short_url')
            payment_page_id = api_response.get('id')

            if not payment_link:
                razorpay_log.status = 'FAILED'
                razorpay_log.response = api_response
                razorpay_log.save()
                return Response({
                    'status': 'error',
                    'error': 'No payment link generated'
                }, status=500)


            razorpay_log.payment_link_id = payment_page_id
            razorpay_log.response = api_response
            razorpay_log.status = 'INITIATED'
            razorpay_log.save()

            
            pg_service_trn = PgServiceTrn.objects.create(
                trn_unique_id=order_id,
                trn_amount=amount,
                trn_response=api_response,
                pg=payment_gateway,
                card_type=card_type,
                is_settled=False,
                trn_status="PENDING",
                created_by=retailer.id,
                buyer_email=user.pu_email,
                buyer_phone=mobile,
                buyer_firstname=customer_name.split()[0] if customer_name else "",
                buyer_lastname=customer_name.split()[1] if len(customer_name.split()) > 1 else "",
                buyer_address=state_name or "",
                buyer_city=city_name or "",
                buyer_state=state_name or "",
                buyer_country="India",
                buyer_pincode=retailer_details.zip_code or 0,
                retailer_charge_percent=total_charge_percent,
                total_charge_amount=total_charge_amount,
                net_credit_to_user=net_credit_to_user,
                is_instant=is_instant,
                sp_mdr_amount=mdr_amount,
                sp_gst_amount=gst_amount,
                sp_receivable_amount=receivable_amount,
                payment_gateway_reference=payment_page_id 
            )


            return Response({
                'status': 'success',
                'message': 'Payment link generated successfully',
                'data': {
                    'paymentLink': payment_link,
                    'paymentPageId': payment_page_id,
                    'orderId': order_id,
                    'amount': str(amount),
                    'isInstant': is_instant,
                    'totalCharge': str(total_charge_percent),
                    'netCredit': str(net_credit_to_user)
                }
            }, status=200)

        except PortalUser.DoesNotExist:
            return Response({'status': 'error', 'error': 'User not found'}, status=404)
        except PortalUserDetails.DoesNotExist:
            return Response({'status': 'error', 'error': 'User details not found'}, status=404)
        except Exception as e:
            return Response({'status': 'error', 'error': f'An unexpected error occurred: {str(e)}'}, status=500)


# ==================== WEBHOOK HANDLER ====================

@csrf_exempt
def razorpay_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        payload_body = request.body.decode('utf-8')
        data = json.loads(payload_body)
        
        webhook_signature = request.headers.get('X-Razorpay-Signature')
        
        if webhook_signature:
            profile = PaymentGetwayAuthenticationDetails.objects.filter(
                sp_id=7,
                is_deactive=False
            ).values('client_secret_key').first()

            if not profile or not profile.get('client_secret_key'):
                return JsonResponse({'error': 'Webhook secret not configured'}, status=400)

            webhook_secret = profile['client_secret_key']

            
            import hmac
            import hashlib
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload_body.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if webhook_signature != expected_signature:
                return JsonResponse({'error': 'Invalid signature'}, status=400)
            
        
        event = data.get('event')
        payload_data = data.get('payload', {})
        
        payment_link_entity = payload_data.get('payment_link', {}).get('entity', {})
        payment_entity = payload_data.get('payment', {}).get('entity', {})
        order_entity = payload_data.get('order', {}).get('entity', {})
        
        order_id = payment_link_entity.get('reference_id')
        
        if not order_id and order_entity:
            order_id = order_entity.get('receipt')
        
        payment_link_id = payment_link_entity.get('id')     
        payment_id = payment_entity.get('id')               
        amount_paid = payment_entity.get('amount', 0) / 100 
        method = payment_entity.get('method', '')
        status = payment_entity.get('status', '')
        
        
        if not order_id:
            return JsonResponse({
                'success': 'true', 
                'message': 'Event acknowledged but not processed (no order_id)'
            }, status=200)
        
        webhook_log = RazorpayPgLogs.objects.create(
            order_id=order_id or 'UNKNOWN',
            payment_link_id=payment_link_id,
            payment_id=payment_id,
            event_type=event,
            request={
                "headers": dict(request.headers),
                "body": payload_body
            },
            response=data,
            status='RECEIVED'
        )


        
        
        
        pg_service_trn = PgServiceTrn.objects.filter(
            trn_unique_id=order_id
        ).first()

        if not pg_service_trn:
            webhook_log.status = 'NOT_FOUND'
            webhook_log.save()
            return JsonResponse({
                'success': 'false',
                'message': 'Transaction not found'
            }, status=404)


        old_status = pg_service_trn.trn_status
        
        if event == 'payment_link.paid':
           
            
            pg_service_trn.trn_status = 'COMPLETED'
            pg_service_trn.payment_gateway_reference = payment_id
            pg_service_trn.trn_response = data
            
            
            if pg_service_trn.is_instant:
                retailer = pg_service_trn.created_by
                user_finance = UserServiceFinance.objects.filter(
                    user_id=retailer
                ).first()
                
                if user_finance:
                    txn_amount = Decimal(str(amount_paid))
                    user_finance.usage_limit += txn_amount
                    user_finance.available_limit -= txn_amount
                    user_finance.save()
                    
                else:
                    print("No UserServiceFinance record found for instant transaction!")
            else:
                print("Not an instant transaction — finance not updated")
            
            webhook_log.status = 'COMPLETED'
            
        elif event == 'payment_link.cancelled':
            pg_service_trn.trn_status = 'CANCELLED'
            pg_service_trn.trn_response = data
            webhook_log.status = 'CANCELLED'
            
        elif event == 'payment_link.expired':
            pg_service_trn.trn_status = 'EXPIRED'
            pg_service_trn.trn_response = data
            webhook_log.status = 'EXPIRED'
        
        else:
            webhook_log.status = 'ACKNOWLEDGED'
        
        

        pg_service_trn.save(update_fields=[
            'trn_status',
            'payment_gateway_reference',
            'trn_response'
        ])

        webhook_log.save(update_fields=['status'])

        

        return JsonResponse({'success': 'true'}, status=200)

    except json.JSONDecodeError as e:
        return JsonResponse({
            'success': 'false',
            'error': 'Invalid JSON'
        }, status=400)
        
    except Exception as e:
        return JsonResponse({
            'success': 'false',
            'error': str(e)
        }, status=500)

class GetAuthRazorPay(APIView):
    def get(self, request):
        try:
            profiles = PaymentGetwayAuthenticationDetails.objects.filter(
                sp_id=7,
                is_deactive=False
            ).values(
                'min_amount',
                'max_amount'
            )

            profiles_list = list(profiles)

            if not profiles_list:
                return Response(
                    {"message": "No active Razorpay auth profiles found"},
                    status=status.HTTP_204_NO_CONTENT
                )

            for profile in profiles_list:
                profile['min_amount'] = float(profile['min_amount'])
                profile['max_amount'] = float(profile['max_amount'])

            logger.info(f"Fetched {len(profiles_list)} Razorpay auth profiles")

            return Response(profiles_list, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error fetching Razorpay auth profiles")
            return Response(
                {
                    "error": "Failed to fetch payment gateway profiles",
                    "detail": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )