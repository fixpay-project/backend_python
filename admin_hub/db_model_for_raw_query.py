import json
import re
from django.db import connections, transaction
from django.utils.timezone import now
from .models import (
    PortalUserCharges, AdHSNSAC, AdServiceProvider,
    PortalUserWallet, PortalUser, AdService,PortalUserDetails
)


def fetch_user_hierarchy(user_id):
    user_lst = []
    user = PortalUser.objects.get(id=user_id)

    # Recursive Query to fetch all users in the hierarchy
    cursor = connections['default'].cursor()

    query = f'''WITH RECURSIVE "Descendants" AS (
    SELECT "pu_id", "created_by", "dh_id"
    FROM "ad_portal_user_details"
    WHERE "pu_id" = {user.id}
    UNION ALL
    SELECT n."pu_id", n."created_by", n."dh_id"
    FROM "ad_portal_user_details" n
    JOIN "Descendants" d ON n."pu_id" = d."created_by"
    WHERE n."pu_id" != 1
    )
    SELECT * FROM "Descendants";'''

    cursor.execute(query)
    result = cursor.fetchall()
    cursor.close()

    for res in result:
        pu_id, created_by, dh_id = res

        user_lst.append({'user_id': pu_id, 'dh_id': dh_id})

    return user_lst


def fetch_user_charges_hierarchy(user_id, sp_id):
    user_lst = []
    user = PortalUser.objects.get(id=user_id)

    # Recursive Query to fetch all users in the hierarchy
    cursor = connections['default'].cursor()

    query = f'''WITH RECURSIVE "Descendants" AS (
        SELECT "pu_id", "parent_id", "puc_charges", "mark_type", "sp_id", "dh_id"
        FROM "ad_portal_user_charges"
        WHERE "pu_id" = {user.id} AND "sp_id" = {sp_id}
        UNION ALL
        SELECT n."pu_id", n."parent_id", n."puc_charges", n."mark_type", n."sp_id", n."dh_id"
        FROM "ad_portal_user_charges" n
        JOIN "Descendants" d ON n."pu_id" = d."parent_id" AND n."sp_id" = d."sp_id"
        )
        SELECT * FROM "Descendants";'''

    cursor.execute(query)
    result = cursor.fetchall()
    cursor.close()

    for res in result:
        pu_id, parent_id, puc_charges, charge_type, sp_id, dh_id = res

        user_lst.append({'pu_id': pu_id, 'parent_id': parent_id, 'puc_charges': puc_charges, 'charge_type': charge_type,
                         'sp_id': sp_id, 'dh_id': dh_id})

    return user_lst



# def fetch_user_hierarchy(user_id):
#     """
#     Fetch all users in the hierarchy under the given user_id using Django ORM.
#     Returns a list of dictionaries with user_id and dh_id.
#     """
#     user_lst = []
    
#     def get_descendants(pu_id):
#         try:
#             user_details = PortalUserDetails.objects.get(pu_id=pu_id)
#             user_lst.append({'user_id': user_details.pu_id, 'dh_id': user_details.dh_id})
#             descendants = PortalUserDetails.objects.filter(
#                 created_by=pu_id
#             ).exclude(pu_id=1)
#             for descendant in descendants:
#                 get_descendants(descendant.pu_id)
#         except PortalUserDetails.DoesNotExist:
#             pass
    
#     try:
#         PortalUser.objects.get(id=user_id)
#         get_descendants(user_id)
#     except PortalUser.DoesNotExist:
#         pass
    
#     print(user_lst)
#     return user_lst

# def fetch_user_charges_hierarchy(user_id, sp_id):
#     """
#     Fetch all user charges in the hierarchy under the given user_id and sp_id using Django ORM.
#     Returns a list of dictionaries with pu_id, parent_id, puc_charges, charge_type, sp_id, and dh_id.
#     """
#     user_lst = []
    
#     def get_charge_descendants(pu_id, sp_id):
#         try:
#             charges = PortalUserCharges.objects.filter(pu_id=pu_id, sp_id=sp_id)
#             for charge in charges:
#                 user_lst.append({
#                     'pu_id': charge.pu_id,
#                     'parent_id': charge.parent_id,
#                     'puc_charges': charge.puc_charges,
#                     'charge_type': charge.mark_type,
#                     'sp_id': charge.sp_id,
#                     'dh_id': charge.dh_id
#                 })
#                 descendants = PortalUserCharges.objects.filter(
#                     parent_id=charge.pu_id,
#                     sp_id=sp_id
#                 )
#                 for descendant in descendants:
#                     get_charge_descendants(descendant.pu_id, sp_id)
#         except PortalUserCharges.DoesNotExist:
#             pass
    
#     try:
#         PortalUser.objects.get(id=user_id)
#         get_charge_descendants(user_id, sp_id)
#     except PortalUser.DoesNotExist:
#         pass
    
#     return user_lst
