# Standard Library Imports
import os

# Django Core Imports
from django.db.models import Q, Prefetch
from django.utils import timezone
from django.db import transaction


# Django REST Framework Imports
from rest_framework.decorators import parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser, FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, permissions

# Local Application Imports
from ssepl_backend.custom_jwt_auth import get_tokens_for_user, IsAdmin, CustomJWTAuthentication
from validation.custom_validation import *
from .serializers import *
from .models import *

"""
    View class for managing banner operations.
    Includes create, get, update, and delete functions.
"""


class BannerAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        if 'page_number' in request.data or 'page_size' in request.data:
            return self.get_banner(request)
        elif 'banner_title' in request.data and 'banner_type' in request.data and 'banner_image' in request.data and 'banner_description' in request.data:
            return self.create_banner(request)
        else:
            return Response({'status': 'fail', 'message': 'Invalid request data.'}, status=status.HTTP_400_BAD_REQUEST)

    def create_banner(self, request):
        try:
            banner_title = request.data.get('banner_title')
            banner_type = request.data.get('banner_type')
            banner_images = request.FILES.getlist('banner_image')
            banner_description = request.data.get('banner_description')

            # Check for existing banner title
            if Banner.objects.filter(banner_title=banner_title, banner_is_delete=False).exists():
                return Response({
                    'status': 'fail',
                    'message': 'A banner with this title already exists.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Validate banner type
            if banner_type and not checkbannertype(banner_type):
                return Response({
                    'status': 'fail',
                    'message': 'Invalid banner type. Allowed values are WEB BANNER, MOBILE BANNER, or LOGIN PAGE BANNER.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Function to save files
            def save_files(files, directory):
                if not os.path.exists(directory):
                    os.makedirs(directory)

                urls = []
                for file in files:
                    # Ensure the file is valid
                    if not hasattr(file, 'name'):
                        return None  # Indicate an error state

                    file_extension = file.name.split('.')[-1].lower()
                    if file_extension not in ['png', 'jpg']:
                        return None  # Indicate an error state

                    # Sanitize file name
                    sanitized_file_name = file.name.replace(' ', '').replace('(', '').replace(')', '')
                    file_path = os.path.join(directory, sanitized_file_name)

                    # Save the file
                    with open(file_path, "wb") as f:
                        f.write(file.read())

                    # Construct URL
                    urls.append(f'http://{request.META["HTTP_HOST"]}/media/Banner/{sanitized_file_name}')

                return urls

            # Check if there are images to save
            if not banner_images:
                return Response({
                    'status': 'fail',
                    'message': 'No banner image provided.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Save the images
            banner_image_urls = save_files(banner_images, 'media/Banner/')

            if banner_image_urls is None:
                return Response({
                    'status': 'fail',
                    'message': 'Invalid file type. Only PNG and JPG files are allowed.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Limit to active banners
            active_banners_count = Banner.objects.filter(is_deactive=False, banner_is_delete=False).count()
            is_deactive = active_banners_count >= 5

            # Create new banner
            Banner.objects.create(
                banner_title=banner_title,
                banner_type=banner_type,
                banner_image=banner_image_urls[0],  # Use the first image URL
                banner_description=banner_description,
                is_deactive=is_deactive,
                created_by=request.user
            )

            return Response({'status': 'success', 'message': 'Banner added successfully.'},
                            status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_banner(self, request):
        data = {
            "total_pages": 0,
            "current_page": 0,
            "total_items": 0,
            "results": []
        }
        try:
            page_number = request.POST.get('page_number', 1)
            page_size = request.POST.get('page_size', 10)
            banner_id = request.POST.get('banner_id', None)

            validation_page_number = isnumber(page_number)
            if validation_page_number == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page number. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            validation_page_size = isnumber(page_size)
            if validation_page_size == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page size. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            if banner_id:
                validation_banner_id = isnumber(banner_id)
                if validation_banner_id == False:
                    return Response({'status': 'fail', 'message': 'Invalid banner ID. It must be a positive integer.',
                                     'data': data}, status=status.HTTP_400_BAD_REQUEST)

            page_size = int(page_size)
            page_number = int(page_number)

            search = request.POST.get('search', '')

            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size

            banners = Banner.objects.filter(banner_is_delete=False)
            if banner_id is not None:
                paginated_banners = banners.filter(banner_id=banner_id, banner_is_delete=False)
                if not paginated_banners.exists():
                    return Response({'status': 'fail', 'message': 'Banner ID does not exist.', 'data': data},
                                    status=status.HTTP_404_NOT_FOUND)


            elif search != '':
                paginated_banners = banners.filter(
                    Q(banner_title__icontains=search) | Q(banner_description__icontains=search), banner_is_delete=False)
                if not paginated_banners.exists():
                    return Response(
                        {'status': 'success', 'message': 'No banners found matching the search criteria.', 'data': data},
                        status=status.HTTP_200_OK)

            else:
                paginated_banners = banners[start_index:end_index]

            total_items = banners.count()
            total_pages = (len(banners) + page_size - 1) // page_size

            serialized_banners = BannerSerializer(paginated_banners, many=True)
            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serialized_banners.data
            }
            return Response({'status': 'success', 'message': 'Banners retrieved successfully.', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}', 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        banner_id = request.data.get('banner_id')
        banner_title = request.data.get('banner_title', None)
        banner_type = request.data.get('banner_type', None)
        banner_image = request.FILES.getlist('banner_image', None)
        banner_description = request.data.get('banner_description', None)
        message = 'Banner Updated Successfully.'


        # Validate banner_id
        if not banner_id:
            return Response({'status': 'fail', 'message': 'Banner ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if not isnumber(banner_id):
                return Response({'status': 'fail', 'message': 'Invalid banner ID. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # Check for existing banner with the same title
            existing_banner = Banner.objects.filter(banner_title=banner_title, banner_is_delete=False).exclude(
                banner_id=banner_id).first()

            if existing_banner:
                return Response({'status': 'fail', 'message': 'A banner with this title already exists.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # Validate banner_type
            if banner_type:
                if not checkbannertype(banner_type):
                    return Response({
                        'status': 'fail',
                        'message': 'Invalid banner type. Allowed values are WEB BANNER, MOBILE BANNER, or LOGIN PAGE BANNER.'
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Check if banner exists
            banner_data = Banner.objects.filter(banner_id=banner_id, banner_is_delete=False).first()

            if not banner_data:
                return Response({'status': 'fail', 'message': 'Banner does not exist.'},
                                status=status.HTTP_404_NOT_FOUND)

            # File saving utility
            def save_files(files, directory):
                if not os.path.exists(directory):
                    os.makedirs(directory)
                urls = []
                for file in files:
                    file_ext = file.name.split('.')[-1].lower()
                    if file_ext not in ['png', 'jpg']:
                        return Response({
                            'status': 'fail',
                            'message': 'Invalid file type. Only PNG and JPG files are allowed.'
                        }, status=status.HTTP_400_BAD_REQUEST)

                    file_path = os.path.join(directory, file.name.replace(' ', '').replace('(', '').replace(')', ''))
                    with open(file_path, "wb") as f:
                        f.write(file.read())

                    urls.append(
                        f'http://{request.META["HTTP_HOST"]}/media/Banner/{file.name.replace(" ", "").replace("(", "").replace(")", "")}')
                return urls

            # Update banner fields if provided
            if banner_title:
                banner_data.banner_title = banner_title

            if banner_type:
                banner_data.banner_type = banner_type

            if banner_image:
                banner_image_urls = save_files(banner_image, 'media/Banner/')
                if isinstance(banner_image_urls, Response):
                    return banner_image_urls  # Return error if file validation failed
                banner_data.banner_image = banner_image_urls[0]

            if banner_description:
                banner_data.banner_description = banner_description

            # Banner activation/deactivation logic
            if banner_id and not any([banner_title, banner_type, banner_image, banner_description]):
                active_banners_count = Banner.objects.filter(is_deactive=False, banner_is_delete=False).count()

                if active_banners_count >= 5 and not banner_data.is_deactive == False:
                    return Response({
                        'status': 'fail',
                        'message': 'Maximum of 5 active banners allowed. Please deactivate an existing banner before activating this one.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if active_banners_count <= 1 and banner_data.is_deactive == False:
                    return Response({
                        'status': 'fail',
                        'message': 'You cannot deactivate this banner. You need to have at least one active banner.'
                    }, status=status.HTTP_200_OK)

                banner_data.is_deactive = not banner_data.is_deactive
                message = 'Banner Deactivated Successfully.' if banner_data.is_deactive else 'Banner Activated Successfully.'

            # Update audit fields and save
            banner_data.updated_at = timezone.now()
            banner_data.updated_by = request.user
            banner_data.save()

            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        banner_id = request.data.get('banner_id')
        if not banner_id:
            return Response({'status': 'fail', 'message': 'banner ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if banner_id:
                banner_validation = isnumber(banner_id)
                if banner_validation == False:
                    return Response({'status': 'fail', 'message': 'Invalid banner ID. It must be a positive integer.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            banner_data = Banner.objects.filter(banner_id=banner_id, banner_is_delete=False).first()
            if not banner_data:
                return Response({'status': 'fail', 'message': 'Banner id is not exists'},
                                status=status.HTTP_404_NOT_FOUND)

            active_banners_count = Banner.objects.filter(is_deactive=False, banner_is_delete=False).count()
            if active_banners_count <= 1 and not banner_data.is_deactive:
                return Response({'status': 'fail',
                                 'message': 'You cannot delete this banner. You need to have at least one active banner.'},
                                status=status.HTTP_200_OK)

            banner_data.banner_is_delete = True
            banner_data.is_deactive = True
            banner_data.save()
            return Response({'status': 'success', 'message': 'Banner Deleted Successfully.'}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    View class for managing partner operations.
    Includes create, get, update, and delete functions.
"""


class PartnerAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        if 'page_number' in request.data or 'page_size' in request.data:
            return self.get_partner(request)
        elif 'partners_name' in request.data and 'partners_logo_image' in request.data and 'partners_description' in request.data:
            return self.create_partner(request)
        else:
            return Response({'status': 'fail', 'message': 'Invalid request data.'}, status=status.HTTP_400_BAD_REQUEST)

    def create_partner(self, request):
        try:
            partner_name = request.data.get('partners_name')
            partners_logo_images = request.FILES.getlist('partners_logo_image')
            partners_description = request.data.get('partners_description')

            partner_name_validation = isstring(partner_name)
            if partner_name_validation == False:
                return Response({'status': 'fail',
                                 'message': 'Invalid partner name. It should contain only alphabetic characters and spaces.'},
                                status=status.HTTP_400_BAD_REQUEST)

            def save_files(files, directory):
                if not os.path.exists(directory):
                    os.makedirs(directory)

                urls = []
                for file in files:
                    # Ensure the file is valid
                    if not hasattr(file, 'name'):
                        return None  # Indicate an error state

                    file_extension = file.name.split('.')[-1].lower()
                    if file_extension not in ['png', 'jpg']:
                        return None  # Indicate an error state

                    # Sanitize file name
                    sanitized_file_name = file.name.replace(' ', '').replace('(', '').replace(')', '')
                    file_path = os.path.join(directory, sanitized_file_name)

                    # Save the file
                    with open(file_path, "wb") as f:
                        f.write(file.read())

                    # Construct URL
                    urls.append(f'http://{request.META["HTTP_HOST"]}/media/Partners/{sanitized_file_name}')

                return urls

            logo_image_urls = save_files(partners_logo_images, 'media/Partners/')

            if logo_image_urls is None:
                return Response({
                    'status': 'fail',
                    'message': 'Invalid file type. Only PNG and JPG files are allowed.'
                }, status=status.HTTP_400_BAD_REQUEST)

            if Partners.objects.filter(partners_name=partner_name, partners_is_delete=False).exists():
                return Response({'status': 'fail', 'message': f'Partner with name "{partner_name}" already exists.'},
                                status=status.HTTP_400_BAD_REQUEST)

            partner = Partners.objects.create(
                partners_name=partner_name,
                partners_logo_image=logo_image_urls[0] if logo_image_urls else None,  # Use the first image if provided
                partners_description=partners_description,
                created_by=request.user
            )

            return Response({'status': 'success', 'message': 'Partner added successfully.'},
                            status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_partner(self, request):
        data = {
            "total_pages": 0,
            "current_page": 0,
            "total_items": 0,
            "results": []
        }
        try:
            # Validate and parse pagination parameters
            page_number = request.data.get('page_number', 1)
            page_size = request.data.get('page_size', 10)
            partner_id = request.data.get('partners_id', None)
            search = request.data.get('search', '').strip()  # Ensure search is not None

            if not page_number.isdigit() or int(page_number) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page number.', 'data': data},
                                status=status.HTTP_400_BAD_REQUEST)
            if not page_size.isdigit() or int(page_size) <= 0:
                return Response({'status': 'fail', 'message': 'Invalid page size.', 'data': data},
                                status=status.HTTP_400_BAD_REQUEST)

            page_number = int(page_number)
            page_size = int(page_size)
            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size

            # Filter partners
            partners = Partners.objects.filter(partners_is_delete=False)

            if partner_id is not None:
                if not str(partner_id).isdigit():
                    return Response({'status': 'fail', 'message': 'Invalid partner ID.', 'data': data},
                                    status=status.HTTP_400_BAD_REQUEST)
                partners = partners.filter(partners_id=partner_id)

            if search:
                partners = partners.filter(
                    Q(partners_name__icontains=search) | Q(partners_description__icontains=search)
                )

            total_items = partners.count()
            total_pages = (total_items + page_size - 1) // page_size

            paginated_partners = partners[start_index:end_index]
            serialized_partners = PartnersSerializer(paginated_partners, many=True)

            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serialized_partners.data
            }
            return Response({'status': 'success', 'message': 'Get all partners.', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        partner_id = request.data.get('partners_id')
        partner_name = request.data.get('partners_name', None)
        partner_logo_image = request.FILES.getlist('partners_logo_image', None)
        partner_description = request.data.get('partners_description', None)
        message = 'Partner updated Successfully.'

        try:
            if not partner_id:
                return Response(
                    {'status': 'fail', 'message': 'partner ID is required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            partner_id_validation = isnumber(partner_id)
            if not partner_id_validation:
                return Response(
                    {'status': 'fail', 'message': 'Invalid partner ID. It must be a positive integer.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if partner_name:
                name_validation = isstring(partner_name)
                if not name_validation:
                    return Response(
                        {'status': 'fail',
                         'message': 'Invalid partner name. It should contain only alphabetic characters and spaces.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                existing_partner = Partners.objects.filter(
                    partners_name=partner_name, partners_is_delete=False
                ).exclude(partners_id=partner_id).first()
                if existing_partner:
                    return Response(
                        {'status': 'fail', 'message': f'Partner with name "{partner_name}" already exists.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            partner_data = Partners.objects.filter(
                partners_id=partner_id, partners_is_delete=False
            ).first()
            if not partner_data:
                return Response(
                    {'status': 'fail', 'message': 'Partner does not exist.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            def save_files(files, directory):
                if not os.path.exists(directory):
                    os.makedirs(directory)
                urls = []
                for file in files:
                    file_extension = file.name.split('.')[-1].lower()
                    if file_extension not in ['png', 'jpg']:
                        return Response(
                            {'status': 'fail', 'message': 'Invalid file type. Only PNG and JPG files are allowed.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    sanitized_file_name = file.name.replace(' ', '').replace('(', '').replace(')', '')
                    file_path = os.path.join(directory, sanitized_file_name)
                    with open(file_path, "wb") as f:
                        f.write(file.read())
                    urls.append(f'http://{request.META["HTTP_HOST"]}/media/Logo/{sanitized_file_name}')
                return urls

            if partner_name is not None:
                partner_data.partners_name = partner_name

            if partner_logo_image:
                logo_image_urls = save_files(partner_logo_image, 'media/Logo/')
                if isinstance(logo_image_urls, Response):
                    return logo_image_urls
                partner_data.partners_logo_image = logo_image_urls[0]

            if partner_description is not None:
                partner_data.partners_description = partner_description

            if not any([partner_name, partner_logo_image, partner_description]):
                active_partner_count = Partners.objects.filter(is_deactive=False, partners_is_delete=False).count()
                if active_partner_count <= 1 and not partner_data.is_deactive:
                    return Response(
                        {'status': 'fail',
                         'message': 'You cannot update this partner. You need to have at least one active partner.'},
                        status=status.HTTP_200_OK
                    )

                partner_data.is_deactive = not partner_data.is_deactive
                message = 'Partner Activated Successfully.' if not partner_data.is_deactive else 'Partner Deactivated Successfully.'

            partner_data.updated_by = request.user
            partner_data.updated_at = timezone.now()
            partner_data.save()

            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        partner_id = request.data.get('partners_id')
        if not partner_id:
            return Response({"status": 'fail', "message": 'partner ID is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            if partner_id:
                partner_id_validation = isnumber(partner_id)
                if partner_id_validation == False:
                    return Response({'status': 'fail', 'message': 'Invalid partner ID. It must be a positive integer.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            partner_data = Partners.objects.filter(partners_id=partner_id, partners_is_delete=False).first()
            if not partner_data:
                return Response({'status': 'fail', 'message': 'Partner id is not exists'},
                                status=status.HTTP_404_NOT_FOUND)

            active_partners_count = Partners.objects.filter(is_deactive=False, partners_is_delete=False).count()

            if active_partners_count <= 1 and not partner_data.is_deactive:
                return Response({
                    'status': 'fail',
                    'message': 'You cannot delete this partner. You need to have at least one active partner.'
                }, status=status.HTTP_200_OK)

            partner_data.partners_is_delete = True
            partner_data.save()
            return Response({'status': 'success', 'message': 'Partner Deleted Successfully.'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    View class for managing news latter operations.
    Includes get, update, and delete functions.
"""


class NewsLatterAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):

        if 'page_number' in request.data or 'page_size' in request.data:
            return self.get_news_latter(request)

        else:
            return Response({'status': 'fail', 'message': 'Invalid request data.'}, status=status.HTTP_400_BAD_REQUEST)

    def get_news_latter(self, request):
        data = {
            'total_pages': 0,
            'current_page': 0,
            'total_items': 0,
            'results': []
        }
        try:
            page_number = request.data.get('page_number', 1)
            page_size = request.data.get('page_size', 10)
            news_id = request.data.get('news_id', None)
            search = request.data.get('search', None)

            validation_page_number = isnumber(page_number)
            if validation_page_number == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page number. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            validation_page_size = isnumber(page_size)
            if validation_page_size == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page size. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            if news_id:
                validation_banner_id = isnumber(news_id)
                if validation_banner_id == False:
                    return Response(
                        {'status': 'fail', 'message': 'Invalid news ID. It must be a positive integer.', 'data': data},
                        status=status.HTTP_400_BAD_REQUEST)

            page_size = int(page_size)
            page_number = int(page_number)

            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size

            news_latter = NewsLatter.objects.filter(news_is_delete=False)

            if news_id is not None:
                paginated_news = news_latter.filter(news_id=news_id, news_is_delete=False)
                if not paginated_news.exists():
                    return Response({'status': 'fail', 'message': 'News ID does not exist.', 'data': data},
                                    status=status.HTTP_404_NOT_FOUND)

            elif search is not None:
                paginated_news = news_latter.filter(
                    Q(news_supplier_name__icontains=search) | Q(news_email_id__icontains=search), news_is_delete=False)
                if not paginated_news.exists():
                    return Response({'status': 'fail', 'message': 'No news latter found matching the search criteria.',
                                     'data': data}, status=status.HTTP_200_OK)

            else:
                paginated_news = news_latter[start_index:end_index]

            total_items = news_latter.count()
            total_pages = (len(news_latter) + page_size - 1) // page_size

            serialized_news = NewsLatterSerializer(paginated_news, many=True)
            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serialized_news.data
            }
            return Response({'status': 'success', 'message': 'Get all news letter.', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        news_id = request.data.get('news_id')
        news_supplier_name = request.data.get('news_supplier_name', None)
        news_email_id = request.data.get('news_email_id', None)
        message = 'News latter updated successfully.'

        if not news_id:
            return Response(
                {'status': 'fail', 'message': 'News ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if NewsLatter.objects.filter(news_email_id=news_email_id).exclude(news_id=news_id).exists():
            return Response(
                {'status': 'fail', 'message': 'A Newsletter with this email already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            news_id_validation = isnumber(news_id)
            if not news_id_validation:
                return Response(
                    {'status': 'fail', 'message': 'Invalid news ID. It must be a positive integer.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            news_latter = NewsLatter.objects.filter(news_id=news_id, news_is_delete=False).first()
            if not news_latter:
                return Response(
                    {'status': 'fail', 'message': 'News latter not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            if news_supplier_name is None and news_email_id is None:
                active_news_count = NewsLatter.objects.filter(is_deactive=False, news_is_delete=False).count()

                if active_news_count <= 1 and not news_latter.is_deactive:
                    return Response(
                        {'status': 'fail',
                         'message': 'You cannot deactivate this news latter. At least one active news latter is required.'},
                        status=status.HTTP_200_OK
                    )

                news_latter.is_deactive = not news_latter.is_deactive
                message = 'News latter activated successfully.' if not news_latter.is_deactive else 'News latter deactivated successfully.'

            else:
                if news_supplier_name is not None:
                    news_latter.news_supplier_name = news_supplier_name
                if news_email_id is not None:
                    news_latter.news_email_id = news_email_id

            news_latter.updated_by = request.user
            news_latter.updated_at = timezone.now()
            news_latter.save()

            return Response(
                {'status': 'success', 'message': message},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request):
        news_id = request.data.get('news_id')

        if not news_id:
            return Response({'status': 'fail', 'message': 'news latter ID is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:

            if news_id:
                validation_news_id = isnumber(news_id)
                if validation_news_id == False:
                    return Response({'status': 'fail', 'message': 'Invalid news ID. It must be a positive integer.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            news_latter = NewsLatter.objects.filter(news_id=news_id, news_is_delete=False).first()
            if not news_latter:
                return Response({'status': 'fail', 'message': 'News latter is not found.'},
                                status=status.HTTP_404_NOT_FOUND)

            active_news_count = NewsLatter.objects.filter(is_deactive=False, news_is_delete=False).count()

            if active_news_count <= 1 and not news_latter.is_deactive:
                return Response({
                    'status': 'fail',
                    'message': 'You cannot delete this news latter. You need to have at least one active news latter.'
                }, status=status.HTTP_200_OK)

            news_latter.news_is_delete = True
            news_latter.save()
            return Response({'status': 'success', 'message': 'News latter deleted successfully.'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    View class for managing about us operations.
    Includes get and update functions.
"""


class AboutUsAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request):
        # data = {
        #     'total_pages': 0,
        #     'current_page': page_number,
        #     'total_items': 0,
        # 'resul/ts': []
        # }
        try:
            # page_number = int(request.data.get('page_number', 1))
            # page_size = int(request.data.get('page_size', 10))
            # validation_page_number = isnumber(page_number)
            # if validation_page_number == False:
            #     return Response({'status': 'fail', 'message': 'Invalid page number. It must be a positive integer.', 'data': data}, status=status.HTTP_400_BAD_REQUEST)

            # validation_page_size = isnumber(page_size)
            # if validation_page_size == False:
            #     return Response({'status': 'fail', 'message': 'Invalid page size. It must be a positive integer.', 'data': data}, status=status.HTTP_400_BAD_REQUEST)

            # page_size = int(page_size)
            # page_number = int(page_number)
            # start_index = (page_number - 1) * page_size
            # end_index = start_index + page_size

            about_us = AboutUs.objects.all()
            # paginated_about_us = about_us[start_index:end_index]

            serialized_about_us = AboutUsSerializer(about_us, many=True)
            print('----------------->',serialized_about_us)

            # total_items = about_us.count()
            # total_pages = (total_items + page_size - 1) // page_size
            data = {
                # 'total_pages': total_pages,
                # 'current_page': page_number,
                # 'total_items': total_items,
                'results': serialized_about_us.data
            }
            return Response({'status': 'success', 'message': 'Get all about us.', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error', 'message': str(e), 'data': data}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        about_description = request.data.get('about_description', None)
        our_focus = request.data.get('about_our_focus', None)
        our_mission = request.data.get('about_our_mission', None)
        our_vision = request.data.get('about_our_vision', None)
        if not about_description:
            return Response({'status': 'fail', 'message': 'About description is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            about_us = AboutUs.objects.all().first()
            if not about_us:
                if about_description is None:
                    return Response({'status': 'fail', 'message': 'Invalid request data.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                AboutUs.objects.create(
                    about_description=about_description,
                    about_our_focus=our_focus,
                    about_our_mission=our_mission,
                    about_our_vision=our_vision,
                    created_by=request.user
                )
                return Response({'status': 'success', 'message': 'About us added successfully.'},
                                status=status.HTTP_200_OK)
            else:
                if about_description is not None:
                    about_us.about_description = about_description
                if our_focus is not None:
                    about_us.about_our_focus = our_focus
                if our_mission is not None:
                    about_us.about_our_mission = our_mission
                if our_vision is not None:
                    about_us.about_our_vision = our_vision
                about_us.updated_at = timezone.now()
                about_us.updated_by = request.user
                about_us.save()
                return Response({'status': 'success', 'message': 'About us updated successfully.'},
                                status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    View class for managing service group operations.
    Includes create, get, update, and delete functions.
"""


class ServiceGroupAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        if 'page_number' in request.data or 'page_size' in request.data:
            return self.get_service_group(request)

        elif 'service_group_title' in request.data and 'service_group_description' in request.data:
            return self.create_service_group(request)

        else:
            return Response({'status': 'fail', 'message': 'Invalid request data'}, status=status.HTTP_400_BAD_REQUEST)

    def create_service_group(self, request):
        title = request.data.get('service_group_title')
        description = request.data.get('service_group_description')

        if not title and not description:
            return Response({'status': 'fail', 'message': 'title and description is required.'})
        

        try:

            title_validation = isstring(title)
            if title_validation == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid title. It should contain only alphabetic characters.'},
                    status=status.HTTP_400_BAD_REQUEST)

            service_group = ServiceGroup.objects.filter(service_group_title=title,
                                                        service_group_is_delete=False).first()
            if service_group:
                return Response({'status': 'fail', 'message': 'Service group is already exists.'},
                                status=status.HTTP_400_BAD_REQUEST)

            ServiceGroup.objects.create(
                service_group_title=title,
                service_group_description=description,
                created_by=request.user
            )
            return Response({'status': 'success', 'message': 'Service group is added successfully.'},
                            status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_service_group(self, request):
        data = {
            "total_pages": 0,
            "current_page": 0,
            "total_items": 0,
            "results": []
        }
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        service_group_id = request.data.get('service_group_id', None)
        search = request.data.get('search', None)

        if not page_size:
            return Response({'status': 'fail', 'message': 'page size is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:

            validation_page_number = isnumber(page_number)
            if validation_page_number == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page number. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            validation_page_size = isnumber(page_size)
            if validation_page_size == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page size. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            if service_group_id:
                validation_banner_id = isnumber(service_group_id)
                if validation_banner_id == False:
                    return Response(
                        {'status': 'fail', 'message': 'Invalid service group ID. It must be a positive integer.',
                         'data': data}, status=status.HTTP_400_BAD_REQUEST)

            page_number = int(page_number)
            page_size = int(page_size)

            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size

            service_group = ServiceGroup.objects.filter(service_group_is_delete=False)

            if service_group_id is not None:
                paginated_service_group = service_group.filter(service_group_id=service_group_id,
                                                               service_group_is_delete=False)
                if not paginated_service_group.exists():
                    return Response({
                        'status': 'fail', 'message': 'Service group id does not exist.', 'data': data},
                        status=status.HTTP_404_NOT_FOUND)

            elif search is not None:
                paginated_service_group = service_group.filter(
                    Q(service_group_title__icontains=search) | Q(service_group_description__icontains=search),
                    service_group_is_delete=False)
                if not paginated_service_group.exists():
                    return Response({
                        'status': 'fail', 'message': 'No service group found matching the search criteria.',
                        'data': data}, status=status.HTTP_200_OK)

            else:
                paginated_service_group = service_group[start_index:end_index]

            total_items = service_group.count()
            total_pages = (len(service_group) + page_size - 1) // page_size

            serialized_service_group = ServiceGroupSerializer(paginated_service_group, many=True)
            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serialized_service_group.data
            }
            return Response({
                'status': 'success', 'message': 'Get all service group.', 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        service_group_id = request.data.get('service_group_id')
        service_group_title = request.data.get('service_group_title', None)
        service_group_description = request.data.get('service_group_description', None)
        message = 'Service group updated Successfully.'

        if not service_group_id:
            return Response({'status': 'fail', 'message': 'Service group id is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        
        if ServiceGroup.objects.filter(service_group_title=service_group_title).exclude(service_group_id=service_group_id).exists():
            return Response(
                {'status': 'fail', 'message': 'A service group title  already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            if service_group_id:
                validation_banner_id = isnumber(service_group_id)
                if validation_banner_id == False:
                    return Response(
                        {'status': 'fail', 'message': 'Invalid service group ID. It must be a positive integer.'},
                        status=status.HTTP_400_BAD_REQUEST)

            if service_group_title:
                title_validation = isstring(service_group_title)
                if title_validation == False:
                    return Response(
                        {'status': 'fail', 'message': 'Invalid title. It should contain only alphabetic characters.'},
                        status=status.HTTP_400_BAD_REQUEST)

            service_group = ServiceGroup.objects.filter(service_group_id=service_group_id,
                                                        service_group_is_delete=False).first()
            if not service_group:
                return Response({'status': 'fail', 'message': 'Service group is not found.'},
                                status=status.HTTP_404_NOT_FOUND)

            if service_group_title is not None:
                service_group.service_group_title = service_group_title

            if service_group_description is not None:
                service_group.service_group_description = service_group_description

            if service_group_id and not any([service_group_title, service_group_description]):
                actvie_service_group_count = ServiceGroup.objects.filter(is_deactive=False,
                                                                         service_group_is_delete=False).count()
                if actvie_service_group_count <= 1:
                    if service_group.is_deactive == True:
                        pass
                    else:
                        return Response({'status': 'fail',
                                         'message': 'You cannot update this service group. You need to have at least one active service group.'},
                                        status=status.HTTP_400_BAD_REQUEST)

                if service_group.is_deactive == True:
                    service_group.is_deactive = False
                    message = 'Service group activated Successfully.'

                else:
                    service_group.is_deactive = True
                    linked_services_count = Services.objects.filter(services_group=service_group,
                                                                    service_is_delete=False).count()
                    if linked_services_count > 0:
                        return Response({
                            'status': 'fail',
                            'message': 'Cannot delete this Service Group. There are services connected to it.'
                        }, status=status.HTTP_200_OK)
                    message = 'Service group Deactivated Successfully.'

            service_group.updated_at = timezone.now()
            service_group.updated_by = request.user

            service_group.save()

            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        service_group_id = request.data.get('service_group_id')
        if not service_group_id:
            return Response({'status': 'fail', 'message': 'Service group ID is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:

            if service_group_id:
                validation_banner_id = isnumber(service_group_id)
                if validation_banner_id == False:
                    return Response(
                        {'status': 'fail', 'message': 'Invalid service group ID. It must be a positive integer.'},
                        status=status.HTTP_400_BAD_REQUEST)

            service_group = ServiceGroup.objects.filter(service_group_id=service_group_id,
                                                        service_group_is_delete=False).first()
            if not service_group:
                return Response({'status': 'fail', 'message': 'Service Group is not found.'},
                                status=status.HTTP_404_NOT_FOUND)
            #
            linked_services_count = Services.objects.filter(services_group=service_group,
                                                            service_is_delete=False).count()
            if linked_services_count > 0:
                return Response({
                    'status': 'fail',
                    'message': 'Cannot delete this Service Group. There are services connected to it.'
                }, status=status.HTTP_200_OK)

            active_service_group_count = ServiceGroup.objects.filter(is_deactive=False,
                                                                     service_group_is_delete=False).count()

            if active_service_group_count <= 1 and not service_group.is_deactive:
                return Response({
                    'status': 'fail',
                    'message': 'You cannot delete this service group. You need to have at least one active service gorup.'
                }, status=status.HTTP_200_OK)

            service_group.service_group_is_delete = True
            service_group.save()
            return Response({'status': 'success', 'message': 'Service Group deleted successfully.'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    View class for managing service operations.
    Includes create, get, update, and delete functions.
"""


class ServiceAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        if 'page_number' in request.data or 'page_size' in request.data:
            return self.get_service(request)

        elif 'service_title' in request.data and 'service_image' in request.data and 'service_description' in request.data:
            return self.create_service(request)

        else:
            return Response({'status': 'fail', 'message': 'Invalid request data.'}, status=status.HTTP_400_BAD_REQUEST)

    def create_service(self, request):
        try:
            service_group_data = None
            service_title = request.data.get('service_title')
            services_group = request.data.get('services_group', None)
            service_images = request.FILES.getlist('service_image')
            service_description = request.data.get('service_description')

            if services_group:
                service_group_validation = isnumber(services_group)
                if service_group_validation == False:
                    return Response(
                        {'status': 'fail', 'message': 'Invalid service group ID. It must be a positive integer.'},
                        status=status.HTTP_400_BAD_REQUEST)

            title_validation = isstring(service_title)
            if not title_validation:
                return Response(
                    {'status': 'fail', 'message': 'Invalid title. It should contain only alphabetic characters.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if services_group is not None:
                service_group_data = ServiceGroup.objects.filter(service_group_id=services_group,
                                                                 service_group_is_delete=False).first()
                if not service_group_data:
                    return Response({'status': 'fail', 'message': 'Service group id does not exist.'},
                                    status=status.HTTP_404_NOT_FOUND)

            service = Services.objects.filter(service_title=service_title, services_group=service_group_data,
                                              service_is_delete=False).first()
            if service:
                return Response({'status': 'fail', 'message': 'Service already exists.'},
                                status=status.HTTP_400_BAD_REQUEST)

            def save_files(files, directory):
                if not os.path.exists(directory):
                    os.makedirs(directory)
                urls = []
                for file in files:
                    if file.name.split('.')[-1].lower() not in ['png', 'jpg']:
                        return Response(
                            {'status': 'fail', 'message': 'Invalid file type. Only PNG and JPG files are allowed.'},
                            status=status.HTTP_400_BAD_REQUEST)

                    file_name = file.name.replace(' ', '').replace('(', '').replace(')', '')
                    file_path = os.path.join(directory, file_name)

                    try:
                        with open(file_path, "wb") as f:
                            f.write(file.read())
                        urls.append(f'http://{request.META["HTTP_HOST"]}/media/Service/{file_name}')
                    except Exception as e:
                        return Response({'status': 'error', 'message': f'Error saving file: {str(e)}'},
                                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                return urls

            if service_images:
                service_image_urls = save_files(service_images, 'media/Service/')
                if isinstance(service_image_urls, Response):
                    return service_image_urls
            else:
                return Response({'status': 'fail', 'message': 'No image files provided.'},
                                status=status.HTTP_400_BAD_REQUEST)

            Services.objects.create(
                service_title=service_title,
                services_group=service_group_data,
                service_image=service_image_urls[0],
                service_description=service_description,
                created_by=request.user
            )

            return Response({'status': 'success', 'message': 'Service added successfully.'}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_service(self, request):
        data = {
            "total_pages": 0,
            "current_page": 0,
            "total_items": 0,
            "results": []
        }
        try:
            page_number = request.data.get('page_number', 1)
            page_size = request.data.get('page_size', 10)
            service_id = request.data.get('service_id', None)

            validation_page_number = isnumber(page_number)
            if validation_page_number == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page number. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            validation_page_size = isnumber(page_size)
            if validation_page_size == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page size. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            if service_id:
                validation_banner_id = isnumber(service_id)
                if validation_banner_id == False:
                    return Response({'status': 'fail', 'message': 'Invalid service ID. It must be a positive integer.',
                                     'data': data}, status=status.HTTP_400_BAD_REQUEST)

            page_number = int(page_number)
            page_size = int(page_size)

            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size

            services = Services.objects.filter(service_is_delete=False)

            if service_id is not None:
                paginated_service = services.filter(service_id=service_id, service_is_delete=False)
                if not paginated_service.exists():
                    return Response({
                        'status': 'fail', 'message': 'Service id does not exist.', 'data': data},
                        status=status.HTTP_404_NOT_FOUND)

            else:
                paginated_service = services[start_index:end_index]

            total_items = services.count()
            total_pages = (len(services) + page_size - 1) // page_size

            serialized_service = ServicesSerializer(paginated_service, many=True)
            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serialized_service.data
            }
            return Response({
                'status': 'success', 'message': 'Get all services.', 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        service_id = request.data.get('service_id')
        service_title = request.data.get('service_title', None)
        services_group = request.data.get('services_group', None)
        service_image = request.FILES.getlist('service_image', None)
        service_description = request.data.get('service_description', None)
        message = 'Service updated Successfully.'

        if not service_id:
            return Response({'status': 'fail', 'message': 'Service ID is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        
        if Services.objects.filter(service_title=service_title).exclude(service_id=service_id).exists():
            return Response(
                {'status': 'fail', 'message': 'A Service already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if not isnumber(service_id):
                return Response({'status': 'fail', 'message': 'Invalid service ID. It must be a positive integer.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if services_group and not isnumber(services_group):
                return Response(
                    {'status': 'fail', 'message': 'Invalid service group ID. It must be a positive integer.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if service_title and not isstring(service_title):
                return Response(
                    {'status': 'fail', 'message': 'Invalid title. It should contain only alphabetic characters.'},
                    status=status.HTTP_400_BAD_REQUEST)

            def save_files(files, directory):
                if not os.path.exists(directory):
                    os.makedirs(directory)
                urls = []
                for file in files:
                    ext = file.name.split('.')[-1].lower()
                    if ext not in ['png', 'jpg']:
                        return {'error': 'Invalid file type. Only PNG and JPG files are allowed.'}
                    file_name = file.name.replace(' ', '').replace('(', '').replace(')', '')
                    file_path = os.path.join(directory, file_name)
                    with open(file_path, "wb") as f:
                        f.write(file.read())
                    urls.append(f"http://{request.META['HTTP_HOST']}/media/Service/{file_name}")
                return urls

            service = Services.objects.filter(service_id=service_id, service_is_delete=False).first()
            if not service:
                return Response({'status': 'fail', 'message': 'Service not found.'}, status=status.HTTP_404_NOT_FOUND)

            if service_title and services_group:
                existing_service = Services.objects.filter(
                    Q(service_title=service_title) & Q(services_group=services_group) & ~Q(service_id=service_id),
                    service_is_delete=False
                ).first()
                if existing_service:
                    return Response({'status': 'fail', 'message': 'Service with this title and group already exists.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if service_image:
                file_save_result = save_files(service_image, 'media/Service/')
                if isinstance(file_save_result, dict) and 'error' in file_save_result:
                    return Response({'status': 'fail', 'message': file_save_result['error']},
                                    status=status.HTTP_400_BAD_REQUEST)
                service.service_image = file_save_result[0]

            if service_title:
                service.service_title = service_title

            if services_group:
                service_group_obj = ServiceGroup.objects.filter(service_group_id=services_group,
                                                                service_group_is_delete=False).first()
                if not service_group_obj:
                    return Response({'status': 'fail', 'message': 'Invalid service group provided.'},
                                    status=status.HTTP_404_NOT_FOUND)
                service.services_group = service_group_obj

            if service_description:
                service.service_description = service_description

            if service_id and not any([service_title, service_image, services_group, service_description]):
                active_service_count = Services.objects.filter(is_deactive=False, service_is_delete=False).count()
                if active_service_count <= 1 and not service.is_deactive:
                    return Response({'status': 'fail', 'message': 'At least one active service is required.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                service.is_deactive = not service.is_deactive
                message = 'Service Activated Successfully.' if not service.is_deactive else 'Service Deactivated Successfully.'

            service.updated_at = timezone.now()
            service.updated_by = request.user
            service.save()

            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        service_id = request.data.get('service_id')

        if not service_id:
            return Response({'status': 'fail', 'message': 'Service ID is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            if service_id:
                validation_banner_id = isnumber(service_id)
                if validation_banner_id == False:
                    return Response({'status': 'fail', 'message': 'Invalid service ID. It must be a positive integer.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            service = Services.objects.filter(service_id=service_id, service_is_delete=False).first()
            if not service:
                return Response({'status': 'fail', 'message': 'Services is not found.'},
                                status=status.HTTP_404_NOT_FOUND)

            active_service_count = Services.objects.filter(is_deactive=False, service_is_delete=False).count()

            if active_service_count <= 1 and not service.is_deactive:
                return Response({
                    'status': 'fail',
                    'message': 'You cannot delete this service. You need to have at least one active service.'
                }, status=status.HTTP_200_OK)

            service.service_is_delete = True
            service.save()
            return Response({'status': 'success', 'message': 'Services deleted successfully.'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    View class for managing random stuff operations.
    Includes create, and update functions.
"""


class RandomStuffAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request):

        try:
            random_stuff = RandomStuff.objects.all()
            serialized_random_stuff = RandomStuffSerializer(random_stuff, many=True)
            data = {
                'total_pages': 0,
                'current_page': 0,
                'total_items': 0,
                'results': serialized_random_stuff.data
            }
            return Response({
                'status': 'success', 'message': 'Get all random stuff.', 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            random_privacy_policy = request.data.get('random_privacy_policy', None)
            random_terms_conditions = request.data.get('random_terms_conditions', None)
            random_return_cancellation = request.data.get('random_return_cancellation', None)
            if random_privacy_policy is None or random_terms_conditions is None or random_return_cancellation is None:
                return Response({'status': 'fail', 'message': 'Invalid request data.'},
                                status=status.HTTP_400_BAD_REQUEST)

            random_stuff = RandomStuff.objects.all().first()
            if not random_stuff:
                if random_privacy_policy is None or random_terms_conditions is None or random_return_cancellation is None:
                    return Response({'status': 'fail', 'message': 'Invalid request data.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                RandomStuff.objects.create(
                    random_privacy_policy=random_privacy_policy,
                    random_terms_conditions=random_terms_conditions,
                    random_return_cancellation=random_return_cancellation,
                    created_by=request.user
                )
                return Response({'status': 'success', 'message': 'Random stuff added successfully.'},
                                status=status.HTTP_200_OK)
            else:
                if random_privacy_policy is not None:
                    random_stuff.random_privacy_policy = random_privacy_policy

                if random_terms_conditions is not None:
                    random_stuff.random_terms_conditions = random_terms_conditions

                if random_return_cancellation is not None:
                    random_stuff.random_return_cancellation = random_return_cancellation

                random_stuff.updated_at = timezone.now()
                random_stuff.updated_by = request.user
                random_stuff.save()
                return Response({'status': 'success', 'message': 'Random stuff updated successfully.'},
                                status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    View class for managing contact enquiry operations.
    Includes get, update, and delete functions.
"""


class ContactEnquiryAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        if 'page_number' in request.data or 'page_size' in request.data:
            return self.get_contact_enquiry(request)

        else:
            return Response({'status': 'fail', 'message': 'Invalid request data.'}, status=status.HTTP_400_BAD_REQUEST)

    def get_contact_enquiry(self, request):
        data = {
            "total_pages": 0,
            "current_page": 0,
            "total_items": 0,
            "results": []
        }
        try:
            page_number = request.data.get('page_number', 1)
            page_size = request.data.get('page_size', 10)
            contact_id = request.data.get('id', None)
            search = request.data.get('search', None)

            validation_page_number = isnumber(page_number)
            if validation_page_number == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page number. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            validation_page_size = isnumber(page_size)
            if validation_page_size == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid page size. It must be a positive integer.', 'data': data},
                    status=status.HTTP_400_BAD_REQUEST)

            if contact_id:
                validation_contact_id = isnumber(contact_id)
                if validation_contact_id == False:
                    return Response(
                        {'status': 'fail', 'message': 'Invalid contact enquiry ID. It must be a positive integer.',
                         'data': data}, status=status.HTTP_400_BAD_REQUEST)

            page_number = int(page_number)
            page_size = int(page_size)

            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size

            leaddetails = LeadDetails.objects.filter(is_delete=False)

            if contact_id is not None:
                paginated_leaddetails = leaddetails.filter(id=contact_id)
                if not paginated_leaddetails.exists():
                    return Response({
                        'status': 'fail', 'message': 'Contact enquiry id does not exist.', 'data': data},
                        status=status.HTTP_404_NOT_FOUND)

            elif search is not None:
                paginated_leaddetails = leaddetails.filter(
                    Q(name__icontains=search) | Q(email__icontains=search) |
                    Q(contact_number__icontains=search) | Q(subject__icontains=search) |
                    Q(message__icontains=search) | Q(shop_name__icontains=search))
                if not paginated_leaddetails.exists():
                    return Response({
                        'status': 'fail', 'message': 'No contact enquiry found matching the search criteria.',
                        'data': data}, status=status.HTTP_200_OK)

            else:
                paginated_leaddetails = leaddetails[start_index:end_index]

            total_items = paginated_leaddetails.count()
            total_pages = (len(leaddetails) + page_size - 1) // page_size

            serialized_leaddetails = LeadDetailsSerializer(paginated_leaddetails, many=True)
            data = {
                'total_pages': total_pages,
                'current_page': page_number,
                'total_items': total_items,
                'results': serialized_leaddetails.data
            }
            return Response({
                'status': 'success', 'message': 'Get all contact enquiry.', 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        id = request.data.get('id')
        contact_enquiry_status = request.data.get('status', None)

        if not id:
            return Response({'status': 'fail', 'message': 'Contact enquiry id is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            contact_id_validation = isnumber(id)
            if contact_id_validation == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid contact enquiry ID. It must be a positive integer.'},
                    status=status.HTTP_400_BAD_REQUEST)

            if contact_enquiry_status:
                if contact_enquiry_status not in ['NEW', 'PROCESSING', 'RESOLVED']:
                    return Response({'status': 'fail',
                                     'message': 'Invalid contact enquiry status. Only allowed NEW, PROCESSING or RESOLVED.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            message = 'Contact enquiry updated Successfully.'
            leaddetails = LeadDetails.objects.filter(id=id, is_delete=False).first()
            if not leaddetails:
                return Response({'status': 'fail', "message": 'Contact enquiry does not exist.'},
                                status=status.HTTP_404_NOT_FOUND)

            if contact_enquiry_status is not None:
                leaddetails.status = contact_enquiry_status

            if id and not any([contact_enquiry_status]):
                actvie_leaddetails_count = LeadDetails.objects.filter(is_deactive=False, is_delete=False).count()
                if actvie_leaddetails_count <= 1:
                    if leaddetails.is_deactive == True:
                        pass
                    else:
                        return Response({'status': 'fail',
                                         'message': 'You cannot update this lead details. You need to have at least one active lead details.'},
                                        status=status.HTTP_200_OK)

            if leaddetails.is_deactive == True:
                leaddetails.is_deactive = False
                message = 'Contact enquiry Activated Successfully.'

            else:
                leaddetails.is_deactive = True
                leaddetails.is_deactive = not leaddetails.is_deactive
                message = 'Contact enquiry Deactivated Successfully.'

            leaddetails.updated_at = timezone.now()
            leaddetails.created_by = request.user
            leaddetails.save()

            return Response(
                {'status': 'success', 'message': message}, status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        id = request.data.get('id')
        if not id:
            return Response({'status': 'fail', 'message': 'contact enquiry ID is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            contact_id_validation = isnumber(id)
            if contact_id_validation == False:
                return Response(
                    {'status': 'fail', 'message': 'Invalid contact enquiry ID. It must be a positive integer.'},
                    status=status.HTTP_400_BAD_REQUEST)

            leaddetails = LeadDetails.objects.filter(id=id, is_delete=False).first()
            if not leaddetails:
                return Response({'status': 'fail', "message": 'Contact enquiry is not exists.'},
                                status=status.HTTP_404_NOT_FOUND)

            leaddetails.is_delete = True
            leaddetails.save()
            return Response({'status': 'success', 'message': 'Contact enquiry is deleted successfully.'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    this class is add contact enquiry without jwt authentication
"""
#========>

class ContactUsAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        name = request.data.get('name')
        email = request.data.get('email')
        contact_number = request.data.get('contact_number')
        subject = request.data.get('subject', None)
        message = request.data.get('message', None)
        type = request.data.get('type')
        shop_name = request.data.get('shop_name', None)

        try:
            if not name:
                return Response({'status': 'fail', 'message': 'Name is a required field.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not email:
                return Response({'status': 'fail', 'message': 'Email is a required field.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not contact_number:
                return Response({'status': 'fail', 'message': 'Contact number is a required field.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not type:
                return Response({'status': 'fail', 'message': 'Type is a required field.'},
                                status=status.HTTP_400_BAD_REQUEST)

            name_validation = isstring(name)
            if name_validation == False:
                return Response({'status': 'fail',
                                 'message': 'Invalid name. It should contain only alphabetic characters and spaces.'},
                                status=status.HTTP_400_BAD_REQUEST)

            mobile_validation = validate_mobile_number(contact_number)
            if not mobile_validation:
                return Response({'status': 'fail', "message": 'Invalid Mobile Number.'},
                                status=status.HTTP_400_BAD_REQUEST)

            email_validation = validation_email_address(email)
            if not email_validation:
                return Response({'status': 'fail', "message": 'Invalid Email Id.'}, status=status.HTTP_400_BAD_REQUEST)

            if type not in ['CONTACT ENQUIRY', 'BECOME A PARTNER']:
                return Response({'status': 'fail',
                                 'message': 'Invalid type. Allowed values are CONTACT ENQUIRY or BECOME A PARTNER.'},
                                status=status.HTTP_400_BAD_REQUEST)

            existing_email = LeadDetails.objects.filter(email=email, is_delete=False).first()
            existing_number = LeadDetails.objects.filter(contact_number=contact_number, is_delete=False).first()

            if existing_email:
                return Response({'status': 'fail', 'message': 'Email ID already exists.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if existing_number:
                return Response({'status': 'fail', 'message': 'Contact number already exists.'},
                                status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                LeadDetails.objects.create(
                    name=name,
                    email=email,
                    contact_number=contact_number,
                    subject=subject,
                    message=message,
                    type=type,
                    shop_name=shop_name
                )

            if type == 'CONTACT ENQUIRY':
                message = 'Contact enquiry is added successfully.'
            else:
                message = 'Become a partner request is added successfully.'

            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    this class is add newslatter without jwt authentication
"""

class NewsAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        news_email_id = request.data.get('news_email_id')

        if not news_email_id:
            return Response({'status': 'fail', 'message': 'email ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:

            email_validation = validation_email_address(news_email_id)

            if email_validation == False:
                return Response({'status': 'fail', 'message': 'Invalid email address.'},
                                status=status.HTTP_400_BAD_REQUEST)

            news_latter = NewsLatter.objects.filter(news_email_id=news_email_id).first()
            if news_latter:
                return Response({'status': 'fail', 'message': 'Email id is already exists.'},
                                status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                NewsLatter.objects.create(
                    news_supplier_name=news_email_id.split('@')[0],
                    news_email_id=news_email_id,
                )
            return Response({'status': 'success', 'message': 'News latter is added successfully.'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    this class is show banner data without jwt authentication
"""


class BannerGetAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            get_all = Banner.objects.filter(banner_is_delete=False, is_deactive=False)

            if not get_all.exists():
                return Response({
                    'status': 'success',
                    'message': 'No banners available',
                    'data': {'results': []}
                }, status=status.HTTP_200_OK)

            banner_serializer = BannerSerializer(get_all, many=True)

            data = {
                'results': banner_serializer.data
            }
            return Response({'status': 'success', 'message': 'get all banner', 'data': data}, status=status.HTTP_200_OK)

        except Exception as e:
            data = {
                'results': []
            }
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    this class is show partner data without jwt authentication
"""


class PartnerGetAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            get_all = Partners.objects.filter(partners_is_delete=False, is_deactive=False)

            if not get_all.exists():
                return Response({
                    'status': 'success',
                    'message': 'No partners available',
                    'data': {'results': []}
                }, status=status.HTTP_200_OK)

            partner_serializer = PartnersSerializer(get_all, many=True)
            data = {
                'results': partner_serializer.data
            }
            return Response({'status': 'success', 'message': 'Get all partners', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            data = {
                'results': []
            }
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    this class is show service group data without jwt authentication
"""


class ServiceGroupGetAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            services_prefetch = Prefetch(
                'services',
                queryset=Services.objects.filter(service_is_delete=False, is_deactive=False)
            )
            get_all_service_group = ServiceGroup.objects.filter(service_group_is_delete=False, is_deactive=False).prefetch_related(services_prefetch)
            get_all_service = Services.objects.filter(service_is_delete=False, services_group=None, is_deactive=False)
            service_group_serializer = ServiceGroupSerializer(get_all_service_group, many=True)
            service_serializer = ServicesSerializer(get_all_service, many=True)
            data = {
                        'results': 
                            {'service_group': service_group_serializer.data,
                            'service': service_serializer.data}
                    }
            return Response({'status': 'success', 'message': 'get all service group', 'data':data}, status=status.HTTP_200_OK)

        except Exception as e:
            data = {
                        'results': []
                    }
            return Response({'status': 'error', 'message': str(e), 'data': data}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    this class is show service data without jwt authentication
"""


class ServiceGetAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            service_id = request.data.get('service_id', None)

            if service_id:
                service_id_validation = isnumber(service_id)
                if service_id_validation == False:
                    return Response({'status': 'fail', 'message': 'Invalid service ID. It must be a positive integer.'})

            if service_id is None:
                get_service = Services.objects.filter(service_is_delete=False, is_deactive=False)

                if not get_service.exists():
                    return Response({
                        'status': 'success',
                        'message': 'No services available',
                        'data': {'results': []}
                    }, status=status.HTTP_200_OK)

                service_serializer = ServicesSerializer(get_service, many=True)
                data = {
                    'results': service_serializer.data
                }

                return Response({
                    'status': 'success',
                    'message': 'Service details retrieved successfully.',
                    'data': data
                }, status=status.HTTP_200_OK)

            get_service = Services.objects.filter(service_id=service_id, service_is_delete=False,
                                                  is_deactive=False).first()
            if not get_service:
                return Response({'status': 'fail', 'message': 'Service ID does not exist.'},
                                status=status.HTTP_404_NOT_FOUND)

            service_serializer = ServicesSerializer(get_service)
            data = {
                'results': service_serializer.data
            }
            
            return Response({
                'status': 'success',
                'message': 'Service details retrieved successfully.',
                'data': data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e),
                'data': {'results': []}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    this class is show random stuff data without jwt authentication
"""


class RandomStuffGetAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            get_all = RandomStuff.objects.filter(random_is_delete=False)
            if not get_all.exists():
                return Response({
                    'status': 'success',
                    'message': 'No random stuff available',
                    'data': {'results': []}
                }, status=status.HTTP_200_OK)
            
            random_stuff_serializer = RandomStuffSerializer(get_all, many=True)

            data = {
                'results': random_stuff_serializer.data
            }
            return Response({'status': 'success', 'message': 'get all random stuff.', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            data = {
                'results': []
            }
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
    this class is show about us data without jwt authentication
"""


class AboutUsGetAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            get_all = AboutUs.objects.filter(about_is_delete=False)

            if not get_all.exists():
                return Response({
                    'status': 'success',
                    'message': 'No about us available',
                    'data': {'results': []}
                }, status=status.HTTP_200_OK)

            about_serializer = AboutUsSerializer(get_all, many=True)
            data = {
                'results': about_serializer.data
            }
            return Response({'status': 'success', 'message': 'Get all about us', 'data': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            data = {
                'results': []
            }
            return Response({'status': 'error', 'message': str(e), 'data': data},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

