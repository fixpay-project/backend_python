import jwt
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework.permissions import BasePermission
from admin_hub.models import PortalUser
from typing import Type
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions
from rest_framework_simplejwt.tokens import RefreshToken
from admin_hub.models import *
from django.http.request import HttpRequest


def get_tokens_for_user(user, lifetime):
    refresh = RefreshToken.for_user(user)

    # access_token = refresh.access_token
    try:
        if user.pu_role == "ADMIN":
            refresh['role'] = user.pu_role  # Assuming 'role' is a field in your user model
        elif user.pu_role == "DISTRIBUTOR":
            refresh['role'] = user.pu_role  # Assuming 'role' is a field in your user model
        elif user.pu_role == "RETAILER":
            refresh['role'] = user.pu_role  # Assuming 'role' is a field in your user model
        else:
            refresh['role'] = "ADMIN"  # Assuming 'role' is a field in your user model
    except:
        refresh['role'] = "ADMIN"
    refresh.set_exp(lifetime=lifetime)

    return refresh.access_token


class IsAdmin(BasePermission):
    """
    Allows access only to manager users.
    """

    def has_permission(self, request: Type[HttpRequest], view):
        try:
            # Manually fetch the PortalUser based on request.user.id or any other field
            portal_user = PortalUser.objects.get(id=request.user.id)  # Adjust for your PortalUser model
            return bool(portal_user and portal_user.pu_role == "ADMIN")
        except PortalUser.DoesNotExist:
            return False

    # def has_permission(self, request: Type[HttpRequest], view):
    #     try:
    #         return bool(request.user and request.user.is_authenticated and request.user.pu_role == "Admin")
    #     except:
    #         return False


class IsDistributor(BasePermission):
    """
    Allows access only to manager users.
    """

    def has_permission(self, request: Type[HttpRequest], view):
        # try:
        #     return bool(request.user and request.user.is_authenticated and request.user.pu_role == "Distributor")
        # except:
        #     return False

        try:
            # Manually fetch the PortalUser based on request.user.id or any other field
            portal_user = PortalUser.objects.get(id=request.user.id)  # Adjust for your PortalUser model
            return bool(portal_user and portal_user.pu_role == "DISTRIBUTOR")
        except PortalUser.DoesNotExist:
            return False


class IsRetailer(BasePermission):
    """
    Allows access only to manager users.
    """

    def has_permission(self, request: Type[HttpRequest], view):
        try:
            # Manually fetch the PortalUser based on request.user.id or any other field
            portal_user = PortalUser.objects.get(id=request.user.id)  # Adjust for your PortalUser model
            return bool(portal_user and portal_user.pu_role == "RETAILER")
        except PortalUser.DoesNotExist:
            return False

    # def has_permission(self, request: Type[HttpRequest], view):
    #     try:
    #         return bool(request.user and request.user.is_authenticated and request.user.pu_role == "Retailer")
    #     except:
    #         return False


class IsSuperAdmin(BasePermission):
    """
    Allows access only to manager users.
    """

    def has_permission(self, request: Type[HttpRequest], view):
        try:
            return bool(request.user and request.user.is_authenticated)
        except:
            return False


class CustomJWTAuthentication(JWTAuthentication):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def authenticate(self, request):
        get_raw_token = self.get_header(request)
        if get_raw_token is None:
            return None

        raw_token = self.get_raw_token(get_raw_token)

        # validated_token = self.get_validated_token(raw_token)

        try:

            # Authenticate using the actual auth model
            user = self.get_user_from_token(raw_token)

            if not user:
                raise exceptions.AuthenticationFailed('User not found in the authentication model.')

            return (user, raw_token)
        except Exception as e:
            raise exceptions.AuthenticationFailed(str(e))

    def get_user_from_token(self, validated_token):

        token = AccessToken(validated_token)
        
        get_user_logs = PortalUserLoginLogs.objects.filter(pu_token=token)
        if get_user_logs:
            if get_user_logs[0].is_expire == True:
                raise exceptions.AuthenticationFailed('Access Token is expired.')
        
        # Print the entire payload to inspect it
        payload = token.payload

        # Attempt to extract 'user_id'
        user_id = payload.get('user_id')
        if user_id:
            if payload.get('role') == "SUPERADMIN":
                try:
                    user = PortalUser.objects.get(id=user_id)  # Use your actual auth model here #--->>>change Custimeruser
                    return user
                except PortalUser.DoesNotExist:
                    return None
            else:
                try:
                    user = PortalUser.objects.get(id=user_id)  # Use your actual auth model here
                    return user
                except PortalUser.DoesNotExist:
                    return None
        else:
            print("User ID not found in token.")
            return None