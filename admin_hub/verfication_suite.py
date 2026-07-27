# Standard Library Imports
import base64
import json
import os
from django.conf import settings
from django.http import JsonResponse
# Third-Party Library Imports
import requests

# Django Core Imports
from django.utils.crypto import get_random_string

# Django REST Framework Imports
from rest_framework import status

client_id = getattr(settings, 'CASHFREE_CLIENT_ID', os.getenv('CASHFREE_CLIENT_ID', ''))
client_secret = getattr(settings, 'CASHFREE_CLIENT_SECRET', os.getenv('CASHFREE_CLIENT_SECRET', ''))


def aadhaar_verify(aadhaar_card):
    aadhaar_url = "https://api.cashfree.com/verification/offline-aadhaar/otp"
    # aadhaar_url = "https://sandbox.cashfree.com/verification/offline-aadhaar/otp"

    aadhaar_payload = {"aadhaar_number": aadhaar_card}
    aadhaar_headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-client-id": client_id,
        "x-client-secret": client_secret
    }

    aadhaar_response = requests.post(aadhaar_url, json=aadhaar_payload, headers=aadhaar_headers)

    res = aadhaar_response.json()
    if aadhaar_response.status_code == 200:

        response_data = {'status': status.HTTP_200_OK,
                         'data': {
                             'status': 'success',
                             'message': 'OTP sent successfully',
                             'is_final': False,
                             'data': {'ref_id': res['ref_id'], 'aadhaar_otp': 267987}
                         }
                         }

    else:
        response_data = {
            'status': aadhaar_response.status_code,
            'data': res
        }
    return response_data


def aadhaar_otp_verify(aadhaar_otp, ref_id, fwdp, codeVerifier):
    otp_url = "https://api.cashfree.com/verification/offline-aadhaar/verify"
    # otp_url = "https://sandbox.cashfree.com/verification/offline-aadhaar/verify"

    otp_payload = {
        "otp": aadhaar_otp,
        "ref_id": ref_id
    }
    otp_headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-client-id": client_id,
        "x-client-secret": client_secret
    }

    otp_response = requests.post(otp_url, json=otp_payload, headers=otp_headers)

    res = otp_response.json()
    if otp_response.status_code == 200:

        response_data = {'status': status.HTTP_200_OK,
                         'data': {
                             'status': 'success',
                             'message': 'Aadhaar verified successfully',
                             'is_final': False,
                             'aadhaar_data': res
                         }
                         }
    else:
        response_data = {
            'status': otp_response.status_code,
            'data': res
        }
    return response_data


def verify_pan_card(pan_card):
    pan_url = "https://api.cashfree.com/verification/pan/advance"
    # pan_url = "https://sandbox.cashfree.com/verification/pan/advance"

    pan_payload = {
        "pan": pan_card,
        "verification_id": get_random_string(length=10)
    }
    pan_headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-client-id": client_id,
        "x-client-secret": client_secret
    }

    pan_response = requests.post(pan_url, json=pan_payload, headers=pan_headers)

    res = pan_response.json()
    if pan_response.status_code == 200:

        response_data = {'status': status.HTTP_200_OK,
                         'data': {
                             'status': 'success',
                             'message': 'Pan verified successfully',
                             'is_final': False,
                             'data': res
                         }
                         }
    else:
        response_data = {
            'status': pan_response.status_code,
            'data': res
        }

    return response_data


def verify_ifsc(ifsc_code):
    url = "https://api.cashfree.com/verification/ifsc"
    payload = {
        "verification_id": get_random_string(length=10),
        "ifsc": ifsc_code
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-client-id": client_id,
        "x-client-secret": client_secret
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=200)
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': str(e)}, status=500)