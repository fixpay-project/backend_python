# from .models import UserActivity, BinChecker, PortalUserCharges, HierarchyCharges  # Import required models
# from rest_framework.response import Response
# from rest_framework import status
# import datetime
# import json
# import os
# import re
# import requests
# from django.db import transaction


# def add_user_activity(data):
#     try:
#         UserActivity.objects.create(**data)

#         response_data = {
#             'status': 'success',
#             'message': 'user activity added successfully',
#         }
#         return Response(response_data, status=status.HTTP_200_OK)
#     except Exception as e:
#         return Response({
#             'status': 'error',
#             'message': f'Internal server error: {str(e)}'
#         }, status=status.HTTP_400_BAD_REQUEST)


# def load_sequences() -> dict:
#     """
#     Load the sequence dictionary from a JSON file.
#     If the file does not exist, return an empty dictionary.
#     """
#     # Base directory for the project
#     BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#     # File to store the sequences
#     SEQUENCE_FILE = os.path.join(BASE_DIR, "utils_files/user_creation_type_sequence.json")

#     if os.path.exists(SEQUENCE_FILE):
#         with open(SEQUENCE_FILE, "r") as file:
#             return json.load(file)
#     return {}


# def save_sequences(sequences: dict):
#     """
#     Save the sequence dictionary to a JSON file.
#     """
#     # Base directory for the project
#     BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#     # File to store the sequences
#     SEQUENCE_FILE = os.path.join(BASE_DIR, "utils_files/user_creation_type_sequence.json")

#     with open(SEQUENCE_FILE, "w") as file:
#         json.dump(sequences, file, indent=4)


# def generate_userid(user_type: str, state_code: str = "GJ") -> str:
#     # Load sequences on startup
#     type_sequences = load_sequences()
#     """
#     Generate a USERID based on user type, state code, and current date.

#     :param user_type: 2-character code for the user type (RT, DT, MD, SD)
#     :param state_code: 2-character state code (default: 'GJ')
#     :return: Generated USERID
#     """
#     # Get current month and year
#     now = datetime.datetime.now()
#     mm = now.strftime("%m")
#     yy = now.strftime("%y")

#     # Initialize sequence for the month if not already done
#     key = f"{user_type}-{state_code}-{mm}{yy}"
#     print('key', key)
#     if key not in type_sequences:
#         type_sequences[key] = 1

#     # Generate sequence and update tracker
#     sequence = type_sequences[key]
    
#     print('sequence', sequence)

#     type_sequences[key] += 1

#     print('type_sequences', type_sequences)
#     # Save updated sequences to file
#     save_sequences(type_sequences)

#     # Format USERID
#     userid = f"{user_type}{state_code}{mm}{yy}{sequence:03}"

#     print('userid', userid)
#     return userid


# def fetch_bin_details(card_no, user_id=None):
#     if not card_no:
#         return {"status": "error", "message": "Card number is required"}

#     try:
#         bin_entry = BinChecker.objects.get(card_number=card_no)
#         charge_type = bin_entry.charge_type  # 'REGULAR' or 'PREMIUM'

#         # Call get_charge_data only if user_id is provided
#         charge_data = get_charge_data(user_id, charge_type) if user_id else {}

#         return {
#             "charge_type": charge_type,
#             "rate_value": charge_data.get('rate_value') if user_id else None,
#             "rate_type": charge_data.get('rate_type') if user_id else None
#         }

#     except BinChecker.DoesNotExist:
#         base_url = "https://bin-ip-checker.p.rapidapi.com/"
#         url = f"{base_url}?bin={card_no}"
#         headers = {
#             "Content-Type": "application/json",
#             "x-rapidapi-host": "bin-ip-checker.p.rapidapi.com",
#             "x-rapidapi-key": "cc2d7a485cmsh2ef097246fe89c4p1817c3jsn6a80e0b7f5cf"
#         }

#         try:
#             response = requests.post(url, headers=headers)
#             response_data = response.json()

#             if response.status_code == 200:
#                 response_data = response.json()

#                 country_name = response_data.get("BIN", {}).get("country", {}).get("name", "").upper()
#                 level = response_data.get("BIN", {}).get("level", "").upper()
#                 brand = response_data.get("BIN", {}).get("brand", "").upper()

#                 charge_type = 'REGULAR'  
#                 if (country_name != 'INDIA' or 
#                     any(keyword in level for keyword in ['BUSINESS', 'CORPORATE']) or 
#                     not any(word in brand for word in ['MASTER', 'VISA', 'RUPAY', 'MAESTRO'])):
#                     charge_type = 'PREMIUM'

#                 with transaction.atomic():
#                     bin_checker = BinChecker.objects.create(
#                         card_number=card_no,
#                         response_data=response_data,
#                         charge_type=charge_type
#                     )

#                     # Call get_charge_data only if user_id is provided
#                     charge_data = get_charge_data(user_id, charge_type) if user_id else {}

#                     return {
#                         "charge_type": charge_type,
#                         "rate_value": charge_data.get('rate_value') if user_id else None,
#                         "rate_type": charge_data.get('rate_type') if user_id else None
#                     }

#             else:
#                 return {"status": "error", "message": "Failed to fetch BIN data from API"}

#         except requests.RequestException as e:
#             return {"status": "error", "message": f"API request failed: {str(e)}"}


# def get_charge_data(user_id, charge_type):
#     """Fetch charges and return applicable rate based on charge_type ('REGULAR' or 'PREMIUM')"""
#     sp_id = 1
#     applicable_rate_key = "regular_rate" if charge_type == "REGULAR" else "premium_rate"

#     # Check in PortalUserCharges first
#     puc_entry = PortalUserCharges.objects.filter(pu_id=user_id, sp_id=sp_id).first()
#     if puc_entry and puc_entry.puc_charges:
#         charge_list = puc_entry.puc_charges  # Assuming JSONField stores a list
#         applicable_charges = extract_applicable_charges(charge_list, applicable_rate_key)
        
#         # Extract rate value
#         rate_value = applicable_charges[0]['rate']  # Since it's a list, access the first dictionary
#         rate_type = applicable_charges[0]['rate_type']  # Since it's a list, access the first dictionary

#         return {"charge_source": "PortalUserCharges", "rate_value": rate_value, 'rate_type': rate_type}

#     # If not found, fetch from HierarchyCharges
#     hc_entry = HierarchyCharges.objects.filter(dh_id=None, sp_id=sp_id).first()
#     if hc_entry and hc_entry.hc_charges:
#         charge_list = hc_entry.hc_charges  # Assuming JSONField stores a list
#         applicable_charges = extract_applicable_charges(charge_list, applicable_rate_key)

#         # Extract rate value
#         rate_value = applicable_charges[0]['rate']  # Since it's a list, access the first dictionary
#         rate_type = applicable_charges[0]['rate_type']  # Since it's a list, access the first dictionary
        
#         return {"charge_source": "HierarchyCharges", "rate_value": rate_value, 'rate_type': rate_type}

#     return {"charge_source": "None", "charges": None}


# def extract_applicable_charges(charge_list, applicable_rate_key):
#     """Extracts relevant charge details based on charge_type (REGULAR or PREMIUM)"""
#     extracted_charges = []
#     for charge in charge_list:
#         extracted_charges.append({
#             "charge_type": charge.get("charge_type"),
#             "rate": charge.get(applicable_rate_key),  # Get either regular_rate or premium_rate
#             "rate_type": charge.get("rate_type"),
#             "commission_type": charge.get("commission_type"),
#             "effective_wallet": charge.get("effective_wallet"),
#         })
#     return extracted_charges

# # FETCH USER API FUNCTION -------------------------------->>>>>>>>>>>>>>>>>>>>

# from django.db.models import Q
# from django.core.paginator import Paginator, EmptyPage
# from .serializers import *
# from django.db.models import Sum

# #POS TRANSACTION FETCH API
# def pos_fetch_transactions(request,queryset,trn_unique_id,terminal_id,search_txt,filter_by,start_date,end_date,list_user,page_size,page_number):

#     if trn_unique_id:
#         queryset = queryset.filter(trn_unique_id=trn_unique_id)

#     if terminal_id:
#         queryset = queryset.filter(terminal_id=terminal_id)

#     if search_txt:
#         queryset = queryset.filter(
#             Q(customer_name__icontains=search_txt) |
#             Q(trn_unique_id__icontains=search_txt) |
#             Q(terminal_id__icontains=search_txt) |
#             Q(created_by__icontains=search_txt) |
#             Q(trn_status__icontains=search_txt) |
#             Q(created_by__in=PortalUser.objects.filter(username__icontains=search_txt).values_list('id', flat=True))
#         )

#     if filter_by:
#         allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']

#         if filter_by not in allowed_filters:
#             return Response({'status': 'fail', 'message': f'Invalid status filter. Allowed values: {", ".join(allowed_filters)}.'}, status=status.HTTP_400_BAD_REQUEST)
#         queryset = queryset.filter(trn_status=filter_by)

#     if start_date and end_date:
#         queryset = queryset.filter(pos_trn_dt__gte=start_date, pos_trn_dt__lte=end_date)

#     if list_user:
#         queryset = queryset.filter(created_by__in=list_user)

#     paginator = Paginator(queryset, page_size)
#     try:
#         page_obj = paginator.page(page_number)
#     except EmptyPage:
#         return Response({'status': 'fail', 'message': 'Page not found.', 'data': {}}, status=status.HTTP_404_NOT_FOUND)

#     serializer = PosServiceTrnSerializer(page_obj, many=True, context={'request': request})

#     serializer_data = serializer.data
    
#     for data in serializer.data:
#         created_by_id = data.get('created_by')
#         service_trn_id = data.get('pos_trn_id')
#         trn_amount = data.get('trn_amount')
#         gl_trn_queryset = PortalUser.objects.filter(id=data['created_by']).first()

#         if gl_trn_queryset:
#             data['retailer_id'] = gl_trn_queryset.id
#             data['retailer_username'] = gl_trn_queryset.username
#             data['retailer_name'] = gl_trn_queryset.pu_name
#         else:
#             data['retailer_id'] = None
#             data['retailer_username'] = None
#             data['retailer_name'] = None

#         portal_user_charge = PortalUserCharges.objects.filter(pu_id=created_by_id).first()

#         gl_trn_record = GlTrn.objects.filter(pu=created_by_id, effective_type="DR", service_trn_id=service_trn_id)







#         if gl_trn_record:
#             charge = transaction_charge(request,gl_trn_record,portal_user_charge)

#             data['total_amount'] = charge.get('total_amount')
#             data['deducted_amount'] = charge.get('deducted_amount')
#             data['settled_amount'] = charge.get('settled_amount')
#             data['applicable_charge'] = charge.get('applicable_charge')
#             data['charge_description'] = charge.get('charge_description')

#         else:
#             data['total_amount'] = trn_amount
#             data['deducted_amount'] = 0.00
#             data['settled_amount'] = 0.00
#             data['applicable_charge'] = 0.00
#             data['charge_description'] = 'Not settled.'

#         if data.get('pos_trn_dt'):
#             data['pos_trn_dt'] = datetime.datetime.strptime(
#                 data['pos_trn_dt'], "%Y-%m-%dT%H:%M:%S.%f%z"
#             ).strftime("%Y-%m-%d %I:%M %p")

#     Response_data = {
#         'total_pages': paginator.num_pages,
#         'current_page': page_obj.number,
#         'total_items': paginator.count,
#         'results': serializer_data 
#     }
#     return Response_data

# # BBPS TRANSACTION FETCH API
# def bbps_fetch_transactions(request,queryset,filter_by,start_date,end_date,list_user,bbps_request_id,bbps_blr_id,search_txt, page_size,page_number):

#     if filter_by:
#         allowed_filters = ['PENDING', 'SUCCESS']
#         if filter_by not in allowed_filters:
#             return Response({'status': 'fail', 'message': f'Invalid status filter. Allowed values: {", ".join(allowed_filters)}.'}, status=status.HTTP_400_BAD_REQUEST)
        
#         queryset = queryset.filter(bbps_status=filter_by)

#     if start_date and end_date:
#         queryset = queryset.filter(created_at__gte=start_date, created_at__lte=end_date)

#     if list_user:
#         queryset = queryset.filter(created_by__in=list_user)

#     if bbps_request_id:
#         queryset = queryset.filter(bbps_request_id=bbps_request_id)

#     if bbps_blr_id:
#         queryset = queryset.filter(bbps_blr_id=bbps_blr_id)

#     if search_txt:
#         queryset = queryset.filter(
#             Q(bbps_contact_no__icontains=search_txt) |
#             Q(bbps_blr_id__icontains=search_txt) |
#             Q(created_by__icontains=search_txt) |
#             Q(bbps_status__icontains=search_txt) |
#             Q(created_by__in=PortalUser.objects.filter(username__icontains=search_txt).values_list('id', flat=True))
#         )

#     paginator = Paginator(queryset, page_size)
#     try:
#         page_obj = paginator.page(page_number)
#     except EmptyPage:
#         return Response({'status': 'fail', 'message': 'Page not found.', 'data': {}}, status=status.HTTP_404_NOT_FOUND)

#     serializer = BBPSBillerPaymentSerializer(page_obj, many=True, context={'request': request})
#     serializer_data  = serializer.data

#     for data in serializer_data:
#         gl_trn_queryset = PortalUser.objects.filter(id=data['created_by']).first()

#         #ADD Category Name
#         bbps_blr_id = data.get('bbps_blr_id')
#         name = BBPSBiller.objects.get(bbps_blr_id=bbps_blr_id)
#         data['category_name'] = name.bbps_category.category_name

#         if gl_trn_queryset:
#             data['retailer_id'] = gl_trn_queryset.id
#             data['retailer_username'] = gl_trn_queryset.username
#             data['retailer_name'] = gl_trn_queryset.pu_name

#         else:
#             data['retailer_id'] = None
#             data['retailer_username'] = None
#             data['retailer_name'] = None

#         if data.get('created_at'):
#             data['created_at'] = datetime.datetime.strptime(data['created_at'], "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%Y-%m-%d %I:%M %p")

#     Response_data = {
#         'total_pages': paginator.num_pages,
#         'current_page': page_obj.number,
#         'total_items': paginator.count,
#         'results': serializer_data 
#     }

#     return Response_data

# # POS TRANSACTION CHARGE CALCULATION
# def transaction_charge(request,gl_trn_queryset,portal_user_charges):

#     settled_summary = gl_trn_queryset.aggregate(
#         total_amt=Sum('gl_trn_amt'),
#         total_tds_amt=Sum('gl_tds_amt'),
#         effectvie_amt=Sum('effectvie_amt'),
#         gl_tax_amt=Sum('gl_tax_amt'),
#         gl_tds_rate=Sum('gl_tds_rate'),
#         gl_tax_rate=Sum('gl_tax_rate')
#     )
    
#     gl_tds_rate = settled_summary.get('gl_tds_rate', 0.00) or 0.00
#     gl_tax_rate = settled_summary.get('gl_tax_rate', 0.00) or 0.00

#     total_amt = settled_summary.get('total_amt', 0.00) or 0.00
#     deducted_amount = settled_summary.get('effectvie_amt', 0.00) or 0.00
#     settled_amount = total_amt - deducted_amount

#     applicable_charge = 0.00
#     charge_description = "No charge applied"

#     if portal_user_charges and portal_user_charges.puc_charges:
#         commission_type = portal_user_charges.puc_charges[0].get('commission_type', '')

#         if commission_type == 'CHARGE WITH GST':
#             applicable_charge = gl_tax_rate
#             charge_description = "GST Charge Applied"

#         elif commission_type == 'COMMISSION WITHOUT GST':
#             applicable_charge = gl_tds_rate
#             charge_description = "TDS Charge Applied"

#         elif commission_type == 'COMMISSION WITH GST':
#             applicable_charge = [gl_tds_rate , gl_tax_rate]
#             charge_description = "TDS + GST Charge Applied"

#     settled_data = {
#         'total_amount': total_amt,
#         'deducted_amount': deducted_amount,
#         'settled_amount': settled_amount,
#         'applicable_charge': applicable_charge,
#         'charge_description': charge_description
#     }
    
#     return settled_data


from .models import UserActivity, BinChecker, PortalUserCharges, HierarchyCharges  # Import required models
from rest_framework.response import Response
from rest_framework import status
import datetime
import json
import os
import re
import requests
from django.db import transaction
from django.db.models.functions import TruncDate



def add_user_activity(data):
    try:
        UserActivity.objects.create(**data)

        response_data = {
            'status': 'success',
            'message': 'user activity added successfully',
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


def load_sequences() -> dict:
    """
    Load the sequence dictionary from a JSON file.
    If the file does not exist, return an empty dictionary.
    """
    # Base directory for the project
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # File to store the sequences
    SEQUENCE_FILE = os.path.join(BASE_DIR, "utils_files/user_creation_type_sequence.json")

    if os.path.exists(SEQUENCE_FILE):
        with open(SEQUENCE_FILE, "r") as file:
            return json.load(file)
    return {}


def save_sequences(sequences: dict):
    """
    Save the sequence dictionary to a JSON file.
    """
    # Base directory for the project
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # File to store the sequences
    SEQUENCE_FILE = os.path.join(BASE_DIR, "utils_files/user_creation_type_sequence.json")

    with open(SEQUENCE_FILE, "w") as file:
        json.dump(sequences, file, indent=4)


def generate_userid(user_type: str, state_code: str = "GJ") -> str:
    # Load sequences on startup
    type_sequences = load_sequences()
    """
    Generate a USERID based on user type, state code, and current date.

    :param user_type: 2-character code for the user type (RT, DT, MD, SD)
    :param state_code: 2-character state code (default: 'GJ')
    :return: Generated USERID
    """
    # Get current month and year
    now = datetime.datetime.now()
    mm = now.strftime("%m")
    yy = now.strftime("%y")

    # Initialize sequence for the month if not already done
    key = f"{user_type}-{state_code}-{mm}{yy}"
    print('key', key)
    if key not in type_sequences:
        type_sequences[key] = 1

    # Generate sequence and update tracker
    sequence = type_sequences[key]

    print('sequence', sequence)

    type_sequences[key] += 1

    print('type_sequences', type_sequences)
    # Save updated sequences to file
    save_sequences(type_sequences)

    # Format USERID
    userid = f"{user_type}{state_code}{mm}{yy}{sequence:03}"

    print('userid', userid)
    return userid






# def fetch_bin_details(card_no, user_id):
#     if not card_no:
#         return {"status": "error", "message": "Card number is required"}

#     try:
#         bin_entry = BinChecker.objects.get(card_number=card_no)
#         charge_type = bin_entry.charge_type  # 'REGULAR' or 'PREMIUM'

#         # Fetch and apply charges based on charge_type
#         charge_data = get_charge_data(user_id, charge_type)

#         return {"charge_type": charge_type, "rate_value": charge_data.get('rate_value'),
#                 "rate_type": charge_data.get('rate_type')}

#     except BinChecker.DoesNotExist:
#         base_url = "https://bin-ip-checker.p.rapidapi.com/"
#         url = f"{base_url}?bin={card_no}"
#         headers = {
#             "Content-Type": "application/json",
#             "x-rapidapi-host": "bin-ip-checker.p.rapidapi.com",
#             "x-rapidapi-key": "cc2d7a485cmsh2ef097246fe89c4p1817c3jsn6a80e0b7f5cf"
#         }

#         try:
#             response = requests.post(url, headers=headers)
#             response_data = response.json()

#             if response.status_code == 200:
#                 response_data = response.json()

#                 country_name = response_data.get("BIN", {}).get("country", {}).get("name", "").upper()
#                 level = response_data.get("BIN", {}).get("level", "").upper()
#                 brand = response_data.get("BIN", {}).get("brand", "").upper()

#                 charge_type = 'REGULAR'
#                 if country_name != 'INDIA' or any(
#                         keyword in level for keyword in ['BUSINESS', 'CORPORATE']) or brand not in ['MASTER', 'VISA',
#                                                                                                     'RUPAY', 'MAESTRO']:
#                     charge_type = 'PREMIUM'

#                 with transaction.atomic():
#                     bin_checker = BinChecker.objects.create(
#                         card_number=card_no,
#                         response_data=response_data,
#                         charge_type=charge_type
#                     )

#                     # Fetch and apply charges based on charge_type
#                     charge_data = get_charge_data(user_id, charge_type)

#                     return {"charge_type": charge_type, "rate_value": charge_data.get('rate_value'),
#                             "rate_type": charge_data.get('rate_type')}

#             else:
#                 return {"status": "error", "message": "Failed to fetch BIN data from API"}

#         except requests.RequestException as e:
#             return {"status": "error", "message": f"API request failed: {str(e)}"}

def fetch_bin_details(card_no, user_id=None):
    if not card_no:
        return {"status": "error", "message": "Card number is required"}

    try:
        bin_entry = BinChecker.objects.get(card_number=card_no)
        charge_type = bin_entry.charge_type  # 'REGULAR' or 'PREMIUM'

        # Call get_charge_data only if user_id is provided
        charge_data = get_charge_data(user_id, charge_type) if user_id else {}

        return {
            "charge_type": charge_type,
            "rate_value": charge_data.get('rate_value') if user_id else None,
            "rate_type": charge_data.get('rate_type') if user_id else None
        }

    except BinChecker.DoesNotExist:
        base_url = "https://bin-ip-checker.p.rapidapi.com/"
        url = f"{base_url}?bin={card_no}"
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": "bin-ip-checker.p.rapidapi.com",
            "x-rapidapi-key": "cc2d7a485cmsh2ef097246fe89c4p1817c3jsn6a80e0b7f5cf"
        }

        try:
            response = requests.post(url, headers=headers)
            response_data = response.json()

            if response.status_code == 200:
                response_data = response.json()

                country_name = response_data.get("BIN", {}).get("country", {}).get("name", "").upper()
                level = response_data.get("BIN", {}).get("level", "").upper()
                brand = response_data.get("BIN", {}).get("brand", "").upper()

                charge_type = 'REGULAR'  
                if (country_name != 'INDIA' or 
                    any(keyword in level for keyword in ['BUSINESS', 'CORPORATE']) or 
                    not any(word in brand for word in ['MASTER', 'VISA', 'RUPAY', 'MAESTRO'])):
                    charge_type = 'PREMIUM'

                with transaction.atomic():
                    bin_checker = BinChecker.objects.create(
                        card_number=card_no,
                        response_data=response_data,
                        charge_type=charge_type
                    )

                    # Call get_charge_data only if user_id is provided
                    charge_data = get_charge_data(user_id, charge_type) if user_id else {}
                    # Call get_charge_data only if user_id is provided
                    charge_data = get_charge_data(user_id, charge_type) if user_id else {}

                    return {
                        "charge_type": charge_type,
                        "rate_value": charge_data.get('rate_value') if user_id else None,
                        "rate_type": charge_data.get('rate_type') if user_id else None
                    }

            else:
                return {"status": "error", "message": "Failed to fetch BIN data from API"}

        except requests.RequestException as e:
            return {"status": "error", "message": f"API request failed: {str(e)}"}



def get_charge_data(user_id, charge_type):
    """Fetch charges and return applicable rate based on charge_type ('REGULAR' or 'PREMIUM')"""
    sp_id = 1
    applicable_rate_key = "regular_rate" if charge_type == "REGULAR" else "premium_rate"

    # Check in PortalUserCharges first
    puc_entry = PortalUserCharges.objects.filter(pu_id=user_id, sp_id=sp_id).first()
    if puc_entry and puc_entry.puc_charges:
        charge_list = puc_entry.puc_charges  # Assuming JSONField stores a list
        applicable_charges = extract_applicable_charges(charge_list, applicable_rate_key)

        # Extract rate value
        rate_value = applicable_charges[0]['rate']  # Since it's a list, access the first dictionary
        rate_type = applicable_charges[0]['rate_type']  # Since it's a list, access the first dictionary

        return {"charge_source": "PortalUserCharges", "rate_value": rate_value, 'rate_type': rate_type}

    # If not found, fetch from HierarchyCharges
    hc_entry = HierarchyCharges.objects.filter(dh_id=None, sp_id=sp_id).first()
    if hc_entry and hc_entry.hc_charges:
        charge_list = hc_entry.hc_charges  # Assuming JSONField stores a list
        applicable_charges = extract_applicable_charges(charge_list, applicable_rate_key)

        # Extract rate value
        rate_value = applicable_charges[0]['rate']  # Since it's a list, access the first dictionary
        rate_type = applicable_charges[0]['rate_type']  # Since it's a list, access the first dictionary

        return {"charge_source": "HierarchyCharges", "rate_value": rate_value, 'rate_type': rate_type}

    return {"charge_source": "None", "charges": None}


def extract_applicable_charges(charge_list, applicable_rate_key):
    """Extracts relevant charge details based on charge_type (REGULAR or PREMIUM)"""
    extracted_charges = []
    for charge in charge_list:
        extracted_charges.append({
            "charge_type": charge.get("charge_type"),
            "rate": charge.get(applicable_rate_key),  # Get either regular_rate or premium_rate
            "rate_type": charge.get("rate_type"),
            "commission_type": charge.get("commission_type"),
            "effective_wallet": charge.get("effective_wallet"),
        })
    return extracted_charges









from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage
from .serializers import *
from django.db.models import Sum

#POS TRANSACTION FETCH API
def pos_fetch_transactions(request,queryset,trn_unique_id,terminal_id,search_txt,filter_by,start_date,end_date,list_user,page_size,page_number):

    if trn_unique_id:
        queryset = queryset.filter(trn_unique_id=trn_unique_id)

    if terminal_id:
        queryset = queryset.filter(terminal_id=terminal_id)

    if search_txt:
        queryset = queryset.filter(
            Q(customer_name__icontains=search_txt) |
            Q(trn_unique_id__icontains=search_txt) |
            Q(terminal_id__icontains=search_txt) |
            Q(created_by__icontains=search_txt) |
            Q(trn_status__icontains=search_txt) |
            Q(created_by__in=PortalUser.objects.filter(username__icontains=search_txt).values_list('id', flat=True))
        )

    if filter_by:
        allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']

        if filter_by not in allowed_filters:
            return Response({'status': 'fail', 'message': f'Invalid status filter. Allowed values: {", ".join(allowed_filters)}.'}, status=status.HTTP_400_BAD_REQUEST)
        queryset = queryset.filter(trn_status=filter_by)

    # if start_date and end_date:
    #     queryset = queryset.filter(pos_trn_dt__gte=start_date, pos_trn_dt__lte=end_date)
    if start_date and end_date:
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

        queryset = queryset.annotate(
            pos_date=TruncDate('pos_trn_dt')
        ).filter(
            pos_date__gte=start_date,
            pos_date__lte=end_date
        )

    if list_user:
        queryset = queryset.filter(created_by__in=list_user)

    totals = queryset.aggregate(

        total_amount=Sum('trn_amount')

    )

    paginator = Paginator(queryset, page_size)
    try:
        page_obj = paginator.page(page_number)
    except EmptyPage:
        return Response({'status': 'fail', 'message': 'Page not found.', 'data': {}}, status=status.HTTP_404_NOT_FOUND)

    serializer = PosServiceTrnSerializer(page_obj, many=True, context={'request': request})

    serializer_data = serializer.data


    

    total_settled_amount_calculated = 0.0

    


    for trn in queryset:

        if trn.is_settled:  # Only for settled transactions

            created_by_id = trn.created_by

            service_trn_id = trn.pos_trn_id

            

            portal_user_charge = PortalUserCharges.objects.filter(pu_id=created_by_id).first()

            gl_trn_record = GlTrn.objects.filter(pu=created_by_id, effective_type="DR", service_trn_id=service_trn_id)

            

            if gl_trn_record.exists():

                charge = transaction_charge(request, gl_trn_record, portal_user_charge)

                total_settled_amount_calculated += float(charge.get('settled_amount', 0))

            else:
                pass

    


    
    for data in serializer.data:
        created_by_id = data.get('created_by')
        service_trn_id = data.get('pos_trn_id')
        trn_amount = data.get('trn_amount')
        gl_trn_queryset = PortalUser.objects.filter(id=data['created_by']).first()

        if gl_trn_queryset:
            data['retailer_id'] = gl_trn_queryset.id
            data['retailer_username'] = gl_trn_queryset.username
            data['retailer_name'] = gl_trn_queryset.pu_name
        else:
            data['retailer_id'] = None
            data['retailer_username'] = None
            data['retailer_name'] = None

        portal_user_charge = PortalUserCharges.objects.filter(pu_id=created_by_id).first()

        gl_trn_record = GlTrn.objects.filter(pu=created_by_id, effective_type="DR", service_trn_id=service_trn_id)

        if gl_trn_record:
            charge = transaction_charge(request,gl_trn_record,portal_user_charge)

            data['total_amount'] = charge.get('total_amount')
            data['deducted_amount'] = charge.get('deducted_amount')
            data['settled_amount'] = charge.get('settled_amount')
            data['applicable_charge'] = charge.get('applicable_charge')
            data['charge_description'] = charge.get('charge_description')

        else:
            data['total_amount'] = trn_amount
            data['deducted_amount'] = 0.00
            data['settled_amount'] = 0.00
            data['applicable_charge'] = 0.00
            data['charge_description'] = 'Not settled.'

        # if data.get('pos_trn_dt'):
        #     data['pos_trn_dt'] = datetime.datetime.strptime(
        #         data['pos_trn_dt'], "%Y-%m-%dT%H:%M:%S.%f%z"
        #     ).strftime("%Y-%m-%d %I:%M %p")
        if data.get('pos_trn_dt'):
            dt_str = data['pos_trn_dt'].replace("Z", "+0000")

            try:
                # Try parsing with microseconds
                dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                # Try without microseconds
                dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z")

            data['pos_trn_dt'] = dt_obj.strftime("%Y-%m-%d %I:%M %p")


    Response_data = {
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
        'total_items': paginator.count,
        'results': serializer_data ,
        'totals': {
            'total_amount': float(totals['total_amount'] or 0),
            'total_settled_amount': round(total_settled_amount_calculated, 2)  # ✅ Actual settled
        }
    }
    return Response_data

# BBPS TRANSACTION FETCH API
def bbps_fetch_transactions(request,queryset,filter_by,start_date,end_date,list_user,bbps_request_id,bbps_blr_id,search_txt, page_size,page_number):

    if filter_by:
        allowed_filters = ['PENDING', 'SUCCESS']
        if filter_by not in allowed_filters:
            return Response({'status': 'fail', 'message': f'Invalid status filter. Allowed values: {", ".join(allowed_filters)}.'}, status=status.HTTP_400_BAD_REQUEST)
        
        queryset = queryset.filter(bbps_status=filter_by)

    # if start_date and end_date:
    #     queryset = queryset.filter(created_at__gte=start_date, created_at__lte=end_date)

    if start_date and end_date:
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        queryset = queryset.annotate(
            created_date=TruncDate('created_at')
        ).filter(
            created_date__gte=start_date,
            created_date__lte=end_date
        )

    if list_user:
        queryset = queryset.filter(created_by__in=list_user)

    if bbps_request_id:
        queryset = queryset.filter(bbps_request_id=bbps_request_id)

    if bbps_blr_id:
        queryset = queryset.filter(bbps_blr_id=bbps_blr_id)

    if search_txt:
        queryset = queryset.filter(
            Q(bbps_contact_no__icontains=search_txt) |
            Q(bbps_blr_id__icontains=search_txt) |
            Q(created_by__icontains=search_txt) |
            Q(bbps_status__icontains=search_txt) |
            Q(created_by__in=PortalUser.objects.filter(username__icontains=search_txt).values_list('id', flat=True))
        )

    totals = queryset.aggregate(
        total_amount=Sum('bbps_amount'),  # Replace with actual field
        total_settled_amount=Sum('bbps_amount', filter=Q(bbps_status='SUCCESS'))
    )

    paginator = Paginator(queryset, page_size)
    try:
        page_obj = paginator.page(page_number)
    except EmptyPage:
        return Response({'status': 'fail', 'message': 'Page not found.', 'data': {}}, status=status.HTTP_404_NOT_FOUND)

    serializer = BBPSBillerPaymentSerializer(page_obj, many=True, context={'request': request})
    serializer_data  = serializer.data

    for data in serializer_data:
        gl_trn_queryset = PortalUser.objects.filter(id=data['created_by']).first()

        #ADD Category Name
        bbps_blr_id = data.get('bbps_blr_id')
        name = BBPSBiller.objects.get(bbps_blr_id=bbps_blr_id)
        data['category_name'] = name.bbps_category.category_name

        if gl_trn_queryset:
            data['retailer_id'] = gl_trn_queryset.id
            data['retailer_username'] = gl_trn_queryset.username
            data['retailer_name'] = gl_trn_queryset.pu_name

        else:
            data['retailer_id'] = None
            data['retailer_username'] = None
            data['retailer_name'] = None

        if data.get('created_at'):
            data['created_at'] = datetime.datetime.strptime(data['created_at'], "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%Y-%m-%d %I:%M %p")

    Response_data = {
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
        'total_items': paginator.count,
        'results': serializer_data ,
        'totals': {
            'total_amount': float(totals['total_amount'] or 0),
            'total_settled_amount': float(totals['total_settled_amount'] or 0)
        }
    }

    return Response_data

# POS TRANSACTION CHARGE CALCULATION
def transaction_charge(request,gl_trn_queryset,portal_user_charges):

    settled_summary = gl_trn_queryset.aggregate(
        total_amt=Sum('gl_trn_amt'),
        total_tds_amt=Sum('gl_tds_amt'),
        effectvie_amt=Sum('effectvie_amt'),
        gl_tax_amt=Sum('gl_tax_amt'),
        gl_tds_rate=Sum('gl_tds_rate'),
        gl_tax_rate=Sum('gl_tax_rate')
    )
    
    gl_tds_rate = settled_summary.get('gl_tds_rate', 0.00) or 0.00
    gl_tax_rate = settled_summary.get('gl_tax_rate', 0.00) or 0.00

    total_amt = settled_summary.get('total_amt', 0.00) or 0.00
    deducted_amount = settled_summary.get('effectvie_amt', 0.00) or 0.00
    settled_amount = total_amt - deducted_amount

    applicable_charge = 0.00
    charge_description = "No charge applied"

    if portal_user_charges and portal_user_charges.puc_charges:
        commission_type = portal_user_charges.puc_charges[0].get('commission_type', '')

        if commission_type == 'CHARGE WITH GST':
            applicable_charge = gl_tax_rate
            charge_description = "GST Charge Applied"

        elif commission_type == 'COMMISSION WITHOUT GST':
            applicable_charge = gl_tds_rate
            charge_description = "TDS Charge Applied"

        elif commission_type == 'COMMISSION WITH GST':
            applicable_charge = [gl_tds_rate , gl_tax_rate]
            charge_description = "TDS + GST Charge Applied"

    settled_data = {
        'total_amount': total_amt,
        'deducted_amount': deducted_amount,
        'settled_amount': settled_amount,
        'applicable_charge': applicable_charge,
        'charge_description': charge_description
    }
    
    return settled_data



def pg_fetch_transactions(request, queryset, trn_unique_id, pg_id, search_txt, filter_by, start_date, end_date, list_user, page_size, page_number):
    # Apply filters
    if trn_unique_id:
        queryset = queryset.filter(trn_unique_id=trn_unique_id)
    
    if pg_id:
        queryset = queryset.filter(pg_id=pg_id)
    

    if search_txt:
        queryset = queryset.filter(
            Q(buyer_firstname__icontains=search_txt) |
            Q(buyer_lastname__icontains=search_txt) |
            Q(buyer_email__icontains=search_txt) |
            Q(buyer_phone__icontains=search_txt) |
            Q(trn_unique_id__icontains=search_txt) |
            Q(trn_status__icontains=search_txt) |
            Q(created_by__in=PortalUser.objects.filter(username__icontains=search_txt).values_list('id', flat=True))
        )
    
    if filter_by:
        allowed_filters = ['COMPLETED', 'SETTLED', 'FAILED']
        if filter_by not in allowed_filters:
            return Response({'status': 'fail', 'message': f'Invalid status filter. Allowed values: {", ".join(allowed_filters)}.'}, status=status.HTTP_400_BAD_REQUEST)
        queryset = queryset.filter(trn_status=filter_by)
    
    # if start_date and end_date:
    #     queryset = queryset.filter(created_at__gte=start_date, created_at__lte=end_date)

    if start_date and end_date:
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        queryset = queryset.annotate(
            created_date=TruncDate('created_at')
        ).filter(
            created_date__gte=start_date,
            created_date__lte=end_date
        )

    
    if list_user:
        queryset = queryset.filter(created_by__in=list_user)

    totals = queryset.aggregate(
        total_amount=Sum('trn_amount'),
        total_settled_amount=Sum('net_credit_to_user', filter=Q(trn_status__in=["COMPLETED", "SETTLED"])),
        total_mdr_amount=Sum('sp_mdr_amount', filter=Q(trn_status__in=["COMPLETED", "SETTLED"])),
        total_gst_amount=Sum('sp_gst_amount', filter=Q(trn_status__in=["COMPLETED", "SETTLED"])),
        total_receivable_amount=Sum('sp_receivable_amount', filter=Q(trn_status__in=["COMPLETED", "SETTLED"]))
    )
    
    # Apply pagination
    paginator = Paginator(queryset, page_size)
    
    try:
        page_obj = paginator.page(page_number)
    except EmptyPage:
        return Response({'status': 'fail', 'message': 'Page not found.', 'data': {}}, status=status.HTTP_404_NOT_FOUND)

    # Serialize data
    serializer = PgServiceTrnSerializer(page_obj, many=True, context={'request': request})
    serializer_data = serializer.data
    
    
    # Process data and add additional fields
    for data in serializer_data:
        created_by_id = data.get('created_by')
        pg_trn_id = data.get('pg_trn_id')
        trn_amount = data.get('trn_amount')

        gl_trn_queryset = PortalUser.objects.filter(id=created_by_id).first()

        if gl_trn_queryset:
            data['retailer_id'] = gl_trn_queryset.id
            data['retailer_username'] = gl_trn_queryset.username
            data['retailer_name'] = gl_trn_queryset.pu_name
        else:
            data['retailer_id'] = None
            data['retailer_username'] = None
            data['retailer_name'] = None

        # Process other fields
        portal_user_charge = PortalUserCharges.objects.filter(pu_id=created_by_id).first()

        gl_trn_record = GlTrn.objects.filter(pu=created_by_id, effective_type="DR", service_trn_id=pg_trn_id)

        if gl_trn_record:
            charge = transaction_charge(request, gl_trn_record, portal_user_charge)

            data['total_amount'] = charge.get('total_amount')
            data['deducted_amount'] = charge.get('deducted_amount')
            data['settled_amount'] = charge.get('settled_amount')
            data['applicable_charge'] = charge.get('applicable_charge')
            data['charge_description'] = charge.get('charge_description')
        else:
            data['total_amount'] = trn_amount
            data['deducted_amount'] = 0.00
            data['settled_amount'] = 0.00
            data['applicable_charge'] = 0.00
            data['charge_description'] = 'Not settled.'

        
        

        # Date format handling
        if data.get('created_at'):
            dt_str = data['created_at'].replace("Z", "+0000")
            try:
                dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z")
            data['created_at'] = dt_obj.strftime("%Y-%m-%d %I:%M %p")


    Response_data = {
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
        'total_items': paginator.count,
        'results': serializer_data,
        'totals': {
            'total_amount': float(totals['total_amount'] or 0),
            'total_settled_amount': float(totals['total_settled_amount'] or 0),
            'total_mdr_amount': float(totals['total_mdr_amount'] or 0),
            'total_gst_amount': float(totals['total_gst_amount'] or 0),
            'total_receivable_amount': float(totals['total_receivable_amount'] or 0),
        }
    }
    return Response_data


def fetch_bin_details_pg(card_no, user_id=None):
    if not card_no:
        return {"status": "error", "message": "Card number is required"}

    try:
        base_url = "https://bin-ip-checker.p.rapidapi.com/"
        url = f"{base_url}?bin={card_no[:6]}" 
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": "bin-ip-checker.p.rapidapi.com",
            "x-rapidapi-key": "cc2d7a485cmsh2ef097246fe89c4p1817c3jsn6a80e0b7f5cf"
        }

        try:
            response = requests.post(url, headers=headers)
            response_data = response.json()

            if response.status_code == 200:
                country_name = response_data.get("BIN", {}).get("country", {}).get("name", "").upper()
                level = response_data.get("BIN", {}).get("level", "").upper()
                brand = response_data.get("BIN", {}).get("brand", "").upper()

                charge_type = 'REGULAR'
                if (country_name != 'INDIA' or 
                    any(keyword in level for keyword in ['BUSINESS', 'CORPORATE']) or 
                    not any(word in brand for word in ['MASTER', 'VISA', 'RUPAY', 'MAESTRO'])):
                    charge_type = 'PREMIUM'

                return {"status": "success", "card_type": charge_type, "brand": brand}

            else:
                return {"status": "error", "message": "Failed to fetch BIN data from API"}

        except requests.RequestException as e:
            return {"status": "error", "message": f"API request failed: {str(e)}"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

